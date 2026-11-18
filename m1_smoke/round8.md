# Round 8: two faults in one decision

Candidate record: `sigma_r8`. Bounds: one-sided 97.5% Clopper-Pearson. Config: backend=llama3.1:8b, corpus=hotpotqa, scorer=f1_guarded, answer_format=short, temperature=0.0, seed=1, pairs=F_R+F_X,F_R+F_T,F_R+F_P,F_R+F_D,F_X+F_T,F_X+F_P,F_X+F_D,F_T+F_P,F_T+F_D,F_P+F_D, n=72, n_extra=36, restricted_frac=0.35, restricted_cap=200, examples=1398, cap_g12=18, cap_g3=4, budget=24, encoder=BAAI/bge-base-en-v1.5.

## Pass and fail

| test | result | bar | verdict |
|---|---|---|---|
| clean runs raise no alarm | 0/10 alarms (upper 0.308) | upper ≤ 0.05 | FAIL |
| single F_R: detected | 4/4 (lower 0.398) | lower ≥ 0.9 | FAIL |
| single F_X: detected | 4/4 (lower 0.398) | lower ≥ 0.9 | FAIL |
| single F_T: detected | 4/4 (lower 0.398) | lower ≥ 0.9 | FAIL |
| single F_P: detected | 4/4 (lower 0.398) | lower ≥ 0.9 | FAIL |
| single F_D: no component blamed | 4/4 (lower 0.398) | lower ≥ 0.9 | FAIL |
| A1 F_R+F_X: both named | 1/1 (lower 0.025) | lower ≥ 0.9 | FAIL |
| A2 F_R+F_X: cross-talk | 0/1 (upper 0.975) | upper ≤ 0.1 | FAIL |
| A1 F_R+F_T: both named | 1/1 (lower 0.025) | lower ≥ 0.9 | FAIL |
| A2 F_R+F_T: cross-talk | 0/1 (upper 0.975) | upper ≤ 0.1 | FAIL |
| A1 F_R+F_P: both named | 1/1 (lower 0.025) | lower ≥ 0.9 | FAIL |
| A2 F_R+F_P: cross-talk | 0/1 (upper 0.975) | upper ≤ 0.1 | FAIL |
| A3 F_R+F_D: partner named and nothing else (prediction) | 0/1 (lower 0.000) | lower ≥ 0.9 | not confirmed |
| A2 F_R+F_D: cross-talk | 0/1 (upper 0.975) | upper ≤ 0.1 | FAIL |
| A1 F_X+F_T: both named | 1/1 (lower 0.025) | lower ≥ 0.9 | FAIL |
| A2 F_X+F_T: cross-talk | 0/1 (upper 0.975) | upper ≤ 0.1 | FAIL |
| A1 F_X+F_P: both named | 1/1 (lower 0.025) | lower ≥ 0.9 | FAIL |
| A2 F_X+F_P: cross-talk | 0/1 (upper 0.975) | upper ≤ 0.1 | FAIL |
| A3 F_X+F_D: partner named and nothing else (prediction) | 1/1 (lower 0.025) | lower ≥ 0.9 | not confirmed |
| A2 F_X+F_D: cross-talk | 0/1 (upper 0.975) | upper ≤ 0.1 | FAIL |
| A1 F_T+F_P: both named | 1/1 (lower 0.025) | lower ≥ 0.9 | FAIL |
| A2 F_T+F_P: cross-talk | 0/1 (upper 0.975) | upper ≤ 0.1 | FAIL |
| A3 F_T+F_D: partner named and nothing else (prediction) | 1/1 (lower 0.025) | lower ≥ 0.9 | not confirmed |
| A2 F_T+F_D: cross-talk | 0/1 (upper 0.975) | upper ≤ 0.1 | FAIL |
| A3 F_P+F_D: partner named and nothing else (prediction) | 1/1 (lower 0.025) | lower ≥ 0.9 | not confirmed |
| A2 F_P+F_D: cross-talk | 0/1 (upper 0.975) | upper ≤ 0.1 | FAIL |

## Part A: pairs in detail

joint = both component classes named; exact = those and nothing else; cross-talk = an uninjected class named; silent = no alarm. For F_D pairs only the partner can be named; exact there is a false exoneration of the library.

| pair | n | joint | exact | cross-talk | silent | harmed | unavailable | sigma_hash_plus | otel_default | otel_content | openinference | openinference_guard | span_otel_default | span_otel_content | span_openinference | span_openinference_guard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F_R+F_X | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 1 | 0 | 0 | 1 | 1 |
| F_R+F_T | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F_R+F_P | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 1 |
| F_R+F_D | 1 | 0 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F_X+F_T | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F_X+F_P | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| F_X+F_D | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 1 | 0 | 0 | 1 | 1 |
| F_T+F_P | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F_T+F_D | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F_P+F_D | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |

### Ground truth from the twins (F_D pairs)

library involved = the pair was harmed and the poison was a cause: the partner alone was not harmed, or the poison alone was.

| pair | n | harmed | library involved | partner needed | poison changed the decision |
|---|---|---|---|---|---|
| F_R+F_D | 1 | 1 | 1 | 0 | 0 |
| F_X+F_D | 1 | 0 | 0 | 0 | 1 |
| F_T+F_D | 1 | 0 | 0 | 0 | 0 |
| F_P+F_D | 1 | 0 | 0 | 0 | 0 |

## Single faults

| class | detected | cross-talk | harmed |
|---|---|---|---|
| F_R | 4/4 | 0 | 1 |
| F_X | 4/4 | 0 | 0 |
| F_T | 4/4 | 0 | 0 |
| F_P | 4/4 | 0 | 2 |
| F_D | 4/4 | 0 | 1 |

## Ablation of sigma_r8

Component-fault runs (singles and pairs) where every injected component class was named, with each element removed.

| element | detected | drop |
|---|---|---|
| t_calls_h | 10/26 | 15 |
| x_hash | 11/26 | 14 |
| z_hashes | 11/26 | 14 |
| c_hash | 17/26 | 8 |
| p_witness | 17/26 | 8 |
| t_attest | 17/26 | 8 |
| m | 25/26 | 0 |
| t_desc_hash | 25/26 | 0 |
| t_id | 25/26 | 0 |
| theta | 25/26 | 0 |
| y_class | 25/26 | 0 |
| y_hash | 25/26 | 0 |
| z_ranks | 25/26 | 0 |

## Record size (bytes, binary hashes)

| runs | n | median | p95 | max |
|---|---|---|---|---|
| all | 40 | 875 | 881 | 881 |
| tool_runs | 32 | 878 | 881 | 881 |
| no_tool_runs | 8 | 632 | 634 | 634 |