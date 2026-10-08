# Round 6: what to run, in order

Unzip this over your existing `msfs-experiment` folder so that
`corpus_cache/` (the HotpotQA index) stays where it is.

**Changed files:** `msfs/pipeline.py` (adds the short-answer format line),
`msfs/verifier.py` (reads that line), `msfs/analysis.py` (ALPHA 0.05 → 0.025,
the paper's registered level), `run_realworld.py` (new `--scorer` and
`--answer-format` flags; with neither flag it behaves as before).

**New files:** `msfs/scoring.py`, `msfs/integrity.py`, `exp_integrity.py`,
`exp_responsibility.py`, `exp_judge.py`, `compose_bound.py`,
`PREREG_round6.md`, `LABELING.md`.

## 0. Commit the pre-registration first

```bash
git add -A && git commit -m "Round 6 pre-registration and experiments"
git rev-parse HEAD     # write this hash down; results cite it
```

## 1. Ollama, as in the pilots

```bash
ollama pull llama3.1:8b && ollama pull llama3.2:3b
export MSFS_API_STYLE=openai MSFS_API_BASE=http://localhost:11434 MSFS_API_KEY=ollama
```

## 2. Integrity (about 1 minute, no model)

The run here already produced the result. Re-running it on your machine
confirms it.

```bash
python exp_integrity.py --trials 500 --out results_integrity
```

## 3. Judge outputs (about 300 model calls; run before bed)

```bash
python exp_judge.py generate --backend llama3.1:8b --corpus hotpotqa \
    --n 300 --out results_judge
```

## 4. Responsibility (overnight; resumable)

```bash
python exp_responsibility.py --backend llama3.1:8b --proxy llama3.2:3b \
    --corpus hotpotqa --disputes 60 --max-runs 600 --out results_responsibility
```

The progress line shows disputes found and model calls used. If the laptop
sleeps or you stop it, run the same command again and it carries on. To
rebuild the report alone:
`python exp_responsibility.py --report-only --out results_responsibility`.

Rough cost: 2 calls per attack run, plus poison generation, plus 16
production and 16 proxy calls per dispute. At the pilots' harm rates, expect
300 to 500 attack runs for 60 disputes. Set `caffeinate -i` in front of the
command so the Mac does not sleep.

## 5. Tomorrow: label, then score

Label `results_judge/label_sheet.csv` following `LABELING.md`. 300 items at
about 30 seconds each is roughly 2.5 hours, and it can be split across
sittings. Then:

```bash
python exp_judge.py score --out results_judge --labels results_judge/label_sheet.csv
```

## 6. Send me these files

- `results_integrity/integrity.md`
- `results_responsibility/report.md` and `disputes.jsonl`
- `results_judge/judge_report.md` (after labelling)

`compose_bound.py` produces no number until the confirmatory run gives ε.
Running it now prints which terms are measured and which are still missing.
