# C7 frozen-policy validation result

**The learned policy showed no advantage in this completed finite-budget validation.** Root's single authorized run exited cleanly after180.05 driver seconds/181.09 wrapper seconds. No additional evaluation was run by the reviewer.

Of224 planned task/seed triplets,194 completed with all three arms, one was partial with two result rows, and29 never started before the wall cutoff. The analysis uses only the194 complete triplets:582 matched episodes. All584 persisted rows, event rows, task/source identities, seeds and completion flags were independently reconciled. The incomplete triplet was excluded for every arm.

| Arm | Known93 recoveries | Rate | Attempted moves | Measured CPU |
|---|---:|---:|---:|---:|
| Learned |119/194 |61.34% |18,173,493 |54.95 s |
| Frozen warm |126/194 |64.95% |16,926,000 |52.33 s |
| Random |155/194 |79.90% |15,054,448 |49.50 s |

The learned source-equal-weight rate difference was−3.61 percentage points versus frozen warm and−18.56 points versus random. Each of the two validation sources contributed97 matched episodes per arm, and the learned difference was negative on both. With only two related source clusters, these are descriptive validation results, not a generalization claim or a broadly reliable confidence interval. Repeated task seeds are not independent source evidence. Equal50k-step/action and four-action caps do not imply equal measured CPU: successful episodes stop early.

All1264 referenced native runs passed existing metadata/profile/binary/bridge/cap checks. Inference events had training=false, no gradient update, no novelty reward and unchanged policy update counters. Every row's before/after weight SHA matched its frozen policy identity; actual source checkpoint hashes remained unchanged. Learned updates stayed39698 throughout evaluation; both baselines stayed39515. Only the14 declared validation tasks/two validation sources appeared in results. The two disjoint final test sources remain unassessed.

There was **no record**: successes are recoveries of the already known93-product bound. Unrecovered matched episodes are UNKNOWN within the declared action budget, not lower bounds; the summary's `censored` count denotes these unrecovered episodes and should not be confused with the one globally incomplete triplet. The remaining29 unstarted triplets were not assessed. No repeat seed or final-test evaluation was requested or performed here, and no promotion is authorized by this analysis.

Evidence: `artifacts/marathon7_20261103T122417Z/rl-validation-analysis-v1/REPORT.json`, its native-stat cache/checksums, and the completed original `marathon7-evaluate44-validation-seed4411034407` results/events/summary. The new read-only analyzer is `scripts/analyze_marathon7_rl_validation.py`. No source task payload was reevaluated, no policy fitted, no queue changed and no old campaign file written by the analysis.
