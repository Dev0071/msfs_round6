# Round 8: two faults in one decision

Candidate record: `sigma_r8`. Bounds: one-sided 97.5% Clopper-Pearson. Config: backend=llama3.1:8b, corpus=hotpotqa, scorer=f1_guarded, answer_format=short, temperature=0.0, seed=20261116, pairs=F_X+F_D, n=72, n_extra=36, restricted_frac=0.35, restricted_cap=200, examples=1398, cap_g12=18, cap_g3=4, budget=24, encoder=BAAI/bge-base-en-v1.5.

## Pass and fail

| test | result | bar | verdict |
|---|---|---|---|
| clean runs raise no alarm | 0/72 alarms (upper 0.050) | upper ≤ 0.05 | PASS |
| single F_X: detected | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| single F_D: no component blamed | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| A3 F_X+F_D: partner named and nothing else (prediction) | 72/72 (lower 0.950) | lower ≥ 0.9 | confirmed |
| A2 F_X+F_D: cross-talk | 0/72 (upper 0.050) | upper ≤ 0.1 | PASS |
| B1 library involvement detected (G1) | 8/11 (lower 0.390) | lower ≥ 0.7 | FAIL |
| B3 partner still named (G1) | 14/14 (lower 0.768) | lower ≥ 0.9 | FAIL |
| B2 innocent library flagged (G2) | 0/15 (upper 0.218) | upper ≤ 0.1 | FAIL |
| B2 innocent library flagged (G3) | 2/4 (upper 0.932) | upper ≤ 0.1 | FAIL |

Part B passes only if B1, B2 (G2 and G3) and B3 all pass: **FAIL**.

## Part A: pairs in detail

joint = both component classes named; exact = those and nothing else; cross-talk = an uninjected class named; silent = no alarm. For F_D pairs only the partner can be named; exact there is a false exoneration of the library.

| pair | n | joint | exact | cross-talk | silent | harmed | unavailable | sigma_hash_plus | otel_default | otel_content | openinference | openinference_guard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F_X+F_D | 72 | 72 | 72 | 0 | 0 | 14 | 0 | 72 | 0 | 0 | 72 | 72 |

### Ground truth from the twins (F_D pairs)

library involved = the pair was harmed and the poison was a cause: the partner alone was not harmed, or the poison alone was.

| pair | n | harmed | library involved | partner needed | poison changed the decision |
|---|---|---|---|---|---|
| F_X+F_D | 72 | 14 | 11 | 5 | 28 |

## Single faults

| class | detected | cross-talk | harmed |
|---|---|---|---|
| F_X | 72/72 | 0 | 15 |
| F_D | 72/72 | 0 | 15 |

## Part B: replay

| group | n | verdicts | library flagged | replays |
|---|---|---|---|---|
| G1 harmed F_D pairs | 14 | library 8, partner 5, unexplained 1 | 8 | 103 |
| G2 partner alone (library innocent) | 15 | partner 15 | 0 | 15 |
| G3 plain model errors | 4 | library 2, unexplained 2 | 2 | 57 |

G1 disputes where the twins say the library was not involved: 3; flagged anyway: 0.

## Ablation of sigma_r8

Component-fault runs (singles and pairs) where every injected component class was named, with each element removed.

| element | detected | drop |
|---|---|---|
| c_hash | 0/144 | 144 |
| t_calls_h | 0/144 | 144 |
| x_hash | 0/144 | 144 |
| z_hashes | 0/144 | 144 |
| m | 144/144 | 0 |
| p_witness | 144/144 | 0 |
| t_attest | 144/144 | 0 |
| t_desc_hash | 144/144 | 0 |
| t_id | 144/144 | 0 |
| theta | 144/144 | 0 |
| y_class | 144/144 | 0 |
| y_hash | 144/144 | 0 |
| z_ranks | 144/144 | 0 |

## Record size (bytes, binary hashes)

| runs | n | median | p95 | max |
|---|---|---|---|---|
| all | 288 | 867 | 883 | 894 |
| tool_runs | 160 | 873 | 890 | 894 |
| no_tool_runs | 128 | 632 | 632 | 632 |