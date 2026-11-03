**Campaign completed at the authorized deadline. See the [final six-hour report](SIX_HOUR_REPORT_20261103.md) and [final handoff](../../artifacts/rl_campaign_20261102T210735Z/HANDOFF.md). The interim snapshots below are preserved as history.**

# IN PROGRESS: six-hour 5×5 F₂ search and RL experiments

**Status checkpoint: 2026-11-03 02:02:00 UTC (02:00 checkpoint). This is an interim research
report, not the final result of the authorized six-hour campaign.** Work began
at **21:07:35 UTC on November 2** and remains bounded by **03:07:35 UTC on
November 3**, four CPU cores and 8 GiB total RAM. Subsequent activity must be
read from timestamped manifests and monitoring records. This report does not
assume completion of any currently running segment.

The objective is an exact 5×5 matrix multiplication algorithm over F₂ using at
most 92 scalar products. The best accessible published upper bound verified
for this session is 93. At this checkpoint, the campaign has **no reported
verified certificate with at most 92 products**. The ongoing work below does
not establish novelty, a learning advantage, or impossibility of rank 92.

## Update at the 02:00 checkpoint, November 3

The collector captured **02:02:00 UTC**, 93 job rows in about 0.144 CPU s; global best remains **93**, no verified≤92 certificate. Active jobs are learned-v4-8, random-record-3, fixed1-1 and the public095 small-local SAT run, one per CPU. Registered caps total 4,096 MiB; guard02:01:40 reports 440,115,200 bytes summed RSS/631,877,632 peak. Auxiliary V3 shares CPU2. **Reserve final tests/evaluation around 02:55; the hard deadline is 03:07:35.** This remains interim work, not six hours completed. [JSON snapshot](../../artifacts/rl_campaign_20261102T210735Z/report-snapshot-0200/report.json), [resource/status CSV](../../artifacts/rl_campaign_20261102T210735Z/report-snapshot-0200/jobs.csv).

Three frozen primary [two-direction pair-block](KERNEL_PAIR_BLOCK.md) jobs (KM93, AE93, public095) are **queued**, each testing the exact finite family of **42,887,691 unordered short-circuit pairs** on its fixed source. No long pair-block search had started at this snapshot. `NO_TARGET` is complete coverage of that exact source catalog only when all contiguous pair prefixes are accounted for; partial wall/signal/pair-limited coverage remains UNKNOWN. Atomic joint vector shifts avoid an intermediate headroom restriction; any found model still needs exact Python-witness and full tensor verification. This is not global UNSAT or a new identity. Larger-local KM+AE600-second trials are queued afterward, with up to 177 free groups/nullity68 from 64-circuit unions and SAT93 controls; preflight nullity does not imply rank92 existence.

Actual completed small-local plans differ by source. **KM:156 unique neighborhoods,149 local UNSAT/7 unresolved,170 queries including21 UNKNOWN retries. AE:153 unique,all153 local UNSAT,153 queries. Public015:157 unique,156 local UNSAT/one unresolved,159 queries including3 UNKNOWN retries.** Public095 is active, final result pending. The unchanged runner retries only unresolved UNKNOWN cases, so query attempts must not be reported as distinct unresolved neighborhoods. [Reconciliation](../../artifacts/rl_campaign_20261102T210735Z/report-snapshot-0200/local-query-reconciliation.json). All negatives remain local to frozen outside assumptions. All three native-cardinality coordinate trials finished UNKNOWN with SAT controls and children reaped.

One-cube native search has exact **rank100→97** branch progress. The queued unrestricted continuation selects16 rank97 sources with16 distinct factor-matrix-rank histograms, removes cyclic/fixed-cube constraints and receives900 seconds;300-second phases will normally reach roughly three of those sources. No global product-bound improvement is claimed. KM short and AE short kernel walks both completed at best93, coset94 pilot at94, and full-span wide search at93. The wide trial accepted only **6 of 29,095,334 long-support proposals**, across 6,660,810,240 total attempts; all reported best/current matrix ranks were independently checked. Full kernel span is not bounded-rank connectivity.

[Coordinate span evidence](../../artifacts/rl_campaign_20261102T210735Z/baseline-alternate-span-analysis-v1/analysis.json) gives AE93 quotient ranks **25/25/0** relative to old1,009/short1,096/full1,165 spans. An exact rank97 live KM-short state has quotient rank1 outside the old span, zero outside short/full: this is direct evidence it left the old span. It concerns vector coordinates in the fixed WU family, **not full-algorithm inequivalence**, novelty or reachability under a rank cap.

Auxiliary V3 launched 01:34:58 (PID129179), cap109, while stopped V2's 112-source status is preserved. Its02:02 elapsed-window observation is approximately **2.04% CPU (33.19/1,627.31 s)** versus 2.5% target; this is measured usage over that window, not a universal hard cap. The prepared 109→93 exact fixture is nonrecord and took 0.099 CPU s. No winner was reported. The earlier V1 quota caveat remains historical.

The inverse-polarization audit found **zero explicit patterns among 65 rank97 states**. Root's original heredoc was captured after the run, and an input manifest has now been reconstructed afterward without rerunning the scan or changing its original result. The manifest explicitly preserves uncertainty about historical input selection; pattern absence is not a lower bound. [Audit provenance](../../artifacts/rl_campaign_20261102T210735Z/inverse-polarization-audit1/program.snapshot.json), [reconstruction](../../artifacts/rl_campaign_20261102T210735Z/inverse-polarization-audit1/reconstructed-input-manifest.json).

The observed nine-package requirements/import audit is retained in [requirements-rl.txt](../../requirements-rl.txt) and [reproduction instructions](REPRODUCING.md), with no installations. Fresh frozen RL evaluation and unmatched live-allocation cautions below are unchanged. Pair-block/large-local/current-run results and the final evaluation remain pending; the [handoff](../../artifacts/rl_campaign_20261102T210735Z/HANDOFF.md) retains exact continuation commands, finalization reserve and older evidence.

## Historical update through 01:25 UTC, November 3


The campaign remains **IN PROGRESS**, best verified global rank **93**, with the hard deadline **03:07:35 UTC** unchanged. At the01:25:36 bounded snapshot, CPU0/1 ran learned-v4-6 and frozen random-record-2; CPU2 ran kernel-expanded-short1 since 01:19:47 and CPU3 native-cardinality VW since 01:19:25. Current registered caps total 4,352 MiB. The 01:22:56 guard sample reported 524,853,248 bytes summed RSS and 602,791,936 peak. The auxiliary watcher shares CPU2 rather than adding a core.

The coset94 pilot completed about 298 s with best94, 21 independently verified checkpoints and no winner. Expanded-short search is active with **9,262 circuits/span 1,096**, versus old 9,008/span 1,009 and full kernel 1,165. It adds 87 measured dimensions but leaves 69 missing; its final result is pending. Six exact rank100/one-cube seeds are ready for the queued 900-second `fixed1-1` trial. Neither preparation nor seed rank is a discovery.

Native-cardinality WU completed **UNKNOWN**, SAT control and child reaped; VW is current and UV next. Earlier coordinate-CNF UV also completed UNKNOWN, leaving all three earlier orientations UNKNOWN. The frozen local full-tensor SAT repair is ready and queued after native UV, with an exactSAT93 full15,625-entry control. It fixes outside-group variables by assumptions on the full formula, avoiding residual-only success claims; target results remain pending. [Local preparation](../../artifacts/rl_campaign_20261102T210735Z/local-fixed-pair-ready-v1/READY.json).

Fresh frozen evaluation produced **latest53/64, warm55/64, random51/64** matched known recoveries; earlier learned was 56/64. The same four tasks/two hard tasks over 16 seeds are a repeated diagnostic, not fresh generalization evidence. [The audit](../../artifacts/rl_campaign_20261102T210735Z/rl-policy-audit-0100/fresh-eval-analysis.md) establishes no convincing gain or dependable regression and recommends retaining current V4 as a conservative portfolio choice. No fitting occurred. Reward scale alone does not prove harmful interference or poor policy: attribution would be needed. Live learned recovery0.2 and reference recovery0 remain unmatched allocations.

Auxiliary watcher V1 stopped **01:20:49**,12 sources checked/no winner, after one-second policy rereads incurred cooldown debt and starved useful work. Its intended 2.5% CPU quota was **not established**. V2 was prepared with cached reads, debt-aware cooldown and measured CPU; its launch records **01:25:32**, newly active by the snapshot, with initial 3 sources/no winner. Sustained2.5% remains a target, not a demonstrated bound. Older watcher source stayed unchanged. [V2 preparation](../../artifacts/rl_campaign_20261102T210735Z/auxiliary-pair-watcher-ready-v2/READY.json), [launch](../../artifacts/rl_campaign_20261102T210735Z/auxiliary_pair_watcher.launch.v2.json).

A separate unlaunched wide-kernel preparation adds 69 directions to reach full span 1,165. Only **1/69 initial modal proposals fit headroom6**,29/69 headroom16. This algebraic span result establishes no bounded-rank connectivity, feasibility or discovery-rate claim. [Initial admissibility](../../artifacts/rl_campaign_20261102T210735Z/kernel-wide-prepared-v1/modal-admissibility.json).

The new [bounded collector](../../scripts/collect_rl_campaign_report.py) exports 85 status/resource rows to [snapshotJSON](../../artifacts/rl_campaign_20261102T210735Z/report-snapshot-0125/report.json) and [CSV](../../artifacts/rl_campaign_20261102T210735Z/report-snapshot-0125/jobs.csv), with input/code hash references and distinct launcher/solver/control statuses. It reads selected root/immediate-child evidence only, avoids recursive recovery scans, starts no workers and verifies no new mathematics. Collection consumed about 0.158 CPU s, CPU2/nice10. Large/partial/missing evidence is flagged; `sat-initial/manifest.json` exceeded 2 MiB. Dictionary grandchild 891.78 CPU s remains separately reconstructed; outer rusage/running jobs leave totals partial, and summed job wall time is not campaign duration. [Repeat command and scope](../../artifacts/rl_campaign_20261102T210735Z/report-snapshot-0125/README.md).

The final standalone six-hour report remains future work. The current [handoff](../../artifacts/rl_campaign_20261102T210735Z/HANDOFF.md) preserves exact recovery commands and all earlier observations below as history.

## Historical update through 01:00 UTC, November 3


The campaign remains **IN PROGRESS**, best verified global rank **93**, no verified≤92 certificate. The hard deadline remains **03:07:35 UTC**. Active manifests show learned-v4-6 CPU0 since 00:56:11, frozen record-only random-record-1 CPU1 since 00:39:50, strict-two-cube fixed2-long3 CPU2 since 00:43:48, and coordinate-stencil UV SAT CPU3 since 00:53:33. Earlier observations retained below are explicitly historical unless superseded here. Current requested caps total 4,096 MiB; the 00:59:47 guard sample reports 465,489,920 bytes summed RSS and 602,791,936 peak. Guard and V2 nested-target-watch supervisor remain live.

**Reference scheduling failure and repair:** learned V4 phases3–5 completed normally; phase6 is active. Random V4 phases5–10 **all exited2 before search** because `--recovery-fraction 0` was incompatible with frozen V4's required0.2. These were configuration failures, not mathematical failures or completed experiments. A valid 300-second repair resumed random-v4-4 with fraction0.2 and completed normally. [train_record_reference.py](../../scripts/train_record_reference.py) now supplies the explicitly **frozen/random, recovery0** reference from that repaired checkpoint, preserving model/RNG, schedule identity, four-source restart order and zero installation reward. Since the actual record-only change, learned and reference allocations are **not matched**, so later raw outcomes cannot establish a causal learning advantage. [Repair result](../../artifacts/rl_campaign_20261102T210735Z/random-reference-repair-job.result.json), [interventions](../../artifacts/rl_campaign_20261102T210735Z/interventions.jsonl).

**All six free-factor searches finished UNKNOWN**: WU/VW/UV on the base dictionary (600 s each), then all three on the 1,536-pair closures (900 s each). Every run had an independently exact **SAT93 positive control** and reaped its solver child. No target model or global negative emerged. Coordinate-stencil WU and VW likewise finished **UNKNOWN**, with SAT controls and children reaped; UV remains **active at 01:00**, result pending. These statements are scoped to their finite families. [Full per-run result links](../../artifacts/rl_campaign_20261102T210735Z/HANDOFF.md), [coordinate driver](../../scripts/campaign_coordinate_stencil_sat.py).

The AlphaTensor96 branch completed with best95; held-three-cube search completed with full best93; kernel-walk1 completed 26,080,203,520 attempted moves and 109 independently checked checkpoints with best93/no winner. Strict-two-cube long3 still has best95. These are branch outcomes, not a new product bound. The earlier slice scan processed 439 valid inputs, best93; the coordinate scan retained93. Kernel-circuit negatives concern only the generated span (dimension1,009 of full kernel 1,165), not global nonexistence.

**Compression corrected a diversification interpretation.** Global active-pair column compression catches dependencies crossing the shared-factor blocks used by the older slice method. [pair-compress-quick1](../../artifacts/rl_campaign_20261102T210735Z/pair-compress-quick1/result.json) processed **58 valid inputs**, best93/no winner. Its overall ERROR and15 error rows came from **verification reports accidentally selected as certificates**; all 15 source basenames are `verification.json`. They do not imply invalid mathematics. Source records separately identify 32 NONCERTIFICATE rows and one duplicate; the 20-second budget did not process every discovered path. [Compression driver](../../scripts/scan_pair_compressions.py).

Of 16 coset seeds,15 compressed to93 and one stayed94. Canonical hashing confirms **all 15 rank93 outputs equal known KM93/public306**, hash `270f411487d4a6b7e22380ea25cd2f26d699c3fea4095a8a9984dfb2f5d9ad2c`; the [compressed pool](../../artifacts/rl_campaign_20261102T210735Z/compressed-coset93-pool/manifest.json) has one distinct known state. Thus there is **no new93 basin** from those outputs. The cheapest exact coset94 seed remains94 and is a **proposed next kernel pilot**, not a completed or active 01:00 experiment. Its coset distinction is relative to the old short-circuit span only and is not full-algorithm inequivalence. [Coset evidence](../../artifacts/rl_campaign_20261102T210735Z/kernel-coset-seeds-v1/result.json), [generator](../../scripts/generate_kernel_coset_seeds.py).

The sections below preserve earlier source assessments, experiments and the 23:27 status snapshot. The [handoff](../../artifacts/rl_campaign_20261102T210735Z/HANDOFF.md) retains exact live-manifest argv extraction, watcher recovery commands, deadline and checkpoint/schedule continuation rules. V4 and dedicated record-only reference entrypoints must retain their different validated recovery fractions. No source or running code changed for this report update.

## Source data and DeepMind resource scope

The starting references include the Moosbauer–Poole 2025 rank-93 construction
from `jakobmoosbauer/symmetric-flips`, commit
`3e2d4dd8acf831ef65c7c6b13ed787330e1e3483`, and the official AlphaEvolve
rank-93 5×5 integer construction, reduced to F₂ for use as another seed.
The latter comes from `google-deepmind/alphaevolve_results`, commit
`4226acbf237ff9ad10ba7673a2af127a2d8a5971`. Its retained notebook hash is
`2cce2543e48c89aa3e91614272a698a0147dd2548ea11cf92f1292b7435d38ff`.

The AlphaEvolve importer reads only approved AST numeric literals and never
executes the notebook. Both the signed integer and binary identities pass all
15,625 coefficient checks and 64 supplementary random products. Modulo-two
normalization retains 93 distinct nonzero terms. The separate signed source
is an integer identity; the literal binary certificate is valid only over F₂.
Imported schemes retain attribution and are not discoveries of this campaign.

AlphaTensor's official public release supplies tensor factorizations, V100
benchmarking, nonequivalence data, and recombination code. It does not supply
its full self-play training pipeline or trained policy/value checkpoints. Its
published 5×5 F₂ baseline in the retained archive uses 96 products. The
AlphaEvolve results repository likewise does not contain execution code for
AlphaEvolve. The complex half-integer 4×4 rank-48 result is a different field
from AlphaTensor's F₂ rank-47 result.

The local V2 controller executes actual installed DeepMind `dm_env` reset/step
calls during training. This is use of the Python environment API with a locally
implemented actor-critic and exact native rewrite actions; it is not a
reproduction of AlphaTensor training. Acme and Mctx were inspected as available
building blocks, not represented as trained tensor agents. See
[DEEPMIND_RESOURCES.md](DEEPMIND_RESOURCES.md),
[CONTINUAL_V2.md](CONTINUAL_V2.md), and
[the bounded publication check](../campaign/RECORD_CHECK.md). arXiv/Nature live
access was limited by the configured network policy, so the publication check
is not exhaustive.

## Experiments completed or deliberately stopped so far

| Segment | Observation at its stop | Interpretation at this checkpoint |
| --- | --- | --- |
| V1 learned versus random operator selection | Each arm executed 285 actions; both retained best rank 93. Cumulative updates: 703 versus 686, including the common 686-update warm start. | The weights changed, but this comparison demonstrates no rank advantage. |
| V2 easy known-recovery pilot | Stopped at 21:35:13 UTC. Learned recovered 409/409 known tasks; random recovered 407/407. Both main record trajectories retained best rank 93. | Recovery to the supplied rank-93 bound is not a new record or useful learning evidence when both controls solve essentially every task. |
| Unconstrained polarized branch | A two-fixed-cube start could return to a rank-93 state with three fixed cubes; the root stopped the branch and changed allocation. | Starting orbit inventory alone did not preserve the desired search branch. This is a diagnostic of the search constraint, not a lower-bound result. |

The V2 task's median recovery length was **13 native attempts**, while useful
differences between the compared operator profiles appeared only with budgets
of **at least 100 attempts**. The easy task therefore usually ended before
profile selection could matter. Additional policy updates and high recovery
success counts would have been misleading as evidence for learning. The stop
decision and rationale are retained in `interventions.jsonl`; pilot counters
are in `pilot_report.json` within the campaign directory.

A separate diagnostic on an AlphaEvolve-derived exact rank-94 state showed
exploit failing to recover within **50,000 attempts**, explore recovering in
**11,340**, and long walk recovering in **37,438**. This is positive evidence
that these bounded profiles can behave differently on a particular state.
It is not a formal hardness result, an estimate of general success probability,
or evidence that the learned policy selects the better profile.

## Historical checkpoint at 23:27 UTC: allocation and V4 continuation

At **23:27 UTC**, V4 phase1 and phase2 had completed normally; learned/random phase3 were active on CPU0/1 since **23:24:05 /23:24:13**. CPU2's published AlphaTensor96 diversification was active since **23:12:58**, and CPU3's VW free-factor trial since **23:23:46**. The queue includes continuations through phase10, but every worker remains clamped to the fixed **03:07:35 UTC** deadline. Global best remains **93**, with no new verified≤92 certificate.

V4 resumes each role's own checkpoint and matching schedule, retaining policy/optimizer, global best, archive and counters. It cycles **AlphaEvolve → public015 → public095 → KM** every **300 measured main-task CPU seconds**; migration immediately installed AlphaEvolve. Supplied-state installation earns **zero reward**, and rollouts do not span externally installed seeds. Both arms had ten cumulative external restarts by phase2 completion. See [seed selection](DIVERSE_RESTART_SEEDS.md), [driver](../../scripts/train_restart_tensor_agent.py), and the campaign's frozen V4 manifest. More training and changed weights do not establish an advantage.

V3's frozen heldout evaluation completed with **56/64 learned, 55/64 frozen-warm and 51/64 random** known recoveries. Four heldout tasks ×16 seeds were used, with no fitting or weight changes and no training tasks evaluated. The delayed-control half was 32/32 for all arms; two hard-unknown tasks gave **24/32, 23/32, 19/32**. This small filtered task distribution and descriptive difference do **not** demonstrate generalization, learning superiority or a record-search advantage. [Evaluation summary](../../artifacts/rl_campaign_20261102T210735Z/eval-v3-1/summary.json).

The completed strict-two-cube long segments remain at **rank95**. Their unchanged frozen worker uses PLUS50,000 / RESET100,000,000 steps, headroom6, archive16 and 600-second phases; no improved rate is claimed. CPU2 now gives the imported DeepMind **AlphaTensor96** source approximately 23:13–23:43 through [campaign_variable_rank_native.py](../../scripts/campaign_variable_rank_native.py), without cyclic or fixed-cube constraints. Its best independently verified state is **95**, branch progress from source96 rather than a global improvement. `fixed2-long3` is queued afterward. See [runner](VARIABLE_RANK_NATIVE.md), [source](../ALPHATENSOR_SOURCE.md), and [current best pointer](../../artifacts/rl_campaign_20261102T210735Z/alphatensor96-native1/best_verified.json).

## Historical checkpoint at 23:27 UTC: exact SAT portfolios and pending work

The C3 portfolios ended with WALL_BUDGET and no candidate. [Small neighborhoods](../../artifacts/rl_campaign_20261102T210735Z/orbit-sat1/summary.json): **776 attempts =657 local bound rejections +108 UNKNOWN +11 solver local UNSAT**. [Large neighborhoods](../../artifacts/rl_campaign_20261102T210735Z/orbit-sat-large1/summary.json): **63 attempts =7 bounds +56 UNKNOWN**, reconciled complete at 23:10:15. Combined totals are 664 bounds, 164 UNKNOWN and 11 local UNSAT. Duplicate patches were skipped separately. All negative conclusions concern only selected neighborhoods with frozen outside terms, never global rank92 nonexistence. [Portfolio documentation](CYCLIC_ORBIT_CAMPAIGN.md).

The broader [fixed-pair/free-factor SAT](FREE_FACTOR_SAT.md) permits an arbitrary third F₂²⁵ factor. The WU 600-second trial finished **UNKNOWN** under its hard wall budget, with exact rank93 control **SAT** and `worker_reaped=true`; [result](../../artifacts/rl_campaign_20261102T210735Z/free-factor-wu1/result.json). VW is active; UV is queued next. Preflight or positive controls are not rank92 candidates. [Driver](../../scripts/campaign_free_factor_sat.py).

[Exact pair closure](../../artifacts/rl_campaign_20261102T210735Z/factor-pair-closure-v1/result.json) produced three **1,536-pair** dictionaries with **377 UV /389 VW /402 WU** additions. Their common column ranks remain **378 /365 /371**, and every new pair column has an exact shared-factor XOR witness in the orientation's `witnesses.json`. Original assignments remain included; broadened group choices are not a multiplication algorithm or rank92 feasibility evidence. [augment_factor_pairs.py](../../scripts/augment_factor_pairs.py) called no solver. Three 900-second closure queries are queued after the base WU/VW/UV trials; outcomes remain pending.

A separate paper-style held-three-cube residual wrapper is being prepared, **not running or queued at this checkpoint**. Raw arbitrary-tensor residual worker ranks do not represent full multiplication algorithms. Held cubes must be reattached and the complete global tensor exhaustively verified; within the held-three cyclic inventory a qualifying full rank must be **≤90**. Residual target89 first permits cyclic residual87, hence full90; raw residual90 gives full93 and does not qualify. Planned adjusted `walk.stats.json` reports full rank separately from raw `residual_walk.stats.json`. Preparation establishes no result or global impossibility claim.

The older dictionary experiment exhausted its **900-second total budget**, outer **BUDGET_EXHAUSTED**, positive control exact SAT at known93, with **no final rank92 solver answer**. Its limiter **4.593932 CPU seconds** omitted a grandchild; [persisted reconstruction](../../artifacts/rl_campaign_20261102T210735Z/dictionary-new1/resource_reconstruction.json) records **891.78 child CPU seconds** from zombie `/proc` counters. Retain that separately reconstructed partial value, not an exact campaign total; no live orphan was observed.

## Historical resources/archives and continuing recovery procedure

At 23:26:15 the guard reported **339,156,992 bytes summed RSS**, peak **602,791,936**; active worker caps total **4,608 MiB**. The four-core/8 GiB scope, CPU-pinned process-tree limiters, single-threaded BLAS, hard deadline and conservative 7 GiB guard threshold remain enforced. All computation uses local installed workers; no external paid compute or publication has occurred or is authorized.

The live [V2 supervisor](../../scripts/rl_campaign_queue_v2.py) retains the unchanged base supervisor and nested `FOUND.json` / record-file target watches. Guard and supervisor were confirmed live at this inspection. A reported target halts further scheduling for independent review, without proving validity or novelty. Default monitoring remains the filesystem-backed [pulse](../../scripts/rl_campaign_pulse.py), writing dated `live_status.json` and `monitor.jsonl`:

```sh
python3 scripts/rl_campaign_pulse.py artifacts/rl_campaign_20261102T210735Z
python3 scripts/rl_campaign_status.py artifacts/rl_campaign_20261102T210735Z --compact
```

The first 1,000 completed known-recovery runs per V3 arm remain losslessly archived and indexed. Two additional **1,000-run V4-phase1** batches completed through [archive_recovery_runs_v2.py](../../scripts/archive_recovery_runs_v2.py), SHA256 `e7d4a7cf68c5d31123b6906c8c0392a149a182be96a15da8eff2e1062f037430`. Its bounded selection reports **2,192 learned /2,164 random unscanned entries**; each batch removed 1,000 originals only after archive/member verification. Learned 481,652,446 raw bytes became 35,952,018 gzip; random 487,239,408 became 36,385,510. Remaining runs remain raw. Known recoveries remain recoveries, never records. Exact paths, hashes, newer job logs, verified restore commands, live-manifest argv extraction and checkpoint/schedule restart rules are in [the handoff](../../artifacts/rl_campaign_20261102T210735Z/HANDOFF.md).

Any ≤92 candidate must be frozen with full provenance, independently checked at all **15,625 exact F₂ coefficients**, then compared against broader publication evidence before a novelty claim. No mathematical record, new proof, global lower bound or demonstrated learning advantage has emerged. This six-hour campaign remains **IN PROGRESS**.
