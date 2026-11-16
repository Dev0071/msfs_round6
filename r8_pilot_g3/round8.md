# Round 8: two faults in one decision

Candidate record: `sigma_r8`. Bounds: one-sided 97.5% Clopper-Pearson. Config: backend=llama3.1:8b, corpus=hotpotqa, scorer=f1_guarded, answer_format=short, temperature=0.0, seed=1, pairs=F_R+F_X, n=40, n_extra=36, restricted_frac=0.35, restricted_cap=200, examples=1398, cap_g12=18, cap_g3=15, budget=24, encoder=BAAI/bge-base-en-v1.5.

## Pass and fail

| test | result | bar | verdict |
|---|---|---|---|
| clean runs raise no alarm | 0/40 alarms (upper 0.088) | upper ≤ 0.05 | FAIL |
| single F_R: detected | 40/40 (lower 0.912) | lower ≥ 0.9 | PASS |
| single F_X: detected | 40/40 (lower 0.912) | lower ≥ 0.9 | PASS |
| A1 F_R+F_X: both named | 40/40 (lower 0.912) | lower ≥ 0.9 | PASS |
| A2 F_R+F_X: cross-talk | 0/40 (upper 0.088) | upper ≤ 0.1 | PASS |
| B2 innocent library flagged (G3) | 9/14 (upper 0.872) | upper ≤ 0.1 | FAIL |

Part B passes only if B1, B2 (G2 and G3) and B3 all pass: **FAIL**.

## Part A: pairs in detail

joint = both component classes named; exact = those and nothing else; cross-talk = an uninjected class named; silent = no alarm. For F_D pairs only the partner can be named; exact there is a false exoneration of the library.

| pair | n | joint | exact | cross-talk | silent | harmed | unavailable | sigma_hash_plus | otel_default | otel_content | openinference | openinference_guard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F_R+F_X | 40 | 40 | 40 | 0 | 0 | 14 | 0 | 40 | 0 | 0 | 40 | 40 |

## Single faults

| class | detected | cross-talk | harmed |
|---|---|---|---|
| F_R | 40/40 | 0 | 9 |
| F_X | 40/40 | 0 | 8 |

## Part B: replay

| group | n | verdicts | library flagged | replays |
|---|---|---|---|---|
| G3 plain model errors | 14 | library 9, unexplained 5 | 9 | 172 |

## Ablation of sigma_r8

Component-fault runs (singles and pairs) where every injected component class was named, with each element removed.

| element | detected | drop |
|---|---|---|
| x_hash | 0/120 | 120 |
| z_hashes | 0/120 | 120 |
| c_hash | 40/120 | 80 |
| t_calls_h | 40/120 | 80 |
| m | 120/120 | 0 |
| p_witness | 120/120 | 0 |
| t_attest | 120/120 | 0 |
| t_desc_hash | 120/120 | 0 |
| t_id | 120/120 | 0 |
| theta | 120/120 | 0 |
| y_class | 120/120 | 0 |
| y_hash | 120/120 | 0 |
| z_ranks | 120/120 | 0 |

## Record size (bytes, binary hashes)

| runs | n | median | p95 | max |
|---|---|---|---|---|
| all | 160 | 748 | 889 | 899 |
| tool_runs | 80 | 872 | 899 | 899 |
| no_tool_runs | 80 | 632 | 632 | 632 |