# Round 8: two faults in one decision

Candidate record: `sigma_r8`. Bounds: one-sided 97.5% Clopper-Pearson. Config: backend=llama3.1:8b, corpus=hotpotqa, scorer=f1_guarded, answer_format=short, temperature=0.0, seed=20261116, pairs=extra, n=72, n_extra=36, restricted_frac=0.35, restricted_cap=200, examples=1398, cap_g12=18, cap_g3=4, budget=24, encoder=BAAI/bge-base-en-v1.5.

## Pass and fail

| test | result | bar | verdict |
|---|---|---|---|
| clean runs raise no alarm | 0/0 alarms (upper -) | upper ≤ 0.05 | FAIL |

## Part A: pairs in detail

joint = both component classes named; exact = those and nothing else; cross-talk = an uninjected class named; silent = no alarm. For F_D pairs only the partner can be named; exact there is a false exoneration of the library.

| pair | n | joint | exact | cross-talk | silent | harmed | unavailable | sigma_hash_plus | otel_default | otel_content | openinference | openinference_guard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

## Single faults

| class | detected | cross-talk | harmed |
|---|---|---|---|

## Descriptive arms

- Rug pull: named F_T and nothing else in 36/36; F_X also raised in 0.
- Lying filter: 23 runs released a violation; F_P named in 23 of them, 0 without y_class.
- Forged witness: F_P named in 36/36.
- Coherent liar (recorder compromised): any alarm in 13/36. By construction; a sanity check, not a result.

## Ablation of sigma_r8

Component-fault runs (singles and pairs) where every injected component class was named, with each element removed.

| element | detected | drop |
|---|---|---|
| c_hash | 0/0 | 0 |
| m | 0/0 | 0 |
| p_witness | 0/0 | 0 |
| t_attest | 0/0 | 0 |
| t_calls_h | 0/0 | 0 |
| t_desc_hash | 0/0 | 0 |
| t_id | 0/0 | 0 |
| theta | 0/0 | 0 |
| x_hash | 0/0 | 0 |
| y_class | 0/0 | 0 |
| y_hash | 0/0 | 0 |
| z_hashes | 0/0 | 0 |
| z_ranks | 0/0 | 0 |

## Record size (bytes, binary hashes)

| runs | n | median | p95 | max |
|---|---|---|---|---|
| all | 288 | 871 | 888 | 899 |
| tool_runs | 214 | 873 | 890 | 899 |
| no_tool_runs | 74 | 632 | 635 | 636 |