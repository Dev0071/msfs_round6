"""
M1, descriptive breakdown: single faults and clean runs, per configuration.

The registered M1 tests (m1.md) pool every run. This splits the same runs by
fault class, so the comparison table can show, per class, which record catches
which fault. No new run, no new test: counts with one-sided 97.5% CP bounds.

    python m1_singles.py results_m1/runs.jsonl > results_m1/singles.md
"""
import json
import sys

from scipy.stats import beta

CONFIGS = ["sigma_r8", "sigma_hash_plus", "span_otel_default", "span_otel_content",
           "span_openinference", "span_openinference_guard"]
COMPONENT = ["F_R", "F_X", "F_T", "F_P"]


def lo(k, n):
    return 0.0 if k == 0 else beta.ppf(0.025, k, n - k + 1)


rows = [json.loads(l) for l in open(sys.argv[1] if len(sys.argv) > 1 else "results_m1/runs.jsonl")]
rows = [r for r in rows if r["arm"] == "pair"]
P = print
P("# M1: single faults per configuration (descriptive)\n")
P("Detected = the injected class named and nothing else. For F_D: no component named. "
  "Lower = one-sided 97.5% CP lower bound.\n")
P("| class | n | " + " | ".join(CONFIGS) + " |")
P("|---|---|" + "---|" * len(CONFIGS))
for c in COMPONENT + ["F_D"]:
    rs = [r for r in rows if r["role"] == "single_" + c]
    cells = []
    for cfg in CONFIGS:
        if c == "F_D":
            k = sum(not (set(r["alarms"][cfg]) & set(COMPONENT)) for r in rs)
        else:
            k = sum(set(r["alarms"][cfg]) == {c} for r in rs)
        cells.append(f"{k} ({lo(k, len(rs)):.2f})")
    P(f"| {c} | {len(rs)} | " + " | ".join(cells) + " |")
clean = [r for r in rows if r["role"] == "clean"]
P(f"| clean, no alarm | {len(clean)} | " +
  " | ".join(str(sum(not r["alarms"][cfg] for r in clean)) for cfg in CONFIGS) + " |")

P("\n## Harmed single faults only\n")
P("| class | n harmed | " + " | ".join(CONFIGS) + " |")
P("|---|---|" + "---|" * len(CONFIGS))
for c in COMPONENT:
    rs = [r for r in rows if r["role"] == "single_" + c and r.get("harmed")]
    P(f"| {c} | {len(rs)} | " +
      " | ".join(str(sum(set(r['alarms'][cfg]) == {c} for r in rs)) for cfg in CONFIGS) + " |")

P("\n## What else was named (single runs where the injected class was not the only alarm)\n")
for cfg in CONFIGS:
    other = {}
    for c in COMPONENT:
        for r in rows:
            if r["role"] == "single_" + c and set(r["alarms"][cfg]) not in ({c}, set()):
                key = (c, tuple(sorted(r["alarms"][cfg])))
                other[key] = other.get(key, 0) + 1
    if other:
        P(f"- {cfg}: " + "; ".join(f"{c} → {list(a)} ×{n}" for (c, a), n in sorted(other.items())))
