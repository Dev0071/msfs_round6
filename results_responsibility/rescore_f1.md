# Re-scoring the saved disputes with `f1` (sensitivity check)

60 disputes, 960 stored coalition outputs; 13 coalition verdicts changed (1.4%).
WARNING: 4 stored outputs are exactly 300 characters and may have been truncated by the round 6 script; their verdicts are unreliable.
Disputes whose full-context output is still scored wrong under `f1`: 59/60 (the rest would not have been disputes at all under this scorer).

## Mixed disputes: hit / wrong / abstain

| method | original (strict) | re-scored (f1) |
|---|---|---|
| shapley | 16/3/9 | 16/3/9 |
| loo | 10/7/11 | 9/7/12 |

On the 27 mixed disputes that remain disputes under `f1`: Shapley hit 15/27 (lower bound 0.35) vs baseline 0.51.

Attributable (some coalition right): 18, Shapley hit 15, wrong 3. Non-attributable: 9, abstained 9.