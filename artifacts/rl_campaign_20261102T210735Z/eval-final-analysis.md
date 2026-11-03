The frozen 02:54:24 policy snapshot recovered the known rank-93 bound in 53/64 matched episodes, versus warm 55/64 and uniform random 51/64. All 64 complete three-arm triplets used the same four tasks, base seed 721101, 50,000-attempt action limit and four-action episode limit. No record target was reached and no WINNER was reported.

| Frozen arm | Successes | Delayed controls | Hard tasks | Native attempts | Measured CPU seconds |
|---|---:|---:|---:|---:|---:|
| Latest learned snapshot | 53/64 | 31/32 | 22/32 | 4,385,680 | 13.8961 |
| Warm | 55/64 | 32/32 | 23/32 | 3,634,918 | 12.2419 |
| Uniform random | 51/64 | 32/32 | 19/32 | 4,141,940 | 12.9518 |

Against warm, learned has four learned-only successes and six warm-only successes; both succeed in 49 pairs and both are budget-censored in five. Against random, learned has nine learned-only successes and seven random-only successes; both succeed in 44 pairs and both are censored in four. These small paired differences do not establish a causal improvement, reliable regression or broader generalization.

Compared with the earlier v4 audit, aggregate success counts remain 53/55/51. The learned episode outcomes nevertheless change: eight previously censored pairs now succeed and eight previously successful pairs are now censored. Learned delayed-control successes move from 32 to 31 and hard-task successes from 21 to 22. Warm and random have identical success outcomes and native-attempt totals across the two evaluations. This is repeated diagnostic evaluation on the same small filtered distribution, not an independent learning-curve experiment.

Costs include every complete matched episode, including finite-budget failures, with no success-only filtering. Final learned uses 750,762 more attempts and 1.6542 more CPU seconds than warm, and 243,740 more attempts and 0.9442 more CPU seconds than random. Learned also uses 373,531 more attempts than its earlier snapshot on these same episodes. Actual work differs because success ends episodes early; these are joint descriptive success/cost outcomes, not equal-success efficiency claims. Cross-run CPU differences also reflect the execution environment.

Independent identity checks pass. The evaluated checkpoint remains SHA256 `dc3ef6139dc997472bc28eb47f71406c5549617e23d1316ac8694880c7a104eb`; its contextual weight hash remains `4477d17450eb04afce47212451c66ec014debc7d49f66716b028e232a0d27182`. The snapshot has 22,861 updates and 6,612 main steps. Recomputed checkpoint and weight hashes agree with the evaluator, every episode has unchanged before/after weights and training=false, and summary update counts remain unchanged. Warm's two zero-weight context rows are included in its evaluated weight identity. No fitting or native replay occurred in this analysis.

This evaluation assesses that frozen snapshot only. Training continued separately, and later or final training weights were not evaluated here. The pool hash is `4c407ce12d57274a150860a1ea6e4a113721a9707ebad54f12b8fd024f2b4a0e`: four held-out tasks repeated over 16 seeds, including only two hard tasks. Repeated seeds do not create 64 independent task draws. These are recoveries of a known rank-93 bound; no inference to rank-92 discovery follows. Full per-task tables, paired checks and input hashes are in eval-final-analysis.json.
