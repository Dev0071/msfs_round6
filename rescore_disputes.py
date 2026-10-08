#!/usr/bin/env python3
"""
Sensitivity check: re-score the saved responsibility disputes with another
outcome scorer, offline, from the coalition outputs stored in disputes.jsonl.

No model calls. This does NOT re-select disputes (that would need the model),
so it answers only: with the labels-chosen scorer, how many of the recorded
coalition verdicts change, and do the Shapley / leave-one-out results move?
Report it as a sensitivity analysis next to the pre-registered result, never
in its place.

  python rescore_disputes.py --out results_responsibility --scorer f1
"""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

from exp_responsibility import cp_lower, leave_one_out, shapley, verdict
from msfs.scoring import SCORERS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results_responsibility")
    ap.add_argument("--scorer", default="f1", choices=sorted(SCORERS))
    a = ap.parse_args()
    out = Path(a.out)
    fn = SCORERS[a.scorer]
    gold = {json.loads(l)["i"]: json.loads(l)["gold"]
            for l in (out / "runs.jsonl").read_text().splitlines() if l}
    disp = [json.loads(l) for l in (out / "disputes.jsonl").read_text().splitlines() if l]
    orig = json.loads((out / "config.json").read_text()).get("scorer", "?")
    cut = sum(len(o) == 300 for d in disp for o in d["outputs"].values())

    changed_cells = total_cells = 0
    rows = []
    for d in disp:
        g, n = gold[d["i"]], d["n"]
        v = {}
        for key_, out_text in d["outputs"].items():
            S = frozenset() if key_ == "-" else frozenset(int(x) for x in key_.split(","))
            v[S] = 0 if fn(out_text, g) else 1
            total_cells += 1
            changed_cells += v[S] != d["v"][key_]
        full = frozenset(range(n))
        still_bad = v[full] == 1
        poison = set(d["poison"])
        phi, loo = shapley(v, n), leave_one_out(v, n)
        sv, _ = verdict(phi, poison)
        lv, _ = verdict(loo, poison)
        rows.append({"i": d["i"], "variant": d["variant"], "case": d["case"],
                     "still_dispute": still_bad,
                     "attributable": any(b == 0 for b in v.values()),
                     "orig_shapley": d["shapley_verdict"], "new_shapley": sv,
                     "orig_loo": d["loo_verdict"], "new_loo": lv,
                     "baseline": len(poison) / n})

    mixed = [r for r in rows if r["case"] == "mixed"]
    L = [f"# Re-scoring the saved disputes with `{a.scorer}` (sensitivity check)\n",
         f"{len(disp)} disputes, {total_cells} stored coalition outputs; "
         f"{changed_cells} coalition verdicts changed ({changed_cells/total_cells:.1%}).",
         (f"WARNING: {cut} stored outputs are exactly 300 characters and may have been "
          "truncated by the round 6 script; their verdicts are unreliable." if cut else ""),
         f"Disputes whose full-context output is still scored wrong under `{a.scorer}`: "
         f"{sum(r['still_dispute'] for r in rows)}/{len(rows)} (the rest would not have "
         "been disputes at all under this scorer).", ""]

    def tab(method):
        o = [r[f"orig_{method}"] for r in mixed]
        nw = [r[f"new_{method}"] for r in mixed]
        return (f"| {method} | {o.count('hit')}/{o.count('wrong')}/{o.count('abstain')} | "
                f"{nw.count('hit')}/{nw.count('wrong')}/{nw.count('abstain')} |")

    L += ["## Mixed disputes: hit / wrong / abstain\n",
          f"| method | original ({orig}) | re-scored ({a.scorer}) |", "|---|---|---|",
          tab("shapley"), tab("loo"), ""]
    keep = [r for r in mixed if r["still_dispute"]]
    if keep:
        h = sum(r["new_shapley"] == "hit" for r in keep)
        base = sum(r["baseline"] for r in keep) / len(keep)
        L.append(f"On the {len(keep)} mixed disputes that remain disputes under "
                 f"`{a.scorer}`: Shapley hit {h}/{len(keep)} (lower bound "
                 f"{cp_lower(h, len(keep)):.2f}) vs baseline {base:.2f}.")
    att = [r for r in keep if r["attributable"]]
    non = [r for r in keep if not r["attributable"]]
    L += ["", f"Attributable (some coalition right): {len(att)}, Shapley hit "
              f"{sum(r['new_shapley']=='hit' for r in att)}, wrong "
              f"{sum(r['new_shapley']=='wrong' for r in att)}. Non-attributable: {len(non)}, "
              f"abstained {sum(r['new_shapley']=='abstain' for r in non)}."]
    moved = [r for r in mixed if r["orig_shapley"] != r["new_shapley"]]
    if moved:
        L += ["", "Disputes whose Shapley verdict moved:", ""]
        for r in moved:
            L.append(f"- run {r['i']} ({r['variant']}): {r['orig_shapley']} -> {r['new_shapley']}")
    md = "\n".join(L)
    (out / f"rescore_{a.scorer}.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
