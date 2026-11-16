# Round 8: what to run, in order

Steps 1 to 4 (acceptance checks, adjudication, feasibility count, smoke test) are done. What is left is to register and run.

Every command needs these in the same terminal, with Ollama running:

```bash
export MSFS_API_STYLE=openai MSFS_API_BASE=http://localhost:11434 MSFS_API_KEY=ollama
export MSFS_ENCODER=BAAI/bge-base-en-v1.5
export MSFS_CACHE=corpus_cache_r8
```

The registered settings (seed, restricted share, replay budget, caps) are now the defaults, so no extra flags are needed. The runner refuses to start on the small library.

## 5. Register

1. Run the count, and write the result in the blank at the end of PREREG_round8.md, section 9:

```bash
python run_round8.py --count-only --corpus hotpotqa
```

2. Then:

```bash
git add PREREG_round8.md && git commit -m "Round 8 pre-registration"
shasum -a 256 PREREG_round8.md
```

3. Put the hash and the date in the last line of the file, and commit again. Email the hash to Dr. Frigui; that's the timestamp.

## 6. Run, one pair at a time (overnight, can be split across nights)

```bash
for p in F_X+F_D F_T+F_D F_P+F_D F_R+F_D F_R+F_X F_R+F_T F_R+F_P F_X+F_T F_X+F_P F_T+F_P extra; do
  caffeinate -i python run_round8.py --backend llama3.1:8b --corpus hotpotqa \
      --pairs $p --out r8_$p || break
done
python run_round8.py --merge r8_F* r8_extra --out results_round8
git add r8_F* r8_extra results_round8 && git commit -m "Round 8 results as run"
```

- The four poison pairs run first. After `F_X+F_D` finishes, open `r8_F_X+F_D/round8.md` and look at its harmed count: if fewer than about 10 of 72 are harmed, tell me before the rest runs, because Part B's main group will be too small.
- Expect about 9 hours in all; it can be split across nights by listing fewer pairs in the loop.
- A chunk that dies is re-run on its own; it gets the same questions and seeds.
- A finished chunk has `runs.jsonl`. An unfinished one has only `runs.partial.jsonl`, which the merge skips.
- A short pair uses every eligible question automatically; nothing to pass.
- The merge names `r8_F*` and `r8_extra` only, so the smoke folder stays out.

## 7. Send me

- `results_round8/round8.md`
- the registration hash
