# Round 8: two faults in one decision

Candidate record: `sigma_r8`. Bounds: one-sided 97.5% Clopper-Pearson. Config: backend=llama3.1:8b, corpus=hotpotqa, scorer=f1_guarded, answer_format=short, temperature=0.0, seed=20261116, pairs=F_R+F_X,F_R+F_T,F_R+F_P,F_R+F_D,F_X+F_T,F_X+F_P,F_X+F_D,F_T+F_P,F_T+F_D,F_P+F_D, n=72, n_extra=36, restricted_frac=0.35, restricted_cap=200, examples=1398, cap_g12=18, cap_g3=4, budget=24, encoder=BAAI/bge-base-en-v1.5.

## Pass and fail

| test | result | bar | verdict |
|---|---|---|---|
| clean runs raise no alarm | 0/240 alarms (upper 0.015) | upper ≤ 0.05 | PASS |
| single F_R: detected | 96/96 (lower 0.962) | lower ≥ 0.9 | PASS |
| single F_X: detected | 96/96 (lower 0.962) | lower ≥ 0.9 | PASS |
| single F_T: detected | 96/96 (lower 0.962) | lower ≥ 0.9 | PASS |
| single F_P: detected | 96/96 (lower 0.962) | lower ≥ 0.9 | PASS |
| single F_D: no component blamed | 96/96 (lower 0.962) | lower ≥ 0.9 | PASS |
| A1 F_R+F_X: both named | 24/24 (lower 0.858) | lower ≥ 0.9 | FAIL |
| A2 F_R+F_X: cross-talk | 0/24 (upper 0.142) | upper ≤ 0.1 | FAIL |
| A1 F_R+F_T: both named | 24/24 (lower 0.858) | lower ≥ 0.9 | FAIL |
| A2 F_R+F_T: cross-talk | 0/24 (upper 0.142) | upper ≤ 0.1 | FAIL |
| A1 F_R+F_P: both named | 24/24 (lower 0.858) | lower ≥ 0.9 | FAIL |
| A2 F_R+F_P: cross-talk | 0/24 (upper 0.142) | upper ≤ 0.1 | FAIL |
| A3 F_R+F_D: partner named and nothing else (prediction) | 2/24 (lower 0.010) | lower ≥ 0.9 | not confirmed |
| A2 F_R+F_D: cross-talk | 0/24 (upper 0.142) | upper ≤ 0.1 | FAIL |
| A1 F_X+F_T: both named | 24/24 (lower 0.858) | lower ≥ 0.9 | FAIL |
| A2 F_X+F_T: cross-talk | 0/24 (upper 0.142) | upper ≤ 0.1 | FAIL |
| A1 F_X+F_P: both named | 24/24 (lower 0.858) | lower ≥ 0.9 | FAIL |
| A2 F_X+F_P: cross-talk | 0/24 (upper 0.142) | upper ≤ 0.1 | FAIL |
| A3 F_X+F_D: partner named and nothing else (prediction) | 24/24 (lower 0.858) | lower ≥ 0.9 | not confirmed |
| A2 F_X+F_D: cross-talk | 0/24 (upper 0.142) | upper ≤ 0.1 | FAIL |
| A1 F_T+F_P: both named | 24/24 (lower 0.858) | lower ≥ 0.9 | FAIL |
| A2 F_T+F_P: cross-talk | 0/24 (upper 0.142) | upper ≤ 0.1 | FAIL |
| A3 F_T+F_D: partner named and nothing else (prediction) | 24/24 (lower 0.858) | lower ≥ 0.9 | not confirmed |
| A2 F_T+F_D: cross-talk | 0/24 (upper 0.142) | upper ≤ 0.1 | FAIL |
| A3 F_P+F_D: partner named and nothing else (prediction) | 24/24 (lower 0.858) | lower ≥ 0.9 | not confirmed |
| A2 F_P+F_D: cross-talk | 0/24 (upper 0.142) | upper ≤ 0.1 | FAIL |

## Part A: pairs in detail

joint = both component classes named; exact = those and nothing else; cross-talk = an uninjected class named; silent = no alarm. For F_D pairs only the partner can be named; exact there is a false exoneration of the library.

| pair | n | joint | exact | cross-talk | silent | harmed | unavailable | sigma_hash_plus | otel_default | otel_content | openinference | openinference_guard | span_otel_default | span_otel_content | span_openinference | span_openinference_guard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F_R+F_X | 24 | 24 | 24 | 0 | 0 | 15 | 0 | 24 | 0 | 0 | 24 | 24 | 0 | 0 | 24 | 24 |
| F_R+F_T | 24 | 24 | 24 | 0 | 0 | 13 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F_R+F_P | 24 | 24 | 24 | 0 | 0 | 10 | 0 | 24 | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 10 |
| F_R+F_D | 24 | 2 | 2 | 0 | 22 | 7 | 0 | 2 | 0 | 2 | 2 | 2 | 0 | 2 | 2 | 2 |
| F_X+F_T | 24 | 24 | 24 | 0 | 0 | 7 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F_X+F_P | 24 | 24 | 24 | 0 | 0 | 9 | 0 | 24 | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 9 |
| F_X+F_D | 24 | 24 | 24 | 0 | 0 | 6 | 0 | 24 | 0 | 0 | 24 | 24 | 0 | 0 | 24 | 24 |
| F_T+F_P | 24 | 24 | 24 | 0 | 0 | 16 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F_T+F_D | 24 | 24 | 24 | 0 | 0 | 9 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F_P+F_D | 24 | 24 | 24 | 0 | 0 | 9 | 0 | 24 | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 9 |

### Ground truth from the twins (F_D pairs)

library involved = the pair was harmed and the poison was a cause: the partner alone was not harmed, or the poison alone was.

| pair | n | harmed | library involved | partner needed | poison changed the decision |
|---|---|---|---|---|---|
| F_R+F_D | 24 | 7 | 7 | 0 | 11 |
| F_X+F_D | 24 | 6 | 5 | 1 | 10 |
| F_T+F_D | 24 | 9 | 9 | 3 | 15 |
| F_P+F_D | 24 | 9 | 0 | 9 | 12 |

## Single faults

| class | detected | cross-talk | harmed |
|---|---|---|---|
| F_R | 96/96 | 0 | 17 |
| F_X | 96/96 | 0 | 10 |
| F_T | 96/96 | 0 | 7 |
| F_P | 96/96 | 0 | 58 |
| F_D | 96/96 | 0 | 20 |

## Ablation of sigma_r8

Component-fault runs (singles and pairs) where every injected component class was named, with each element removed.

| element | detected | drop |
|---|---|---|
| t_calls_h | 242/624 | 360 |
| x_hash | 264/624 | 338 |
| z_hashes | 264/624 | 338 |
| c_hash | 410/624 | 192 |
| p_witness | 410/624 | 192 |
| t_attest | 410/624 | 192 |
| m | 602/624 | 0 |
| t_desc_hash | 602/624 | 0 |
| t_id | 602/624 | 0 |
| theta | 602/624 | 0 |
| y_class | 602/624 | 0 |
| y_hash | 602/624 | 0 |
| z_ranks | 602/624 | 0 |

## Record size (bytes, binary hashes)

| runs | n | median | p95 | max |
|---|---|---|---|---|
| all | 960 | 871 | 890 | 899 |
| tool_runs | 668 | 874 | 892 | 899 |
| no_tool_runs | 292 | 632 | 634 | 635 |