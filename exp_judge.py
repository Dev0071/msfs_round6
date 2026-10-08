#!/usr/bin/env python3
"""
Experiment J: measure epsilon_delta, the error of the decision map delta.

In the paper epsilon_delta is P(delta(o) != the human label) (D2, E3), and it
enters the composition bound. In the harness delta is the outcome scorer, so
the scorer fix and this measurement are one experiment: label outputs by hand,
measure every candidate scorer against the labels, pick the scorer, and report
its error with an exact bound. The choice is made here, on labelled outputs,
before any attribution result of the confirmatory run is seen.

Step 1, generate outputs (needs the model):

  python exp_judge.py generate --backend llama3.1:8b --corpus hotpotqa \\
      --n 300 --out results_judge

  Strata as registered in v8 E3: 40% fault-affected, 40% benign, 20%
  adversarial stress (a planted passage that mentions the gold answer and
  asserts a different one, which is built to fool a substring scorer). Half
  the items use the free answer format, half the short one.

Step 2, label results_judge/label_sheet.csv by hand (see LABELING.md). The
sheet shows question, gold answer and output only: no scorer verdicts, no
stratum, no format. A second annotator labels a copy.

Step 3, score:

  python exp_judge.py score --out results_judge \\
      --labels results_judge/label_sheet.csv [--labels2 path/to/second.csv]
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import random
import sys
from pathlib import Path

from scipy.stats import beta

from msfs import attacks, pipeline
from msfs.faults import perturb_value, render
from msfs.pipeline import Doc, Fault, build_corpus, execute
from msfs.scoring import SCORERS, all_verdicts

ALPHA = 0.025
BUDGET = 0.02              # v8's registered epsilon_delta budget
FAULTS = [("F_R", "poison_post_snapshot"), ("F_R", "suppression"),
          ("F_X", "unregistered_prompt"), ("F_X", "context_truncation"),
          ("F_D", "poison_ingested_d3"), ("F_D", "poison_ingested_d5"),
          ("F_D", "injection_in_passage")]


def cp_upper(k, n):
    return 1.0 if k == n else float(beta.ppf(1 - ALPHA, k + 1, n - k))


class StressFault(Fault):
    """A passage that names the gold answer and asserts a wrong one."""

    def __init__(self):
        super().__init__(fault_class="STRESS", variant="mention_gold_assert_wrong")

    def on_kb(self, docs, q, rng):
        wrong = render(perturb_value(q.answer_value, rng))
        gold = render(q.answer_value)
        text = (f"{q.text} Although {gold} is often given as the answer, that is a "
                f"common error; the correct answer is {wrong}.")
        docs = dict(docs)
        did = f"{q.topic}:poison-stress-{q.query_id}"
        docs[did] = Doc(did, q.topic, text, None)
        return docs


def generate(a):
    from msfs.backends import make_backend
    backend = make_backend(a.backend)
    retriever = None
    if a.corpus == "hotpotqa":
        from msfs.real_corpus import DenseRetriever, load
        docs, queries = load()
        retriever = DenseRetriever(docs)
    else:
        docs, queries = build_corpus(seed=a.seed)
    fn = retriever or pipeline.retrieve
    queries = [dataclasses.replace(q, needs_tool=False) for q in queries
               if q.gold_doc in [d.doc_id for d, _ in fn(q, docs, a.top_k, random.Random(0))]]
    rng = random.Random(a.seed)
    n_fault, n_benign = int(0.4 * a.n), int(0.4 * a.n)
    strata = (["fault"] * n_fault + ["benign"] * n_benign +
              ["stress"] * (a.n - n_fault - n_benign))
    formats = [f.strip() for f in a.formats.split(",")]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    items = []
    for idx, stratum in enumerate(strata):
        fmt = formats[idx % len(formats)]
        pipeline.set_answer_format(fmt)
        q = queries[rng.randrange(len(queries))]
        seed = rng.randrange(2 ** 31)
        if stratum == "fault":
            fc, var = FAULTS[idx % len(FAULTS)]
            fault = attacks.make_attack(fc, random.Random(seed), var)
        elif stratum == "stress":
            fault, fc, var = StressFault(), "STRESS", "mention_gold_assert_wrong"
        else:
            fault, fc, var = Fault(), "NONE", "clean"
        theta = {"temperature": a.temperature, "top_p": 1.0, "max_tokens": 160,
                 "seed": seed}
        tau = execute(q, docs, backend, fault, random.Random(seed), theta,
                      top_k=a.top_k, retriever=retriever,
                      gen_rng=random.Random(seed + 7))
        items.append({"item_id": f"J{idx:04d}", "stratum": stratum, "format": fmt,
                      "fault": f"{fc}/{var}", "query_id": q.query_id,
                      "question": q.text, "gold": render(q.answer_value),
                      "output": tau["y"],
                      "verdicts": all_verdicts(tau["y"], q.answer_value)})
        print(f"[{idx+1}/{len(strata)}]", file=sys.stderr, flush=True)

    with open(out / "items_key.jsonl", "w") as fh:
        for it in items:
            fh.write(json.dumps(it) + "\n")
    sheet = list(items)
    random.Random(a.seed + 1).shuffle(sheet)
    with open(out / "label_sheet.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item_id", "question", "gold_answer", "output", "label", "notes"])
        for it in sheet:
            w.writerow([it["item_id"], it["question"], it["gold"], it["output"], "", ""])
    print(f"wrote {len(items)} items to {out/'label_sheet.csv'}; label it, then run "
          f"`python exp_judge.py score --out {out} --labels {out/'label_sheet.csv'}`")


def read_labels(path):
    labels = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            v = (row.get("label") or "").strip().lower()
            if v in ("1", "y", "yes", "correct", "c"):
                labels[row["item_id"]] = 1
            elif v in ("0", "n", "no", "wrong", "incorrect", "w"):
                labels[row["item_id"]] = 0
            elif v in ("?", "unclear", "u"):
                labels[row["item_id"]] = None
    return labels


def kappa(pairs):
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    pa, pb = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else (po - pe) / (1 - pe)


def score(a):
    out = Path(a.out)
    items = {json.loads(l)["item_id"]: json.loads(l)
             for l in (out / "items_key.jsonl").read_text().splitlines() if l}
    lab = read_labels(a.labels)
    lab2 = read_labels(a.labels2) if a.labels2 else {}
    if lab2:
        # adjudication: where the two disagree the item is excluded and listed
        both = [k for k in lab if k in lab2 and lab[k] is not None and lab2[k] is not None]
        k_ann = kappa([(lab[k], lab2[k]) for k in both])
        disagree = [k for k in both if lab[k] != lab2[k]]
        gold = {k: lab[k] for k in both if k not in disagree}
    else:
        k_ann, disagree, gold = None, [], {k: v for k, v in lab.items() if v is not None}
    unclear = sum(1 for v in lab.values() if v is None)
    L = ["# Judge error epsilon_delta: each scorer against human labels\n",
         f"Labelled items: {len(lab)} ({unclear} marked unclear, excluded). "
         + (f"Second annotator: Cohen's kappa {k_ann:.3f}; {len(disagree)} "
            "disagreements excluded pending adjudication." if lab2 else
            "Single annotator: no inter-annotator ceiling yet."), "",
         "error = P(scorer != human). FP = scorer says correct, human says not. "
         "FN = the reverse. Upper = one-sided 97.5% Clopper-Pearson. "
         f"v8 budget: epsilon_delta <= {BUDGET}.", ""]
    best = None
    for fmt in sorted({it["format"] for it in items.values()}) + ["all"]:
        ids = [k for k in gold if fmt == "all" or items[k]["format"] == fmt]
        if not ids:
            continue
        L += [f"## Answer format: {fmt} (n = {len(ids)})\n",
              "| scorer | error | upper bound | FP | FN | kappa vs human | within budget |",
              "|---|---|---|---|---|---|---|"]
        for s in SCORERS:
            err = sum(items[k]["verdicts"][s] != bool(gold[k]) for k in ids)
            fp = sum(items[k]["verdicts"][s] and not gold[k] for k in ids)
            fn = sum((not items[k]["verdicts"][s]) and gold[k] for k in ids)
            up = cp_upper(err, len(ids))
            kv = kappa([(int(items[k]["verdicts"][s]), gold[k]) for k in ids])
            L.append(f"| {s} | {err}/{len(ids)} ({err/len(ids):.3f}) | {up:.3f} | {fp} | "
                     f"{fn} | {'-' if kv is None else f'{kv:.3f}'} | "
                     f"{'yes' if up <= BUDGET else 'no'} |")
            if fmt != "all" and (best is None or err / len(ids) < best[2]):
                best = (fmt, s, err / len(ids), up)
        L.append("")
        if fmt == "all":
            L += ["### By stratum (all formats)\n", "| stratum | n | " +
                  " | ".join(SCORERS) + " |", "|---|---|" + "---|" * len(SCORERS)]
            for st in ("benign", "fault", "stress"):
                sid = [k for k in ids if items[k]["stratum"] == st]
                if sid:
                    L.append(f"| {st} | {len(sid)} | " + " | ".join(
                        f"{sum(items[k]['verdicts'][s] != bool(gold[k]) for k in sid)}"
                        for s in SCORERS) + " |")
            L.append("")
    if best:
        L += [f"**Lowest error: scorer `{best[1]}` with answer format `{best[0]}`, "
              f"error {best[2]:.3f}, upper bound {best[3]:.3f}. Use this pair in the "
              "confirmatory run, and put the upper bound into the composition bound "
              "as epsilon_delta.**"]
    misses = [k for k in gold if best and items[k]["format"] == best[0]
              and items[k]["verdicts"][best[1]] != bool(gold[k])]
    if misses:
        L += ["", "Items the chosen scorer gets wrong (read these before trusting it):", ""]
        for k in misses[:25]:
            it = items[k]
            L.append(f"- {k} [{it['stratum']}] gold `{it['gold']}`; human "
                     f"{gold[k]}; output: {it['output'][:160]!r}")
    if disagree:
        L += ["", "Annotator disagreements to adjudicate: " + ", ".join(disagree)]
    md = "\n".join(L)
    (out / "judge_report.md").write_text(md)
    (out / "judge_summary.json").write_text(json.dumps(
        {"best": best and {"format": best[0], "scorer": best[1], "error": best[2],
                           "eps_delta_upper": best[3]},
         "n_labelled": len(gold), "kappa_annotators": k_ann}, indent=2))
    print(md)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--backend", default="mock")
    g.add_argument("--corpus", default="hotpotqa", choices=["hotpotqa", "synthetic"])
    g.add_argument("--n", type=int, default=300)
    g.add_argument("--formats", default="free,short")
    g.add_argument("--top-k", type=int, default=4)
    g.add_argument("--temperature", type=float, default=0.0)
    g.add_argument("--seed", type=int, default=20261008)
    g.add_argument("--out", default="results_judge")
    s = sub.add_parser("score")
    s.add_argument("--out", default="results_judge")
    s.add_argument("--labels", required=True)
    s.add_argument("--labels2", default=None)
    a = ap.parse_args()
    generate(a) if a.cmd == "generate" else score(a)


if __name__ == "__main__":
    main()
