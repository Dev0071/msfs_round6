# Round 8: two faults in one decision

Candidate record: `sigma_r8`. Bounds: one-sided 97.5% Clopper-Pearson. Config: backend=llama3.1:8b, corpus=hotpotqa, scorer=f1_guarded, answer_format=short, temperature=0.0, seed=20261116, pairs=F_X+F_P, n=72, n_extra=36, restricted_frac=0.35, restricted_cap=200, examples=1398, cap_g12=18, cap_g3=4, budget=24, encoder=BAAI/bge-base-en-v1.5.

## Pass and fail

| test | result | bar | verdict |
|---|---|---|---|
| clean runs raise no alarm | 0/72 alarms (upper 0.050) | upper ≤ 0.05 | PASS |
| single F_X: detected | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| single F_P: detected | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| A1 F_X+F_P: both named | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| A2 F_X+F_P: cross-talk | 0/72 (upper 0.050) | upper ≤ 0.1 | PASS |

## Part A: pairs in detail

joint = both component classes named; exact = those and nothing else; cross-talk = an uninjected class named; silent = no alarm. For F_D pairs only the partner can be named; exact there is a false exoneration of the library.

| pair | n | joint | exact | cross-talk | silent | harmed | unavailable | sigma_hash_plus | otel_default | otel_content | openinference | openinference_guard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F_X+F_P | 72 | 72 | 72 | 0 | 0 | 34 | 0 | 72 | 0 | 0 | 0 | 72 |

## Single faults

| class | detected | cross-talk | harmed |
|---|---|---|---|
| F_X | 72/72 | 0 | 0 |
| F_P | 72/72 | 0 | 44 |

## Ablation of sigma_r8

Component-fault runs (singles and pairs) where every injected component class was named, with each element removed.

| element | detected | drop |
|---|---|---|
| c_hash | 72/216 | 144 |
| p_witness | 72/216 | 144 |
| t_calls_h | 72/216 | 144 |
| x_hash | 72/216 | 144 |
| z_hashes | 72/216 | 144 |
| m | 216/216 | 0 |
| t_attest | 216/216 | 0 |
| t_desc_hash | 216/216 | 0 |
| t_id | 216/216 | 0 |
| theta | 216/216 | 0 |
| y_class | 216/216 | 0 |
| y_hash | 216/216 | 0 |
| z_ranks | 216/216 | 0 |

## Record size (bytes, binary hashes)

| runs | n | median | p95 | max |
|---|---|---|---|---|
| all | 288 | 867 | 885 | 895 |
| tool_runs | 152 | 875 | 890 | 895 |
| no_tool_runs | 136 | 632 | 635 | 635 |