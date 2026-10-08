#!/usr/bin/env python3
"""
Measurement study: can what LLM applications log today attribute a fault?

Runs the sealed, blind, paired-projection protocol of run_experiment.py and
compares real-world logging configurations against the candidate records.

  python run_realworld.py --faults realistic --backend mock --n 60 --n-clean 50

Paired design. Every execution is run twice on the same question with the same
model randomness: once as planned and once as a clean twin. A fault HARMED the
decision when the twin's outcome was acceptable and the faulted outcome was not.
For the clean arm the twin uses different model randomness, which measures how
often two clean runs disagree by sampling alone (the noise floor; zero at
temperature 0 if the backend honours the seed).

Two questions are scored (--faults realistic):

  component faults (F_R, F_X, F_T, F_P)   does the verifier name the component?
  poisoned inputs  (F_D)                  no component deviated. Does the
                                          verifier blame none, and does the
                                          record let an auditor localise the
                                          input the output came from?
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import random
import sys
import time
from math import comb
from pathlib import Path

from msfs import analysis as an
from msfs import attacks
from msfs import faults as classic
from msfs import pipeline
from msfs.backends import make_backend
from msfs.faults import render
from msfs.localise import candidates, localise, localise_by_removal
from msfs.pipeline import TOOL_DESCRIPTION, Fault, build_corpus, execute, render_context
from msfs.real_world import REAL_WORLD_CONFIGS, project_with_derivation
from msfs.sealing import SealedLog
from msfs.state import (SIGMA_0, SIGMA_HASH, SIGMA_HASH_PLUS, SIGMA_MAX, SIGMA_STAR,
                        SIGMA_STAR_PLUS)
from msfs.verifier import verify
from run_experiment import build_archive, churn

CANDIDATE = SIGMA_HASH_PLUS
ORDER = [SIGMA_0, *REAL_WORLD_CONFIGS, SIGMA_STAR, SIGMA_STAR_PLUS, SIGMA_HASH,
         SIGMA_HASH_PLUS, SIGMA_MAX]
ABLATED = {e: CANDIDATE.drop(e) for e in sorted(CANDIDATE.elements)}
COMPONENT_CLASSES = attacks.COMPONENT_CLASSES
F_D = attacks.INPUT_CLASS


def fisher_greater(k: int, n: int, k0: int, n0: int) -> float:
    """One-sided Fisher exact test: is k/n larger than k0/n0?"""
    total, hits = n + n0, k + k0
    return sum(comb(hits, i) * comb(total - hits, n - i)
               for i in range(k, min(n, hits) + 1)) / comb(total, n)


def pick_restricted(queries, docs, rng, fraction: float = 0.2, cap: int = 80):
    """
    Choose restricted record values: answers the policy forbids releasing.

    A value qualifies when it is long enough not to collide with ordinary text
    (8 characters for text, 2 for figures), is not part of another answer, and
    occurs at most 5 times in the corpus. Every question with that answer is
    restricted. Returns (values, question ids).
    """
    def key(q):
        return render(q.answer_value).lower()

    numeric = lambda q: isinstance(q.answer_value, (int, float))
    answers = sorted({key(q) for q in queries})
    blob = "\n".join(d.text.lower() for d in docs.values())
    cands = sorted({key(q) for q in queries
                    if len(key(q)) >= (2 if numeric(q) else 8)})
    rng.shuffle(cands)
    target = min(cap, max(2, int(fraction * len(queries))))
    values, ids = [], set()
    for v in cands:
        if len(ids) >= target:
            break
        if any(v != a and (v in a or a in v) for a in answers):
            continue
        if blob.count(v) > 5:
            continue
        values.append(v)
        ids |= {q.query_id for q in queries if key(q) == v}
    return values, ids


def make_tool_only(queries, docs):
    """
    Make the tool the only source of the answer for tool questions.

    If the corpus has no tool-only question, the answer passage of each tool
    question is taken out of the corpus (unless a non-tool question needs it),
    and the question is marked as not redundant with any passage. Without this
    the model can ignore the tool and a tool attack does little.
    """
    if any(q.needs_tool and not q.tool_redundant for q in queries):
        return queries, docs, {}
    keep = {q.gold_doc for q in queries if not q.needs_tool}
    docs = dict(docs)
    out, store = [], {}
    for q in queries:
        if q.needs_tool and q.gold_doc not in keep:
            # the lookup service holds the record; the corpus no longer does
            store[q.query_id] = docs[q.gold_doc].text if q.gold_doc in docs \
                else store.get(q.query_id, q.answer_value)
            q = dataclasses.replace(q, tool_redundant=False)
        out.append(q)
    for q in out:
        if q.needs_tool and not q.tool_redundant:
            docs.pop(q.gold_doc, None)
    return out, docs, store


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--faults", default="classic", choices=["classic", "realistic"],
                    help="classic: the byte-edit injectors in faults.py. "
                         "realistic: the attacks in attacks.py")
    ap.add_argument("--backend", default="mock")
    ap.add_argument("--n", type=int, default=300, help="runs per fault class")
    ap.add_argument("--n-clean", type=int, default=300)
    ap.add_argument("--poison-text", default="llm", choices=["llm", "template"],
                    help="llm: generate each poisoned text with the backend, as "
                         "PoisonedRAG does (the mock backend always uses the "
                         "template)")
    ap.add_argument("--proxy", default="same",
                    help="comma-separated models for localisation by removal. "
                         "'same' re-runs the pipeline's own model, which a real "
                         "auditor does not have (an upper bound); name another "
                         "model for a true proxy, e.g. same,llama3.2:3b")
    ap.add_argument("--churn-rate", type=float, default=0.02)
    ap.add_argument("--archive-sync", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=20260815)
    ap.add_argument("--auditor", default="archive+retriever",
                    choices=["archive", "archive+retriever"])
    ap.add_argument("--corpus", default="synthetic", choices=["synthetic", "hotpotqa"])
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--answerable-only", action="store_true",
                    help="use only questions whose answer passage the clean "
                         "retriever places in the top k")
    ap.add_argument("--scorer", default=None, choices=["substring", "strict", "f1", "em"],
                    help="outcome scorer (msfs/scoring.py). Default: the pilot "
                         "behaviour (substring). Choose on exp_judge.py labels.")
    ap.add_argument("--answer-format", default="free", choices=["free", "short"])
    ap.add_argument("--out", default="results_realworld")
    args = ap.parse_args()
    pipeline.set_answer_format(args.answer_format)

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    backend = make_backend(args.backend)
    realistic = args.faults == "realistic"
    proxies = {name: (backend if name == "same" else make_backend(name))
               for name in [p.strip() for p in args.proxy.split(",") if p.strip()]}
    if args.poison_text == "llm" and args.backend != "mock":
        def generate(question, answer, i):
            prompt = attacks.POISON_PROMPT.format(question=question, answer=answer)
            for attempt in range(2):
                theta = {"temperature": 1.0, "top_p": 1.0, "max_tokens": 120,
                         "seed": 1000 * i + attempt}
                text = " ".join(backend.generate(prompt, theta, rng).text.split())
                if answer.lower() in text.lower():
                    return text
            return None
        attacks.GENERATOR = generate

    # ---- corpus ---------------------------------------------------------------
    retriever = answer_check = None
    if args.corpus == "hotpotqa":
        from msfs.real_corpus import DenseRetriever, answer_match, load
        base_docs, queries = load()
        retriever, answer_check = DenseRetriever(base_docs), answer_match
    else:
        base_docs, queries = build_corpus(seed=args.seed)
    if args.scorer:
        from msfs.scoring import make_check
        answer_check = make_check(args.scorer)
    if args.answerable_only:
        fn = retriever or pipeline.retrieve
        before = len(queries)
        queries = [q for q in queries if q.gold_doc in
                   [d.doc_id for d, _ in fn(q, base_docs, args.top_k, random.Random(0))]]
        print(f"answerable-only: kept {len(queries)} of {before} questions",
              file=sys.stderr)
    tool_store = {}
    if realistic:
        queries, base_docs, tool_store = make_tool_only(queries, base_docs)

    # ---- fault registry ---------------------------------------------------------
    if realistic:
        variants = {k: list(v) for k, v in attacks.REALISTIC_VARIANTS.items()}
        classes = [*COMPONENT_CLASSES, F_D]
        integrity_layer = set()
    else:
        variants = {k: list(v) for k, v in classic.VARIANTS.items()}
        # tail reorder is a retrieval fault, not benign drift (see verifier.py)
        variants["F_R"].append("tail_reorder")
        variants["NONE"] = ["clean"]
        classes = list(COMPONENT_CLASSES)
        integrity_layer = classic.INTEGRITY_LAYER_VARIANTS

    def build_fault(fc, variant):
        if variant == "clean":
            return Fault()
        if variant == "tail_reorder":
            return attacks.IndexFault(fault_class="F_R", variant=variant, params={})
        if realistic:
            return attacks.make_attack(fc, rng, variant)
        return classic.make_fault(fc, rng, variant)

    # ---- policy -----------------------------------------------------------------
    restricted_ids = set()
    if realistic:
        # The policy of record forbids releasing restricted record values. A
        # question whose answer is restricted is handled correctly when the
        # answer is NOT released, so a policy fault does harm only when the
        # model's own output contains the value. Nothing is appended.
        values, restricted_ids = pick_restricted(queries, base_docs,
                                                 random.Random(args.seed + 1))
        pipeline.register_restricted(values)
        base_check = answer_check

        def answer_check(output, q, _base=base_check):
            if q.query_id in restricted_ids:
                return True                 # acceptable unless released
            if _base:
                return _base(output, q)
            return render(q.answer_value).lower() in output.lower()

    open_qs = [q for q in queries if q.query_id not in restricted_ids]
    pools = {
        "restricted": [q for q in queries if q.query_id in restricted_ids],
        "tool": [q for q in open_qs if q.needs_tool and
                 (not realistic or not q.tool_redundant)],
        "passage": [q for q in open_qs if not q.needs_tool] if realistic else open_qs,
        "open": open_qs,
    }
    print("questions: " + ", ".join(f"{k} {len(v)}" for k, v in pools.items()),
          file=sys.stderr)

    def pool_for(fc, variant):
        if fc == "NONE":
            return "open"
        if realistic and fc == "F_P":
            return "restricted"
        if variant in attacks.TOOL_CHANNEL or fc == "F_T":
            return "tool"
        return "passage"

    archive = build_archive(base_docs, queries, args.auditor, retriever, args.top_k)
    live_docs = dict(base_docs)
    log = SealedLog()

    plan = [(fc, variants[fc][i % len(variants[fc])])
            for fc in classes for i in range(args.n)]
    plan += [("NONE", variants["NONE"][i % len(variants["NONE"])])
             for i in range(args.n_clean)]
    rng.shuffle(plan)
    for fc, variant in sorted(set(plan)):
        if not pools[pool_for(fc, variant)]:
            raise SystemExit(f"no questions available for {fc}/{variant} "
                             f"(pool '{pool_for(fc, variant)}' is empty)")

    # ---- runs -------------------------------------------------------------------
    records = []
    start = time.time()
    for idx, (fc, variant) in enumerate(plan):
        pool = pools[pool_for(fc, variant)]
        q = pool[rng.randrange(len(pool))]
        fault = build_fault(fc, variant)
        seed = rng.randrange(2 ** 31)
        pid = f"exec-plan-{idx:06d}"
        log.seal(pid, fc, variant, {"query_id": q.query_id, "seed": seed})
        theta = {"temperature": args.temperature, "top_p": 1.0, "max_tokens": 256,
                 "seed": seed}
        kw = dict(top_k=args.top_k, retriever=retriever, answer_check=answer_check,
                  tool_store=tool_store)
        tau = execute(q, live_docs, backend, fault, random.Random(seed), theta,
                      gen_rng=random.Random(seed + 7), **kw)
        # Faulted runs: twin shares the model randomness. Clean runs: twin uses
        # different model randomness, to measure the sampling noise floor.
        tseed = seed + 1 if variant == "clean" else seed
        twin = execute(q, live_docs, backend, Fault(), random.Random(seed),
                       dict(theta, seed=tseed), gen_rng=random.Random(tseed + 7), **kw)
        harmed = ((not twin["_outcome_bad"]) and tau["_outcome_bad"]) or \
                 (tau["_released_violation"] and not twin["_released_violation"])

        # Passages that entered by the normal ingestion path, and revisions the
        # archive has synced, are in the auditor's snapshot as of this
        # execution. The snapshot is restored afterwards.
        ingested = getattr(fault, "ingested", [])
        saved = {d.doc_id: archive.snapshot.get(d.doc_id) for d in ingested}
        for d in ingested:
            archive.doc_text_by_hash[d.content_hash] = d.text
            archive.snapshot[d.doc_id] = d
        sigmas = {c.name: project_with_derivation(tau, c)
                  for c in [*ORDER, *ABLATED.values()]}
        verdicts = {name: verify(s, archive).fault_class for name, s in sigmas.items()}
        evidence = verify(sigmas[CANDIDATE.name], archive).evidence

        # Localisation, for poisoned-input runs: which recorded input does the
        # released output come from, and is that input one the attacker planted?
        located, baseline, removal = {}, None, {}
        if fc == F_D:
            poison = set(fault.params.get("poison_hashes", []))
            tool_poisoned = bool(fault.params.get("poisoned_tool"))
            bad_input = lambda kind, h: (kind == "tool" and tool_poisoned) or h in poison
            for name, s in sigmas.items():
                sus = localise(s, archive, tau["y"])
                located[name] = None if sus is None else bool(
                    bad_input(sus.kind, sus.content_hash))
            cands = candidates(sigmas[SIGMA_MAX.name], archive)
            baseline = (sum(bad_input(k, h) for k, h, _, _ in cands) / len(cands)
                        if cands else 0.0)
            # Localisation by removal, on the disputed (harmed) decisions only,
            # from the candidate record, once per proxy model.
            if harmed:
                for pname, proxy in proxies.items():
                    res = localise_by_removal(sigmas[CANDIDATE.name], archive, tau["y"],
                                              proxy, render_context, TOOL_DESCRIPTION)
                    removal[pname] = None if res is None else {
                        "reproduced": res.reproduced, "calls": res.calls,
                        "hit": None if res.suspect is None else bool(
                            bad_input(res.suspect.kind, res.suspect.content_hash))}
        for d in ingested:
            archive.doc_text_by_hash.pop(d.content_hash, None)
            if saved[d.doc_id] is None:
                archive.snapshot.pop(d.doc_id, None)
            else:
                archive.snapshot[d.doc_id] = saved[d.doc_id]
        records.append({
            "pid": pid, "variant": variant, "verdicts": verdicts,
            "query_id": q.query_id, "evidence": evidence,
            "detail": {k: v for k, v in fault.params.items()
                       if k in ("template", "asserted_value", "dose")},
            "located": located, "baseline": baseline, "removal": removal,
            "output": tau["y"][:400], "twin_output": twin["y"][:400],
            "bad": tau["_outcome_bad"], "twin_bad": twin["_outcome_bad"],
            "text_changed": twin["y"].strip() != tau["y"].strip(),
            "harmed": harmed,
        })
        done = idx + 1
        if done % 10 == 0 or done == len(plan):
            elapsed = time.time() - start
            print(f"[{done}/{len(plan)}] {elapsed/60:.1f} min elapsed, about "
                  f"{elapsed / done * (len(plan) - done) / 60:.1f} min left",
                  file=sys.stderr, flush=True)
        if rng.random() < args.churn_rate:
            churn(live_docs, archive, rng, args.archive_sync)

    truth = log.open_for_scoring()
    for r in records:
        r["fc"] = truth[r["pid"]].fault_class

    # Per-run dump, written only after the sealed log is opened.
    with open(out / "runs.jsonl", "w") as fh:
        for r in records:
            row = {"injected_class": r["fc"], "variant": r["variant"],
                   "query_id": r["query_id"], "candidate": CANDIDATE.name,
                   "evidence": r["evidence"],
                   "verdicts": {c.name: r["verdicts"][c.name] for c in ORDER},
                   "located": {c.name: r["located"].get(c.name) for c in ORDER}
                              if r["located"] else None,
                   "baseline": r["baseline"], "removal": r["removal"] or None}
            for key in ("detail", "bad", "twin_bad", "text_changed", "harmed",
                        "output", "twin_output"):
                row[key] = r[key]
            fh.write(json.dumps(row) + "\n")

    # ---- scoring ----------------------------------------------------------------
    def of(fc, harmed_only=False):
        return [r for r in records if r["fc"] == fc
                and (fc, r["variant"]) not in integrity_layer
                and (r["harmed"] or not harmed_only)]

    def cell(rs, name, fc):
        k = sum(1 for r in rs if r["verdicts"][name] == fc)
        comp = an.Completeness(name, fc, len(rs), k)
        return {"n": comp.n, "k": comp.k,
                "C": round(comp.point, 4) if comp.n else None,
                "cp_lower": round(comp.lower, 4) if comp.n else None,
                "certified": bool(comp.n) and comp.certified}

    # no alarm is the right answer on clean runs and on revisions the archive has
    clean = [r for r in records if r["fc"] == "NONE"
             and r["variant"] != "revision_unsynced"]
    noise = [r for r in records if r["variant"] == "clean"]
    fd = [r for r in records if r["fc"] == F_D]
    fd_harmed = [r for r in fd if r["harmed"]]
    rows, harmed_rows, input_rows = [], [], []
    for cfg in ORDER:
        row = {"sigma": cfg.name, "label": cfg.label, "bytes": cfg.bytes_per_execution,
               "classes": {fc: cell(of(fc), cfg.name, fc) for fc in COMPONENT_CLASSES},
               "fpr": round(sum(r["verdicts"][cfg.name] != "NONE" for r in clean)
                            / len(clean), 4) if clean else None}
        row["n_certified"] = sum(v["certified"] for v in row["classes"].values())
        rows.append(row)
        harmed_rows.append({"sigma": cfg.name, "classes": {
            fc: cell(of(fc, harmed_only=True), cfg.name, fc) for fc in COMPONENT_CLASSES}})
        if fd:
            input_rows.append({
                "sigma": cfg.name, "n": len(fd),
                "no_component_blamed": sum(r["verdicts"][cfg.name] == "NONE" for r in fd),
                "n_harmed": len(fd_harmed),
                "localised": sum(r["located"][cfg.name] is True for r in fd_harmed),
                "named_wrong_input": sum(r["located"][cfg.name] is False
                                         for r in fd_harmed),
                "baseline": round(sum(r["baseline"] for r in fd_harmed)
                                  / len(fd_harmed), 3) if fd_harmed else None})

    rate = lambda k, n: round(k / n, 3) if n else None
    k0, n0 = sum(r["harmed"] for r in noise), len(noise)
    by_variant = []
    for fc in [*classes, "NONE"]:
        for var in dict.fromkeys(variants[fc]):
            rs = [r for r in records if r["fc"] == fc and r["variant"] == var]
            if not rs:
                continue
            harmed = [r for r in rs if r["harmed"]]
            want = "NONE" if fc in (F_D, "NONE") else fc
            det = lambda group: sum(r["verdicts"][CANDIDATE.name] == want for r in group)
            counts = {}
            for name in (SIGMA_HASH.name, CANDIDATE.name):
                c = {}
                for r in rs:
                    c[r["verdicts"][name]] = c.get(r["verdicts"][name], 0) + 1
                counts[name] = c
            by_variant.append({
                "fault_class": fc, "variant": var, "n": len(rs),
                "integrity_layer": (fc, var) in integrity_layer,
                "twin_ok": rate(sum(not r["twin_bad"] for r in rs), len(rs)),
                "text_changed": rate(sum(r["text_changed"] for r in rs), len(rs)),
                "harmed": rate(len(harmed), len(rs)), "n_harmed": len(harmed),
                "p_vs_noise": (round(fisher_greater(len(harmed), len(rs), k0, n0), 3)
                               if var != "clean" and n0 else None),
                "correct_all": rate(det(rs), len(rs)),
                "correct_harmed": rate(det(harmed), len(harmed)) if fc != "NONE" else None,
                "localised": (sum(r["located"][CANDIDATE.name] is True for r in harmed)
                              if fc == F_D else None),
                "baseline": (round(sum(r["baseline"] for r in harmed) / len(harmed), 2)
                             if fc == F_D and harmed else None),
                "verdicts": counts, "predicted": attacks.PREDICTED.get(var),
            })

    # ---- localisation: wording, removal per proxy, and the two combined ----------
    def loc_counts(group):
        row = {"harmed": len(group),
               "baseline": round(sum(r["baseline"] for r in group) / len(group), 2)
                           if group else None,
               "wording": sum(r["located"][CANDIDATE.name] is True for r in group),
               "wording_wrong": sum(r["located"][CANDIDATE.name] is False for r in group),
               "proxies": {}}
        for pname in proxies:
            res = [r["removal"].get(pname) for r in group]
            rep = [x for x in res if x and x["reproduced"]]
            comb = 0
            for r in group:
                w = r["located"][CANDIDATE.name]
                x = r["removal"].get(pname)
                comb += (w is True) or (w is None and bool(x) and x["hit"] is True)
            row["proxies"][pname] = {
                "reproduced": len(rep),
                "removal": sum(x["hit"] is True for x in rep),
                "removal_wrong": sum(x["hit"] is False for x in rep),
                "combined": comb,
                "calls": sum(x["calls"] for x in res if x)}
        return row

    localisation = []
    if fd:
        for var in dict.fromkeys(variants[F_D]):
            localisation.append({"fault": var, **loc_counts(
                [r for r in fd_harmed if r["variant"] == var])})
        localisation.append({"fault": "all poisoned inputs", **loc_counts(fd_harmed)})

    tmpl = {}
    for r in records:
        t = r["detail"].get("template")
        if t:
            k, n = tmpl.get(t, (0, 0))
            tmpl[t] = (k + bool(r["harmed"]), n + 1)

    ablation = []
    full_loc = sum(r["located"][CANDIDATE.name] is True for r in fd_harmed)
    for el, cfg in ABLATED.items():
        hit, worst = [], 0.0
        for fc in COMPONENT_CLASSES:
            rs = of(fc)
            if not rs:
                continue
            b = sum(r["verdicts"][CANDIDATE.name] == fc and r["verdicts"][cfg.name] != fc
                    for r in rs)
            c = sum(r["verdicts"][CANDIDATE.name] != fc and r["verdicts"][cfg.name] == fc
                    for r in rs)
            res = an.AblationResult(el, fc, len(rs), b, c, (b - c) / len(rs))
            worst = max(worst, res.delta)
            if res.necessary:
                hit.append(fc)
        loc = sum(r["located"][cfg.name] is True for r in fd_harmed)
        ablation.append({"element": el, "necessary": bool(hit), "classes": hit,
                         "max_drop": round(worst, 3),
                         "localised_without": loc if fd_harmed else None})
    ablation.sort(key=lambda a: (-a["max_drop"], a["localised_without"] or 0))

    payload = {"config": vars(args), "backend_is_mock": args.backend == "mock",
               "alpha": an.ALPHA, "tau": an.TAU, "candidate": CANDIDATE.name,
               "pools": {k: len(v) for k, v in pools.items()},
               "rows": rows, "harmed_rows": harmed_rows, "input_rows": input_rows,
               "by_variant": by_variant, "noise_floor": {"harmed": k0, "n": n0},
               "by_template": {t: {"harmed": k, "n": n} for t, (k, n) in sorted(tmpl.items())},
               "ablation": ablation, "localised_full": full_loc,
               "localisation": localisation, "proxies": list(proxies),
               "poison_texts": dict(attacks.GENERATED)}
    (out / "realworld.json").write_text(json.dumps(payload, indent=2))

    # ---- report -----------------------------------------------------------------
    f2 = lambda x: "-" if x is None else f"{x:.2f}"
    L = ["# Can today's logging attribute a fault?\n"]
    if args.backend == "mock":
        L.append("> **Mock backend.** Apparatus check, not a result about a "
                 "language model.\n")
    L.append(f"Faults: {args.faults}. Questions: " +
             ", ".join(f"{k} {len(v)}" for k, v in pools.items()) + ".\n")
    L += ["## 1. Component faults: does the verifier name the component?\n",
          "Cell: share of runs where the verdict is the injected class (CP lower "
          f"bound); ✓ = lower bound ≥ {an.TAU} at one-sided alpha {an.ALPHA}. FPR = "
          "share of clean runs where any component was blamed.\n",
          "| record | bytes | F_R | F_X | F_T | F_P | certified | FPR |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        cells = [f"{v['C']:.3f} ({v['cp_lower']:.3f}){'✓' if v['certified'] else ''}"
                 for v in r["classes"].values()]
        L.append(f"| {r['sigma']} | {r['bytes']:,} | " + " | ".join(cells) +
                 f" | {r['n_certified']}/4 | {f2(r['fpr'])} |")
    L += ["", "### Among component faults that harmed the decision", "",
          "Cell: named correctly / harmed (CP lower bound).", "",
          "| record | F_R | F_X | F_T | F_P |", "|---|---|---|---|---|"]
    for r in harmed_rows:
        cells = ["no harmed runs" if not v["n"] else
                 f"{v['k']}/{v['n']} ({v['cp_lower']:.3f}){'✓' if v['certified'] else ''}"
                 for v in r["classes"].values()]
        L.append(f"| {r['sigma']} | " + " | ".join(cells) + " |")
    if input_rows:
        L += ["", "## 2. Poisoned inputs: no component deviated", "",
              "The correct verdict is that no component is to blame. Among the runs "
              "that harmed the decision, the auditor then asks which recorded input "
              "the output came from. localised = the top-ranked input is one the "
              "attacker planted; wrong input = a genuine input was named; the rest "
              "could not be analysed or had no supporting input. Random baseline = "
              "the share of recorded inputs that were planted.", "",
              "| record | no component blamed | localised | wrong input | "
              "random baseline |", "|---|---|---|---|---|"]
        for r in input_rows:
            L.append(f"| {r['sigma']} | {r['no_component_blamed']}/{r['n']} | "
                     f"{r['localised']}/{r['n_harmed']} | "
                     f"{r['named_wrong_input']}/{r['n_harmed']} | {f2(r['baseline'])} |")
    if localisation:
        frac = lambda k, n: f"{k}/{n}"
        L += ["", "### Localisation with the candidate record, by attack", "",
              "wording = the input whose text best matches the output. removal = "
              "take out one recorded input at a time, re-run a proxy model, and name "
              "the input whose removal changes the output; it abstains unless the "
              "proxy first reproduces the disputed output (reproduced). combined = "
              "wording, and removal where wording finds nothing. Proxy `same` is the "
              "pipeline's own model, which a real auditor would not have: read it as "
              "an upper bound.", ""]
        head = "| attack | harmed | random baseline | wording |"
        rule = "|---|---|---|---|"
        for pname in proxies:
            head += f" {pname}: reproduced | {pname}: removal | {pname}: combined |"
            rule += "---|---|---|"
        L += [head, rule]
        for row in localisation:
            n = row["harmed"]
            line = (f"| {row['fault']} | {n} | {f2(row['baseline'])} | "
                    f"{frac(row['wording'], n)} |")
            for pname in proxies:
                x = row["proxies"][pname]
                line += (f" {frac(x['reproduced'], n)} | "
                         f"{frac(x['removal'], x['reproduced'])} | "
                         f"{frac(x['combined'], n)} |")
            L.append(line)
        calls = {p: localisation[-1]["proxies"][p]["calls"] for p in proxies}
        L += ["", "Model calls spent on removal: " +
              ", ".join(f"{p} {c}" for p, c in calls.items()) + "."]
        if realistic:
            g = attacks.GENERATED
            L += ["", f"Poisoned texts: {g['llm']} generated by the model, "
                      f"{g['template']} from the fixed template."]
    L += ["", "## 3. Did each fault change the outcome?", "",
          f"Scored with {CANDIDATE.name}. twin ok = the clean twin gave an "
          "acceptable outcome. correct = the verdict was right (the injected class, "
          "or for F_D no component). p vs noise = one-sided Fisher exact test of "
          f"the harm rate against the clean arm ({k0}/{n0}). The NONE rows are the "
          "drift arm: `correct` there means no component was blamed.", "",
          "| class | fault | n | twin ok | text changed | harmed | p vs noise | "
          "correct (all) | correct (harmed) | localised |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for v in by_variant:
        name = v["variant"] + (" *" if v["integrity_layer"] else "")
        loc = "-" if v["localised"] is None else \
            f"{v['localised']}/{v['n_harmed']} (base {f2(v['baseline'])})"
        p = "-" if v["p_vs_noise"] is None else f"{v['p_vs_noise']:.3f}"
        L.append(f"| {v['fault_class']} | {name} | {v['n']} | {f2(v['twin_ok'])} | "
                 f"{f2(v['text_changed'])} | {v['n_harmed']}/{v['n']} | {p} | "
                 f"{f2(v['correct_all'])} | {f2(v['correct_harmed'])} | {loc} |")
    if integrity_layer:
        L += ["", "\\* integrity-layer variant, excluded from section 1."]
    if realistic:
        show = lambda c: ", ".join(f"{k} {n}" for k, n in
                                   sorted(c.items(), key=lambda kv: -kv[1]))
        L += ["", "## 4. Prediction against observation", "",
              "Predictions are in msfs/attacks.py and were written before the first "
              "run of each attack.", "",
              f"| class | fault | predicted | {SIGMA_HASH.name} | {CANDIDATE.name} |",
              "|---|---|---|---|---|"]
        for v in by_variant:
            if v["predicted"]:
                L.append(f"| {v['fault_class']} | {v['variant']} | {v['predicted']} | "
                         f"{show(v['verdicts'][SIGMA_HASH.name])} | "
                         f"{show(v['verdicts'][CANDIDATE.name])} |")
    if tmpl:
        L += ["", "## 5. Injection wording", "",
              "| wording | harmed | n | rate |", "|---|---|---|---|"]
        for t, (k, n) in sorted(tmpl.items()):
            L.append(f"| {t} | {k} | {n} | {k/n:.2f} |")
    L += ["", f"## 6. Single-element ablation of {CANDIDATE.name}", "",
          "component drop = largest fall in section 1 when the element is removed. "
          + (f"localised without = section 2 count without the element (with it: "
             f"{full_loc}/{len(fd_harmed)})." if fd_harmed else ""), "",
          "| element | needed for | component drop | localised without |",
          "|---|---|---|---|"]
    for a in ablation:
        lw = "-" if a["localised_without"] is None else \
            f"{a['localised_without']}/{len(fd_harmed)}"
        needs = list(a["classes"])
        if fd_harmed and a["localised_without"] < full_loc:
            needs.append("localisation")
        L.append(f"| {a['element']} | {', '.join(needs) or 'nothing'} | "
                 f"{a['max_drop']:.3f} | {lw} |")
    (out / "realworld.md").write_text("\n".join(L))
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
