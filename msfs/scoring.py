"""
The decision map delta: is a released output a correct answer?

Every harm label in the experiment, and so every number built on harm labels
(responsibility, localisation, the noise floor), is only as good as this
function. The paper calls its error rate epsilon_delta (D2, E3) and puts it in
the composition bound. It is measured against human labels in exp_judge.py.

Scorers, from most lenient to strictest:

  substring      gold string appears anywhere in the normalised output. The
                 pilot scorer. Counts hedged or multi-answer outputs as correct
                 when they happen to mention the gold string.
  strict         substring, AND the output is not a refusal, AND the extracted
                 answer is short (gold length + SLACK tokens). Rejects "it could
                 be X or Y" style answers that contain the gold by accident.
  f1             token F1 between extracted answer and gold >= F1_BAR
                 (SQuAD/HotpotQA token F1).
  em             normalised exact match of the extracted answer (HotpotQA EM).
                 Only meaningful with the short answer format.

Answer formats (pipeline.set_answer_format):
  free           the pilot prompt; the model answers in prose.
  short          the model is told to reply with the answer only, or NOT FOUND.

Which scorer to use in the confirmatory run is chosen on the human labels from
exp_judge.py, before any attribution result is looked at.
"""

from __future__ import annotations

import re
import string
from collections import Counter
from typing import Callable, List

_ARTICLES = re.compile(r"\b(a|an|the)\b")
_PUNCT = str.maketrans("", "", string.punctuation)

SLACK = 4
F1_BAR = 0.5

_REFUSAL = re.compile(
    r"not found|not (?:provided|mentioned|stated|specified|available|given|contain)"
    r"|does not (?:say|state|mention|contain|provide|specify)|no information"
    r"|cannot (?:be )?(?:determine|answer|find)|can't (?:determine|answer)"
    r"|unable to|insufficient|not enough information|i don't know|unknown",
    re.I)


def _text(v) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


def normalize(s) -> str:
    s = _text(s).lower().translate(_PUNCT)
    s = _ARTICLES.sub(" ", s)
    return " ".join(s.split())


def extract_answer(output: str) -> str:
    """The answer span: text after an ANSWER: prefix, first non-empty line."""
    text = str(output).strip()
    m = re.search(r"answer\s*[:\-]\s*(.*)", text, re.I | re.S)
    if m:
        text = m.group(1)
    for line in text.splitlines():
        if line.strip():
            return line.strip().rstrip(".")
    return ""


def is_refusal(output: str) -> bool:
    return bool(_REFUSAL.search(str(output)))


def f1_score(pred: str, gold: str) -> float:
    p, g = normalize(pred).split(), normalize(gold).split()
    if not p or not g:
        return float(p == g)
    common = Counter(p) & Counter(g)
    same = sum(common.values())
    if same == 0:
        return 0.0
    prec, rec = same / len(p), same / len(g)
    return 2 * prec * rec / (prec + rec)


def score_substring(output: str, gold) -> bool:
    g = normalize(gold)
    return bool(g) and g in normalize(output)


def score_strict(output: str, gold) -> bool:
    if not score_substring(output, gold) or is_refusal(output):
        return False
    ans = extract_answer(output)
    return len(normalize(ans).split()) <= len(normalize(gold).split()) + SLACK \
        and normalize(gold) in normalize(ans)


def score_f1(output: str, gold) -> bool:
    if is_refusal(output) and not score_substring(output, gold):
        return False
    return f1_score(extract_answer(output), _text(gold)) >= F1_BAR


def score_em(output: str, gold) -> bool:
    return normalize(extract_answer(output)) == normalize(gold)


# --- f1_guarded: the amendment registered after round 6 (PREREG_round7.md) ---
#
# Round 6 labels showed F1 passing answers that are one token away from the
# gold on exactly the attacked runs ("October 2033" for "October 1922", "LP 3"
# for "LP 2"), and failing "1986-2013" for "from 1986 to 2013" because the
# hyphen vanished in normalisation. Two guards, fixed before the fresh batch:
#   digit veto   if the gold contains numbers, the extracted answer must contain
#                the same numbers (as a multiset) and no others
#   hyphen fix   a hyphen or en dash between tokens is a space, not deleted
#   length guard an answer more than twice as long as the gold
#                is a hedge or a list, not an answer

_NUM = re.compile(r"\d+(?:\.\d+)?")
_DASH = re.compile(r"[-\u2013\u2014]")


def normalize_guarded(s) -> str:
    return normalize(_DASH.sub(" ", _text(s)))


def score_f1_guarded(output: str, gold) -> bool:
    if is_refusal(output) and not score_substring(output, gold):
        return False
    ans = extract_answer(output)
    gold_nums = sorted(_NUM.findall(_text(gold)))
    if gold_nums and sorted(_NUM.findall(ans)) != gold_nums:
        return False
    p, g = normalize_guarded(ans).split(), normalize_guarded(gold).split()
    if not p or not g:
        return p == g
    if len(p) > 2 * len(g):
        return False
    common = Counter(p) & Counter(g)
    same = sum(common.values())
    if same == 0:
        return False
    prec, rec = same / len(p), same / len(g)
    return 2 * prec * rec / (prec + rec) >= F1_BAR


SCORERS = {"substring": score_substring, "strict": score_strict,
           "f1": score_f1, "em": score_em, "f1_guarded": score_f1_guarded}


def make_check(name: str) -> Callable:
    """answer_check(output, query) for pipeline.execute."""
    fn = SCORERS[name]

    def check(output: str, query) -> bool:
        return fn(output, query.answer_value)
    check.scorer = name
    return check


def all_verdicts(output: str, gold) -> dict:
    return {name: bool(fn(output, gold)) for name, fn in SCORERS.items()}


def scorer_names() -> List[str]:
    return list(SCORERS)
