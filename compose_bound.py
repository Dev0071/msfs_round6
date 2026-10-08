#!/usr/bin/env python3
"""
The composition bound with every term measured, replacing v8's 0.829.

  Pr[correct attribution from storage] >= 1 - eps_int - eps - eps_delta

  eps_int    upper bound from exp_integrity.py (in-model attacks only)
  eps        1 - the smallest per-class Clopper-Pearson lower bound of the
             candidate record, from a run_realworld.py realworld.json
             (recomputed here at one-sided alpha 0.025, the paper's level)
  eps_delta  upper bound from exp_judge.py for the chosen scorer

  python compose_bound.py --integrity results_integrity/integrity.json \\
      --realworld results_confirmatory/realworld.json \\
      --judge results_judge/judge_summary.json

Any term whose file is missing is printed as "not measured", and no bound is
claimed. That is the point.
"""

import argparse
import json
from pathlib import Path

from scipy.stats import beta

ALPHA = 0.025


def cp_lower(k, n):
    return 0.0 if k == 0 else float(beta.ppf(ALPHA, k, n - k + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--integrity")
    ap.add_argument("--realworld")
    ap.add_argument("--judge")
    ap.add_argument("--sigma", default=None, help="record to use (default: the run's candidate)")
    a = ap.parse_args()
    terms, notes = {}, []

    if a.integrity and Path(a.integrity).exists():
        s = json.loads(Path(a.integrity).read_text())["summary"]
        terms["eps_int"] = s["eps_int_upper"]
        notes.append(f"eps_int: {s['undetected']} undetected in {s['n']} in-model attacks. "
                     "Capture-time lies and unanchored-tail attacks are outside this term.")
    if a.realworld and Path(a.realworld).exists():
        rw = json.loads(Path(a.realworld).read_text())
        name = a.sigma or rw["candidate"]
        row = next(r for r in rw["rows"] if r["sigma"] == name)
        lows = {fc: cp_lower(c["k"], c["n"]) for fc, c in row["classes"].items() if c["n"]}
        worst = min(lows, key=lows.get)
        terms["eps"] = 1 - lows[worst]
        notes.append(f"eps: record {name}; weakest class {worst} with lower bound "
                     f"{lows[worst]:.4f} (" + ", ".join(f"{k} {v:.3f}" for k, v in lows.items())
                     + "). Backend " + rw["config"]["backend"] + ".")
        if rw.get("backend_is_mock"):
            notes.append("WARNING: realworld.json is from the mock backend.")
    if a.judge and Path(a.judge).exists():
        j = json.loads(Path(a.judge).read_text())
        if j.get("best"):
            terms["eps_delta"] = j["best"]["eps_delta_upper"]
            notes.append(f"eps_delta: scorer {j['best']['scorer']} ({j['best']['format']} "
                         f"format), {j['n_labelled']} labelled items.")

    print("# Composition bound\n")
    for t in ("eps_int", "eps", "eps_delta"):
        print(f"- {t}: " + (f"{terms[t]:.4g}" if t in terms else "not measured"))
    print()
    for n in notes:
        print(f"- {n}")
    print()
    if len(terms) == 3:
        union = 1 - sum(terms.values())
        prod = (1 - terms["eps_int"]) * (1 - terms["eps"] - terms["eps_delta"])
        print(f"**Union bound: >= {union:.4f}.** Product form (independence): >= {prod:.4f}.")
        print("v8 stated 0.829 from assumed budgets; this figure replaces it.")
    else:
        print("No bound: at least one term is not measured.")


if __name__ == "__main__":
    main()
