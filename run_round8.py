#!/usr/bin/env python3
"""
Round 8: two faults in one decision.

Dr. Fang's question (9 Nov 2026): if an attacker poisons the knowledge base and
also breaks a component in the same decision, can the investigator tell?

  Part A, record only. Every pair of the five fault classes. Does each component
          fault trip its own witness? What does the investigator see when the
          library is poisoned alongside a component fault?
  Part B, replay. On disputed decisions, can an investigator who re-runs the
          production model detect that the library was involved, without
          flagging an innocent library? (msfs/replay.py)

The plan, the predictions and the pass bars are in PREREG_round8.md. This file
implements them; if the two disagree, the registration governs.

Design, per question in a pair arm: four executions with the same seed and the
same model randomness: the pair, fault A alone, fault B alone, and clean. The
singles and the clean run are the twins: they say whether a fault changed the
decision.

  python run_round8.py --backend mock --corpus synthetic --scorer substring --n 8
  python run_round8.py --count-only --corpus hotpotqa
  python run_round8.py --backend llama3.1:8b --corpus hotpotqa --pairs F_R+F_D --out r8_FR_FD
  python run_round8.py --merge r8_* --out results_round8

Every pair can be run as its own chunk (--pairs) into its own folder and the
chunks merged afterwards; a chunk that dies is simply re-run.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
import time
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional

from msfs import analysis as an
from msfs import attacks, pipeline
from msfs.attacks import CompositeFault
from msfs.backends import make_backend
from msfs.pipeline import (TOOL_DESCRIPTION, Fault, apply_policy, build_corpus, call_tool,
                           execute, render_context)
from msfs.real_world import (OPENINFERENCE, OPENINFERENCE_GUARD, OTEL_CONTENT, OTEL_DEFAULT,
                             project_with_derivation)
from msfs.replay import ReplayEnv, investigate
from msfs.sealing import SealedLog
from msfs.state import SIGMA_HASH_PLUS, SIGMA_R8
from msfs.util import sha256
from msfs.verifier import verify_all
from run_experiment import build_archive
from run_realworld import pick_restricted

# --- registered design (PREREG_round8.md, sections 3 and 5) --------------------

CLASSES = ["F_R", "F_X", "F_T", "F_P", "F_D"]
VARIANT = {"F_R": "suppression", "F_X": "context_truncation",
           "F_T": "server_name_squatting", "F_P": "fail_open", "F_D": "poison_ingested_d5"}
COMPONENT = {"F_R", "F_X", "F_T", "F_P"}
PAIRS = ["+".join(p) for p in combinations(CLASSES, 2)]
CANDIDATE = SIGMA_R8
COMPARE = [SIGMA_HASH_PLUS, OTEL_DEFAULT, OTEL_CONTENT, OPENINFERENCE, OPENINFERENCE_GUARD]
ABLATED = {e: CANDIDATE.drop(e) for e in sorted(CANDIDATE.elements)}
BLOCKED_MARK = "[BLOCKED BY POLICY]"

# pass bars, one-sided 97.5% Clopper-Pearson (alpha = an.ALPHA = 0.025)
BAR = {
    "clean_fpr_upper": 0.05,     # clean runs raise no alarm
    "single_lower": 0.90,        # each single fault still detected
    "A1_lower": 0.90,            # both faults named, each runtime pair
    "A2_upper": 0.10,            # cross-talk, each pair
    "A3_lower": 0.90,            # prediction: record names the partner only
    "B1_lower": 0.70,            # library involvement detected (G1)
    "B2_upper": 0.10,            # innocent library flagged (G2, G3)
    "B3_lower": 0.90,            # partner still named (G1)
}

EXTRA = {   # small descriptive arms
    "rug_pull": ("F_T", "rug_pull"),
    "lying_filter": ("F_P", "lying_filter"),
    "forged_witness": ("F_P", "forged_witness"),
}


def lower(k, n):
    return an.Completeness("", "", n, k).lower if n else None


def upper(k, n):
    if not n:
        return None
    from scipy.stats import beta
    return 1.0 if k >= n else float(beta.ppf(1 - an.ALPHA, k + 1, n - k))


def bin_size(stored) -> int:
    """Serialized size with 32-byte binary hashes (as measure_bytes.py)."""
    text = json.dumps(stored, sort_keys=True, separators=(",", ":"), default=str)
    return len(text.encode("utf-8")) - len(re.findall(r'"[0-9a-f]{64}"', text)) * 34


# --- setup ------------------------------------------------------------------------

def eligible(q, classes, restricted) -> bool:
    """
    Which questions a set of faults can act on. Policy faults run on restricted
    questions only (harm is releasing the restricted value); no other arm uses
    them, since there the policy of record blocks every release. Tool faults need
    a tool call. Every question keeps its gold passage in the corpus (no
    tool-only questions in round 8), so retrieval faults act on all of them.
    """
    if ("F_P" in classes) != (q.query_id in restricted):
        return False
    if "F_T" in classes and not q.needs_tool:
        return False
    return True


def setup(args):
    pipeline.set_answer_format(args.answer_format)
    retriever = None
    if args.corpus == "hotpotqa":
        from msfs.real_corpus import DenseRetriever, load
        docs, queries = load()
        retriever = DenseRetriever(docs)
    else:
        docs, queries = build_corpus(seed=args.seed)
    if args.answerable_only:
        fn = retriever or pipeline.retrieve
        before = len(queries)
        queries = [q for q in queries if q.gold_doc in
                   [d.doc_id for d, _ in fn(q, docs, args.top_k, random.Random(0))]]
        print(f"answerable-only: kept {len(queries)} of {before} questions", file=sys.stderr)
    values, restricted = pick_restricted(queries, docs, random.Random(args.seed + 1),
                                         fraction=args.restricted_frac,
                                         cap=args.restricted_cap)
    pipeline.register_restricted(values)
    return docs, queries, retriever, restricted


def plan_blocks(args, queries, restricted):
    """
    Every arm draws its questions and seeds from its own random stream, keyed by
    the arm's name, so a pair gets the same questions and seeds whether it runs
    alone (--pairs F_R+F_D) or with all the others. Block ids are unique across
    arms, so chunks can be merged.
    """
    wanted = PAIRS if args.pairs == "all" else args.pairs.split(",")
    blocks = []

    def add(arm_key, arm, pool, n, extra):
        rng = random.Random(f"{args.seed}-{arm_key}")
        base = 1000 * ([*PAIRS, *EXTRA, "liar"].index(arm_key) + 1)
        for i, q in enumerate(rng.sample(pool, min(n, len(pool)))):
            blocks.append(dict(arm=arm, query_id=q.query_id, block=base + i,
                               seed=rng.randrange(2 ** 31), **extra))

    for pair in wanted:
        if pair == "extra":
            continue
        classes = pair.split("+")
        add(pair, "pair", [q for q in queries if eligible(q, classes, restricted)],
            args.n, {"pair": pair, "classes": classes})
    if args.pairs == "all" or "extra" in wanted:
        for name, (fc, _) in EXTRA.items():
            add(name, name, [q for q in queries if eligible(q, [fc], restricted)],
                args.n_extra, {"classes": [fc]})
        # coherent liar: a recorder that rewrites the record as the clean twin's
        rng = random.Random(f"{args.seed}-liar")
        for i in range(args.n_extra):
            pair = PAIRS[i % len(PAIRS)]
            pool = [q for q in queries if eligible(q, pair.split("+"), restricted)]
            if pool:
                blocks.append({"arm": "liar", "pair": pair, "classes": pair.split("+"),
                               "query_id": rng.choice(pool).query_id,
                               "block": 1000 * (len(PAIRS) + len(EXTRA) + 1) + i,
                               "seed": rng.randrange(2 ** 31)})
    random.Random(f"{args.seed}-order").shuffle(blocks)
    return blocks


def count_only(args, queries, restricted) -> int:
    print(f"questions: {len(queries)} usable, {len(restricted)} restricted")
    print(f"{'pair':<12} eligible  (need {args.n})")
    short = []
    for pair in PAIRS:
        n = sum(eligible(q, pair.split("+"), restricted) for q in queries)
        flag = "" if n >= args.n else "  SHORT"
        short += [pair] if flag else []
        print(f"{pair:<12} {n:>8}{flag}")
    for name, (fc, _) in EXTRA.items():
        print(f"{name:<12} {sum(eligible(q, [fc], restricted) for q in queries):>8}  "
              f"(need {args.n_extra})")
    if short:
        print("\nShort pairs: draw more HotpotQA examples (real_corpus.build) and "
              "re-run the gold@4 check, or register the smaller n. " + ", ".join(short))
    return 0


# --- one block --------------------------------------------------------------------

def build(classes, variants, seeds):
    members = [attacks.make_attack(c, random.Random(0), v) for c, v in zip(classes, variants)]
    return CompositeFault(members, member_seeds=seeds)


def decision(tau) -> str:
    """The released decision, for comparing twins: class plus normalised answer."""
    from msfs.scoring import extract_answer, normalize
    return f"{tau['y_class']}|{normalize(extract_answer(tau['y']))}"


def run_block(b, ctx) -> List[Dict[str, Any]]:
    args, q, arc = ctx["args"], ctx["by_id"][b["query_id"]], ctx["arc"]
    seed = b["seed"]
    member_seeds = {c: (seed * 31 + i + 1) % (2 ** 31) for i, c in enumerate(CLASSES)}
    theta = {"temperature": args.temperature, "top_p": 1.0, "max_tokens": 256, "seed": seed}
    kw = dict(top_k=args.top_k, retriever=ctx["retriever"], answer_check=ctx["check"],
              tool_store=ctx["tool_store"], signed_witness=True)

    if b["arm"] == "pair":
        a, c2 = b["classes"]
        runs = [("pair", [a, c2]), ("single_" + a, [a]), ("single_" + c2, [c2]), ("clean", [])]
    elif b["arm"] == "liar":
        runs = [("pair", list(b["classes"])), ("clean", [])]
    else:
        runs = [(b["arm"], list(b["classes"])), ("clean", [])]

    taus, faults = {}, {}
    for role, classes in runs:
        variants = ([EXTRA[b["arm"]][1]] if b["arm"] in EXTRA and role != "clean"
                    else [VARIANT[c] for c in classes])
        fault = build(classes, variants, [member_seeds[c] for c in classes]) \
            if classes else Fault()
        pid = f"r8-{b['block']:05d}-{role}"
        ctx["log"].seal(pid, "+".join(classes) or "NONE", "+".join(variants) or "clean",
                        {"query_id": q.query_id, "seed": seed, "block": b["block"],
                         "arm": b["arm"]})
        tau = execute(q, ctx["docs"], ctx["backend"], fault, random.Random(seed),
                      dict(theta), gen_rng=random.Random(seed + 7), **kw)
        arc.blob_by_hash.update(tau["_store"])          # capture writes the store
        taus[role], faults[role] = (pid, tau), fault

    clean = taus["clean"][1]

    def harmed(t):
        return ((not clean["_outcome_bad"]) and t["_outcome_bad"]) or \
               (t["_released_violation"] and not clean["_released_violation"])

    rows = []
    for role, (pid, tau) in taus.items():
        fault = faults[role]
        ingested = getattr(fault, "ingested", [])
        saved = {d.doc_id: arc.snapshot.get(d.doc_id) for d in ingested}
        for d in ingested:                     # normal-path ingestion: archived
            arc.doc_text_by_hash[d.content_hash] = d.text
            arc.snapshot[d.doc_id] = d
        if b["arm"] == "liar" and role == "pair":
            # The recorder is compromised and tells a coherent lie: every field it
            # writes is the clean twin's, except the commitment to the released
            # output, which the complainant holds.
            liar = dict(clean, y_hash=tau["y_hash"])
            sigma_src = liar
        else:
            sigma_src = tau
        sig = {c.name: project_with_derivation(sigma_src, c)
               for c in [CANDIDATE, *COMPARE, *ABLATED.values()]}
        alarms = {name: sorted(verify_all(s, arc).classes) for name, s in sig.items()}
        cand = verify_all(sig[CANDIDATE.name], arc)
        row = {
            "pid": pid, "block": b["block"], "arm": b["arm"], "pair": b.get("pair"),
            "role": role, "query_id": q.query_id, "restricted": q.query_id in ctx["restricted"],
            "needs_tool": q.needs_tool, "alarms": alarms,
            "unavailable": cand.unavailable, "evidence": cand.evidence,
            "bad": tau["_outcome_bad"], "violation": tau["_released_violation"],
            "harmed": harmed(tau) if role != "clean" else None,
            "decision": decision(tau), "output": tau["y"][:300],
            "bytes": bin_size(sig[CANDIDATE.name].stored),
            "tool_run": tau["t_calls"] is not None,
        }
        # Part B, inline, while this run's ingested passages are in the archive.
        group = part_b_group(b, role, row, taus, harmed, ctx)
        cap = args.cap_g3 if group == "G3" else args.cap_g12
        key = f"{group}:{b.get('pair')}"
        if group and ctx["budget"].get(key, 0) < cap:
            ctx["budget"][key] = ctx["budget"].get(key, 0) + 1
            row["part_b"] = dict(group=group, **run_part_b(sig[CANDIDATE.name], tau, q, ctx))
        for d in ingested:
            arc.doc_text_by_hash.pop(d.content_hash, None)
            if saved[d.doc_id] is None:
                arc.snapshot.pop(d.doc_id, None)
            else:
                arc.snapshot[d.doc_id] = saved[d.doc_id]
        rows.append(row)

    # Ground truth for "contributed", from the twins (PREREG section 3).
    if b["arm"] == "pair" and "F_D" in b["classes"]:
        partner = [c for c in b["classes"] if c != "F_D"][0]
        d = {r["role"]: r for r in rows}
        pair_h = d["pair"]["harmed"]
        lib_needed = pair_h and not d["single_" + partner]["harmed"]
        lib_alone = bool(d["single_F_D"]["harmed"])
        for r in rows:
            r["truth"] = {"library_involved": bool(pair_h and (lib_needed or lib_alone)),
                          "partner_needed": bool(pair_h and not d["single_F_D"]["harmed"]),
                          "library_changed_decision": d["pair"]["decision"] !=
                          d["single_" + partner]["decision"]}
    return rows


def part_b_group(b, role, row, taus, harmed, ctx) -> Optional[str]:
    if ctx["args"].no_part_b or b["arm"] != "pair":
        return None
    if "F_D" in b["classes"]:
        partner = [c for c in b["classes"] if c != "F_D"][0]
        if role == "pair" and row["harmed"]:
            return "G1"
        if role == "single_" + partner and row["harmed"]:
            return "G2"
    if role == "clean" and row["bad"] and not row["restricted"]:
        return "G3"                       # a plain model error, nothing injected
    return None


def run_part_b(sigma, tau, q, ctx) -> Dict[str, Any]:
    if q.query_id in ctx["restricted"]:
        # For a restricted question the decision the complainant says was right
        # is that the policy withheld the answer.
        claimed = lambda o: o == BLOCKED_MARK
    else:
        claimed = lambda o: ctx["check"](o, q) and not any(
            b in o.lower() for b in pipeline.BLOCKED)
    f = investigate(sigma, ctx["arc"], tau["y"], claimed, ctx["env"],
                    budget=ctx["args"].budget)
    return {"verdict": f.verdict, "library_flagged": f.library_flagged,
            "alarms": list(f.alarms), "partner_explains": f.partner_explains,
            "joint_testable": f.joint_testable, "reproduced": f.reproduced,
            "removed": f.removed, "replays": f.replays, "note": f.note}


# --- scoring ----------------------------------------------------------------------

def frac(k, n):
    return {"k": k, "n": n, "rate": round(k / n, 3) if n else None,
            "lower": None if not n else round(lower(k, n), 3),
            "upper": None if not n else round(upper(k, n), 3)}


def score(rows) -> Dict[str, Any]:
    C = CANDIDATE.name
    out: Dict[str, Any] = {"alpha": an.ALPHA, "bars": BAR, "candidate": C}
    comp = lambda r: set(r["pair"].split("+") if r["role"] == "pair" else
                         r["role"].split("_", 1)[1:] if r["role"].startswith("single_")
                         else []) & COMPONENT
    pair_rows = [r for r in rows if r["arm"] == "pair"]

    # clean arm
    clean = [r for r in pair_rows if r["role"] == "clean"]
    fa = sum(bool(r["alarms"][C]) for r in clean)
    out["clean"] = dict(frac(fa, len(clean)),
                        passed=bool(clean) and upper(fa, len(clean)) <= BAR["clean_fpr_upper"])

    # singles
    singles = {}
    for c in CLASSES:
        rs = [r for r in pair_rows if r["role"] == "single_" + c]
        if not rs:
            continue
        want = {c} & COMPONENT
        k = sum(set(r["alarms"][C]) == want for r in rs) if c == "F_D" else \
            sum(want <= set(r["alarms"][C]) for r in rs)
        x = sum(bool(set(r["alarms"][C]) - want) for r in rs)
        singles[c] = dict(detected=frac(k, len(rs)), cross_talk=frac(x, len(rs)),
                          harmed=sum(bool(r["harmed"]) for r in rs),
                          passed=lower(k, len(rs)) >= BAR["single_lower"])
    out["singles"] = singles

    # pairs
    pairs = {}
    for pair in PAIRS:
        rs = [r for r in pair_rows if r["pair"] == pair and r["role"] == "pair"]
        if not rs:
            continue
        S = set(pair.split("+")) & COMPONENT
        V = [set(r["alarms"][C]) for r in rs]
        n = len(rs)
        joint = sum(S <= v for v in V)
        exact = sum(S == v for v in V)
        cross = sum(bool(v - S) for v in V)
        silent = sum(not v for v in V)
        row = {"n": n, "joint": frac(joint, n), "exact": frac(exact, n),
               "cross_talk": frac(cross, n), "silent": frac(silent, n),
               "harmed": sum(bool(r["harmed"]) for r in rs),
               "unavailable": sum(r["unavailable"] for r in rs),
               "A2_passed": upper(cross, n) <= BAR["A2_upper"]}
        if "F_D" in pair:
            row["kind"] = "F_D pair"
            row["false_exoneration"] = frac(exact, n)       # partner named, nothing else
            row["A3_confirmed"] = lower(exact, n) >= BAR["A3_lower"]
            tr = [r["truth"] for r in rs if "truth" in r]
            row["truth"] = {"library_involved": sum(t["library_involved"] for t in tr),
                            "partner_needed": sum(t["partner_needed"] for t in tr),
                            "library_changed_decision":
                                sum(t["library_changed_decision"] for t in tr)}
        else:
            row["kind"] = "runtime pair"
            row["A1_passed"] = lower(joint, n) >= BAR["A1_lower"]
        row["compare"] = {cfg.name: sum(S <= set(r["alarms"][cfg.name]) for r in rs)
                          for cfg in COMPARE}
        pairs[pair] = row
    out["pairs"] = pairs

    # ablation of the candidate over every component-fault run (singles and pairs)
    faulted = [r for r in pair_rows if r["role"] != "clean" and comp(r)]
    base = sum(comp(r) <= set(r["alarms"][C]) for r in faulted)
    out["ablation"] = []
    for el, cfg in ABLATED.items():
        k = sum(comp(r) <= set(r["alarms"][cfg.name]) for r in faulted)
        out["ablation"].append({"element": el, "detected": k, "of": len(faulted),
                                "with_element": base, "drop": base - k})
    out["ablation"].sort(key=lambda a: -a["drop"])

    # extra arms
    extra = {}
    for name in EXTRA:
        rs = [r for r in rows if r["arm"] == name and r["role"] == name]
        if not rs:
            continue
        if name == "rug_pull":
            k = sum(set(r["alarms"][C]) == {"F_T"} for r in rs)
            extra[name] = {"exact_F_T": frac(k, len(rs)),
                           "also_F_X": sum("F_X" in r["alarms"][C] for r in rs)}
        elif name == "lying_filter":
            viol = [r for r in rs if r["violation"]]
            k = sum("F_P" in r["alarms"][C] for r in viol)
            no_class = sum("F_P" in r["alarms"][f"{C}-y_class"] for r in viol)
            extra[name] = {"violations_released": len(viol), "detected": frac(k, len(viol)),
                           "detected_without_y_class": no_class,
                           "alarms_when_clean": sum("F_P" in r["alarms"][C]
                                                    for r in rs if not r["violation"])}
        else:
            k = sum("F_P" in r["alarms"][C] for r in rs)
            extra[name] = {"detected": frac(k, len(rs))}
    liar = [r for r in rows if r["arm"] == "liar" and r["role"] == "pair"]
    if liar:
        k = sum(bool(r["alarms"][C]) for r in liar)
        extra["liar"] = {"any_alarm": frac(k, len(liar))}
    out["extra"] = extra

    # Part B
    pb = [r for r in rows if "part_b" in r]
    groups = {}
    for g in ("G1", "G2", "G3"):
        rs = [r for r in pb if r["part_b"]["group"] == g]
        if not rs:
            continue
        verdicts: Dict[str, int] = {}
        for r in rs:
            verdicts[r["part_b"]["verdict"]] = verdicts.get(r["part_b"]["verdict"], 0) + 1
        flagged = sum(r["part_b"]["library_flagged"] for r in rs)
        row = {"n": len(rs), "verdicts": verdicts, "flagged": frac(flagged, len(rs)),
               "replays": sum(r["part_b"]["replays"] for r in rs)}
        if g == "G1":
            inv = [r for r in rs if r.get("truth", {}).get("library_involved")]
            not_inv = [r for r in rs if not r.get("truth", {}).get("library_involved")]
            k = sum(r["part_b"]["library_flagged"] for r in inv)
            row["B1"] = dict(frac(k, len(inv)),
                             passed=bool(inv) and lower(k, len(inv)) >= BAR["B1_lower"])
            row["flagged_when_not_involved"] = frac(
                sum(r["part_b"]["library_flagged"] for r in not_inv), len(not_inv))
            partner_named = sum(
                (set(r["pair"].split("+")) & COMPONENT) <= set(r["alarms"][C]) for r in rs)
            row["B3"] = dict(frac(partner_named, len(rs)),
                             passed=lower(partner_named, len(rs)) >= BAR["B3_lower"])
        else:
            row["B2"] = dict(frac(flagged, len(rs)),
                             passed=upper(flagged, len(rs)) <= BAR["B2_upper"])
        groups[g] = row
    out["part_b"] = groups
    if groups:
        ok = [groups.get("G1", {}).get("B1", {}).get("passed"),
              groups.get("G1", {}).get("B3", {}).get("passed"),
              groups.get("G2", {}).get("B2", {}).get("passed"),
              groups.get("G3", {}).get("B2", {}).get("passed")]
        out["part_b_passed"] = all(x is True for x in ok)

    # record size
    sizes = [r["bytes"] for r in rows]
    tool = [r["bytes"] for r in rows if r["tool_run"]]
    notool = [r["bytes"] for r in rows if not r["tool_run"]]
    summ = lambda xs: None if not xs else {
        "n": len(xs), "median": int(statistics.median(xs)),
        "p95": sorted(xs)[min(len(xs) - 1, int(0.95 * len(xs)))], "max": max(xs)}
    out["bytes"] = {"all": summ(sizes), "tool_runs": summ(tool), "no_tool_runs": summ(notool)}
    return out


def report(s, meta) -> str:
    P = lambda ok: "PASS" if ok else "FAIL"
    f = lambda x: "-" if x is None else f"{x:.3f}"
    L = ["# Round 8: two faults in one decision\n"]
    if meta.get("backend") == "mock":
        L.append("> **Mock backend.** Apparatus check, not a result about a language model.\n")
    L.append(f"Candidate record: `{s['candidate']}`. Bounds: one-sided "
             f"{100 * (1 - s['alpha']):.1f}% Clopper-Pearson. Config: " +
             ", ".join(f"{k}={v}" for k, v in meta.items()) + ".\n")
    c = s["clean"]
    L += ["## Pass and fail\n", "| test | result | bar | verdict |", "|---|---|---|---|",
          f"| clean runs raise no alarm | {c['k']}/{c['n']} alarms (upper {f(c['upper'])}) "
          f"| upper ≤ {BAR['clean_fpr_upper']} | {P(c['passed'])} |"]
    for cls, v in s["singles"].items():
        d = v["detected"]
        what = "no component blamed" if cls == "F_D" else "detected"
        L.append(f"| single {cls}: {what} | {d['k']}/{d['n']} (lower {f(d['lower'])}) | "
                 f"lower ≥ {BAR['single_lower']} | {P(v['passed'])} |")
    for pair, v in s["pairs"].items():
        j, x = v["joint"], v["cross_talk"]
        if v["kind"] == "runtime pair":
            L.append(f"| A1 {pair}: both named | {j['k']}/{j['n']} (lower {f(j['lower'])}) | "
                     f"lower ≥ {BAR['A1_lower']} | {P(v['A1_passed'])} |")
        else:
            e = v["false_exoneration"]
            L.append(f"| A3 {pair}: partner named and nothing else (prediction) | "
                     f"{e['k']}/{e['n']} (lower {f(e['lower'])}) | lower ≥ {BAR['A3_lower']} | "
                     f"{'confirmed' if v['A3_confirmed'] else 'not confirmed'} |")
        L.append(f"| A2 {pair}: cross-talk | {x['k']}/{x['n']} (upper {f(x['upper'])}) | "
                 f"upper ≤ {BAR['A2_upper']} | {P(v['A2_passed'])} |")
    pb = s.get("part_b", {})
    if "G1" in pb:
        b1, b3 = pb["G1"]["B1"], pb["G1"]["B3"]
        L.append(f"| B1 library involvement detected (G1) | {b1['k']}/{b1['n']} "
                 f"(lower {f(b1['lower'])}) | lower ≥ {BAR['B1_lower']} | {P(b1['passed'])} |")
        L.append(f"| B3 partner still named (G1) | {b3['k']}/{b3['n']} (lower {f(b3['lower'])}) "
                 f"| lower ≥ {BAR['B3_lower']} | {P(b3['passed'])} |")
    for g in ("G2", "G3"):
        if g in pb:
            b2 = pb[g]["B2"]
            L.append(f"| B2 innocent library flagged ({g}) | {b2['k']}/{b2['n']} "
                     f"(upper {f(b2['upper'])}) | upper ≤ {BAR['B2_upper']} | {P(b2['passed'])} |")
    if pb:
        L.append(f"\nPart B passes only if B1, B2 (G2 and G3) and B3 all pass: "
                 f"**{P(s.get('part_b_passed'))}**.")

    L += ["", "## Part A: pairs in detail\n",
          "joint = both component classes named; exact = those and nothing else; "
          "cross-talk = an uninjected class named; silent = no alarm. For F_D pairs only "
          "the partner can be named; exact there is a false exoneration of the library.\n",
          "| pair | n | joint | exact | cross-talk | silent | harmed | unavailable | " +
          " | ".join(c.name for c in COMPARE) + " |",
          "|---|---|---|---|---|---|---|---|" + "---|" * len(COMPARE)]
    for pair, v in s["pairs"].items():
        L.append(f"| {pair} | {v['n']} | {v['joint']['k']} | {v['exact']['k']} | "
                 f"{v['cross_talk']['k']} | {v['silent']['k']} | {v['harmed']} | "
                 f"{v['unavailable']} | " +
                 " | ".join(str(v["compare"][c.name]) for c in COMPARE) + " |")
    fd = {p: v for p, v in s["pairs"].items() if "truth" in v}
    if fd:
        L += ["", "### Ground truth from the twins (F_D pairs)\n",
              "library involved = the pair was harmed and the poison was a cause: the "
              "partner alone was not harmed, or the poison alone was.\n",
              "| pair | n | harmed | library involved | partner needed | poison changed the decision |",
              "|---|---|---|---|---|---|"]
        for p, v in fd.items():
            t = v["truth"]
            L.append(f"| {p} | {v['n']} | {v['harmed']} | {t['library_involved']} | "
                     f"{t['partner_needed']} | {t['library_changed_decision']} |")
    L += ["", "## Single faults\n", "| class | detected | cross-talk | harmed |",
          "|---|---|---|---|"]
    for cls, v in s["singles"].items():
        L.append(f"| {cls} | {v['detected']['k']}/{v['detected']['n']} | "
                 f"{v['cross_talk']['k']} | {v['harmed']} |")
    if s["extra"]:
        L += ["", "## Descriptive arms\n"]
        e = s["extra"]
        if "rug_pull" in e:
            r = e["rug_pull"]
            L.append(f"- Rug pull: named F_T and nothing else in {r['exact_F_T']['k']}/"
                     f"{r['exact_F_T']['n']}; F_X also raised in {r['also_F_X']}.")
        if "lying_filter" in e:
            r = e["lying_filter"]
            L.append(f"- Lying filter: {r['violations_released']} runs released a violation; "
                     f"F_P named in {r['detected']['k']} of them, "
                     f"{r['detected_without_y_class']} without y_class.")
        if "forged_witness" in e:
            r = e["forged_witness"]
            L.append(f"- Forged witness: F_P named in {r['detected']['k']}/{r['detected']['n']}.")
        if "liar" in e:
            r = e["liar"]
            L.append(f"- Coherent liar (recorder compromised): any alarm in "
                     f"{r['any_alarm']['k']}/{r['any_alarm']['n']}. By construction; a "
                     f"sanity check, not a result.")
    if pb:
        L += ["", "## Part B: replay\n", "| group | n | verdicts | library flagged | replays |",
              "|---|---|---|---|---|"]
        names = {"G1": "G1 harmed F_D pairs", "G2": "G2 partner alone (library innocent)",
                 "G3": "G3 plain model errors"}
        for g, v in pb.items():
            vd = ", ".join(f"{k} {n}" for k, n in sorted(v["verdicts"].items()))
            L.append(f"| {names[g]} | {v['n']} | {vd} | {v['flagged']['k']} | {v['replays']} |")
        if "G1" in pb:
            x = pb["G1"]["flagged_when_not_involved"]
            L.append(f"\nG1 disputes where the twins say the library was not involved: "
                     f"{x['n']}; flagged anyway: {x['k']}.")
    L += ["", f"## Ablation of {s['candidate']}\n",
          "Component-fault runs (singles and pairs) where every injected component "
          "class was named, with each element removed.\n",
          "| element | detected | drop |", "|---|---|---|"]
    for a in s["ablation"]:
        L.append(f"| {a['element']} | {a['detected']}/{a['of']} | {a['drop']} |")
    b = s["bytes"]
    if b["all"]:
        L += ["", "## Record size (bytes, binary hashes)\n", "| runs | n | median | p95 | max |",
              "|---|---|---|---|---|"]
        for k in ("all", "tool_runs", "no_tool_runs"):
            if b[k]:
                L.append(f"| {k} | {b[k]['n']} | {b[k]['median']} | {b[k]['p95']} | {b[k]['max']} |")
    return "\n".join(L)


# --- main -------------------------------------------------------------------------

def merge(dirs, out: Path) -> int:
    rows, meta = [], {}
    for d in dirs:
        p = Path(d) / "runs.jsonl"
        if not p.exists():
            print(f"skipping {d}: no runs.jsonl", file=sys.stderr)
            continue
        rows += [json.loads(l) for l in p.read_text().splitlines() if l]
        m = Path(d) / "meta.json"
        if m.exists():
            meta = json.loads(m.read_text())
    out.mkdir(parents=True, exist_ok=True)
    meta["merged_from"] = len(dirs)
    s = score(rows)
    (out / "round8.json").write_text(json.dumps(s, indent=2))
    md = report(s, meta)
    (out / "round8.md").write_text(md)
    print(md)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="mock")
    ap.add_argument("--corpus", default="synthetic", choices=["synthetic", "hotpotqa"])
    ap.add_argument("--n", type=int, default=72, help="questions per pair")
    ap.add_argument("--n-extra", type=int, default=36, help="runs per descriptive arm")
    ap.add_argument("--restricted-frac", type=float, default=0.2,
                    help="share of questions whose answer the policy restricts")
    ap.add_argument("--restricted-cap", type=int, default=80)
    ap.add_argument("--cap-g12", type=int, default=18,
                    help="Part B: G1 and G2 disputes per F_D pair (4 pairs: 72 in all)")
    ap.add_argument("--cap-g3", type=int, default=8,
                    help="Part B: G3 disputes per pair (10 pairs: 80 in all)")
    ap.add_argument("--budget", type=int, default=40, help="Part B replays per dispute")
    ap.add_argument("--pairs", default="all",
                    help="'all', or a comma list of pairs such as F_R+F_D, and/or 'extra'")
    ap.add_argument("--scorer", default="f1_guarded",
                    choices=["substring", "strict", "f1", "em", "f1_guarded"])
    ap.add_argument("--answer-format", default="short", choices=["free", "short"])
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20261113)
    ap.add_argument("--poison-text", default="llm", choices=["llm", "template"])
    ap.add_argument("--answerable-only", action="store_true", default=None,
                    help="default: on for hotpotqa, off for synthetic")
    ap.add_argument("--no-part-b", action="store_true")
    ap.add_argument("--count-only", action="store_true")
    ap.add_argument("--merge", nargs="+", default=None)
    ap.add_argument("--out", default="results_round8")
    args = ap.parse_args()
    out = Path(args.out)
    if args.merge:
        return merge(args.merge, out)
    if args.answerable_only is None:
        args.answerable_only = args.corpus == "hotpotqa"

    docs, queries, retriever, restricted = setup(args)
    if args.count_only:
        return count_only(args, queries, restricted)
    out.mkdir(parents=True, exist_ok=True)
    backend = make_backend(args.backend)

    from msfs.scoring import make_check
    base = make_check(args.scorer)

    def check(output, q):
        return True if q.query_id in restricted else base(output, q)

    if args.poison_text == "llm" and args.backend != "mock":
        cache: Dict[tuple, Optional[str]] = {}

        def generate(question, answer, i):
            key = (question, answer, i)
            if key not in cache:
                prompt = attacks.POISON_PROMPT.format(question=question, answer=answer)
                cache[key] = None
                for attempt in range(2):
                    theta = {"temperature": 1.0, "top_p": 1.0, "max_tokens": 120,
                             "seed": 1000 * i + attempt}
                    text = " ".join(backend.generate(prompt, theta, random.Random(0)).text.split())
                    if answer.lower() in text.lower():
                        cache[key] = text
                        break
            return cache[key]
        attacks.GENERATOR = generate

    # The lookup service returns the record of reference (the gold passage) on
    # HotpotQA, as in pilot 5; the synthetic corpus keeps the bare figure. Unlike
    # pilot 5 the passage also stays in the corpus (see eligible()).
    tool_store = ({q.query_id: docs[q.gold_doc].text for q in queries
                   if q.needs_tool and q.gold_doc in docs} if args.corpus == "hotpotqa" else {})
    arc = build_archive(docs, queries, "archive+retriever", retriever, args.top_k)
    arc.require_witness_tag = True
    arc.cross_source_check = False     # framable by poisoning; see verifier.Archive
    by_id = {q.query_id: q for q in queries}
    by_hash = {sha256(q.text): q for q in queries}
    env = ReplayEnv(
        generate=lambda prompt, theta: backend.generate(
            prompt, theta, random.Random(int(theta.get("seed", 0)) + 7)).text,
        render_context=render_context,
        apply_policy_of_record=lambda raw: apply_policy(raw)[0],
        tool_replay=lambda x_hash, a: call_tool(by_hash[x_hash], docs,
                                                tool_store)["returned"]["value"],
        registered_description=TOOL_DESCRIPTION)
    ctx = {"args": args, "docs": docs, "by_id": by_id, "arc": arc, "backend": backend,
           "retriever": retriever, "check": check, "restricted": restricted,
           "log": SealedLog(), "env": env, "budget": {}, "tool_store": tool_store}

    blocks = plan_blocks(args, queries, restricted)
    meta = {"backend": args.backend, "corpus": args.corpus, "scorer": args.scorer,
            "answer_format": args.answer_format, "temperature": args.temperature,
            "seed": args.seed, "pairs": args.pairs, "n": args.n, "n_extra": args.n_extra,
            "restricted_frac": args.restricted_frac, "restricted_cap": args.restricted_cap,
            "examples": len(queries), "cap_g12": args.cap_g12, "cap_g3": args.cap_g3, "budget": args.budget,
            "encoder": getattr(retriever, "model_name", None)}
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    (out / "plan.json").write_text(json.dumps(blocks, indent=1))
    print(f"{len(blocks)} blocks, about {sum(4 if b['arm'] == 'pair' else 2 for b in blocks)} "
          f"executions plus Part B replays", file=sys.stderr)

    rows, start = [], time.time()
    with open(out / "runs.partial.jsonl", "w") as fh:
        for i, b in enumerate(blocks):
            for r in run_block(b, ctx):
                rows.append(r)
                fh.write(json.dumps(r) + "\n")
            fh.flush()
            if (i + 1) % 5 == 0 or i + 1 == len(blocks):
                el = time.time() - start
                print(f"[{i + 1}/{len(blocks)}] {el / 60:.1f} min, about "
                      f"{el / (i + 1) * (len(blocks) - i - 1) / 60:.1f} min left; "
                      f"Part B {ctx['budget']}", file=sys.stderr, flush=True)

    # Ground truth is attached to each row from the sealed log, opened only now.
    truth = ctx["log"].open_for_scoring()
    for r in rows:
        rec = truth[r["pid"]]
        r["injected"] = rec.fault_class
        r["variant"] = rec.variant
    ctx["log"].write(out / "sealed_log.json")
    with open(out / "runs.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    (out / "runs.partial.jsonl").unlink()
    s = score(rows)
    (out / "round8.json").write_text(json.dumps(s, indent=2))
    md = report(s, meta)
    (out / "round8.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
