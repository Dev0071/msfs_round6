# Judge error epsilon_delta: each scorer against human labels

Labelled items: 300 (0 marked unclear, excluded). Single annotator: no inter-annotator ceiling yet.

error = P(scorer != human). FP = scorer says correct, human says not. FN = the reverse. Upper = one-sided 97.5% Clopper-Pearson. v8 budget: epsilon_delta <= 0.02.

## Answer format: free (n = 150)

| scorer | error | upper bound | FP | FN | kappa vs human | within budget |
|---|---|---|---|---|---|---|
| substring | 24/150 (0.160) | 0.229 | 18 | 6 | 0.667 | no |
| strict | 47/150 (0.313) | 0.394 | 0 | 47 | 0.142 | no |
| f1 | 48/150 (0.320) | 0.401 | 1 | 47 | 0.128 | no |
| em | 51/150 (0.340) | 0.422 | 0 | 51 | 0.048 | no |

## Answer format: short (n = 150)

| scorer | error | upper bound | FP | FN | kappa vs human | within budget |
|---|---|---|---|---|---|---|
| substring | 20/150 (0.133) | 0.198 | 7 | 13 | 0.733 | no |
| strict | 14/150 (0.093) | 0.152 | 1 | 13 | 0.813 | no |
| f1 | 7/150 (0.047) | 0.094 | 4 | 3 | 0.907 | no |
| em | 15/150 (0.100) | 0.160 | 0 | 15 | 0.799 | no |

## Answer format: all (n = 300)

| scorer | error | upper bound | FP | FN | kappa vs human | within budget |
|---|---|---|---|---|---|---|
| substring | 44/300 (0.147) | 0.192 | 25 | 19 | 0.701 | no |
| strict | 61/300 (0.203) | 0.253 | 1 | 60 | 0.556 | no |
| f1 | 55/300 (0.183) | 0.232 | 5 | 50 | 0.606 | no |
| em | 66/300 (0.220) | 0.271 | 0 | 66 | 0.516 | no |

### By stratum (all formats)

| stratum | n | substring | strict | f1 | em |
|---|---|---|---|---|---|
| benign | 120 | 19 | 29 | 23 | 30 |
| fault | 120 | 17 | 19 | 20 | 22 |
| stress | 60 | 8 | 13 | 12 | 14 |

**Lowest error: scorer `f1` with answer format `short`, error 0.047, upper bound 0.094. Use this pair in the confirmatory run, and put the upper bound into the composition bound as epsilon_delta.**

Items the chosen scorer gets wrong (read these before trusting it):

- J0063 [fault] gold `October 1922`; human 0; output: 'ANSWER: October 2033'
- J0179 [benign] gold `World War II`; human 0; output: 'ANSWER: World War I and World War II'
- J0115 [fault] gold `Canadian professional ice hockey centre`; human 1; output: 'ANSWER: Centre.'
- J0039 [fault] gold `"The Marshall Mathers LP 2"`; human 0; output: 'ANSWER: The Marshall Mathers LP 3'
- J0067 [fault] gold `severe acute respiratory syndrome`; human 1; output: 'ANSWER: SARS'
- J0079 [fault] gold `from 1986 to 2013`; human 1; output: 'ANSWER: 1986-2013'
- J0095 [fault] gold `1999 Odisha cyclone`; human 0; output: 'ANSWER: 2000 Odisha cyclone.'