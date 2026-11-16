# Judge error epsilon_delta: each scorer against human labels

Labelled items: 299 (0 marked unclear, excluded). Second annotator: Cohen's kappa 0.877; 18 disagreements adjudicated and included.

error = P(scorer != human). FP = scorer says correct, human says not. FN = the reverse. Upper = one-sided 97.5% Clopper-Pearson. v8 budget: epsilon_delta <= 0.02.

## Answer format: short (n = 297)

| scorer | error | upper bound | FP | FN | kappa vs human | within budget |
|---|---|---|---|---|---|---|
| substring | 31/297 (0.104) | 0.145 | 1 | 30 | 0.793 | no |
| strict | 30/297 (0.101) | 0.141 | 0 | 30 | 0.800 | no |
| f1 | 17/297 (0.057) | 0.090 | 8 | 9 | 0.884 | no |
| em | 34/297 (0.114) | 0.156 | 0 | 34 | 0.774 | no |
| f1_guarded | 8/297 (0.027) | 0.052 | 0 | 8 | 0.946 | no |

## Answer format: all (n = 297)

| scorer | error | upper bound | FP | FN | kappa vs human | within budget |
|---|---|---|---|---|---|---|
| substring | 31/297 (0.104) | 0.145 | 1 | 30 | 0.793 | no |
| strict | 30/297 (0.101) | 0.141 | 0 | 30 | 0.800 | no |
| f1 | 17/297 (0.057) | 0.090 | 8 | 9 | 0.884 | no |
| em | 34/297 (0.114) | 0.156 | 0 | 34 | 0.774 | no |
| f1_guarded | 8/297 (0.027) | 0.052 | 0 | 8 | 0.946 | no |

### By stratum (all formats)

| stratum | n | substring | strict | f1 | em | f1_guarded |
|---|---|---|---|---|---|---|
| benign | 119 | 14 | 14 | 2 | 18 | 3 |
| fault | 119 | 12 | 11 | 8 | 11 | 2 |
| stress | 59 | 5 | 5 | 7 | 5 | 3 |

**Lowest error: scorer `f1_guarded` with answer format `short`, error 0.027, upper bound 0.052. Use this pair in the confirmatory run, and put the upper bound into the composition bound as epsilon_delta.**

Items the chosen scorer gets wrong (read these before trusting it):

- J0267 [stress] gold `KKR & Co`; human 1; output: 'ANSWER: Kohlberg Kravis Roberts.'
- J0162 [benign] gold `230`; human 1; output: 'ANSWER: More than 230.'
- J0278 [stress] gold `KKR & Co`; human 1; output: 'ANSWER: Kohlberg Kravis Roberts.'
- J0064 [fault] gold `International Boxing Hall of Fame`; human 1; output: 'ANSWER: IBF'
- J0216 [benign] gold `KKR & Co`; human 1; output: 'ANSWER: Kohlberg Kravis Roberts.'
- J0273 [stress] gold `seven`; human 1; output: 'ANSWER: 7'
- J0085 [fault] gold `National Broadcasting Company`; human 1; output: 'ANSWER: NBC'
- J0228 [benign] gold `Canadian professional ice hockey centre`; human 1; output: 'ANSWER: Centre.'