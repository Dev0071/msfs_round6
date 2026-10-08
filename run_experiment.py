#!/usr/bin/env python3
"""
MSFS experiment runner.

Arms:
  A  completeness      C(sigma, F_j) for sigma in {sigma0, sigma1, sigma*, sigma_max}
  B  ablation          single-element ablation of sigma* (Proposition 1)
  C  storage           bytes per execution per configuration
  D  responsibility    R_i = Delta(outcome | do(C_i)) and its attribution accuracy

Usage:
  python run_experiment.py --backend mock --n 300 --out results/
  python run_experiment.py --backend claude-sonnet-4-6 --n 300 --out results/
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List

from msfs import analysis as an
from msfs.backends import make_backend
from msfs.faults import (FAULT_CLASSES, INTEGRITY_LAYER_VARIANTS,
                         VARIANTS, make_fault)
from msfs.pipeline import Doc, build_corpus, execute, retrieve
from msfs.responsibility import profile
from msfs.sealing import SealedLog
from msfs.util import sha256
from msfs.state import (SIGMA_0, SIGMA_1, SIGMA_MAX, SIGMA_STAR, SIGMA_STAR_PLUS,
                        STANDARD_CONFIGS, project)

# The configuration whose minimality is under test.
CANDIDATE = SIGMA_STAR_PLUS
from msfs.verifier import Archive, verify


def build_archive(docs: Dict[str, Doc], queries, auditor: str = "archive+retriever",
                  retriever=None, top_k: int = 4) -> Archive:
    """
    auditor = "archive"            archive snapshot and specification only
    auditor = "archive+retriever"  the auditor can also re-run the published
                                   retriever over the archived snapshot

    No answer key is passed in either mode. `arc.snapshot` is the auditor's own
    copy of the knowledge base; churn() updates it only when the archive syncs.
    """
    arc = Archive(
        doc_text_by_hash={d.content_hash: d.text for d in docs.values()},
        query_text_by_hash={sha256(q.text): q.text for q in queries},
    )
    arc.snapshot = dict(docs)
    if auditor == "archive+retriever":
        by_hash = {sha256(q.text): q for q in queries}
        # The dense retriever is deterministic, so every position reproduces.
        # The synthetic stand-in jitters its scores, so only rank 1 does.
        stable = top_k if retriever is not None else 1
        fn = retriever or retrieve

        def reretrieve(x_hash: str):
            q = by_hash.get(x_hash)
            if q is None:
                return None
            hits = fn(q, arc.snapshot, top_k, random.Random(0))
            return [d.content_hash for d, _ in hits[:stable]]

        arc.reretrieve = reretrieve
    return arc


def churn(docs: Dict[str, Doc], arc: Archive, rng: random.Random, sync: float) -> None:
    """
    Benign KB drift after archiving: a record is revised and its hash moves.
    With probability `sync` the archive is brought up to date; otherwise the
    archive lags, and a content-addressed verifier sees a phantom anomaly.
    """
    did = rng.choice([d for d in docs if ":poison" not in d])
    old = docs[did]
    new = Doc(did, old.topic, old.text + " (rev.)", old.value)
    docs[did] = new
    if rng.random() < sync:
        arc.doc_text_by_hash[new.content_hash] = new.text
        arc.snapshot[did] = new


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="mock")
    ap.add_argument("--n", type=int, default=300, help="executions per fault class")
    ap.add_argument("--n-clean", type=int, default=300)
    ap.add_argument("--churn-rate", type=float, default=0.02)
    ap.add_argument("--archive-sync", type=float, default=0.8,
                    help="probability the archive is updated when the KB drifts")
    ap.add_argument("--seed", type=int, default=20260815)
    ap.add_argument("--eps-int", type=float, default=0.010, help="integrity-layer failure prob")
    ap.add_argument("--eps-delta", type=float, default=0.030, help="judge error")
    ap.add_argument("--responsibility-n", type=int, default=130)
    ap.add_argument("--corpus", default="synthetic",
                    choices=["synthetic", "hotpotqa"],
                    help="hotpotqa requires datasets, sentence-transformers, faiss-cpu "
                         "and a prior `python -m msfs.real_corpus`")
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--auditor", default="archive+retriever",
                    choices=["archive", "archive+retriever"],
                    help="what the offline verifier may use besides sigma")
    ap.add_argument("--out", default="results")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    backend = make_backend(args.backend)

    retriever = None
    answer_check = None
    if args.corpus == "hotpotqa":
        from msfs.real_corpus import DenseRetriever, answer_match, load
        base_docs, queries = load()
        retriever = DenseRetriever(base_docs)
        answer_check = answer_match
        print(f"corpus=hotpotqa  passages={len(base_docs)}  questions={len(queries)}",
              file=sys.stderr)
    else:
        base_docs, queries = build_corpus(seed=args.seed)
    archive = build_archive(base_docs, queries, args.auditor, retriever, args.top_k)
    live_docs = dict(base_docs)
    log = SealedLog()

    # ablation set: every element of sigma* gets exactly one ablated config
    ablated = {e: CANDIDATE.drop(e) for e in sorted(CANDIDATE.elements)}
    all_configs = {c.name: c for c in STANDARD_CONFIGS}
    all_configs.update({c.name: c for c in ablated.values()})

    plan: List[tuple] = []
    for fc in FAULT_CLASSES:
        for i in range(args.n):
            plan.append((fc, VARIANTS[fc][i % len(VARIANTS[fc])]))
    plan += [("NONE", "clean")] * (args.n_clean // 2)
    plan += [("NONE", "tail_reorder")] * (args.n_clean - args.n_clean // 2)
    rng.shuffle(plan)

    print(f"backend={args.backend}  executions={len(plan)}  "
          f"sigma configs={len(all_configs)}", file=sys.stderr)

    records = []
    for idx, (fc, variant) in enumerate(plan):
        pool = [x for x in queries if x.needs_tool] if fc == "F_T" else queries
        q = pool[rng.randrange(len(pool))]

        fault = make_fault(fc, rng, variant)
        exec_seed = rng.randrange(2 ** 31)
        # SEAL FIRST -- ground truth is committed before the pipeline runs.
        placeholder = f"exec-plan-{idx:06d}"
        rec = log.seal(placeholder, fc, variant, {"query_id": q.query_id,
                                                  "seed": exec_seed})

        tau = execute(q, live_docs, backend, fault, random.Random(exec_seed),
                      top_k=args.top_k, retriever=retriever,
                      answer_check=answer_check)
        tau["_planned_id"] = placeholder

        verdicts = {}
        for name, cfg in all_configs.items():
            v = verify(project(tau, cfg), archive)
            verdicts[name] = {"verdict": v.fault_class, "abstained": v.abstained,
                              "evidence": v.evidence}

        records.append({
            "planned_id": placeholder,
            "variant": variant,
            "execution_id": tau["execution_id"],
            "query_id": q.query_id,
            "outcome_correct": tau["_outcome_correct"],
            "verdicts": verdicts,
        })

        if rng.random() < args.churn_rate:
            churn(live_docs, archive, rng, args.archive_sync)

    # --- unseal, only now -----------------------------------------------------
    truth = log.open_for_scoring()
    print(f"sealed chain verified; head={log.head[:16]}...", file=sys.stderr)

    # --- Arm A: completeness --------------------------------------------------
    comp: List[an.Completeness] = []
    fpr: Dict[str, float] = {}
    for name in all_configs:
        for fc in FAULT_CLASSES:
            rows = [r for r in records if truth[r["planned_id"]].fault_class == fc]
            k = sum(1 for r in rows if r["verdicts"][name]["verdict"] == fc)
            comp.append(an.Completeness(name, fc, len(rows), k))
        clean = [r for r in records if truth[r["planned_id"]].fault_class == "NONE"]
        fp = sum(1 for r in clean if r["verdicts"][name]["verdict"] != "NONE")
        fpr[name] = fp / len(clean) if clean else 0.0

    # per-variant breakdown and the epsilon-relevant completeness
    per_variant = []
    for fc in FAULT_CLASSES:
        for var in VARIANTS[fc]:
            rows = [r for r in records
                    if truth[r["planned_id"]].fault_class == fc
                    and r["variant"] == var]
            if not rows:
                continue
            k = sum(1 for r in rows
                    if r["verdicts"][CANDIDATE.name]["verdict"] == fc)
            per_variant.append({
                "fault_class": fc, "variant": var, "n": len(rows), "k": k,
                "C": round(k / len(rows), 4),
                "integrity_layer": (fc, var) in INTEGRITY_LAYER_VARIANTS,
            })

    comp_eps: List[an.Completeness] = []
    for fc in FAULT_CLASSES:
        rows = [r for r in records
                if truth[r["planned_id"]].fault_class == fc
                and (fc, r["variant"]) not in INTEGRITY_LAYER_VARIANTS]
        k = sum(1 for r in rows if r["verdicts"][CANDIDATE.name]["verdict"] == fc)
        comp_eps.append(an.Completeness("sigma_star", fc, len(rows), k))

    # --- Arm B: ablation ------------------------------------------------------
    abl: List[an.AblationResult] = []
    for element in ablated:
        aname = ablated[element].name
        for fc in FAULT_CLASSES:
            rows = [r for r in records if truth[r["planned_id"]].fault_class == fc]
            b = sum(1 for r in rows
                    if r["verdicts"][CANDIDATE.name]["verdict"] == fc
                    and r["verdicts"][aname]["verdict"] != fc)
            c = sum(1 for r in rows
                    if r["verdicts"][CANDIDATE.name]["verdict"] != fc
                    and r["verdicts"][aname]["verdict"] == fc)
            n = len(rows)
            abl.append(an.AblationResult(element, fc, n, b, c,
                                         delta=(b - c) / n if n else 0.0))
    necessity = an.summarize_necessity(abl)

    # --- Arm D: responsibility ------------------------------------------------
    resp = []
    rng2 = random.Random(args.seed + 1)
    for i in range(args.responsibility_n):
        fc = FAULT_CLASSES[i % len(FAULT_CLASSES)]
        pool = [x for x in queries if x.needs_tool] if fc == "F_T" else queries
        q = pool[rng2.randrange(len(pool))]
        f = make_fault(fc, rng2)
        p = profile(q, base_docs, backend, f, fc, f"resp-{i:04d}",
                    n_mc=12, base_seed=args.seed + i,
                    retriever=retriever, answer_check=answer_check)
        resp.append(p)
    manifesting = [p for p in resp if p.manifested]
    resp_acc = sum(1 for p in resp if p.correct) / len(resp) if resp else float("nan")
    resp_acc_m = (sum(1 for p in manifesting if p.correct) / len(manifesting)
                  if manifesting else float("nan"))

    # --- composition ----------------------------------------------------------
    eps = 1.0 - min(c.point for c in comp_eps)
    bound = an.CompositionBound(args.eps_int, eps, args.eps_delta)

    # --- report ---------------------------------------------------------------
    payload = {
        "config": vars(args),
        "harness": {
            "sealed_chain_head": log.head,
            "chain_verified": True,
            "executions": len(records),
            "required_successes_at_n": an.required_successes(args.n),
            "tau": an.TAU, "alpha": an.ALPHA,
            "backend_is_mock": args.backend == "mock",
        },
        "completeness": [
            {"sigma": c.sigma_name, "fault_class": c.fault_class, "n": c.n, "k": c.k,
             "C": round(c.point, 4), "cp_lower": round(c.lower, 4),
             "certified": c.certified} for c in comp
        ],
        "false_positive_rate": fpr,
        "per_variant": per_variant,
        "completeness_excluding_integrity_layer": [
            {"fault_class": c.fault_class, "n": c.n, "k": c.k,
             "C": round(c.point, 4), "cp_lower": round(c.lower, 4),
             "certified": c.certified} for c in comp_eps
        ],
        "ablation": [
            {"element": r.element, "fault_class": r.fault_class, "n": r.n_pairs,
             "b": r.b, "c": r.c, "delta": round(r.delta, 4),
             "p": round(r.p_value, 6), "necessary": r.necessary} for r in abl
        ],
        "necessity": {e: {"necessary": v["necessary"], "classes": v["classes"],
                          "max_delta": round(v["max_delta"], 4)}
                      for e, v in necessity.items()},
        "monotonicity_violations": an.monotonicity_violations(
            [(c.sigma_name, c.fault_class, c.point) for c in comp],
            [("sigma0", "sigma1"), ("sigma1", "sigma_max"),
             ("sigma_star", "sigma_max")]),
        "storage": an.storage_table(STANDARD_CONFIGS),
        "responsibility": {
            "n": len(resp),
            "argmax_attribution_accuracy": round(resp_acc, 4),
            "n_manifesting": len(manifesting),
            "argmax_attribution_accuracy_manifesting": round(resp_acc_m, 4),
            "manifest_by_variant": {
                v: {"n": sum(1 for p in resp if p.variant == v),
                    "rate": round(sum(1 for p in resp if p.variant == v and p.manifested)
                                  / max(1, sum(1 for p in resp if p.variant == v)), 3)}
                for v in sorted({p.variant for p in resp})},
            "profiles": [asdict(p) for p in resp[:20]],
        },
        "composition": {"eps_int": bound.eps_int, "eps": round(bound.eps, 4),
                        "eps_delta": bound.eps_delta,
                        "lower_bound": round(bound.lower_bound, 4),
                        "statement": bound.render()},
    }
    (out / "results.json").write_text(json.dumps(payload, indent=2, default=str))
    log.write(out / "sealed_injection_log.json")
    (out / "report.md").write_text(render(payload))
    print(f"wrote {out/'results.json'} and {out/'report.md'}", file=sys.stderr)
    return 0


def render(p: dict) -> str:
    L = []
    mock = p["harness"]["backend_is_mock"]
    L.append("# MSFS experiment results\n")
    if mock:
        L.append("> **Harness validation run (mock backend).** These numbers "
                 "exercise the apparatus — injection, sealing, projection, "
                 "blinding, and the statistics — end to end. They are not "
                 "results about a language model and must not be reported as "
                 "such. Re-run with `--backend <model-id>` for reportable "
                 "numbers.\n")
    h = p["harness"]
    L.append(f"Executions: {h['executions']}. Sealed chain head "
             f"`{h['sealed_chain_head'][:16]}…`, verified. "
             f"tau = {h['tau']}, one-sided alpha = {h['alpha']}, "
             f"k >= {h['required_successes_at_n']} required per class.\n")

    L.append("\n## E1 — Completeness C(sigma, F_j)\n")
    L.append("| sigma | F_R | F_X | F_T | F_P | FPR |")
    L.append("|---|---|---|---|---|---|")
    order = ["sigma0", "sigma1", "sigma_star", "sigma_star_plus", "sigma_max"]
    by = {}
    for r in p["completeness"]:
        by.setdefault(r["sigma"], {})[r["fault_class"]] = r
    for s in order:
        cells = []
        for fc in ["F_R", "F_X", "F_T", "F_P"]:
            r = by[s][fc]
            mark = "✓" if r["certified"] else ""
            cells.append(f"{r['C']:.3f} ({r['cp_lower']:.3f}){mark}")
        L.append(f"| {s} | " + " | ".join(cells) +
                 f" | {p['false_positive_rate'][s]:.3f} |")
    L.append("\nCell format: point estimate (Clopper-Pearson lower bound). "
             "✓ marks lower bound ≥ tau.\n")

    L.append("\n### Per-variant, under the candidate configuration\n")
    L.append("| fault class | variant | n | C | note |")
    L.append("|---|---|---|---|---|")
    for r in p["per_variant"]:
        note = "integrity layer — counted in eps_int" if r["integrity_layer"] else ""
        L.append(f"| {r['fault_class']} | {r['variant']} | {r['n']} | "
                 f"{r['C']:.3f} | {note} |")

    L.append("\n## E2 — Single-element ablation of the candidate\n")
    L.append("| element | necessary | classes affected | max delta |")
    L.append("|---|---|---|---|")
    for e, v in sorted(p["necessity"].items(),
                       key=lambda kv: -kv[1]["max_delta"]):
        L.append(f"| {e} | {'yes' if v['necessary'] else 'NO'} | "
                 f"{', '.join(v['classes']) or '—'} | {v['max_delta']:.3f} |")

    L.append("\n## E4 — Monotonicity (Lemma A)\n")
    mv = p["monotonicity_violations"]
    L.append("No violations observed." if not mv
             else "Violations:\n" + "\n".join(f"- {m}" for m in mv))

    L.append("\n## Storage\n")
    L.append("| sigma | bytes/execution | GB/day @ 1M | fraction of maximalist |")
    L.append("|---|---|---|---|")
    for r in p["storage"]:
        L.append(f"| {r['sigma']} | {r['bytes_per_execution']:,} | "
                 f"{r['gb_per_day_at_1M']:.1f} | {r['fraction_of_maximalist']:.3f} |")

    L.append("\n## RQ3 — Responsibility\n")
    r = p["responsibility"]
    L.append(f"argmax_i R_i identified the injected component in "
             f"**{r['argmax_attribution_accuracy_manifesting']:.3f}** of the "
             f"{r['n_manifesting']} injections that actually moved the decision "
             f"(and {r['argmax_attribution_accuracy']:.3f} of all {r['n']} "
             f"profiled executions).\n")
    L.append("\nDetectability and responsibility answer different questions. The "
             "fraction of injections of each variant that actually moved the "
             "decision:\n")
    L.append("| variant | n | manifest rate |")
    L.append("|---|---|---|")
    for v, m in sorted(r["manifest_by_variant"].items(), key=lambda kv: kv[1]["rate"]):
        L.append(f"| {v} | {m['n']} | {m['rate']:.2f} |")
    L.append("\nA semantics-preserving paraphrase and a stale policy version hash "
             "are both fully visible in sigma and cause nothing. R_i is correctly "
             "near zero for them, and an evaluation that scored responsibility "
             "against the injection label alone would misread that as failure.\n")
    if mock:
        L.append("\nTwo manifest rates are artefacts of the mock backend rather "
                 "than findings: it does not read system-prompt semantics, so "
                 "`system_substitution` and `paraphrase` cannot move its output. "
                 "Retrieval variants read low for a real reason — when a tool "
                 "return is present this pipeline lets it shadow the retrieved "
                 "passages, so the retriever leaves the causal path. Re-check "
                 "both against a real backend.\n")

    L.append("\n## Composition corollary\n")
    L.append(p["composition"]["statement"] + "\n")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
