# Round 8: what to run, in order

Unzip over your `msfs_round6` folder, as before. Every command assumes the virtual environment is active and, from step 3 on, these exports in the same terminal:

```bash
export MSFS_API_STYLE=openai MSFS_API_BASE=http://localhost:11434 MSFS_API_KEY=ollama
export MSFS_ENCODER=BAAI/bge-base-en-v1.5
```

**New:**
- `run_round8.py`
- `msfs/replay.py`
- `msfs/keys.py`
- `tests_round8.py`
- `PREREG_round8.md`
- this file

**Changed:**
- `msfs/pipeline.py`: HMAC, the witness wrapper, the hashed tool transcript and the content store.
- `msfs/attacks.py`: composite faults, lying filter, forged witness.
- `msfs/verifier.py`: every alarm returned, the content store, the explain-away rule, the witness tag.
- `msfs/state.py`: the `sigma_r8` candidate.
- `run_experiment.py`: re-retrieval with passages left out.
- `exp_judge.py`: adjudication.

The old runners give the same verdicts as before.

## 1. Commit, then the acceptance checks (1 min, no model)

```bash
git add -A && git commit -m "Round 8 code and draft pre-registration"
python tests_round8.py
```

Every line must say `ok`. If one says FAIL, stop and send it to me.

## 2. Settle the 18 judge disagreements (about 1 hour, both annotators)

```bash
python exp_judge.py disagreements --out results_judge2 \
    --labels results_judge2/label_sheet.csv --labels2 results_judge2/label_sheet_annotator2.csv
```

1. Open `results_judge2/adjudication_sheet.csv` with your second annotator and decide each row together. Put 1 (correct) or 0 (wrong) in `label`.
2. Save the file as `results_judge2/adjudicated.csv`.
3. Score:

```bash
python exp_judge.py score --out results_judge2 --labels results_judge2/label_sheet.csv \
    --labels2 results_judge2/label_sheet_annotator2.csv --adjudicated results_judge2/adjudicated.csv
git add results_judge2 && git commit -m "Round 8: judge batch 2 adjudicated"
```

Write the f1_guarded upper bound into PREREG_round8.md, section 9, item 1.

## 3. Feasibility count (2 min, no model)

```bash
python run_round8.py --count-only --corpus hotpotqa
```

It lists eligible questions per pair. F_T+F_P is the likely short one: it needs questions that are both restricted and tool-called. For each pair marked SHORT, choose one:
- accept its smaller n, and write it in section 9, item 2; or
- tell me, and we draw more HotpotQA examples. That changes the library, and gold@4 has to be re-checked.

## 4. Smoke test on the real model (about 15 min)

```bash
python run_round8.py --backend llama3.1:8b --corpus hotpotqa --n 3 --n-extra 2 \
    --pairs F_R+F_D,F_X+F_T,extra --out r8_smoke
```

The progress line shows minutes per block. Multiply by the full plan:
- 10 pairs × 72 blocks × 4 executions;
- extras;
- Part B, up to 40 replays for each of about 230 disputes.

Write the seconds per execution in section 9, item 4. **`r8_smoke` is not a result**; don't commit it with the results.

## 5. Register

1. Confirm the two decisions with Dr. Frigui (section 9, item 3).
2. Then:

```bash
git add PREREG_round8.md && git commit -m "Round 8 pre-registration"
shasum -a 256 PREREG_round8.md
```

3. Put the hash and the date in the last line of the file, and commit again. Email the hash to Dr. Frigui; that's the timestamp.

## 6. Run, one pair at a time (overnight, can be split across nights)

```bash
for p in F_R+F_X F_R+F_T F_R+F_P F_R+F_D F_X+F_T F_X+F_P F_X+F_D F_T+F_P F_T+F_D F_P+F_D extra; do
  caffeinate -i python run_round8.py --backend llama3.1:8b --corpus hotpotqa \
      --pairs $p --out r8_$p || break
done
python run_round8.py --merge r8_F* r8_extra --out results_round8
git add r8_F* r8_extra results_round8 && git commit -m "Round 8 results as run"
```

- A chunk that dies is re-run on its own; it gets the same questions and seeds.
- A finished chunk has `runs.jsonl`. An unfinished one has only `runs.partial.jsonl`, which the merge skips.
- A short pair uses every eligible question automatically; nothing to pass.
- The merge names `r8_F*` and `r8_extra` only, so the smoke folder stays out.

## 7. Send me

- `results_round8/round8.md`
- the output of step 3
- the step 2 score line for f1_guarded
