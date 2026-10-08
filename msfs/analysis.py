"""
Pre-registered analysis. Exact methods only -- no normal approximations.

  E1  C(sigma, F_j) with one-sided Clopper-Pearson lower bounds, tested against
      tau = 0.85.
  E2  Single-element ablation of sigma* (Proposition 1: |sigma*| tests, not
      2^|sigma*|), scored by exact McNemar on paired executions.
  E3  Judge error epsilon_delta, supplied from the judge-calibration arm.
  E4  Empirical monotonicity (Lemma A): C is non-decreasing in sigma.

  Composition corollary:
      Pr[correct attribution from storage] >= 1 - eps_int - eps - eps_delta
"""

from __future__ import annotations

from dataclasses import dataclass
from math import comb
from typing import Dict, List, Optional, Sequence, Tuple

from scipy.stats import beta

TAU = 0.85
ALPHA = 0.025          # one-sided; the paper registers 97.5% lower bounds (v4 7.6)


# --- E1: completeness --------------------------------------------------------

@dataclass
class Completeness:
    sigma_name: str
    fault_class: str
    n: int
    k: int

    @property
    def point(self) -> float:
        return self.k / self.n if self.n else float("nan")

    @property
    def lower(self) -> float:
        """One-sided Clopper-Pearson lower bound at 1 - ALPHA."""
        if self.k == 0:
            return 0.0
        return float(beta.ppf(ALPHA, self.k, self.n - self.k + 1))

    @property
    def certified(self) -> bool:
        return self.lower >= TAU


def required_successes(n: int, tau: float = TAU, alpha: float = ALPHA) -> int:
    """Smallest k with CP lower bound >= tau. n=300, tau=0.85 -> the k in the plan."""
    for k in range(1, n + 1):
        if float(beta.ppf(alpha, k, n - k + 1)) >= tau:
            return k
    return n + 1


# --- E2: ablation ------------------------------------------------------------

def mcnemar_exact(b: int, c: int) -> float:
    """
    One-sided exact McNemar. b = full sigma* correct while ablated sigma wrong;
    c = the reverse. Returns P(B >= b | B ~ Bin(b+c, 0.5)): the probability of a
    drop this large under the null that the dropped element carries no
    forensic information.
    """
    n = b + c
    if n == 0:
        return 1.0
    return sum(comb(n, i) for i in range(b, n + 1)) / (2 ** n)


@dataclass
class AblationResult:
    element: str
    fault_class: str
    n_pairs: int
    b: int          # sigma* right, ablated wrong  (evidence element is needed)
    c: int          # sigma* wrong, ablated right  (noise)
    delta: float    # C(sigma*) - C(sigma* minus e)

    @property
    def p_value(self) -> float:
        return mcnemar_exact(self.b, self.c)

    @property
    def necessary(self) -> bool:
        return self.p_value < ALPHA and self.delta > 0


def summarize_necessity(results: Sequence[AblationResult]) -> Dict[str, Dict]:
    """An element is minimality-necessary if it is necessary for SOME fault class."""
    by_el: Dict[str, Dict] = {}
    for r in results:
        e = by_el.setdefault(r.element, {"necessary": False, "classes": [],
                                         "max_delta": 0.0, "detail": []})
        e["detail"].append(r)
        e["max_delta"] = max(e["max_delta"], r.delta)
        if r.necessary:
            e["necessary"] = True
            e["classes"].append(r.fault_class)
    return by_el


# --- E4: monotonicity --------------------------------------------------------

def monotonicity_violations(rows: Sequence[Tuple[str, str, float]],
                            nesting: Sequence[Tuple[str, str]]) -> List[str]:
    """rows: (sigma_name, fault_class, C). nesting: (subset_name, superset_name)."""
    idx = {(s, f): c for s, f, c in rows}
    out = []
    for sub, sup in nesting:
        for (s, f), c in list(idx.items()):
            if s != sub:
                continue
            c_sup = idx.get((sup, f))
            if c_sup is not None and c_sup + 1e-12 < c:
                out.append(f"{f}: C({sup})={c_sup:.3f} < C({sub})={c:.3f}")
    return out


# --- composition -------------------------------------------------------------

@dataclass
class CompositionBound:
    eps_int: float      # integrity-layer failure probability (Nitro-class)
    eps: float          # 1 - min_j C(sigma*, F_j)
    eps_delta: float    # judge / adjudication error

    @property
    def lower_bound(self) -> float:
        return max(0.0, 1.0 - self.eps_int - self.eps - self.eps_delta)

    def render(self) -> str:
        return (f"Pr[correct attribution from storage] >= 1 - {self.eps_int:.3f} "
                f"- {self.eps:.3f} - {self.eps_delta:.3f} = {self.lower_bound:.3f}")


# --- storage -----------------------------------------------------------------

def storage_table(configs, executions_per_day: int = 1_000_000) -> List[Dict]:
    rows = []
    for cfg in configs:
        b = cfg.bytes_per_execution
        rows.append({
            "sigma": cfg.name,
            "bytes_per_execution": b,
            "gb_per_day_at_1M": b * executions_per_day / 1e9,
        })
    base = next((r["bytes_per_execution"] for r in rows if r["sigma"] == "sigma_max"), None)
    for r in rows:
        r["fraction_of_maximalist"] = r["bytes_per_execution"] / base if base else float("nan")
    return rows
