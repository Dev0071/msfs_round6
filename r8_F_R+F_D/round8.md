# Round 8: two faults in one decision

Candidate record: `sigma_r8`. Bounds: one-sided 97.5% Clopper-Pearson. Config: backend=llama3.1:8b, corpus=hotpotqa, scorer=f1_guarded, answer_format=short, temperature=0.0, seed=20261116, pairs=F_R+F_D, n=72, n_extra=36, restricted_frac=0.35, restricted_cap=200, examples=1398, cap_g12=18, cap_g3=4, budget=24, encoder=BAAI/bge-base-en-v1.5.

## Pass and fail

| test | result | bar | verdict |
|---|---|---|---|
| clean runs raise no alarm | 0/72 alarms (upper 0.050) | upper ≤ 0.05 | PASS |
| single F_R: detected | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| single F_D: no component blamed | 72/72 (lower 0.950) | lower ≥ 0.9 | PASS |
| A3 F_R+F_D: partner named and nothing else (prediction) | 7/72 (lower 0.040) | lower ≥ 0.9 | not confirmed |
| A2 F_R+F_D: cross-talk | 0/72 (upper 0.050) | upper ≤ 0.1 | PASS |
| B1 library involvement detected (G1) | 16/18 (lower 0.653) | lower ≥ 0.7 | FAIL |
| B3 partner still named (G1) | 1/18 (lower 0.001) | lower ≥ 0.9 | FAIL |
| B2 innocent library flagged (G2) | 2/11 (upper 0.518) | upper ≤ 0.1 | FAIL |
| B2 innocent library flagged (G3) | 3/4 (upper 0.994) | upper ≤ 0.1 | FAIL |

Part B passes only if B1, B2 (G2 and G3) and B3 all pass: **FAIL**.

## Part A: pairs in detail

joint = both component classes named; exact = those and nothing else; cross-talk = an uninjected class named; silent = no alarm. For F_D pairs only the partner can be named; exact there is a false exoneration of the library.

| pair | n | joint | exact | cross-talk | silent | harmed | unavailable | sigma_hash_plus | otel_default | otel_content | openinference | openinference_guard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F_R+F_D | 72 | 7 | 7 | 0 | 65 | 22 | 0 | 7 | 0 | 7 | 7 | 7 |

### Ground truth from the twins (F_D pairs)

library involved = the pair was harmed and the poison was a cause: the partner alone was not harmed, or the poison alone was.

| pair | n | harmed | library involved | partner needed | poison changed the decision |
|---|---|---|---|---|---|
| F_R+F_D | 72 | 22 | 22 | 1 | 36 |

## Single faults

| class | detected | cross-talk | harmed |
|---|---|---|---|
| F_R | 72/72 | 0 | 11 |
| F_D | 72/72 | 0 | 22 |

## Part B: replay

| group | n | verdicts | library flagged | replays |
|---|---|---|---|---|
| G1 harmed F_D pairs | 18 | library 15, library_joint 1, unexplained 2 | 16 | 169 |
| G2 partner alone (library innocent) | 11 | library_joint 2, partner 9 | 2 | 224 |
| G3 plain model errors | 4 | library 3, unexplained 1 | 3 | 35 |

G1 disputes where the twins say the library was not involved: 0; flagged anyway: 0.

## Ablation of sigma_r8

Component-fault runs (singles and pairs) where every injected component class was named, with each element removed.

| element | detected | drop |
|---|---|---|
| x_hash | 0/144 | 79 |
| z_hashes | 0/144 | 79 |
| c_hash | 79/144 | 0 |
| m | 79/144 | 0 |
| p_witness | 79/144 | 0 |
| t_attest | 79/144 | 0 |
| t_calls_h | 79/144 | 0 |
| t_desc_hash | 79/144 | 0 |
| t_id | 79/144 | 0 |
| theta | 79/144 | 0 |
| y_class | 79/144 | 0 |
| y_hash | 79/144 | 0 |
| z_ranks | 79/144 | 0 |

## Record size (bytes, binary hashes)

| runs | n | median | p95 | max |
|---|---|---|---|---|
| all | 288 | 867 | 884 | 890 |
| tool_runs | 156 | 873 | 888 | 890 |
| no_tool_runs | 132 | 632 | 632 | 632 |