# Round 8: two faults in one decision

Candidate record: `sigma_r8`. Bounds: one-sided 97.5% Clopper-Pearson. Config: backend=llama3.1:8b, corpus=hotpotqa, scorer=f1_guarded, answer_format=short, temperature=0.0, seed=20261116, pairs=extra, n=72, n_extra=36, restricted_frac=0.35, restricted_cap=200, examples=1398, cap_g12=18, cap_g3=4, budget=24, encoder=BAAI/bge-base-en-v1.5, merged_from=11.

## Pass and fail

| test | result | bar | verdict |
|---|---|---|---|
| clean runs raise no alarm | 0/720 alarms (upper 0.005) | upper ≤ 0.05 | PASS |
| single F_R: detected | 288/288 (lower 0.987) | lower ≥ 0.9 | PASS |
| single F_X: detected | 288/288 (lower 0.987) | lower ≥ 0.9 | PASS |
| single F_T: detected | 288/288 (lower 0.987) | lower ≥ 0.9 | PASS |
| single F_P: detected | 288/288 (lower 0.987) | lower ≥ 0.9 | PASS |
| single F_D: no component blamed | 288/288 (lower 0.987) | lower ≥ 0.9 | PASS |
| A1 F_R+F_X: both named | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| A2 F_R+F_X: cross-talk | 0/72 (upper 0.050) | upper ≤ 0.1 | PASS |
| A1 F_R+F_T: both named | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| A2 F_R+F_T: cross-talk | 0/72 (upper 0.050) | upper ≤ 0.1 | PASS |
| A1 F_R+F_P: both named | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| A2 F_R+F_P: cross-talk | 0/72 (upper 0.050) | upper ≤ 0.1 | PASS |
| A3 F_R+F_D: partner named and nothing else (prediction) | 7/72 (lower 0.040) | lower ≥ 0.9 | not confirmed |
| A2 F_R+F_D: cross-talk | 0/72 (upper 0.050) | upper ≤ 0.1 | PASS |
| A1 F_X+F_T: both named | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| A2 F_X+F_T: cross-talk | 0/72 (upper 0.050) | upper ≤ 0.1 | PASS |
| A1 F_X+F_P: both named | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| A2 F_X+F_P: cross-talk | 0/72 (upper 0.050) | upper ≤ 0.1 | PASS |
| A3 F_X+F_D: partner named and nothing else (prediction) | 72/72 (lower 0.950) | lower ≥ 0.9 | confirmed |
| A2 F_X+F_D: cross-talk | 0/72 (upper 0.050) | upper ≤ 0.1 | PASS |
| A1 F_T+F_P: both named | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| A2 F_T+F_P: cross-talk | 0/72 (upper 0.050) | upper ≤ 0.1 | PASS |
| A3 F_T+F_D: partner named and nothing else (prediction) | 72/72 (lower 0.950) | lower ≥ 0.9 | confirmed |
| A2 F_T+F_D: cross-talk | 0/72 (upper 0.050) | upper ≤ 0.1 | PASS |
| A3 F_P+F_D: partner named and nothing else (prediction) | 72/72 (lower 0.950) | lower ≥ 0.9 | confirmed |
| A2 F_P+F_D: cross-talk | 0/72 (upper 0.050) | upper ≤ 0.1 | PASS |
| B1 library involvement detected (G1) | 41/47 (lower 0.743) | lower ≥ 0.7 | PASS |
| B3 partner still named (G1) | 51/68 (lower 0.630) | lower ≥ 0.9 | FAIL |
| B2 innocent library flagged (G2) | 4/49 (upper 0.196) | upper ≤ 0.1 | FAIL |
| B2 innocent library flagged (G3) | 10/24 (upper 0.634) | upper ≤ 0.1 | FAIL |

Part B passes only if B1, B2 (G2 and G3) and B3 all pass: **FAIL**.

## Part A: pairs in detail

joint = both component classes named; exact = those and nothing else; cross-talk = an uninjected class named; silent = no alarm. For F_D pairs only the partner can be named; exact there is a false exoneration of the library.

| pair | n | joint | exact | cross-talk | silent | harmed | unavailable | sigma_hash_plus | otel_default | otel_content | openinference | openinference_guard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F_R+F_X | 72 | 72 | 72 | 0 | 0 | 29 | 0 | 72 | 0 | 0 | 72 | 72 |
| F_R+F_T | 72 | 72 | 72 | 0 | 0 | 34 | 0 | 72 | 0 | 0 | 0 | 0 |
| F_R+F_P | 72 | 72 | 72 | 0 | 0 | 29 | 0 | 72 | 0 | 0 | 0 | 72 |
| F_R+F_D | 72 | 7 | 7 | 0 | 65 | 22 | 0 | 7 | 0 | 7 | 7 | 7 |
| F_X+F_T | 72 | 72 | 72 | 0 | 0 | 19 | 0 | 72 | 0 | 0 | 0 | 0 |
| F_X+F_P | 72 | 72 | 72 | 0 | 0 | 34 | 0 | 72 | 0 | 0 | 0 | 72 |
| F_X+F_D | 72 | 72 | 72 | 0 | 0 | 14 | 0 | 72 | 0 | 0 | 72 | 72 |
| F_T+F_P | 72 | 72 | 72 | 0 | 0 | 44 | 0 | 72 | 0 | 0 | 0 | 0 |
| F_T+F_D | 72 | 72 | 72 | 0 | 0 | 31 | 0 | 72 | 0 | 0 | 0 | 0 |
| F_P+F_D | 72 | 72 | 72 | 0 | 0 | 25 | 0 | 72 | 0 | 0 | 0 | 72 |

### Ground truth from the twins (F_D pairs)

library involved = the pair was harmed and the poison was a cause: the partner alone was not harmed, or the poison alone was.

| pair | n | harmed | library involved | partner needed | poison changed the decision |
|---|---|---|---|---|---|
| F_R+F_D | 72 | 22 | 22 | 1 | 36 |
| F_X+F_D | 72 | 14 | 11 | 5 | 28 |
| F_T+F_D | 72 | 31 | 30 | 16 | 46 |
| F_P+F_D | 72 | 25 | 2 | 25 | 37 |

## Single faults

| class | detected | cross-talk | harmed |
|---|---|---|---|
| F_R | 288/288 | 0 | 37 |
| F_X | 288/288 | 0 | 31 |
| F_T | 288/288 | 0 | 15 |
| F_P | 288/288 | 0 | 172 |
| F_D | 288/288 | 0 | 52 |

## Descriptive arms

- Rug pull: named F_T and nothing else in 36/36; F_X also raised in 0.
- Lying filter: 23 runs released a violation; F_P named in 23 of them, 0 without y_class.
- Forged witness: F_P named in 36/36.
- Coherent liar (recorder compromised): any alarm in 13/36. By construction; a sanity check, not a result.

## Part B: replay

| group | n | verdicts | library flagged | replays |
|---|---|---|---|---|
| G1 harmed F_D pairs | 68 | library 31, library_joint 11, partner 23, unexplained 3 | 42 | 866 |
| G2 partner alone (library innocent) | 49 | library_joint 4, partner 45 | 4 | 751 |
| G3 plain model errors | 24 | library 10, unexplained 14 | 10 | 374 |

G1 disputes where the twins say the library was not involved: 21; flagged anyway: 1.

## Ablation of sigma_r8

Component-fault runs (singles and pairs) where every injected component class was named, with each element removed.

| element | detected | drop |
|---|---|---|
| t_calls_h | 727/1872 | 1080 |
| x_hash | 792/1872 | 1015 |
| z_hashes | 792/1872 | 1015 |
| c_hash | 1231/1872 | 576 |
| p_witness | 1231/1872 | 576 |
| t_attest | 1231/1872 | 576 |
| m | 1807/1872 | 0 |
| t_desc_hash | 1807/1872 | 0 |
| t_id | 1807/1872 | 0 |
| theta | 1807/1872 | 0 |
| y_class | 1807/1872 | 0 |
| y_hash | 1807/1872 | 0 |
| z_ranks | 1807/1872 | 0 |

## Record size (bytes, binary hashes)

| runs | n | median | p95 | max |
|---|---|---|---|---|
| all | 3168 | 871 | 889 | 904 |
| tool_runs | 2294 | 874 | 890 | 904 |
| no_tool_runs | 874 | 632 | 635 | 636 |