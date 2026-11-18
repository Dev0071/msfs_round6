# Round 8: notes on the registered run

Registration: `PREREG_round8.md`, commit 64ad85c, sha256 b16bc525…1c32, OpenTimestamps proof complete (commit a217395). Results: `results_round8/round8.md`, merged from 11 chunks, unchanged.

## Deviations

None. Nothing in the registered design, code, seed, bars or sample was changed after registration.

## Problems in the registered design, found while it ran

These were noticed while the chunks ran. None was fixed, because fixing them would have meant changing the analysis after seeing output. All verdicts are reported as registered.

1. **B3 measures the record, not the replay.** Section 6 says a B3 failure means "replay broke partner attribution". But B3 is computed from the record's alarms, which replay never changes. And the G1 sample includes F_R+F_D disputes, which E5 predicted would raise no alarm. So the registration contradicts itself: E5 predicts that B3 fails. As registered, B3 is 51/68 (lower 0.630), FAIL. Without F_R+F_D (post hoc, `explore.md` §4) it passes. Neither figure tests what B3 was meant to test.
2. **The joint test can't run for policy partners.** Fixing a broken filter always gives the claimed decision ("blocked"), so the joint test then runs with the filter still broken, and a broken filter never blocks. In F_P+F_D, a guilty library can't be flagged. This used 36 disputes and about 864 replays. It affects B1 only through the F_P+F_D disputes where the library was involved: 1 of 47.
3. **The joint test can't run for F_X partners**, because a record that only holds hashes can't rebuild the faulty context. This was known at registration (`replay.py`); it is listed here for completeness.
4. **G3 holds 24 disputes, not 40.** The four pairs that include F_P use only restricted questions, and G3 takes only non-restricted ones. The G3 bound is wider than planned (upper 0.634). E7 is confirmed anyway.

## Exploratory analysis

`explore_round8.py` reads `results_round8/runs.jsonl` and writes `results_round8/explore.md`. None of it is a registered test.

5. **The merge writes less than section 7 says.** `--merge` writes `round8.md` and `round8.json`, but not a combined `runs.jsonl` or `sealed_log.json`. Those stay in the 11 chunk folders. `results_round8/runs.jsonl` is the chunks' `runs.jsonl` files joined in the order the merge read them (`cat r8_F*/runs.jsonl r8_extra/runs.jsonl`), made on 17 Nov for the exploratory analysis. The registered code was not changed.
