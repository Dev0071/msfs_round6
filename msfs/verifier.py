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
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

from . import keys
from .pipeline import (BLOCKED, POLICY_VERSION_HASH, SYSTEM_PROMPT,
                       SYSTEM_PROMPT_HASH, TOOL_DESCRIPTION, tool_signature,
                       witness_payload)
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
    # Round 8: off. The cross-source check (a tool figure that disagrees with an
    # archived record) fires on poisoned passages that assert a different
    # figure, so planting records frames an honest tool. Not used on HotpotQA,
    # whose tool returns text.
    cross_source_check: bool = True
    # Round 8, Part B: re-retrieval over the archived snapshot with some passages
    # left out, returning the full top k: "what would the retriever have
    # returned had these passages not been in the library".
    reretrieve_excluding: Optional[Callable[[str, Any], Optional[List[str]]]] = None
    # Round 8. The deployer-side content-addressed store: tool responses and the
    # tool descriptions the model was shown, written at capture time and keyed
    # by content hash. It holds what the pipeline RECEIVED, which for an
    # impostor tool is the impostor's response. Empty for earlier rounds.
    blob_by_hash: Dict[str, Any] = field(default_factory=dict)
    # Round 8 schema: every policy witness carries the wrapper's signature.
    require_witness_tag: bool = False


@dataclass
class Verdict:
    fault_class: str            # F_R | F_X | F_T | F_P | NONE
    confidence: float
    evidence: str
    abstained: bool


@dataclass
class VerdictSet:
    """Round 8: every alarm, not only the strongest (two faults, two alarms)."""
    classes: FrozenSet[str]                 # component classes that raised an alarm
    signals: List[Tuple[str, float, str]]   # every signal, strongest first
    unavailable: bool                       # some evidence was missing from the store

    @property
    def evidence(self) -> List[str]:
        return [f"{c}: {e}" for c, _, e in self.signals]


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


def _tool_call(sigma, arc: Archive):
    """
    The tool call the record implies, and how it is known.

      ("none", None)          the record keeps no tool transcript at all
      ("no_call", None)       the record says no tool was called
      ("ok", tc)              the transcript, with the returned value
      ("unavailable", None)   the record holds a value hash the store does not
    """
    if sigma.has("t_calls"):
        tc = sigma.get("t_calls")
        return ("ok", tc) if tc else ("no_call", None)
    if "t_calls" in sigma.stored:
        return "no_call", None
    if "t_calls_h" in sigma.stored:
        th = sigma.stored["t_calls_h"]
        if not th:
            return "no_call", None
        h = th["returned"]["value_hash"]
        if h not in arc.blob_by_hash:
            return "unavailable", None
        tc = {k: v for k, v in th.items() if k != "returned"}
        tc["returned"] = {"value": arc.blob_by_hash[h], "unit": th["returned"].get("unit")}
        return "ok", tc
    return "none", None


def _shown_description(sigma, arc: Archive) -> str:
    """
    The tool description the model was shown. Round 8: fetched from the store by
    t_desc_hash, so that the context check compares against the context built
    from the inputs the pipeline actually used. A changed description is then the
    tool's fault alone (F_T) and no longer also raises F_X. Without the store
    (earlier rounds) this is the registered description, as before.
    """
    if sigma.has("t_desc_hash"):
        h = sigma.get("t_desc_hash")
        if h in arc.blob_by_hash:
            return arc.blob_by_hash[h]
    return TOOL_DESCRIPTION


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
    status, tc = _tool_call(sigma, arc)
    if status == "unavailable":
        return None
    if status == "ok":
        parts.append(f"[TOOL {tc['tool']}@{tc['version']}] {_shown_description(sigma, arc)}")
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
        if not (sigma.has("c_hash") and _tool_call(sigma, arc)[0] in ("ok", "no_call")):
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
    if _tool_call(sigma, arc)[0] not in ("ok", "no_call"):
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
    status, tc = _tool_call(sigma, arc)
    if status == "unavailable":
        out.append(("UNAVAILABLE", 0.0, "the recorded tool-response hash is absent "
                                        "from the content store"))
        return out
    if status != "ok":
        return out                                  # Lemma C.T: transcript is required

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
    if arc.cross_source_check and isinstance(returned, (int, float)) \
            and not isinstance(returned, bool) and sigma.has("z_hashes"):
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
    if "tag" in w:
        if not keys.verify(keys.WITNESS_KEY, witness_payload(w), w["tag"]):
            out.append(("F_P", 0.97, "policy witness does not verify against the "
                                     "witness wrapper's key"))
    elif arc.require_witness_tag:
        out.append(("F_P", 0.97, "policy witness carries no wrapper signature"))
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


def _signals(sigma, arc: Archive) -> List[Signal]:
    signals: List[Signal] = []
    signals += _detect_retrieval(sigma, arc)
    signals += _detect_policy(sigma, arc)
    signals += _detect_prompt(sigma, arc)
    signals += _detect_tool(sigma, arc)
    return signals


def verify_all(sigma, arc: Archive) -> VerdictSet:
    """Round 8: the set of component classes that raised an alarm, with evidence."""
    raw = _signals(sigma, arc)
    unavailable = any(c == "UNAVAILABLE" for c, _, _ in raw)
    signals = sorted([s for s in raw if s[0] != "UNAVAILABLE"],
                     key=lambda s: (s[1], PRIORITY[s[0]]), reverse=True)
    return VerdictSet(frozenset(c for c, _, _ in signals), signals, unavailable)


def verify(sigma, arc: Archive) -> Verdict:
    signals = [s for s in _signals(sigma, arc) if s[0] != "UNAVAILABLE"]

    if not signals:
        return Verdict("NONE", 1.0, "no anomaly derivable from the stored state", True)

    signals.sort(key=lambda s: (s[1], PRIORITY[s[0]]), reverse=True)
    cls, conf, ev = signals[0]
    return Verdict(cls, conf, ev, False)
