# Round 8: two faults in one decision

Candidate record: `sigma_r8`. Bounds: one-sided 97.5% Clopper-Pearson. Config: backend=llama3.1:8b, corpus=hotpotqa, scorer=f1_guarded, answer_format=short, temperature=0.0, seed=20261116, pairs=F_R+F_T, n=72, n_extra=36, restricted_frac=0.35, restricted_cap=200, examples=1398, cap_g12=18, cap_g3=4, budget=24, encoder=BAAI/bge-base-en-v1.5.

## Pass and fail

| test | result | bar | verdict |
|---|---|---|---|
| clean runs raise no alarm | 0/72 alarms (upper 0.050) | upper ≤ 0.05 | PASS |
| single F_R: detected | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| single F_T: detected | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| A1 F_R+F_T: both named | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| A2 F_R+F_T: cross-talk | 0/72 (upper 0.050) | upper ≤ 0.1 | PASS |
| B2 innocent library flagged (G3) | 2/4 (upper 0.932) | upper ≤ 0.1 | FAIL |

Part B passes only if B1, B2 (G2 and G3) and B3 all pass: **FAIL**.

## Part A: pairs in detail

joint = both component classes named; exact = those and nothing else; cross-talk = an uninjected class named; silent = no alarm. For F_D pairs only the partner can be named; exact there is a false exoneration of the library.

| pair | n | joint | exact | cross-talk | silent | harmed | unavailable | sigma_hash_plus | otel_default | otel_content | openinference | openinference_guard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F_R+F_T | 72 | 72 | 72 | 0 | 0 | 34 | 0 | 72 | 0 | 0 | 0 | 0 |

## Single faults

| class | detected | cross-talk | harmed |
|---|---|---|---|
| F_R | 72/72 | 0 | 4 |
| F_T | 72/72 | 0 | 6 |

## Part B: replay

| group | n | verdicts | library flagged | replays |
|---|---|---|---|---|
| G3 plain model errors | 4 | library 2, unexplained 2 | 2 | 54 |

## Ablation of sigma_r8

Component-fault runs (singles and pairs) where every injected component class was named, with each element removed.

| element | detected | drop |
|---|---|---|
| t_attest | 72/216 | 144 |
| t_calls_h | 72/216 | 144 |
| x_hash | 72/216 | 144 |
| z_hashes | 72/216 | 144 |
| c_hash | 216/216 | 0 |
| m | 216/216 | 0 |
| p_witness | 216/216 | 0 |
| t_desc_hash | 216/216 | 0 |
| t_id | 216/216 | 0 |
| theta | 216/216 | 0 |
| y_class | 216/216 | 0 |
| y_hash | 216/216 | 0 |
| z_ranks | 216/216 | 0 |

## Record size (bytes, binary hashes)

| runs | n | median | p95 | max |
|---|---|---|---|---|
| all | 288 | 872 | 890 | 900 |
| tool_runs | 288 | 872 | 890 | 900 |