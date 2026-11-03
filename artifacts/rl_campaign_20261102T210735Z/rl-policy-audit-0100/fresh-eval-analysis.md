Keep current v4 training as the existing campaign portfolio arm. The fresh evaluation supplies no reliable performance difference that warrants replacing it with a novelty-only branch. This is a conservative recommendation under the remaining time, not evidence that v4 is optimal or improves rank-92 discovery.

All 64 complete matched triplets used the same task, seed, input rank, 50,000-attempt action cap, and four-action episode cap. All observations below include both successful and budget-censored episodes; actual work varies because recovery ends an episode early.

| Evaluation | Learned successes | Warm successes | Random successes | Learned-only / warm-only successes | Learned-only / random-only successes |
|---|---:|---:|---:|---:|---:|
| Earlier v3 | 56/64 | 55/64 | 51/64 | 4 / 3 | 6 / 1 |
| Fresh v4 | 53/64 | 55/64 | 51/64 | 2 / 4 | 2 / 0 |

Fresh learned and warm both succeed in 51 pairs and both are censored in seven. Learned and random both succeed in 51 pairs and both are censored in eleven. Directly pairing latest learned with earlier learned gives two newly successful pairs and five newly censored pairs, a net difference of minus three. These few discordances do not demonstrate a gain or a dependable regression. There are only four distinct tasks, each repeated over 16 seeds; two delayed-control tasks succeed for every arm, leaving two hard tasks to distinguish policies. Reusing the same tasks and seeds makes this a repeated diagnostic, not a fresh generalization test.

| Fresh arm, same 64 matched episodes | Native attempts | Measured CPU seconds |
|---|---:|---:|
| Learned | 4,012,149 | 13.3333 |
| Warm | 3,634,918 | 12.2311 |
| Random | 4,141,940 | 13.5294 |

Latest learned uses 377,231 more attempts and 1.1022 more CPU seconds than warm, and 129,791 fewer attempts and 0.1961 fewer CPU seconds than random on these exact matched episodes. Success rates differ, so these are joint finite-budget outcomes, not equal-success efficiency claims. Earlier learned used 3,459,748 attempts; current learned uses 552,401 more. Warm and random have exactly identical attempt totals across the two evaluations while their CPU totals change, illustrating why cross-run timing differences need caution.

Checkpoint identities and frozen behavior checks pass independently. The latest snapshot still hashes to `775eee1d9871e2edf97b8b7754561159c9f4a28f0a52939897a63c2c91c6cf02`. Its contextual weight hash remains `010298d344878f640770248f86520f974f0c33fea879bd5a11b784fb2aab93dd`, and updates remain 14,456. Earlier learned remains at 2,841 updates and warm at 686. Recomputed checkpoint and contextual weight hashes match the evaluator summaries and every episode's before/after weight hash; every episode has `training=false`. Warm's evaluator hash includes the documented two zero-weight context rows appended to its original 18-feature policy. These checks corroborate no fitting; this analysis did not replay native searches.

Large recovery rewards alone do not establish harmful interference. The controller exposes the recovery-task flag and remaining novelty budget, so shared weights can condition behavior by task. Gradient magnitudes and their effects would need direct attribution to establish interference. Current behavior still uses multiple native profiles.

A novelty-only branch based on the existing exact term-set novelty has a weak experimental rationale: about 99.9% of main transitions already produce unseen term sets, and the audit snapshot had paid 24.285 of the shared cap of 25. That signal is nearly constant before exhaustion and zero afterward. Changing or renewing the cap would introduce a new objective without evidence that it distinguishes useful record-search coverage. Preserve v4 now; reconsider a bounded branch only with a predeclared, discriminating coverage measure and a matched main-CPU comparison. No code changes or training were launched here.

These evaluations measure recovery of known rank 93; no arm reported a new record. The live random-record arm's zero recovery allocation versus learned's 0.2 is a separate scope difference and does not apply to the matched frozen episode comparisons above. Detailed per-task tables, paired formulas, and input hashes are in fresh-eval-analysis.json. All analysis ran on CPU 2 with nice 10; the final scalar analysis completed in approximately 0.25 seconds.
