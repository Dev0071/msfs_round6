"""
Round 8, exploratory analysis. NOT a registered test.

Reads results_round8/runs.jsonl (the merged run, unchanged) and prints the
breakdowns used to explain the registered verdicts. Every number here is
post hoc and is reported as such (PREREG_round8.md, section 7 governs only
round8.md).

    python explore_round8.py results_round8/runs.jsonl > results_round8/explore.md
"""
import json
import sys
from collections import Counter, defaultdict

from scipy.stats import beta, fisher_exact

C = "sigma_r8"
COMPONENT = {"F_R", "F_X", "F_T", "F_P"}


def lo(k, n):
    return 0.0 if k == 0 else beta.ppf(0.025, k, n - k + 1)


def up(k, n):
    return 1.0 if k == n else beta.ppf(0.975, k + 1, n - k)


def fr(k, n):
    return f"{k}/{n} ({k / n:.2f}; {lo(k, n):.3f}–{up(k, n):.3f})" if n else "0/0"


rows = [json.loads(l) for l in open(sys.argv[1] if len(sys.argv) > 1 else
                                     "results_round8/runs.jsonl")]
pb = [r for r in rows if "part_b" in r]
P = print

P("# Round 8: exploratory breakdowns (post hoc, not registered)\n")

# 1. Part B by group and pair
P("## 1. Part B by group and pair\n")
P("| group | pair | n | involved (G1) | flagged | flagged when involved | "
  "verdicts | median replays | replays when flagged |")
P("|---|---|---|---|---|---|---|---|---|")
by = defaultdict(list)
for r in pb:
    by[(r["part_b"]["group"], r["pair"])].append(r)
for (g, pair), rs in sorted(by.items()):
    inv = [r for r in rs if r.get("truth", {}).get("library_involved")]
    fl = [r for r in rs if r["part_b"]["library_flagged"]]
    v = Counter(r["part_b"]["verdict"] for r in rs)
    rp = sorted(r["part_b"]["replays"] for r in rs)
    rpf = sorted(r["part_b"]["replays"] for r in fl)
    P(f"| {g} | {pair} | {len(rs)} | {len(inv) if g == 'G1' else '–'} | {len(fl)} | "
      f"{sum(r['part_b']['library_flagged'] for r in inv) if g == 'G1' else '–'} | "
      f"{dict(v)} | {rp[len(rp) // 2] if rp else '–'} | {rpf if rpf else '–'} |")

# 2. Same procedure, with and without poison: G1 F_R+F_D vs G3
P("\n## 2. Same procedure, poison present or not\n")
P("F_R+F_D disputes raise no alarm (E5), so the investigator runs exactly the "
  "search it runs on a plain model error (G3).\n")
frd = [r for r in pb if r["part_b"]["group"] == "G1" and r["pair"] == "F_R+F_D"]
noal = [r for r in frd if not r["alarms"][C]]
g3 = [r for r in pb if r["part_b"]["group"] == "G3"]
a = sum(r["part_b"]["library_flagged"] for r in noal)
b = sum(r["part_b"]["library_flagged"] for r in g3)
P(f"- F_R+F_D, no alarm, poison present: flagged {fr(a, len(noal))}")
P(f"- G3, nothing injected: flagged {fr(b, len(g3))}")
if noal and g3:
    odds, p = fisher_exact([[a, len(noal) - a], [b, len(g3) - b]], alternative="greater")
    P(f"- Fisher exact, one-sided: odds ratio {odds:.1f}, p = {p:.4f}")
    s, f = a / len(noal), b / len(g3)
    P("\nWhat a flag is worth for one dispute, at these rates "
      "(precision = share of flags that are real poisoning):\n")
    for prior in (0.01, 0.05, 0.20, 0.50):
        P(f"- poisoning in {prior:.0%} of disputes: precision {s * prior / (s * prior + f * (1 - prior)):.2f}")

# 3. Removal size and stage of the flag
P("\n## 3. How the flag was reached\n")
P("| group | removed 1 | removed 2 | removed 3+ | flags reached after replay 12 |")
P("|---|---|---|---|---|")
for g in ("G1", "G2", "G3"):
    fl = [r for r in pb if r["part_b"]["group"] == g and r["part_b"]["library_flagged"]]
    sz = Counter(min(len(r["part_b"]["removed"] or []), 3) for r in fl)
    late = sum(r["part_b"]["replays"] > 12 for r in fl)
    P(f"| {g} | {sz.get(1, 0)} | {sz.get(2, 0)} | {sz.get(3, 0)} | {late}/{len(fl)} |")

# 4. B3 as registered vs. without the masked pair
P("\n## 4. B3 (partner still named) with and without F_R+F_D\n")
g1 = [r for r in pb if r["part_b"]["group"] == "G1"]


def named(r):
    return (set(r["pair"].split("+")) & COMPONENT) <= set(r["alarms"][C])


k = sum(named(r) for r in g1)
P(f"- As registered (all G1): {fr(k, len(g1))}")
ex = [r for r in g1 if r["pair"] != "F_R+F_D"]
P(f"- Without F_R+F_D (predicted silent, E5): {fr(sum(named(r) for r in ex), len(ex))}")
for pair in sorted({r["pair"] for r in g1}):
    rs = [r for r in g1 if r["pair"] == pair]
    P(f"  - {pair}: {sum(named(r) for r in rs)}/{len(rs)}")
P("- Replay never changes the record's alarms, so B3 as computed measures the "
  "record, not the replay.")

# 5. Joint test reachability
P("\n## 5. Was the joint test reachable?\n")
for pair in sorted({r["pair"] for r in g1}):
    rs = [r for r in g1 if r["pair"] == pair]
    pe = sum(bool(r["part_b"]["partner_explains"]) for r in rs)
    jt = sum(bool(r["part_b"]["joint_testable"]) for r in rs)
    inv = sum(r.get("truth", {}).get("library_involved", False) for r in rs)
    P(f"- {pair}: partner repair explains {pe}/{len(rs)}; joint test runnable {jt}; "
      f"library involved {inv}; replays {sum(r['part_b']['replays'] for r in rs)}")

# 6. Elements with zero drop in the main ablation: needed anywhere else?
P("\n## 6. Elements needed by the descriptive arms\n")
P("The registered ablation covers singles and pairs only. Here: each element "
  "removed, on the descriptive arms.\n")
els = sorted({k.split(C + "-", 1)[1] for r in rows[:1] for k in r["alarms"]
              if k.startswith(C + "-")})
arms = {
    "rug_pull": lambda r, cfg: "F_T" in r["alarms"][cfg],
    "lying_filter": lambda r, cfg: "F_P" in r["alarms"][cfg],
    "forged_witness": lambda r, cfg: "F_P" in r["alarms"][cfg],
}
P("| element | " + " | ".join(arms) + " |")
P("|---|" + "---|" * len(arms))
for el in els:
    cells = []
    for arm, hit in arms.items():
        rs = [r for r in rows if r["arm"] == arm and r["role"] == arm]
        if arm == "lying_filter":
            rs = [r for r in rs if r["violation"]]
        base = sum(hit(r, C) for r in rs)
        k = sum(hit(r, f"{C}-{el}") for r in rs)
        cells.append(f"{k}/{len(rs)}" + (f" (−{base - k})" if base - k else ""))
    P(f"| {el} | " + " | ".join(cells) + " |")

# 7. Coherent liar: which alarms, and why (E9)
P("\n## 7. Coherent liar alarms (E9)\n")
liar = [r for r in rows if r["arm"] == "liar" and r["role"] == "pair"]
P(f"- any alarm: {sum(bool(r['alarms'][C]) for r in liar)}/{len(liar)}")
P(f"- classes: {dict(Counter(tuple(r['alarms'][C]) for r in liar))}")
P(f"- evidence on alarmed runs (first 5): "
  f"{[r.get('evidence') for r in liar if r['alarms'][C]][:5]}")
