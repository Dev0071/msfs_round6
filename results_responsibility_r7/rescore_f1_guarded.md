# Re-scoring the saved disputes with `f1_guarded` (sensitivity check)

60 disputes, 960 stored coalition outputs; 26 coalition verdicts changed (2.7%).

Disputes whose full-context output is still scored wrong under `f1_guarded`: 60/60 (the rest would not have been disputes at all under this scorer).

## Mixed disputes: hit / wrong / abstain

| method | original (f1) | re-scored (f1_guarded) |
|---|---|---|
| shapley | 16/7/14 | 16/5/16 |
| loo | 7/9/21 | 9/4/24 |

On the 37 mixed disputes that remain disputes under `f1_guarded`: Shapley hit 16/37 (lower bound 0.27) vs baseline 0.54.

Attributable (some coalition right): 21, Shapley hit 16, wrong 5. Non-attributable: 16, abstained 16.

Disputes whose Shapley verdict moved:

- run 92 (injection_in_passage): wrong -> hit
- run 98 (injection_in_passage): hit -> abstain
- run 102 (poison_ingested_d3): wrong -> abstain