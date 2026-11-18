"""
M1 scoring: projections vs emitted spans, on the same executions.

    python m1_score.py results_m1 [results_round8/runs.jsonl] > results_m1/m1.md

1. Same executions as round 8? Outputs and projection alarms, by run id.
2. What each configuration's record holds (fields present, from the spans).
3. Clean runs: false alarms from span-built records.
4. Both components named, per pair: projection vs spans.
5. Run-level agreement of the alarm sets, and the disagreements.
6. The guardrail: F_P runs caught from spans, by whether a violation was released.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from scipy.stats import beta

import msfs_m1

COMPONENT = {"F_R", "F_X", "F_T", "F_P"}


def lo(k, n):
    return 0.0 if k == 0 else beta.ppf(0.025, k, n - k + 1)


def up(k, n):
    return 1.0 if k == n else beta.ppf(0.975, k + 1, n - k)


def fr(k, n):
    return f"{k}/{n} ({lo(k, n):.3f}–{up(k, n):.3f})" if n else "0/0"


out = Path(sys.argv[1] if len(sys.argv) > 1 else "results_m1")
rows = [json.loads(l) for l in open(out / "runs.jsonl")]
r8 = {}
if len(sys.argv) > 2:
    r8 = {r["pid"]: r for r in map(json.loads, open(sys.argv[2]))}
pairs = [r for r in rows if r["arm"] == "pair"]
P = print
P("# M1: today's logging from emitted spans vs projections\n")
P(json.dumps(json.loads((out / "m1_versions.json").read_text()), indent=1).join(["```json\n", "\n```\n"]))


def injected(r):
    if r["role"] == "pair":
        return set(r["pair"].split("+")) & COMPONENT
    if r["role"].startswith("single_"):
        return {r["role"][7:]} & COMPONENT
    return set()


# 1. sanity against round 8
P("## 1. Same executions as round 8\n")
if r8:
    common = [r for r in pairs if r["pid"] in r8]
    same_out = sum(r["output"] == r8[r["pid"]]["output"] for r in common)
    P(f"- runs matched to round 8 by id: {len(common)}/{len(pairs)}")
    P(f"- identical released output: {same_out}/{len(common)}")
    for cfg in ["sigma_r8", "otel_default", "otel_content", "openinference", "openinference_guard"]:
        k = sum(sorted(r["alarms"][cfg]) == sorted(r8[r["pid"]]["alarms"][cfg]) for r in common)
        P(f"- identical alarms, {cfg}: {k}/{len(common)}")
    bad = [r["pid"] for r in common if r["output"] != r8[r["pid"]]["output"]][:10]
    if bad:
        P(f"- first differing runs: {bad}")
else:
    P("(round 8 runs.jsonl not given)")

# 2. fields present
P("\n## 2. What each record holds (share of runs with the field)\n")
present = defaultdict(Counter)
n_exec = 0
for line in open(out / "spans.jsonl"):
    e = json.loads(line)
    n_exec += 1
    for cfg in msfs_m1.SPAN_CONFIGS:
        s = msfs_m1.sigma_from_spans({"_spans": e["spans"], "_logs": e["logs"]}, cfg.name)
        for k, v in s.stored.items():
            present[cfg.name][k] += v is not None
fields = sorted({k for c in present.values() for k in c})
P("| field | " + " | ".join(c.name for c in msfs_m1.SPAN_CONFIGS) + " |")
P("|---|" + "---|" * len(msfs_m1.SPAN_CONFIGS))
for f in fields:
    P(f"| {f} | " + " | ".join(f"{present[c.name][f]}/{n_exec}" for c in msfs_m1.SPAN_CONFIGS) + " |")
P("\nNever present in any span configuration: c_hash, y_hash, y_class, t_attest, t_id, p_witness.")

# 3. clean false alarms
P("\n## 3. Clean runs: false alarms\n")
clean = [r for r in pairs if r["role"] == "clean"]
for cfg in msfs_m1.SPAN_CONFIGS:
    proj = msfs_m1.PROJECTION_OF[cfg.name]
    k = sum(bool(r["alarms"][cfg.name]) for r in clean)
    kp = sum(bool(r["alarms"][proj]) for r in clean)
    P(f"- {cfg.name}: {fr(k, len(clean))}   (projection {proj}: {kp}/{len(clean)})")
    ev = Counter(c for r in clean for c in r["alarms"][cfg.name])
    if ev:
        P(f"    classes: {dict(ev)}")

# 4. both named per pair
P("\n## 4. Both component faults named, pair runs (projection → spans)\n")
P("| pair | n | " + " | ".join(msfs_m1.PROJECTION_OF[c.name] for c in msfs_m1.SPAN_CONFIGS) + " |")
P("|---|---|" + "---|" * len(msfs_m1.SPAN_CONFIGS))
for pair in sorted({r["pair"] for r in pairs}):
    rs = [r for r in pairs if r["pair"] == pair and r["role"] == "pair"]
    S = set(pair.split("+")) & COMPONENT
    cells = []
    for cfg in msfs_m1.SPAN_CONFIGS:
        proj = msfs_m1.PROJECTION_OF[cfg.name]
        a = sum(S <= set(r["alarms"][proj]) for r in rs)
        b = sum(S <= set(r["alarms"][cfg.name]) for r in rs)
        cells.append(f"{a} → {b}")
    P(f"| {pair} | {len(rs)} | " + " | ".join(cells) + " |")

# 5. run-level agreement
P("\n## 5. Same alarms from projection and spans, every run\n")
for cfg in msfs_m1.SPAN_CONFIGS:
    proj = msfs_m1.PROJECTION_OF[cfg.name]
    k = sum(sorted(r["alarms"][proj]) == sorted(r["alarms"][cfg.name]) for r in pairs)
    P(f"- {cfg.name} vs {proj}: {fr(k, len(pairs))}")
    diff = Counter((tuple(sorted(r["alarms"][proj])), tuple(sorted(r["alarms"][cfg.name])))
                   for r in pairs if sorted(r["alarms"][proj]) != sorted(r["alarms"][cfg.name]))
    for (a, b), n in diff.most_common(6):
        P(f"    {n:>4}  projection {list(a)} → spans {list(b)}")

# 6. guardrail
P("\n## 6. Policy faults and the guardrail span\n")
fp = [r for r in pairs if "F_P" in injected(r)]
for label, rs in [("released a violation", [r for r in fp if r["violation"]]),
                  ("released no violation", [r for r in fp if not r["violation"]])]:
    k = sum("F_P" in r["alarms"]["span_openinference_guard"] for r in rs)
    kp = sum("F_P" in r["alarms"]["openinference_guard"] for r in rs)
    kc = sum("F_P" in r["alarms"]["sigma_r8"] for r in rs)
    P(f"- F_P runs that {label}: spans {fr(k, len(rs))}; projection {kp}/{len(rs)}; "
      f"sigma_r8 {kc}/{len(rs)}")
