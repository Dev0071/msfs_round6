# Pre-registration, round 8: two faults in one decision

Status: DRAFT. Not registered until the four items in section 9 are filled in, this file is committed, and its hash is recorded with a timestamp. Nothing in round 8 may be run on the real model before that, except the feasibility count and the smoke test of RUN_ROUND8.md, whose outputs are not results.

Code: `run_round8.py`, `msfs/replay.py` and the round 8 changes in `msfs/`. Where code and this document disagree, this document governs and the disagreement is reported.

## 1. Question

Dr. Fang (9 Nov 2026): if an attacker poisons the knowledge base and also breaks a component in the same decision, can the investigator tell?

- **Part A, record only.** With two faults in one execution, does each component fault trip its own witness? What does the investigator see when the library is poisoned alongside a component fault?
- **Part B, replay.** On disputed decisions, can an investigator who re-runs the production model detect that the library was involved, without flagging an innocent library?

Out of scope: which passage was poisoned (localisation); three or more faults; independent attacks (confirmatory study).

## 2. Assumptions

- **A-T:** each tool service signs every response (HMAC in the harness; public-key signatures in a deployment).
- **A-P:** the policy witness is produced and signed by a wrapper outside the filter. The wrapper observes the version the filter loaded, whether the evaluation call returned, and the rule count. It cannot see inside the evaluation.
- **A-S:** the registered prompt, policy version, tool description and tool key are fixed before the decisions they govern.
- **A-R (Part B):** the investigator can replay the production model at the recorded configuration, apply the registered policy, and re-invoke the registered tool with the recorded request.
- **A-D (Part B):** the dispute states the decision the complainant says was right. On HotpotQA the gold answer stands in. For a restricted question, the right decision is that the policy withheld the answer.
- **Single recorder, honest after sealing:** tampering after sealing is round 6's question. The coherent-liar arm only illustrates the boundary.

## 3. Design

**Workload.**
- HotpotQA distractor, 1,991 passages, retriever bge-base-en-v1.5 (gold@4 0.77, below the 0.80 bar; disclosed).
- Answerable questions only.
- llama3.1:8b Q4_K_M, temperature 0, recorded seed, 4,096-token context.
- Short answer format, scored by f1_guarded. ε_δ is from judge batch 2 after adjudication (section 9).

**Changes from pilot 5** (all decided before any round 8 output):
1. Every question keeps its gold passage in the corpus. Tool questions are no longer tool-only, so retrieval faults can act on every question.
2. The lookup tool returns the gold passage (the record of reference), as in pilot 5.
3. Policy faults run on restricted questions only, and no other arm uses restricted questions.
4. The verifier's cross-source check is off. It fires on poisoned passages that assert a different figure, so planting records frames an honest tool. It never fired on HotpotQA, whose tool returns text.
5. Every signature is HMAC-SHA256; it was sha256(key + payload).
6. The witness is built and signed by the wrapper (A-P).
7. Tool responses are stored as a hash in the record, with the text in a deployer-side content-addressed store. That store also holds the tool descriptions the model was shown.
8. The context check rebuilds the context from the description actually shown, fetched by hash. A changed description is then the tool's fault alone and no longer also raises F_X.
9. The verifier returns every alarm, not only the strongest.

**Candidate record `sigma_r8`:**
- input hash
- context commitment
- passage hashes and ranks
- tool transcript, with the returned value hashed
- tool identity, attestation and description hash
- policy witness, with the wrapper's tag
- model identity and sampling parameters (needed for replay)
- output commitment and decision class

**Faults (one variant per class):**

| Class | Variant |
|---|---|
| F_R | suppression |
| F_X | context_truncation |
| F_T | server_name_squatting |
| F_P | fail_open |
| F_D | PoisonedRAG, dose 5 |

**Pairs:** all 10 combinations of the five classes.

**Eligibility:**
- A pair containing F_P uses restricted questions; a pair without F_P never does.
- A pair containing F_T uses questions that call the tool.

**Block:** per question in a pair arm, four executions with the same seed and the same model randomness: the pair, A alone, B alone, and clean. Each fault has its own random stream, so it draws the same wrong answer and the same poison texts alone or in the pair.

**n:** 72 questions per pair, drawn without replacement from each pair's own seeded stream. If a pair has fewer eligible questions, it uses all of them. The n per pair is fixed in section 9 from the feasibility count.

**Ground truth.** For each fault, from the sealed log. "Harmed": the clean run was acceptable and the faulted run was not, or the faulted run released a restricted value the clean run did not. For F_D pairs, the library was involved when the pair was harmed and either the partner alone was not harmed or the poison alone was.

**Descriptive arms, 36 runs each (fewer if not eligible):**
- **Rug pull:** checks the explain-away rule.
- **Lying filter:** loads the version of record, evaluates nothing, reports a full evaluation.
- **Forged witness:** a rolled-back filter writes its own witness claiming the version of record, signed with its own key.
- **Coherent liar:** a compromised recorder rewrites every field as the clean twin's, except the output commitment.

**Part B investigator.** As specified in `msfs/replay.py`:
1. Replay the recorded state and require it to reproduce the disputed decision. This is skipped when an F_X alarm makes the faulty context unrebuildable.
2. Repair every alarmed component and replay.
3. Take passages out of the library and re-retrieve over the snapshot without them:
   - every set of one or two recorded passages;
   - then peeling from the top, up to five deep;
   - then larger sets.
4. Stop at the first replay that gives the claimed decision, within 40 replays per dispute. When the repair already gives it, the removal search runs with the partner left faulty, to detect a joint cause.

Verdicts: partner, library, library_joint, unexplained, not_reproduced, no_input. "Library flagged" means library or library_joint.

**Part B groups:**

| Group | What it is | Cap |
|---|---|---|
| G1 | Harmed pair runs from the four F_D pairs | 18 per pair |
| G2 | Harmed partner-alone runs from the same blocks (library innocent) | 18 per pair |
| G3 | Clean runs on non-restricted questions whose outcome is wrong (plain model errors, nothing injected) | 8 per pair |

Within each pair, disputes are taken in plan order.

## 4. Predictions (registered before any round 8 output)

| # | Prediction |
|---|---|
| E1 | Runtime pairs: both classes named in every run, at the single-fault rate |
| E2 | No cross-talk in any runtime pair. F_R+F_X was the pair most expected to be ambiguous; the verifier rebuilds the context from the recorded (faulty) retrieval set, so it should stay clean |
| E3 | Rug pull is named F_T and nothing else |
| E4 | F_X+F_D, F_T+F_D, F_P+F_D, record only: the partner is named and nothing else in about every run, a false exoneration of the library |
| E5 | F_R+F_D: mostly silent. At dose 5 the planted passages fill the top 4 in the live index and in the snapshot alike, so removing the gold passage leaves no trace and has no effect. This is masking, not a verifier miss |
| E6 | Part B, G1: the library is flagged in most disputes where the twins say it was involved |
| E7 | Part B, G3: some false library flags, where removing a distractor fixes a plain model error. This is the bar most likely to fail |
| E8 | Lying filter: caught only when it releases a violation, and only through y_class; never without it. Forged witness: always caught, by the tag |
| E9 | Coherent liar: no alarm except where the archive contradicts the lie (passages the snapshot holds that the forged record does not) |
| E10 | Record size: flat in passage length; tool runs a fixed amount larger than no-tool runs |

## 5. Pass and fail

One-sided 97.5% Clopper–Pearson bounds. Bars at n = 72 are given in brackets.

| Test | Pass if |
|---|---|
| Clean arm false alarms | upper ≤ 0.05 (0 of 72) |
| Each single class detected (F_D: no component blamed) | lower ≥ 0.90 (at most 2 misses in 72) |
| **A1** both named, each runtime pair | lower ≥ 0.90 |
| **A2** cross-talk, each pair | upper ≤ 0.10 (at most 2 of 72) |
| **A3** (prediction) partner named and nothing else, F_D pairs | confirmed if lower ≥ 0.90. F_R+F_D is predicted not to confirm (E5) |
| **B1** library flagged when involved (G1) | lower ≥ 0.70 |
| **B2** innocent library flagged (G2 and G3, each) | upper ≤ 0.10 |
| **B3** partner still named (G1) | lower ≥ 0.90 |

Part B passes only if B1, B2 (both groups) and B3 all pass. If Part B fails, the claim is Part A alone.

## 6. What each failure means

- **A1 fails for a pair:** "two faults, two witnesses" does not hold for that pair. Report which witness was missing.
- **A2 fails:** the witnesses are not independent. Lemma C needs a coupling edge for that pair.
- **B1 fails:** replay cannot recover the library's role. Report the record-only result.
- **B2 fails:** the method frames the library. Part B is not claimed.
- **B3 fails:** replay broke partner attribution, which would be a bug.

## 7. Analysis

`run_round8.py` (or `--merge` over per-pair chunks) writes `round8.md`, `round8.json`, `runs.jsonl` and `sealed_log.json`. Every bar is reported, failures included. The comparison configurations (otel_default, otel_content, openinference, openinference_guard, sigma_hash_plus) are descriptive.

## 8. Deviations

Any change after registration is logged here with its date and reason, before the affected output is seen.

## 9. To fill in before registering

1. ε_δ after adjudicating the 18 judge batch 2 disagreements: ____.
2. Eligible questions per pair from `--count-only`, and the n used for each short pair: ____.
3. Dr. Frigui's confirmation of the retriever (keep bge, disclose) and of tool responses (hash plus deployer store): ____.
4. Seconds per execution from the smoke test, and the resulting Part B budget and caps if they change: ____.

Registration hash (sha256 of this file as committed): ____  Timestamp: ____
