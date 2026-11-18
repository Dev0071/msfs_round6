# Round 8: exploratory breakdowns (post hoc, not registered)

## 1. Part B by group and pair

| group | pair | n | involved (G1) | flagged | flagged when involved | verdicts | median replays | replays when flagged |
|---|---|---|---|---|---|---|---|---|
| G1 | F_P+F_D | 18 | 1 | 0 | 0 | {'partner': 18} | 24 | – |
| G1 | F_R+F_D | 18 | 18 | 16 | 16 | {'library': 15, 'library_joint': 1, 'unexplained': 2} | 7 | [2, 2, 3, 4, 4, 4, 6, 6, 7, 7, 12, 12, 12, 13, 13, 14] |
| G1 | F_T+F_D | 18 | 17 | 18 | 17 | {'library_joint': 10, 'library': 8} | 8 | [3, 3, 3, 7, 7, 7, 7, 8, 8, 8, 8, 10, 10, 13, 15, 15, 15, 15] |
| G1 | F_X+F_D | 14 | 11 | 8 | 8 | {'library': 8, 'partner': 5, 'unexplained': 1} | 6 | [2, 6, 6, 8, 12, 12, 14, 14] |
| G2 | F_P+F_D | 18 | – | 0 | – | {'partner': 18} | 24 | – |
| G2 | F_R+F_D | 11 | – | 2 | – | {'partner': 9, 'library_joint': 2} | 24 | [3, 5] |
| G2 | F_T+F_D | 5 | – | 2 | – | {'partner': 3, 'library_joint': 2} | 24 | [3, 5] |
| G2 | F_X+F_D | 15 | – | 0 | – | {'partner': 15} | 1 | – |
| G3 | F_R+F_D | 4 | – | 3 | – | {'unexplained': 1, 'library': 3} | 6 | [2, 3, 6] |
| G3 | F_R+F_T | 4 | – | 2 | – | {'library': 2, 'unexplained': 2} | 24 | [2, 4] |
| G3 | F_R+F_X | 4 | – | 2 | – | {'unexplained': 2, 'library': 2} | 24 | [3, 7] |
| G3 | F_T+F_D | 4 | – | 0 | – | {'unexplained': 4} | 24 | – |
| G3 | F_X+F_D | 4 | – | 2 | – | {'unexplained': 2, 'library': 2} | 24 | [2, 7] |
| G3 | F_X+F_T | 4 | – | 1 | – | {'library': 1, 'unexplained': 3} | 24 | [2] |

## 2. Same procedure, poison present or not

F_R+F_D disputes raise no alarm (E5), so the investigator runs exactly the search it runs on a plain model error (G3).

- F_R+F_D, no alarm, poison present: flagged 15/17 (0.88; 0.636–0.985)
- G3, nothing injected: flagged 10/24 (0.42; 0.221–0.634)
- Fisher exact, one-sided: odds ratio 10.5, p = 0.0028

What a flag is worth for one dispute, at these rates (precision = share of flags that are real poisoning):

- poisoning in 1% of disputes: precision 0.02
- poisoning in 5% of disputes: precision 0.10
- poisoning in 20% of disputes: precision 0.35
- poisoning in 50% of disputes: precision 0.68

## 3. How the flag was reached

| group | removed 1 | removed 2 | removed 3+ | flags reached after replay 12 |
|---|---|---|---|---|
| G1 | 10 | 17 | 15 | 10/42 |
| G2 | 4 | 0 | 0 | 0/4 |
| G3 | 7 | 3 | 0 | 0/10 |

## 4. B3 (partner still named) with and without F_R+F_D

- As registered (all G1): 51/68 (0.75; 0.630–0.847)
- Without F_R+F_D (predicted silent, E5): 50/50 (1.00; 0.929–1.000)
  - F_P+F_D: 18/18
  - F_R+F_D: 1/18
  - F_T+F_D: 18/18
  - F_X+F_D: 14/14
- Replay never changes the record's alarms, so B3 as computed measures the record, not the replay.

## 5. Was the joint test reachable?

- F_P+F_D: partner repair explains 18/18; joint test runnable 18; library involved 1; replays 432
- F_R+F_D: partner repair explains 1/18; joint test runnable 1; library involved 18; replays 169
- F_T+F_D: partner repair explains 10/18; joint test runnable 10; library involved 17; replays 162
- F_X+F_D: partner repair explains 5/14; joint test runnable 0; library involved 11; replays 103

## 6. Elements needed by the descriptive arms

The registered ablation covers singles and pairs only. Here: each element removed, on the descriptive arms.

| element | rug_pull | lying_filter | forged_witness |
|---|---|---|---|
| c_hash | 36/36 | 23/23 | 36/36 |
| m | 36/36 | 23/23 | 36/36 |
| p_witness | 36/36 | 0/23 (−23) | 0/36 (−36) |
| t_attest | 36/36 | 23/23 | 36/36 |
| t_calls_h | 36/36 | 23/23 | 36/36 |
| t_desc_hash | 0/36 (−36) | 23/23 | 36/36 |
| t_id | 36/36 | 23/23 | 36/36 |
| theta | 36/36 | 23/23 | 36/36 |
| x_hash | 36/36 | 23/23 | 36/36 |
| y_class | 36/36 | 0/23 (−23) | 36/36 |
| y_hash | 36/36 | 23/23 | 36/36 |
| z_hashes | 36/36 | 23/23 | 36/36 |
| z_ranks | 36/36 | 23/23 | 36/36 |

## 7. Coherent liar alarms (E9)

- any alarm: 13/36
- classes: {(): 23, ('F_R',): 13}
- evidence on alarmed runs (first 5): [['F_R: offline re-retrieval over the archived snapshot places a passage at rank 1 that is absent from the recorded retrieval set'], ['F_R: offline re-retrieval over the archived snapshot places a passage at rank 1 that is absent from the recorded retrieval set'], ['F_R: offline re-retrieval over the archived snapshot places a passage at rank 1 that is absent from the recorded retrieval set'], ['F_R: offline re-retrieval over the archived snapshot places a passage at rank 1 that is absent from the recorded retrieval set'], ['F_R: offline re-retrieval over the archived snapshot places a passage at rank 1 that is absent from the recorded retrieval set']]
