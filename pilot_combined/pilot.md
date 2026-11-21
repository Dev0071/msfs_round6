# Pilot: causal and content tests on innocent and poisoned passages (exploratory)

Innocent arm: 98 disputes, 392 passages. Poison arm: 202 poisoned passages in harmed runs.

Causal test, innocent passages flagged: 47/392 (0.12; 0.09–0.16)

## Content score S1 (threshold 0.722, matched to the causal rate)

- content flags innocent: 47/392 (0.12; 0.09–0.16)
- both flag innocent (joint false alarm): 5/392 (0.01; 0.00–0.03)
- of the innocent passages the causal test flags, content also flags: 5/47 (0.11; 0.04–0.23)
- correlation phi: -0.02 (bootstrap over disputes, 95%: -0.11–0.10)
- independent would give a joint rate of 0.014

| poison form | n | causal | content | both |
|---|---|---|---|---|
| d1_I | 4 | 4/4 (1.00; 0.40–1.00) | 0/4 (0.00; 0.00–0.60) | 0/4 (0.00; 0.00–0.60) |
| d1_QI | 14 | 14/14 (1.00; 0.77–1.00) | 11/14 (0.79; 0.49–0.95) | 11/14 (0.79; 0.49–0.95) |
| d5_I | 53 | 9/53 (0.17; 0.08–0.30) | 21/53 (0.40; 0.26–0.54) | 3/53 (0.06; 0.01–0.16) |
| d5_QI | 131 | 25/131 (0.19; 0.13–0.27) | 121/131 (0.92; 0.86–0.96) | 18/131 (0.14; 0.08–0.21) |

Precision at dose 1 (share of flags that are poison), by prevalence of poisoned passages among candidates:

| prevalence | causal alone | both |
|---|---|---|
| 1% | 0.08 | 0.33 |
| 5% | 0.31 | 0.72 |
| 20% | 0.68 | 0.92 |

**Decision rule (S1):** phi ≤ 0.3: yes; joint false alarm under half the causal rate: yes; both catch ≥ 80% of dose-1 poison: no. **Not worth registering**.

## Content score S2 (threshold 0.636, matched to the causal rate)

- content flags innocent: 48/392 (0.12; 0.09–0.16)
- both flag innocent (joint false alarm): 5/392 (0.01; 0.00–0.03)
- of the innocent passages the causal test flags, content also flags: 5/47 (0.11; 0.04–0.23)
- correlation phi: -0.02 (bootstrap over disputes, 95%: -0.10–0.07)
- independent would give a joint rate of 0.015

| poison form | n | causal | content | both |
|---|---|---|---|---|
| d1_I | 4 | 4/4 (1.00; 0.40–1.00) | 3/4 (0.75; 0.19–0.99) | 3/4 (0.75; 0.19–0.99) |
| d1_QI | 14 | 14/14 (1.00; 0.77–1.00) | 14/14 (1.00; 0.77–1.00) | 14/14 (1.00; 0.77–1.00) |
| d5_I | 53 | 9/53 (0.17; 0.08–0.30) | 44/53 (0.83; 0.70–0.92) | 8/53 (0.15; 0.07–0.28) |
| d5_QI | 131 | 25/131 (0.19; 0.13–0.27) | 131/131 (1.00; 0.97–1.00) | 25/131 (0.19; 0.13–0.27) |

Precision at dose 1 (share of flags that are poison), by prevalence of poisoned passages among candidates:

| prevalence | causal alone | both |
|---|---|---|
| 1% | 0.08 | 0.43 |
| 5% | 0.31 | 0.80 |
| 20% | 0.68 | 0.95 |

**Decision rule (S2):** phi ≤ 0.3: yes; joint false alarm under half the causal rate: yes; both catch ≥ 80% of dose-1 poison: yes. **Worth registering**.

