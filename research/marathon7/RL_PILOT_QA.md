# C7 RL pilot collection and validation proposal

**All three 450-main-CPU pilots completed cleanly and passed query-free checks.** The new collector uses explicit C7 learned/frozen/random job IDs; it does not infer their roles from the beginning of a filename. Frozen runtime/proposal checksums were checked. Old campaign artifacts were read only; outputs and snapshots are new C7 artifacts.

| Arm | Actual main CPU | Actual recovery CPU | Policy updates | Final best/current rank |
|---|---:|---:|---:|---:|
| Learned |450.762349 s |24.007401 s |39515→39698 |93/93 |
| Frozen |450.905023 s |23.863826 s |39515→39515 |93/94 |
| Random |450.886438 s |23.698256 s |39515→39515 |93/93 |

Learned weights and both Adam moment arrays changed; its update count increased by 183. Frozen and random policies, including weights, both Adam arrays, hyperparameters and counters, are exactly unchanged from the common initial policy. These are optimization/accounting observations, not evidence of a learning advantage or a new multiplication record.

All 1236 referenced native runs were covered: 416 learned, 402 frozen, 418 random. Checks passed for binary/source/bridge/profile identity, 50k recovery-step caps, native headroom, accepted-state best+6 caps, cadence, burst/dwell settings, phase/operator/pool lineage, novelty cap, and checkpoint/schedule coherence. Event counters match final schedules. Every auxiliary recovery start satisfied the inherited phase CPU-debt inequality and used the training split; no clock/origin or debt reset occurred. Initial debt was 0.069700 CPU seconds; final debt was −0.199214/−0.055683/+0.100679 for learned/frozen/random, respectively. The incomplete old partial experiment remains separately accounted, not relabeled as a completed arm.

The actual learned checkpoint was copied byte-for-byte, together with its matching schedule, best/proof sidecars and clean job result, into immutable `rl-pilot-collection-v1/learned-frozen/`. Its SHA256 is `2fde85dccfa18b9737eea1b951e5b3a26d8b1f114de007e06a5802e696ad146e`. Independent audit rechecked every copy against its actual source, readonly mode, schedule hash binding, operator loader and finite actor/Adam arrays. The frozen reference policy equals the original common policy.

A **disabled** fresh validation proposal is ready for root's result review:

- `rl-validation-proposal-v1/proposed_job.json`, SHA256 `50c87fa71516b3123a3a757188cf61f8a2d93c9f4c5b27ac648fa38b09fa3042`.
- Manifest SHA256 `9fa45083338ab935f6fd6427d094583a8c65c97fe0839096be7a808aa7540bad`.
- 14 validation tasks from two validation sources; 16 repeats, 224 planned matched triplets/672 maximum episodes, seed 4411034407.
- Learned/frozen-warm/random inference uses the same 50k steps/action and four-action cap, with no fitting and the shared frozen novelty ledger. CPU3, 1024 MiB, 180-second driver/195-second outer envelope. Completed triplets and censoring must be reported from actual results, not assumed from the plan.
- The old proposed output is absent, and neither its old ID nor the new C7 ID appears in old/current queue metadata. Reusing the previously unlaunched seed therefore does not reuse a completed V44 assessment. Two final test sources remain reserved and disjoint; the proposal selects only validation sources.

The actual append helper validated the strict six-key disabled job. Source/checkpoint/reference/pool/runtime hashes are pinned in the proposal. **No evaluation CLI or preview, environment episode, native query, training, validation call, queue write, or promotion was performed.** Pool split/task metadata were inspected; frozen ready-file integrity checking can hash validation fixture bytes without assessing them. Final test task payloads were not assessed.

Evidence: `rl-pilot-collection-v1/REPORT.json`, its native-stat cache and readonly learned snapshot; `rl-validation-proposal-v1/PILOT_INDEPENDENT_QA.json`, task metadata index, source pins and checksums. New scripts are `scripts/collect_marathon7_operator44_pilots.py` and `scripts/prepare_marathon7_rl_validation.py`. Root must review these actual results and explicitly authorize the validation launch; this report does not authorize it.
