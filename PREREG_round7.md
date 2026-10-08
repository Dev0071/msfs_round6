# Pre-registration: round 7 (scorer amendment, retriever, narrower responsibility claim, proxy family)

Written 2026-10-08 after the round 6 results and before any round 7 run.
Commit before running. Everything here was decided with the round 6 data in
view, which is why each item is tested on fresh data.

## J2: certify the scorer (exp_judge.py, batch 2)

**Chosen by the round 6 rule:** F1 with the short answer format (7/150 errors,
upper bound 0.094, single annotator).

**Amendment, frozen now:** `f1_guarded` = F1 plus three guards written to
address the round 6 misses: a digit veto (numbers in the gold must appear in
the answer, and no others), a hyphen fix (dashes are spaces, not deleted),
and a length guard (an answer more than twice the gold's length is a hedge).
On the round 6 items it would fix 5 of F1's 7 misses; that figure is in-sample
and is not a result.

**Design.** 300 new outputs, short format only, new seed, the retriever chosen
in R0 below. Two annotators, each blind to the other, labels committed before
scoring. Disagreements adjudicated by discussion and recorded.

**Rules.**
- The reported scorer is `f1_guarded` if its error on batch 2 is at or below
  F1's; otherwise F1. Decided by batch 2 alone.
- epsilon_delta = the one-sided 97.5% CP upper bound of the reported scorer's
  error on batch 2 against the adjudicated labels. Within v8's budget if
  <= 0.02; otherwise the measured value replaces the budget in the
  composition bound.
- Cohen's kappa between annotators is reported as the ceiling.

## R0: the retrieval gate (msfs/real_corpus.py, MSFS_ENCODER)

MiniLM gave gold@4 = 0.60. Encoders are tried in this order, and the first to
reach gold@4 >= 0.80 on the selftest is used for every round 7 run:
1. BAAI/bge-base-en-v1.5
2. intfloat/e5-base-v2
3. none passes: keep MiniLM, keep the answerable-only restriction, and state
   both in the paper as a limitation.

The gate result for each encoder tried is recorded, including the failures.

## R1' and R1'': the narrower responsibility claim (exp_responsibility.py)

Round 6 R1 failed and that stands. Afterwards, all 9 Shapley abstentions were
found to be disputes where no coalition of the recorded passages gave a
correct answer. The claim below is the post-hoc reading, stated before fresh
data.

**Claim.** Removal-based attribution is defined only when some subset of the
recorded inputs yields a correct outcome. On those disputes it finds the
planted input; on the others it abstains.

**Design.** As round 6 (dose 3, dose 5, injection; 2^4 coalitions; production
model llama3.1:8b at temperature 0) with: a new seed, the R0 retriever, the
F1 scorer (the round 6 choice; `f1_guarded` is not yet certified), and two
proxies run on the same disputes: llama3.2:3b (smaller, same family) and
qwen2.5:7b (same size class, different family). Target 60 disputes, at most
600 attack runs.

**Rules.**
| test | passes if |
|---|---|
| R1': attributable mixed disputes | one-sided 97.5% CP lower bound of Shapley's hit rate > the mean random baseline on those disputes |
| R1'': non-attributable mixed disputes | Shapley blames a genuine passage in 0 of them |
| R3a: llama3.2:3b proxy | argmax agreement lower bound >= 0.9 (v8's bar), on attributable disputes |
| R3b: qwen2.5:7b proxy | same bar |

**What follows.**
- R1' and R1'' pass: a narrowed §5 may return, as "attribution with an
  identifiability condition", with Frigui's agreement. The round 6 failure of
  the original claim is still reported.
- Either fails: §5 stays in future work.
- R3b passes and R3a fails: proxy failure was about size, not model
  difference; A1 may hold for size-matched proxies. Both fail: A1 is removed.
  R3b is exploratory in the sense that it was added after round 6, but its
  rule is fixed here.

## Threats carried forward

- Same author for attacks, detectors and auditor.
- One production model (llama3.1:8b, Q4_K_M), which is also the attacker.
- Temperature 0 and one sample per coalition.
