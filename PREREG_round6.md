# Pre-registration: round 6 (responsibility, epsilon_int, epsilon_delta)

Written 2026-10-07, before any run of these three experiments on a language
model. Commit this file before running, and keep the commit hash. Each
experiment's verdict is decided by the rules below. If a rule changes after
data exists, both versions are reported, and the change is labelled.

## Why these three

Two v8 claims rest on nothing measured:

- §5, the responsibility score R_i, and its proxy assumption A1. In the
  pilots, removal on the production model found the planted input 6/16 times,
  against a random baseline of 0.53, and the proxy reproduced 1 of 16 outputs.
- §6.2, the composition bound of 0.829. It was built from an asserted
  epsilon_int, an assumed epsilon_delta, and an epsilon taken from pilots only.

## Experiment R: responsibility (exp_responsibility.py)

**Question.** On a disputed decision caused by planted passages, does the
Shapley value of each recorded passage rank a planted one first? Does a proxy
model give the same answer?

**Explanation registered in advance for the pilot failure.** Leave-one-out
cannot see a cause that is duplicated. At dose 3 and 5, removing one planted
passage leaves the others in place, so every passage scores zero. If this
explanation is right, Shapley hits where leave-one-out abstains, on the same
runs.

**Design.** HotpotQA, answer passage in the clean top 4, passages only.
Attacks: ingested poisoning at dose 3 and 5, and an injection in one passage,
in rotation. Short answer format, `strict` scorer, temperature 0. A dispute is
a run whose clean twin was correct and whose attacked run was not. For each
dispute, all 16 coalitions are run on the production model (llama3.1:8b) and
on the proxy (llama3.2:3b). Target: 60 disputes, with at most 600 attack runs.

**Scored set.** Mixed disputes only: at least one planted and at least one
genuine passage in the record. Disputes where every recorded passage is
planted, or none is, are reported and not scored.

**Rules.**

| test | passes if |
|---|---|
| R1: Shapley on the production model | one-sided 97.5% CP lower bound of the hit rate > mean random baseline |
| R2: the redundancy explanation | on dose-3 and dose-5 mixed disputes, Shapley hits > leave-one-out hits (reported as counts; descriptive, not a test) |
| R3: proxy, A1 | argmax agreement CP lower bound >= 0.9 (v8 §5.4's bar). Below 36 mixed disputes the test cannot pass, and it is reported as underpowered |

**What follows.**

- R1 and R3 pass: keep §5, with the measured proxy agreement as ε_proxy.
- R1 passes and R3 fails: §5 stays as an auditor-side method that needs the
  production model (or its provider's cooperation). The proxy claim is
  removed.
- R1 fails: §5 moves to future work, and the title drops "and
  Responsibility".

**Known deviations from v8 §5.4.** Temperature 0 and one sample per
coalition, instead of 20 samples per coalition at the production temperature.
Passages only, without the tool.

## Experiment I: epsilon_int (exp_integrity.py)

**Question.** Does the integrity layer detect tampering after sealing, and
where exactly does it stop?

**Design.** Six of v8's seven clauses are built (WF, CHAIN, AUTH with
forward-secure key evolution, FRESH with anchoring every 16 entries, BIND,
CLASS). ATTEST is not built. 15 in-model attacks and 3 out-of-model attacks
are run, 500 trials each, on logs of 70 entries.

**Rule.** Every in-model attack is detected on every trial. epsilon_int is
the one-sided 97.5% CP upper bound on misses. The out-of-model attacks are
reported as the boundary, and none of them counts toward epsilon_int.

**Result already obtained (no model is involved).** 0 misses in 7,500
in-model attacks, upper bound 4.9e-4. All three out-of-model attacks went
undetected on every trial (3 × 500), as expected. BIND fires on untampered
records whenever a genuine F_X fault or a rug-pull F_T fault is present; see
the report.

## Experiment J: epsilon_delta (exp_judge.py)

**Question.** How often does each outcome scorer disagree with a human?

**Design.** 300 outputs. Strata as in v8 E3: 40% fault-affected, 40% benign,
20% adversarial stress. Half use the free answer format and half the short
one. Labelling is blind: the sheet shows the question, the gold answer and
the output, and nothing else.

**Rule.** The scorer and format with the lowest error become the outcome
variable of the confirmatory run, chosen before any confirmatory attribution
result is seen. Its CP upper bound is epsilon_delta.

**Sample size.** v8's budget of epsilon_delta <= 0.02 needs about 183 items
in one format with zero errors, or about 279 with one error. This round
chooses the scorer. A second batch of about 300 items in the chosen format
then certifies it.

**Second annotator.** Required by v8 E3 for the reported figure. A
single-annotator result is labelled as preliminary.

## The composition bound (compose_bound.py)

The bound is reported only when all three terms are measured, and epsilon
comes from the confirmatory run, not from pilots. Until then, the paper
gives no number.
