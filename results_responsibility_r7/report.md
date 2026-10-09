# Responsibility: does R_i find the planted input?

Backend llama3.1:8b, scorer f1, answer format short, temperature 0.0, top k 4. 

## Harm per attack

| attack | runs | disputes (harmed) |
|---|---|---|
| poison_ingested_d3 | 48 | 17 |
| poison_ingested_d5 | 47 | 28 |
| injection_in_passage | 47 | 15 |

Disputes: 60; reproduced at temperature 0 from the recorded passages: 60. Of those: mixed (planted and genuine inputs both recorded) 37, all recorded inputs planted 23, none planted 0. Only mixed disputes can separate a method from guessing; the others are reported, not scored.

## Attribution on mixed disputes

hit = every top-scoring input was planted; wrong = a genuine input is among the top; abstain = no input has a positive score. Baseline = expected hit rate of naming one recorded input at random. Lower bound = one-sided 97.5% Clopper-Pearson on the hit rate.

| method | attack | n | hit | wrong | abstain | hit rate (lower bound) | baseline |
|---|---|---|---|---|---|---|---|
| shapley | injection_in_passage | 15 | 9 | 3 | 3 | 0.60 (0.32) | 0.25 |
| shapley | poison_ingested_d3 | 17 | 6 | 3 | 8 | 0.35 (0.14) | 0.74 |
| shapley | poison_ingested_d5 | 5 | 1 | 1 | 3 | 0.20 (0.01) | 0.75 |
| shapley | **all** | 37 | 16 | 7 | 14 | 0.43 (0.27) | 0.54 |
| loo | injection_in_passage | 15 | 4 | 7 | 4 | 0.27 (0.08) | 0.25 |
| loo | poison_ingested_d3 | 17 | 3 | 2 | 12 | 0.18 (0.04) | 0.74 |
| loo | poison_ingested_d5 | 5 | 0 | 0 | 5 | 0.00 (0.00) | 0.75 |
| loo | **all** | 37 | 7 | 9 | 21 | 0.19 (0.08) | 0.54 |

Repair: removing every input with positive Shapley value restored a correct answer in 21/23 mixed disputes.

**Pre-registered test (Shapley, production model): lower bound 0.27 vs baseline 0.54 -> FAIL.**

## Attributable vs non-attributable disputes (round 7 rules R1', R1'')

attributable = at least one coalition of the recorded passages gives a correct answer. R1': on attributable disputes, Shapley's hit-rate lower bound beats the random baseline. R1'': on non-attributable disputes, Shapley never blames a genuine passage (abstains).

| set | n | hit | wrong | abstain | hit rate (lower bound) | baseline | rule |
|---|---|---|---|---|---|---|---|
| attributable | 23 | 16 | 7 | 0 | 0.70 (0.47) | 0.49 | R1': FAIL |
| non-attributable | 14 | 0 | 0 | 14 | 0.00 (0.00) | 0.62 | R1'': PASS |

## Proxy (Assumption A1)

coalition agreement = share of the 2^k interventions on which the proxy reaches the same outcome as the production model (A1 tested directly). argmax agreement = the proxy blames the same inputs. v8 registered bar: argmax agreement >= 0.9. Scored on attributable mixed disputes (round 7 rule); all mixed disputes in brackets.

| proxy | attributable disputes | mean coalition agreement | all coalitions agree | argmax agreement (lower bound) | proxy hit | verdict |
|---|---|---|---|---|---|---|
| llama3.2:3b | 23 | 0.77 | 1/23 | 6/23 (0.10) [20/37] | 10/23 | FAIL |
| qwen2.5:7b | 23 | 0.74 | 0/23 | 6/23 (0.10) [20/37] | 6/23 | FAIL |