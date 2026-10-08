"""
R_i = Delta(outcome | do(C_i))

The forensic reading of the do-operator: hold the execution fixed, replace
component C_i with its sound counterpart, and measure how much the probability
of the bad outcome moves. A component with high R_i is the one whose soundness
would have changed the decision.

Estimation uses common random numbers -- the factual and counterfactual arms are
driven by identically seeded generators -- so the paired difference cancels most
of the pipeline's stochasticity instead of drowning in it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .pipeline import Fault, Query, execute

COMPONENTS = ["R", "X", "T", "P"]
CLASS_OF = {"R": "F_R", "X": "F_X", "T": "F_T", "P": "F_P"}


class _Restricted(Fault):
    """The injected fault with component `component` restored to sound behaviour."""

    def __init__(self, inner: Fault, component: str):
        super().__init__(fault_class=inner.fault_class,
                         variant=inner.variant, params=dict(inner.params))
        self._inner = inner
        self._off = component

    def on_kb(self, docs, q, rng):
        return docs if self._off == "R" else self._inner.on_kb(docs, q, rng)

    def on_retrieved(self, hits, q, rng):
        return hits if self._off == "R" else self._inner.on_retrieved(hits, q, rng)

    def on_prompt(self, prompt, q, rng):
        return prompt if self._off == "X" else self._inner.on_prompt(prompt, q, rng)

    def on_tool(self, result, q, rng):
        return result if self._off == "T" else self._inner.on_tool(result, q, rng)

    def on_policy(self, output, witness, q, rng):
        if self._off == "P":
            return output, witness
        return self._inner.on_policy(output, witness, q, rng)


MANIFEST_EPS = 0.10


@dataclass
class ResponsibilityProfile:
    execution_id: str
    injected_class: str
    variant: str
    scores: Dict[str, float]
    factual_bad_rate: float
    clean_bad_rate: float

    @property
    def manifested(self) -> bool:
        """
        Did the injection actually move the decision? A semantics-preserving
        paraphrase or a stale policy version hash can be perfectly detectable
        while carrying near-zero causal responsibility. Detectability and
        responsibility are different questions, and conflating them is how an
        attribution metric ends up looking broken when it is behaving correctly.
        """
        return (self.factual_bad_rate - self.clean_bad_rate) > MANIFEST_EPS

    @property
    def argmax_component(self) -> Optional[str]:
        top = max(self.scores, key=lambda c: self.scores[c])
        return top if self.scores[top] > MANIFEST_EPS else None

    @property
    def argmax_class(self) -> Optional[str]:
        c = self.argmax_component
        return CLASS_OF[c] if c else None

    @property
    def correct(self) -> bool:
        return self.argmax_class == self.injected_class


def _bad_rate(query, docs, backend, fault, seeds, theta, retriever=None,
              answer_check=None) -> float:
    bad = 0
    for s in seeds:
        tau = execute(query, docs, backend, fault, random.Random(s), theta,
                      retriever=retriever, answer_check=answer_check)
        bad += 1 if tau["_outcome_bad"] else 0
    return bad / len(seeds)


def profile(
    query: Query,
    docs: Dict[str, Any],
    backend,
    fault: Fault,
    injected_class: str,
    execution_id: str,
    n_mc: int = 12,
    base_seed: int = 0,
    theta: Optional[Dict[str, Any]] = None,
    retriever=None,
    answer_check=None,
) -> ResponsibilityProfile:
    seeds = [base_seed * 1000 + i for i in range(n_mc)]
    kw = {"retriever": retriever, "answer_check": answer_check}
    factual = _bad_rate(query, docs, backend, fault, seeds, theta, **kw)
    clean = _bad_rate(query, docs, backend, Fault(), seeds, theta, **kw)
    scores: Dict[str, float] = {}
    for comp in COMPONENTS:
        cf = _bad_rate(query, docs, backend, _Restricted(fault, comp), seeds, theta, **kw)
        scores[comp] = round(factual - cf, 4)      # how much this component contributed
    return ResponsibilityProfile(execution_id, injected_class, fault.variant,
                                 scores, round(factual, 4), round(clean, 4))
