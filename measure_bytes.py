"""
Measure the actual size of each record, run by run.

The byte figures in earlier reports (1,117 for the candidate, 30,433 for
log-everything) are sums of fixed per-element estimates in state.OMEGA. They do
not depend on the question, the passages or the output. This script measures
the real serialised size of every record on real executions, so the size claim
can be stated as a distribution rather than a constant.

Two encodings are reported for each record:
  json   canonical JSON (sorted keys, no whitespace), hashes as 64-char hex
  bin    the same, with every SHA-256 hex digest counted at 32 raw bytes
         (what a binary log format would store)

Usage, on the machine with the corpus cache and Ollama:
  python measure_bytes.py --corpus hotpotqa --backend llama3.1:8b \
      --answer-format short --answerable-only --n 60 --out results_bytes
  python measure_bytes.py --backend mock --n 30      # apparatus check only
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
from pathlib import Path

from msfs import attacks, pipeline
from msfs.backends import make_backend
from msfs.pipeline import Fault, build_corpus, execute
from msfs.real_world import project_with_derivation
from run_realworld import ORDER, make_tool_only, pick_restricted

HEX64 = re.compile(r'"[0-9a-f]{64}"')


def json_size(stored) -> int:
    return len(json.dumps(stored, sort_keys=True, separators=(",", ":"),
                          default=str).encode("utf-8"))


def bin_size(stored) -> int:
    text = json.dumps(stored, sort_keys=True, separators=(",", ":"), default=str)
    n_hashes = len(HEX64.findall(text))
    return len(text.encode("utf-8")) - n_hashes * 34   # 66 chars incl. quotes -> 32 bytes


def summary(xs):
    xs = sorted(xs)
    p95 = xs[min(len(xs) - 1, int(0.95 * len(xs)))]
    return {"n": len(xs), "min": xs[0], "median": int(statistics.median(xs)),
            "mean": round(statistics.mean(xs)), "p95": p95, "max": xs[-1]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="synthetic", choices=["synthetic", "hotpotqa"])
    ap.add_argument("--backend", default="mock")
    ap.add_argument("--n", type=int, default=60, help="runs per arm")
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--answer-format", default="short", choices=["free", "short"])
    ap.add_argument("--answerable-only", action="store_true")
    ap.add_argument("--seed", type=int, default=20261019)
    ap.add_argument("--out", default="results_bytes")
    args = ap.parse_args()

    pipeline.set_answer_format(args.answer_format)
    rng = random.Random(args.seed)
    backend = make_backend(args.backend)

    retriever = None
    if args.corpus == "hotpotqa":
        from msfs.real_corpus import DenseRetriever, load
        base_docs, queries = load()
        retriever = DenseRetriever(base_docs)
    else:
        base_docs, queries = build_corpus(seed=args.seed)
    if args.answerable_only:
        fn = retriever or pipeline.retrieve
        queries = [q for q in queries if q.gold_doc in
                   [d.doc_id for d, _ in fn(q, base_docs, args.top_k, random.Random(0))]]
    queries, base_docs, tool_store = make_tool_only(queries, base_docs)
    values, restricted = pick_restricted(queries, base_docs, random.Random(args.seed + 1))
    pipeline.register_restricted(values)

    # Arms: clean runs, plus one realistic attack per class, so the sizes cover
    # poisoned passages, rewritten prompts and changed tool results too.
    arms = [("NONE", "clean")] + [(fc, None) for fc in
                                  [*attacks.COMPONENT_CLASSES, attacks.INPUT_CLASS]]
    sizes = {c.name: {"json": [], "bin": []} for c in ORDER}
    lengths = {"question_chars": [], "passage_chars": [], "output_chars": [],
               "prompt_chars": []}
    rows = []

    for fc, variant in arms:
        for i in range(args.n):
            q = queries[rng.randrange(len(queries))]
            fault = Fault() if fc == "NONE" else attacks.make_attack(fc, rng, variant)
            seed = rng.randrange(2 ** 31)
            theta = {"temperature": 0.0, "top_p": 1.0, "max_tokens": 256, "seed": seed}
            tau = execute(q, base_docs, backend, fault, random.Random(seed), theta,
                          top_k=args.top_k, retriever=retriever,
                          gen_rng=random.Random(seed + 7), tool_store=tool_store)
            lengths["question_chars"].append(len(tau["x_text"]))
            lengths["passage_chars"].append(sum(len(t) for t in tau["z_text"]))
            lengths["output_chars"].append(len(tau["y"]))
            lengths["prompt_chars"].append(len(tau["c"]))
            row = {"arm": fc, "variant": getattr(fault, "variant", "clean"),
                   "tool_run": tau["t_calls"] is not None,
                   "passage_chars": lengths["passage_chars"][-1],
                   "tool_chars": len(json.dumps(tau["t_calls"])) if tau["t_calls"] else 0}
            for c in ORDER:
                stored = {e: tau.get(e) for e in sorted(c.elements)}  # as recorded
                sizes[c.name]["json"].append(json_size(stored))
                sizes[c.name]["bin"].append(bin_size(stored))
                row[c.name] = sizes[c.name]["bin"][-1]
            rows.append(row)
        print(f"{fc}: {args.n} runs", file=sys.stderr)

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    report = {
        "config": vars(args),
        "estimate_bytes": {c.name: c.bytes_per_execution for c in ORDER},
        "measured": {name: {enc: summary(v) for enc, v in d.items()}
                     for name, d in sizes.items()},
        "inputs": {k: summary(v) for k, v in lengths.items()},
    }
    (out / "bytes.json").write_text(json.dumps(report, indent=2))

    L = [f"# Record sizes, measured ({args.corpus}, backend {args.backend}, "
         f"{len(arms) * args.n} runs)", "",
         "| record | estimate | median (bin) | p95 (bin) | max (bin) | median (json) |",
         "|---|---:|---:|---:|---:|---:|"]
    for c in ORDER:
        m = report["measured"][c.name]
        L.append(f"| {c.name} | {c.bytes_per_execution:,} | {m['bin']['median']:,} | "
                 f"{m['bin']['p95']:,} | {m['bin']['max']:,} | {m['json']['median']:,} |")
    L += ["", "| input | median chars | p95 | max |", "|---|---:|---:|---:|"]
    for k, s in report["inputs"].items():
        L.append(f"| {k} | {s['median']:,} | {s['p95']:,} | {s['max']:,} |")
    # Split by whether the run called the tool: the candidate stores the tool
    # transcript verbatim, so that is the one place content length enters it.
    import csv
    with open(out / "runs.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    L += ["", "| record | runs | n | median (bin) | p95 (bin) | max (bin) |",
          "|---|---|---:|---:|---:|---:|"]
    for name in ("sigma_hash_plus", "openinference", "sigma_max"):
        for tool in (False, True):
            xs = [r[name] for r in rows if r["tool_run"] == tool]
            if xs:
                m = summary(xs)
                L.append(f"| {name} | {'tool' if tool else 'no tool'} | {m['n']} | "
                         f"{m['median']:,} | {m['p95']:,} | {m['max']:,} |")
    def corr(a, b):
        ma, mb = statistics.mean(a), statistics.mean(b)
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
        return num / den if den else float("nan")
    pc = [r["passage_chars"] for r in rows]
    L += ["", "Correlation of record size with retrieved passage length (all runs): " +
          ", ".join(f"{n} {corr(pc, [r[n] for r in rows]):.2f}"
                    for n in ("sigma_hash_plus", "openinference", "sigma_max"))]
    (out / "bytes.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())