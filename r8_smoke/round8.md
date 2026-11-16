# Round 8: two faults in one decision

Candidate record: `sigma_r8`. Bounds: one-sided 97.5% Clopper-Pearson. Config: backend=llama3.1:8b, corpus=hotpotqa, scorer=f1_guarded, answer_format=short, temperature=0.0, seed=20261113, pairs=F_R+F_D,F_X+F_T,extra, n=3, n_extra=2, restricted_frac=0.35, restricted_cap=200, examples=1398, cap_g12=18, cap_g3=8, budget=40, encoder=BAAI/bge-base-en-v1.5.

## Pass and fail

| test | result | bar | verdict |
|---|---|---|---|
| clean runs raise no alarm | 0/6 alarms (upper 0.459) | upper ≤ 0.05 | FAIL |
| single F_R: detected | 3/3 (lower 0.292) | lower ≥ 0.9 | FAIL |
| single F_X: detected | 3/3 (lower 0.292) | lower ≥ 0.9 | FAIL |
| single F_T: detected | 3/3 (lower 0.292) | lower ≥ 0.9 | FAIL |
| single F_D: no component blamed | 3/3 (lower 0.292) | lower ≥ 0.9 | FAIL |
| A3 F_R+F_D: partner named and nothing else (prediction) | 0/3 (lower 0.000) | lower ≥ 0.9 | not confirmed |
| A2 F_R+F_D: cross-talk | 0/3 (upper 0.708) | upper ≤ 0.1 | FAIL |
| A1 F_X+F_T: both named | 3/3 (lower 0.292) | lower ≥ 0.9 | FAIL |
| A2 F_X+F_T: cross-talk | 0/3 (upper 0.708) | upper ≤ 0.1 | FAIL |
| B2 innocent library flagged (G3) | 1/2 (upper 0.987) | upper ≤ 0.1 | FAIL |

Part B passes only if B1, B2 (G2 and G3) and B3 all pass: **FAIL**.

## Part A: pairs in detail

joint = both component classes named; exact = those and nothing else; cross-talk = an uninjected class named; silent = no alarm. For F_D pairs only the partner can be named; exact there is a false exoneration of the library.

| pair | n | joint | exact | cross-talk | silent | harmed | unavailable | sigma_hash_plus | otel_default | otel_content | openinference | openinference_guard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F_R+F_D | 3 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F_X+F_T | 3 | 3 | 3 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 |

### Ground truth from the twins (F_D pairs)

library involved = the pair was harmed and the poison was a cause: the partner alone was not harmed, or the poison alone was.

| pair | n | harmed | library involved | partner needed | poison changed the decision |
|---|---|---|---|---|---|
| F_R+F_D | 3 | 0 | 0 | 0 | 1 |

## Single faults

| class | detected | cross-talk | harmed |
|---|---|---|---|
| F_R | 3/3 | 0 | 0 |
| F_X | 3/3 | 0 | 0 |
| F_T | 3/3 | 0 | 0 |
| F_D | 3/3 | 0 | 0 |

## Descriptive arms

- Rug pull: named F_T and nothing else in 2/2; F_X also raised in 0.
- Lying filter: 1 runs released a violation; F_P named in 1 of them, 0 without y_class.
- Forged witness: F_P named in 2/2.
- Coherent liar (recorder compromised): any alarm in 0/2. By construction; a sanity check, not a result.

## Part B: replay

| group | n | verdicts | library flagged | replays |
|---|---|---|---|---|
| G3 plain model errors | 2 | library 1, unexplained 1 | 1 | 43 |

## Ablation of sigma_r8

Component-fault runs (singles and pairs) where every injected component class was named, with each element removed.

| element | detected | drop |
|---|---|---|
| t_calls_h | 3/15 | 9 |
| x_hash | 3/15 | 9 |
| z_hashes | 3/15 | 9 |
| c_hash | 6/15 | 6 |
| t_attest | 6/15 | 6 |
| m | 12/15 | 0 |
| p_witness | 12/15 | 0 |
| t_desc_hash | 12/15 | 0 |
| t_id | 12/15 | 0 |
| theta | 12/15 | 0 |
| y_class | 12/15 | 0 |
| y_hash | 12/15 | 0 |
| z_ranks | 12/15 | 0 |

## Record size (bytes, binary hashes)

| runs | n | median | p95 | max |
|---|---|---|---|---|
| all | 40 | 867 | 885 | 885 |
| tool_runs | 22 | 870 | 885 | 885 |
| no_tool_runs | 18 | 632 | 636 | 636 |