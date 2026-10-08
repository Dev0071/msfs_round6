#!/usr/bin/env python3
"""
List every run the candidate record got wrong.

  python show_misses.py pilots/<run>/runs.jsonl            every wrong verdict
  python show_misses.py pilots/<run>/runs.jsonl --harmed   only runs that did harm
  python show_misses.py pilots/<run>/runs.jsonl --text     also print the outputs

Component faults (F_R, F_X, F_T, F_P): wrong when the verdict is not the
injected class. Poisoned inputs (F_D): wrong when a component is blamed, or
when the run did harm and the planted input was not the one localised.
"""
import collections
import json
import sys

path = next((a for a in sys.argv[1:] if not a.startswith("--")),
            "results_realworld/runs.jsonl")
only_harmed, show_text = "--harmed" in sys.argv, "--text" in sys.argv
rows = [json.loads(line) for line in open(path)]
summary = collections.Counter()
for r in rows:
    name = r.get("candidate", "sigma_hash")
    inj, got = r["injected_class"], r["verdicts"][name]
    located = (r.get("located") or {}).get(name)
    if inj == "F_D":
        if got != "NONE":
            kind = "COMPONENT BLAMED"
        elif r.get("harmed") and located is not True:
            kind = "WRONG INPUT NAMED" if located is False else "NOT LOCALISED"
        else:
            continue
    elif inj == got:
        continue
    else:
        kind = ("FALSE ALARM" if inj == "NONE" else
                "MISS" if got == "NONE" else "WRONG CLASS")
    if only_harmed and not r.get("harmed"):
        continue
    summary[(kind, f"{inj}/{r['variant']}", got)] += 1
    extra = "".join(f"  {k}={v}" for k, v in (r.get("detail") or {}).items())
    print(f"{kind}: injected {inj}/{r['variant']}  verdict {got}  "
          f"harmed={r.get('harmed')}  q={r['query_id']}{extra}")
    print(f"    evidence: {r.get('evidence', r.get('evidence_sigma_hash'))}")
    for proxy, res in (r.get("removal") or {}).items():
        if res is None:
            print(f"    removal ({proxy}): record cannot support it")
        else:
            verdict = ("abstained" if res["hit"] is None else
                       "named the planted input" if res["hit"] else "named a genuine input")
            print(f"    removal ({proxy}): reproduced={res['reproduced']}, {verdict}")
    if show_text:
        print(f"    output:      {r.get('output')!r}")
        print(f"    clean twin:  {r.get('twin_output')!r}")
print(f"\n{len(rows)} runs read")
for (kind, what, got), n in sorted(summary.items()):
    print(f"  {n:4d}  {kind:18s}  {what}  ->  {got}")
