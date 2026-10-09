# Judge error epsilon_delta: each scorer against human labels

Labelled items: 299 (0 marked unclear, excluded). Second annotator: Cohen's kappa 0.877; 18 disagreements excluded pending adjudication.

error = P(scorer != human). FP = scorer says correct, human says not. FN = the reverse. Upper = one-sided 97.5% Clopper-Pearson. v8 budget: epsilon_delta <= 0.02.

## Answer format: short (n = 279)

| scorer | error | upper bound | FP | FN | kappa vs human | within budget |
|---|---|---|---|---|---|---|
| substring | 29/279 (0.104) | 0.146 | 1 | 28 | 0.794 | no |
| strict | 28/279 (0.100) | 0.142 | 0 | 28 | 0.801 | no |
| f1 | 11/279 (0.039) | 0.069 | 3 | 8 | 0.920 | no |
| em | 32/279 (0.115) | 0.158 | 0 | 32 | 0.774 | no |
| f1_guarded | 7/279 (0.025) | 0.051 | 0 | 7 | 0.949 | no |

## Answer format: all (n = 279)

| scorer | error | upper bound | FP | FN | kappa vs human | within budget |
|---|---|---|---|---|---|---|
| substring | 29/279 (0.104) | 0.146 | 1 | 28 | 0.794 | no |
| strict | 28/279 (0.100) | 0.142 | 0 | 28 | 0.801 | no |
| f1 | 11/279 (0.039) | 0.069 | 3 | 8 | 0.920 | no |
| em | 32/279 (0.115) | 0.158 | 0 | 32 | 0.774 | no |
| f1_guarded | 7/279 (0.025) | 0.051 | 0 | 7 | 0.949 | no |

### By stratum (all formats)

| stratum | n | substring | strict | f1 | em | f1_guarded |
|---|---|---|---|---|---|---|
| benign | 116 | 13 | 13 | 1 | 17 | 2 |
| fault | 110 | 11 | 10 | 6 | 10 | 2 |
| stress | 53 | 5 | 5 | 4 | 5 | 3 |

**Lowest error: scorer `f1_guarded` with answer format `short`, error 0.025, upper bound 0.051. Use this pair in the confirmatory run, and put the upper bound into the composition bound as epsilon_delta.**

Items the chosen scorer gets wrong (read these before trusting it):

- J0267 [stress] gold `KKR & Co`; human 1; output: 'ANSWER: Kohlberg Kravis Roberts.'
- J0162 [benign] gold `230`; human 1; output: 'ANSWER: More than 230.'
- J0278 [stress] gold `KKR & Co`; human 1; output: 'ANSWER: Kohlberg Kravis Roberts.'
- J0064 [fault] gold `International Boxing Hall of Fame`; human 1; output: 'ANSWER: IBF'
- J0216 [benign] gold `KKR & Co`; human 1; output: 'ANSWER: Kohlberg Kravis Roberts.'
- J0273 [stress] gold `seven`; human 1; output: 'ANSWER: 7'
- J0085 [fault] gold `National Broadcasting Company`; human 1; output: 'ANSWER: NBC'

Annotator disagreements to adjudicate: J0090, J0223, J0109, J0002, J0116, J0058, J0021, J0296, J0063, J0104, J0040, J0284, J0275, J0242, J0228, J0260, J0151, J0287