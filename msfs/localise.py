"""
Localisation: when no component deviated, which recorded input does the
disputed output come from?

The verifier answers "which component broke its specification". Some attacks
break no specification: a passage that entered through normal ingestion, or
content an honest tool returned, is processed exactly as designed. For those
the verifier's correct answer is "no component deviated", and the forensic
question moves to the inputs. The record's job is then to say which inputs
were in front of the model, so that an attribution method can rank them.

The method here is deliberately the simplest one that can fail: lexical
support. Each recorded input (every retrieved passage, and the tool result) is
scored by the share of the output's content words it contains, after removing
the words of the question. The top-scoring input is the suspect. A stronger
method (RAGOrigin and its successors) would replace `support`, not the record.

Rules the auditor follows:
  * the disputed output must be bound to the record: either the record stores
    it, or it stores a commitment that the supplied text matches. An output
    that cannot be bound is not analysed.
  * the passages must be recoverable: stored, or stored as hashes that resolve
    in the content-addressed archive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .util import sha256

# Function words, plus the words the poisoning templates lean on. Leaving the
# template words in would let the localiser find the templates, not the content.
_STOP = frozenset("""a an the of to in on at by for from with and or but is are was
were be been it its this that these those as not no yes i you he she they we his her
their there which who whom what when where why how do does did has have had can could
will would should may might based provided material available according answer
answers question correct state states stated records record sources source""".split())

MIN_SUPPORT = 0.15


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", str(text).lower())


@dataclass
class Suspect:
    kind: str                    # "passage" | "tool"
    content_hash: Optional[str]  # for a passage
    rank: Optional[int]
    score: float


def candidates(sigma, arc) -> List[Tuple[str, Optional[str], Optional[int], str]]:
    """(kind, hash, rank, text) for every recorded input whose text is recoverable."""
    out = []
    if sigma.has("z_hashes"):
        for rank, h in enumerate(sigma.get("z_hashes"), start=1):
            text = arc.doc_text_by_hash.get(h)
            if text is not None:
                out.append(("passage", h, rank, text))
    if sigma.has("t_calls"):
        tc = sigma.get("t_calls")
        if tc:
            out.append(("tool", None, None, str((tc.get("returned") or {}).get("value"))))
    return out


def localise(sigma, arc, disputed_output: str) -> Optional[Suspect]:
    """The recorded input that best supports the disputed output, or None."""
    if sigma.has("y"):
        output = sigma.get("y")
    elif sigma.has("y_hash") and sha256(disputed_output) == sigma.get("y_hash"):
        output = disputed_output
    else:
        return None                  # the output cannot be bound to this record

    cands = candidates(sigma, arc)
    if not cands:
        return None

    question = ""
    if sigma.has("x_hash"):
        question = arc.query_text_by_hash.get(sigma.get("x_hash"), "")
    drop = _STOP | set(_tokens(question))
    words = {w for w in _tokens(output) if w not in drop}
    if not words:
        return None

    best: Optional[Suspect] = None
    for kind, h, rank, text in cands:
        score = len(words & set(_tokens(text))) / len(words)
        if best is None or score > best.score:
            best = Suspect(kind, h, rank, score)
    return best if best and best.score >= MIN_SUPPORT else None


# --- localisation by removal ---------------------------------------------------
#
# Wording cannot find an input the output does not quote: an injection that
# makes the model refuse leaves no trace of itself in the refusal. The second
# method is interventional. Rebuild the context from the record, take out one
# recorded input at a time, run a model on each reduced context, and name the
# input whose removal moves the output furthest from the disputed one.
#
# This is the responsibility score of the paper applied to inputs, in its
# leave-one-out form (the first-order term of the Shapley value: with five
# inputs the full value costs 32 runs per dispute, this costs six).
#
# The model that ran the decision is not available to an offline auditor, so
# the runs use a proxy. Before any input is blamed, the proxy must reproduce
# the disputed output from the full recorded context; if it does not, the
# method abstains. That check is Assumption A1 tested on the one dispute.

REPRODUCED = 0.5       # similarity to the disputed output needed to proceed
DISPLACED = 0.5        # displacement needed to blame an input
TIE = 0.05


# For comparing two outputs only function words are dropped, so that the words
# of a refusal ("not provided in the material") still count as content.
_FUNCTION = frozenset("""a an the of to in on at by for from with and or but is are
was were be been it its this that as i you answer question""".split())


def similarity(a: str, b: str, drop=frozenset()) -> float:
    """Jaccard similarity of content words; two outputs with none are alike."""
    skip = _FUNCTION | set(drop)
    x = {w for w in _tokens(a) if w not in skip}
    y = {w for w in _tokens(b) if w not in skip}
    if not x and not y:
        return 1.0
    return len(x & y) / len(x | y)


@dataclass
class Removal:
    reproduced: bool
    suspect: Optional[Suspect]
    calls: int


def localise_by_removal(sigma, arc, disputed_output: str, proxy,
                        render_context, tool_description: str) -> Optional[Removal]:
    """None when the record cannot support the analysis at all."""
    if sigma.has("y"):
        output = sigma.get("y")
    elif sigma.has("y_hash") and sha256(disputed_output) == sigma.get("y_hash"):
        output = disputed_output
    else:
        return None
    if not (sigma.has("x_hash") and sigma.has("z_hashes")):
        return None
    question = arc.query_text_by_hash.get(sigma.get("x_hash"))
    hashes = sigma.get("z_hashes")
    if question is None or any(h not in arc.doc_text_by_hash for h in hashes):
        return None
    passages = [arc.doc_text_by_hash[h] for h in hashes]
    tc = sigma.get("t_calls") if sigma.has("t_calls") else None
    tool = ((tc["tool"], tc["version"], tool_description, tc["returned"]["value"])
            if tc else None)

    import random as _random
    theta = {"temperature": 0.0, "top_p": 1.0, "max_tokens": 256, "seed": 0}

    def run(ps, t):
        return proxy.generate(render_context(question, ps, t), theta,
                              _random.Random(0)).text

    drop = frozenset(_tokens(question))
    sim = lambda text: similarity(text, output, drop)
    calls = 1
    if sim(run(passages, tool)) < REPRODUCED:
        return Removal(False, None, calls)

    scored: List[Suspect] = []
    for i, h in enumerate(hashes):
        reduced = passages[:i] + passages[i + 1:]
        scored.append(Suspect("passage", h, i + 1,
                              1.0 - sim(run(reduced, tool))))
        calls += 1
    if tool is not None:
        scored.append(Suspect("tool", None, None,
                              1.0 - sim(run(passages, None))))
        calls += 1

    scored.sort(key=lambda s: -s.score)
    if not scored or scored[0].score < DISPLACED:
        return Removal(True, None, calls)        # no single input carries it
    if len(scored) > 1 and scored[0].score - scored[1].score < TIE:
        return Removal(True, None, calls)        # two inputs tie: do not guess
    return Removal(True, scored[0], calls)
