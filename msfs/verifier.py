"""
The offline verifier V.

Constraints, enforced structurally:
  * V reads sigma(tau) and the forensic archive. It never touches the live
    pipeline, the retriever, the model, or the tool service.
  * V never imports `sealing` or `faults`. It cannot see ground truth.
  * Every read of an Omega element is guarded by sigma.has(). When a detector's
    inputs are absent, that detector does not fire -- which is exactly how the
    d-separation lemmas of Lemma C become empirically testable rather than
    merely asserted.

V abstains (verdict NONE) when no detector fires. Abstention is scored as a
miss on faulted executions and as a correct rejection on clean ones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from .pipeline import (BLOCKED, POLICY_VERSION_HASH, SYSTEM_PROMPT,
                       SYSTEM_PROMPT_HASH, TOOL_DESCRIPTION, tool_signature)
from .util import sha256

NUM = re.compile(r"is (\d+(?:\.\d+)?)\.")


@dataclass
class Archive:
    """
    What the forensic archive holds independently of any single execution:
    a content-addressed KB snapshot, the registered system prompt catalogue,
    the policy version register, and the text of the disputed inputs.

    The archive holds NO answer key. It does not know which passage is correct
    for a question, nor which topic a question belongs to. What an auditor may
    additionally have is the retriever itself: `reretrieve`, when set, re-runs
    the published retriever over the archived snapshot and returns the content
    hashes of the leading positions that are reproducible run to run. That is
    replay of a deterministic component over archived data, not ground truth.
    With `reretrieve` left as None the auditor has the archive and the
    specification only (the strict reading of Definition D3).
    """
    doc_text_by_hash: Dict[str, str]
    query_text_by_hash: Dict[str, str]
    reretrieve: Optional[Callable[[str], Optional[List[str]]]] = None
    registered_prompt_hashes: Tuple[str, ...] = (SYSTEM_PROMPT_HASH,)
    registered_policy_hash: str = POLICY_VERSION_HASH


@dataclass
class Verdict:
    fault_class: str            # F_R | F_X | F_T | F_P | NONE
    confidence: float
    evidence: str
    abstained: bool


Signal = Tuple[str, float, str]


# --- detectors ---------------------------------------------------------------

def _detect_retrieval(sigma, arc: Archive) -> List[Signal]:
    out: List[Signal] = []
    if not sigma.has("z_hashes"):
        return out
    hashes: List[str] = sigma.get("z_hashes")

    unknown = [h for h in hashes if h not in arc.doc_text_by_hash]
    if unknown:
        out.append(("F_R", 0.92,
                    f"{len(unknown)} retrieved passage(s) have content hashes absent "
                    f"from the archived KB snapshot"))

    # Suppression and rank manipulation leave only archived passages in the
    # record, so nothing above fires. They are visible only against what the
    # retriever WOULD have returned, which needs the retriever, not a label.
    if arc.reretrieve is None or not sigma.has("x_hash"):
        return out
    expected = arc.reretrieve(sigma.get("x_hash"))
    if not expected:
        return out
    ranks = sigma.get("z_ranks") if sigma.has("z_ranks") else None
    for want_rank, h in enumerate(expected, start=1):
        if h not in hashes:
            out.append(("F_R", 0.85,
                        f"offline re-retrieval over the archived snapshot places a "
                        f"passage at rank {want_rank} that is absent from the "
                        f"recorded retrieval set"))
            break
        # Every position the archive reports is checked. The archive returns
        # only the positions that reproduce run to run (all of them for a
        # deterministic dense retriever, rank 1 for the jittered synthetic
        # stand-in). A reorder below rank 1 is NOT treated as benign: with a
        # real model it changed the released output in about 4 runs in 10 and
        # harmed about 1 in 10 (pilots of 2026-10-04).
        if ranks is not None and ranks[hashes.index(h)] != want_rank:
            out.append(("F_R", 0.80,
                        f"a passage that offline re-retrieval places at rank "
                        f"{want_rank} is recorded at rank {ranks[hashes.index(h)]}"))
            break
    return out


def _canonical_prompt(sigma, arc: Archive) -> Optional[str]:
    """Recompute the prompt that the stored evidence implies. None if not derivable."""
    if not (sigma.has("z_hashes") and sigma.has("x_hash")):
        return None
    hashes = sigma.get("z_hashes")
    if any(h not in arc.doc_text_by_hash for h in hashes):
        return None                                # unexplained provenance -> F_R's job
    qtext = arc.query_text_by_hash.get(sigma.get("x_hash"))
    if qtext is None:
        return None
    parts = [SYSTEM_PROMPT, "", f"[SYSTEM_PROMPT_HASH] {SYSTEM_PROMPT_HASH}", ""]
    for rank, h in enumerate(hashes, start=1):
        parts.append(f"[DOC rank={rank}] {arc.doc_text_by_hash[h]}")
    if sigma.has("t_calls"):
        tc = sigma.get("t_calls")
        if tc:
            # the registered tool description, from the specification
            parts.append(f"[TOOL {tc['tool']}@{tc['version']}] {TOOL_DESCRIPTION}")
            parts.append(f"[TOOL_RESULT] {tc['returned']['value']}")
    from . import pipeline as _pipeline
    parts += _pipeline.question_lines(qtext)
    return "\n".join(parts)


def _elide_tool_line(text: str) -> str:
    return "\n".join(l for l in text.split("\n")
                     if not l.startswith(("[TOOL_RESULT]", "[TOOL ")))


def _detect_prompt(sigma, arc: Archive) -> List[Signal]:
    if not sigma.has("c"):
        # Commitment-only record: the binding check still works, as an equality
        # of hashes, provided every input to the recomputation is recorded.
        if not (sigma.has("c_hash") and sigma.has("t_calls") or
                sigma.has("c_hash") and "t_calls" in sigma.stored
                and sigma.stored["t_calls"] is None):
            return []                               # Lemma C.X: nothing to compare
        canonical = _canonical_prompt(sigma, arc)
        if canonical is None or sha256(canonical) == sigma.get("c_hash"):
            return []
        return [("F_X", 0.88, "context commitment does not match the context "
                              "recomputed from the recorded input, retrieval set "
                              "and tool transcript")]
    stored = sigma.get("c")
    canonical = _canonical_prompt(sigma, arc)
    if canonical is None:
        return []
    if not sigma.has("t_calls"):
        # The tool return is not derivable, so it is excluded from the comparison
        # on both sides rather than counted as an unexplained span.
        stored, canonical = _elide_tool_line(stored), _elide_tool_line(canonical)
    if stored == canonical:
        return []

    head = stored.split("\n[SYSTEM_PROMPT_HASH]")[0]
    if sha256(head) not in arc.registered_prompt_hashes:
        return [("F_X", 0.94,
                 "system-prompt region of the stored context does not hash to any "
                 "registered prompt version")]
    extra = len(stored) - len(canonical)
    return [("F_X", 0.88,
             f"stored context contains {extra} bytes not derivable from the recorded "
             f"input, retrieval set, and tool transcript")]


def _detect_tool(sigma, arc: Archive) -> List[Signal]:
    out: List[Signal] = []
    # The description the model was shown, against the registered one. This
    # needs only the commitment, not the transcript.
    if sigma.has("t_desc_hash") and sigma.get("t_desc_hash") != sha256(TOOL_DESCRIPTION):
        out.append(("F_T", 0.95, "the tool description shown to the model does not "
                                 "hash to the registered description"))
    if not sigma.has("t_calls"):
        return out                                  # Lemma C.T: transcript is required
    tc = sigma.get("t_calls")
    if not tc:
        return out

    if sigma.has("t_id"):
        declared = f"{tc.get('tool')}@{tc.get('version')}"
        if declared != sigma.get("t_id"):
            out.append(("F_T", 0.90, "tool identity in the transcript disagrees with "
                                     "the recorded tool binding"))

    if sigma.has("t_attest"):
        expected = tool_signature({k: tc[k] for k in ("tool", "version", "args", "returned")})
        if expected != sigma.get("t_attest"):
            out.append(("F_T", 0.96,
                        "tool response does not verify against the attestation "
                        "recorded for this call"))

    # Cross-source check. Only possible where some retrieved record asserts the
    # same figure. On tool-only topics there is no second source and this returns
    # nothing -- the pre-registered hard case.
    # Numeric answers only: a text answer has no figure to cross-check, and
    # float() on it would raise.
    returned = (tc.get("returned") or {}).get("value")
    if isinstance(returned, (int, float)) and not isinstance(returned, bool) \
            and sigma.has("z_hashes"):
        for h in sigma.get("z_hashes"):
            text = arc.doc_text_by_hash.get(h)
            if not text:
                continue
            m = NUM.search(text)
            if m and abs(float(m.group(1)) - float(returned)) > 1e-9:
                out.append(("F_T", 0.89,
                            f"tool returned {returned:g} while an archived record "
                            f"asserts {m.group(1)}"))
                break
    return out


def _detect_policy(sigma, arc: Archive) -> List[Signal]:
    if not sigma.has("p_witness"):
        return []                                   # Lemma C.P
    w = sigma.get("p_witness")
    out: List[Signal] = []
    if not w.get("heartbeat", False) or w.get("rules_evaluated", 0) == 0:
        out.append(("F_P", 0.95, "policy witness reports no rule evaluation for this "
                                 "execution"))
    if w.get("policy_version_hash") != arc.registered_policy_hash:
        out.append(("F_P", 0.91, "policy witness carries a version hash that is not "
                                 "the version of record"))
    if sigma.has("y") and w.get("verdict") == "ALLOW":
        y = sigma.get("y", "").lower()
        if any(b in y for b in BLOCKED):
            out.append(("F_P", 0.93, "witness records ALLOW over an output containing "
                                     "prohibited language"))
    elif sigma.has("y_class") and w.get("verdict") == "ALLOW" \
            and sigma.get("y_class") == "VIOLATION":
        out.append(("F_P", 0.93, "witness records ALLOW while the recorded decision "
                                 "class of the released output is VIOLATION"))
    return out


# --- verifier ----------------------------------------------------------------

PRIORITY = {"F_P": 3, "F_R": 2, "F_X": 1, "F_T": 0}


def verify(sigma, arc: Archive) -> Verdict:
    signals: List[Signal] = []
    signals += _detect_retrieval(sigma, arc)
    signals += _detect_policy(sigma, arc)
    signals += _detect_prompt(sigma, arc)
    signals += _detect_tool(sigma, arc)

    if not signals:
        return Verdict("NONE", 1.0, "no anomaly derivable from the stored state", True)

    signals.sort(key=lambda s: (s[1], PRIORITY[s[0]]), reverse=True)
    cls, conf, ev = signals[0]
    return Verdict(cls, conf, ev, False)
