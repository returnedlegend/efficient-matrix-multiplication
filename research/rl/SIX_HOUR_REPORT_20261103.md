# Six-hour F₂ matrix-multiplication campaign — completed, budget exhausted

**Finalized 2026-11-03 03:08:38 UTC: authorized search budget exhausted.**
The authorized window is **2026-11-02 21:07:35–2026-11-03 03:07:35 UTC**.
The deadline was 03:07:35 UTC; the guard recorded its global stop at **03:07:35.972347 UTC**.
There are **zero running job registrations**, no WINNER and no improved product bound.

## Objective and final outcome

Find an exact 5×5 matrix-multiplication identity over **F₂ with at most 92 products**.
The best accessible published bound independently verified for this campaign is **93**.
**Final outcome: no new bound below 93; best verified 93; rank 92 existence remains unsettled by these experiments.**
Imported or recovered 93-product identities are references, not discoveries.
No negative experiment below proves global nonexistence of rank 92.

## Sources, literature scope and field

Moosbauer–Poole's 93-product source is `jakobmoosbauer/symmetric-flips`,
commit `3e2d4dd8acf831ef65c7c6b13ed787330e1e3483`.
Official AlphaEvolve 93 data use `google-deepmind/alphaevolve_results`,
commit `4226acbf237ff9ad10ba7673a2af127a2d8a5971`.
Its signed integer identity and its reduction to F₂ were checked separately;
the resulting binary coefficient literal is not itself an integer lift.
Official AlphaTensor 96 data use commit `1949163da3bef7e3eb268a3ac015fd1c2dbfc767`,
archive SHA256 `70f09f349d8d2874ef0e0e089459c7320f5aa3eef277df5ffa67f573709db2da`.
See [AlphaTensor source/attribution](../ALPHATENSOR_SOURCE.md) and [DeepMind scope](DEEPMIND_RESOURCES.md).
The release provides factorizations, not AlphaTensor's complete training pipeline or pretrained agent.
The 307 imported FastMatrixF2 seeds retain source, license, hashes and verification.
Earlier live arXiv/Nature access was restricted by network policy;
[the publication comparison](../campaign/RECORD_CHECK.md) is bounded, not an exhaustive latest-literature claim.
All new search conclusions concern F₂; no integer, real or complex algorithm is claimed.

## Compute, verification and reproducibility

Allocation: **four CPU cores, 8 GiB total RAM**, local execution; no paid external compute or publication.
Process-tree limiters pin one search per core, constrain address space and remaining wall time.
A guard observes registered groups and stops them at deadline or conservative 7 GiB summed RSS.
Auxiliary compression shares CPU 2; it is not a fifth core.
[requirements](../../requirements-rl.txt) and [reproduction instructions](REPRODUCING.md) pin the observed nine-package stack.
The imports/versions were audited without installing packages during that check.
For any accepted candidate, an independent verifier checks all **15,625 tensor coefficients** exactly modulo 2.
The trace convention is `T[5*i+j,5*j+k,5*k+i]=1`; other entries are zero.
Random matrix products supplement, rather than replace, exhaustive coefficient checks.
Inputs, source/binary hashes, commands, solver maps and immutable reports are retained by each family.
[The collector snapshot](../../artifacts/rl_campaign_20261102T210735Z/report-snapshot-0235/report.json)
reports existing evidence only; collecting statistics is not new mathematical verification.

## Learned search: implementation and evidence

The agent is a lightweight **NumPy actor-critic selecting exact native operator profiles**.
It uses actual installed DeepMind `dm_env` reset/step calls with locally implemented tensor dynamics.
It is not a reproduction of AlphaTensor self-play or AlphaEvolve execution.
A common warm start precedes learned versus frozen/random controls.
V1 arms each took 285 actions and retained 93; the easy V2 recovery pilot was stopped as trivial.
V3 used fixed 50,000-attempt actions and a small screened known-recovery pool with heldout tasks.
V4 cycles AlphaEvolve/public015/public095/KM states every 300 measured main-search CPU seconds.
External installation earns zero reward and preserves global best, optimizer, archive and counters.
Updated weights, update counts and successful recovery of known 93 are not record progress.

| Frozen matched evaluation | Learned | Warm | Random |
| --- | ---: | ---: | ---: |
| Earlier V3, 64 episodes/arm | 56 | 55 | 51 |
| Fresh V4 diagnostic, 64 episodes/arm | 53 | 55 | 51 |
| Final frozen 02:54:24 snapshot, 64 episodes/arm | **53** | **55** | **51** |

Only four tasks, including two hard tasks, were repeated over 16 seeds; no fitting occurred.
[The audit](../../artifacts/rl_campaign_20261102T210735Z/rl-policy-audit-0100/fresh-eval-analysis.md)
shows no convincing gain or dependable regression and supports retaining V4 conservatively.
Reward-scale imbalance alone does not establish harmful interference or a bad policy.
The [completed frozen evaluation](../../artifacts/rl_campaign_20261102T210735Z/eval-final-analysis.md) used the same four filtered tasks, two hard tasks, base seed 721101 and 64 complete triplets.
Checkpoint SHA256: `dc3ef6139dc997472bc28eb47f71406c5549617e23d1316ac8694880c7a104eb`, 22,861 updates/6,612 main steps.
Weights stayed `4477d17450eb04afce47212451c66ec014debc7d49f66716b028e232a0d27182`, training=false; later V4-10 weights are **not assessed**.
Learned/warm/random attempts: **4,385,680 /3,634,918 /4,141,940**; measured CPU: **13.8961 /12.2419 /12.9518 s**.
Costs include censored episodes; early stopping and environment effects prevent equal-success efficiency or reliable regression claims.
Random V4 phases 5–10 failed CLI validation before search after an unsupported recovery 0 request.
A valid recovery 0.2 repair preceded the dedicated frozen, record-only random reference.
Later learned recovery 0.2 versus reference recovery 0 allocations are **not matched causal comparisons**.

## Exact search families and their limits

| Family | Observed result | Scope of the observation |
| --- | --- | --- |
| Unrestricted AlphaTensor96 native | Best95 | Imported96 basin progress, not global improvement |
| Strict two-cube C3 long walks | Best95 | PLUS50k/RESET100m; cube count preserved |
| Held three specific cubes | Full best 93 | Reattach before verifying; qualifying C3 full rank must be≤90 |
| One-cube C3 | 100→97 | One-cube ranks are1 mod3; qualifying result would be≤91 |
| Unrestricted continuation from97 | **97→93**,32 retained full term sets | Exact states, not new algorithms or a record |
| Six free-factor SAT trials | UNKNOWN; SAT93 controls | Three base and three closure dictionaries; children reaped |
| Coordinate CNF and native-cardinality trials | All orientations UNKNOWN; SAT controls | Finite independently exact source-stencil choices |
| Old finite dictionary SAT | Budget exhausted; SAT93 control | No final target solver answer; not UNSAT |
| Inverse-polarization scans | No target | Explicit pattern family only |

C3 constraints and unrestricted searches explore different spaces; starting orbit inventory alone is insufficient.
The 16-state continuation pool has 16 distinct factor-matrix-rank histograms.
Its 32 candidate93 term sets differ from the listed public references, but inequivalence/novelty is unproved.
The completed new-pool pair batch has **13 NO_TARGET** and **3 SKIPPED_NOT_IN_FAMILY**, no winner;
the three missing-pair cases are not negative results.

## Kernel methods, span and conditional SAT

Shared-factor closure enlarged each orientation to 1,536 fixed pairs without increasing column rank.
For WU, common rank 371 gives full kernel dimension 1,165.
Measured move spans grew **1,009→1,096→1,165**; these are exact linear-algebra statements.
They do not establish bounded-rank connectivity or rank 92 feasibility.
KM/AE short walks retained 93; the cheapest outside-old-span coset pilot retained 94.
A rank97 live KM-short snapshot left the old span; AE93 quotient ranks were 25/25/0.
Those coordinate statements are not full-algorithm inequivalence results.
Fifteen compressed coset93 outputs all deduplicated to known KM93; they were not new93 basins.
Global active-pair compression detects dependencies crossing blocks missed by local slice factorization.
Its 15 ERROR rows were misselected verification-report JSON, not invalid mathematical certificates;
58 valid inputs were processed and no winner appeared.

Full-span wide search retained 93, accepting 6 of29,095,334 long-support proposals.
Later long-biased H16/H32 trials also retained 93: **89/243,279,196** and **582/243,567,106** long-support acceptances.
Those counters describe particular walks, not multiplication speed or a controlled runtime benchmark.
Exact pair-block enumeration exhausted **42,887,691 unordered blocks per source** on KM/AE/public095.
All three returned **NO_TARGET** for the fixed source and supplied short-direction catalog.
Wider catalogs also completed NO_TARGET, 43,529,115 pairs/source.
NO_TARGET requires complete contiguous catalog coverage; partial wall/signal/pair-limited scans are UNKNOWN.
Atomic two-direction vector optimization is exact, but failure is not global UNSAT.
[Pair-block scope and resume semantics](KERNEL_PAIR_BLOCK.md).

| Small conditional SAT source | Unique local UNSAT / planned | Unresolved unique | Solver queries / UNKNOWN retries |
| --- | ---: | ---: | --- |
| KM93 | 149/156 | 7 | 170 /21 |
| AE93 | 153/153 | 0 | 153 /0 |
| Public015 | 156/157 | 1 | 159 /3 |
| Public095 | 156/158 | 2 | 162 /6 |

Only unresolved cases retry; UNKNOWN query counts are not counts of distinct neighborhoods.
Larger conditional KM/AE trials ended UNKNOWN, with 14/28 local UNSAT query counts respectively.
All negatives fix recorded outside-baseline variables on a full tensor formula.
The newly prepared extended family has **1,541 pairs, rank 371, nullity 1,170**, five new directions of lengths 4,4,9,9,9.
All three extended-family cases completed **NO_TARGET**, each exhausting **43,575,780 pairs**; this remains a finite fixed-model negative, not global UNSAT.

## Validation, lifecycle correction and proof boundary

The first full suite ran 387 tests with two hard-timeout cleanup failures.
Forked children inherited flag-only SIGTERM/SIGINT handlers, delaying termination.
The correction restores default child handlers and uses 0.1 s termination grace before kill/reap.
[Lifecycle provenance](../../artifacts/rl_campaign_20261102T210735Z/solver-worker-lifecycle-ready-v1/READY.json)
records unchanged mathematical encoding/RREF AST and untouched earlier frozen snapshots.
New free-factor source SHA256: `2f7456f11b2d194f33a61ca5c41d99e3a5b4e1378790910ebbca8f5550569761`.
New XOR source SHA256: `f9ff3054ee8efede170c2392cff34c97b38620cfe04f209c07ee0460f7344321`.
The full rerun passed **390 tests**, launched 02:33:51 and completed about 14 s later;
[log](../../artifacts/rl_campaign_20261102T210735Z/final-unit-suite-v2-job.log), [limiter result](../../artifacts/rl_campaign_20261102T210735Z/final-unit-suite-v2-job.result.json).
The first inverse audit's source/input manifest was captured/reconstructed after execution;
historical input selection remains explicitly uncertain and its original result was not rewritten.
A fresh 24-input audit applied six expected100→95 controls, best95, no winner.
Auxiliary V1's policy-read/cooldown bug was corrected; V3 caps active states at 109.
[H32 postcompression](../../artifacts/rl_campaign_20261102T210735Z/h32-pair-postprocess1/summary.json) finished all 20 eligible rank 122–125 inputs: 20 DROP, best 93, no winner, 4.676 CPU/4.684 wall seconds.
No record certificate triggered a new Lean proof: **no new Lean theorem is claimed**.
[Existing Lean infrastructure/trust audit](../../lean/README.md) distinguishes generic correctness,
certificate checks and the native-evaluator trust boundary; [core audit](../../lean/CoreAudit.log).
Additions, numerical stability, practical multiplication runtime and integer/complex lifts were not established.
[Predeadline independent rechecking](../../artifacts/rl_campaign_20261102T210735Z/predeadline-best-verification/result.json) at 02:55:58 validated five 93-product sources: KM, AE and three new pair-outsider states.
Each passed all 15,625 coefficients plus 64 random products using the standard-library-only verifier; no improved product bound was present.
[Augmented new93 WU stencil SAT](../../artifacts/rl_campaign_20261102T210735Z/coordinate-native-new931/result.json) finished **UNKNOWN/controlSAT**; the final UV 360-second query also completed **UNKNOWN/controlSAT**, exit 0; no target candidate was found.

## Final stop, checkpoints and accounting

[Final run summary](../../artifacts/rl_campaign_20261102T210735Z/final_run_summary.json) records `budget_exhausted`; queue stop is `global campaign deadline reached`.
[Guard stop](../../artifacts/rl_campaign_20261102T210735Z/guard_stopped.json): **2026-11-03 03:07:35.972347 UTC**; active registrations **0**.
Learner V4-10 exited 0 with limiter `timed_out=true`, saving a clean deadline checkpoint: **6,881 main steps, 23,790 updates, best 93**.
[Final checkpoint](../../artifacts/rl_campaign_20261102T210735Z/learned-v4-10/checkpoint.json) SHA256 `12c12313fe37e18226a0cbc11b4ec4381ea319828cb7ce732864659ef87f6e8c`;
its [matching schedule](../../artifacts/rl_campaign_20261102T210735Z/learned-v4-10/checkpoint.schedule.json) is required for any newly authorized continuation.
The evaluated 02:54:24 snapshot had 22,861 updates; **the final 23,790-update checkpoint was not evaluated**.
Core 1/core 2 final native jobs exited 0 at clean caps; final augmented UV SAT exited 0 with UNKNOWN/controlSAT.
CPU2's fixed2-long4 was intentionally stopped partially around 02:34:47 and reallocated, not mathematically refuted.
Random-record4 ended naturally, followed by new93 native allocations; these are not matched policy-causality experiments.
Auxiliary V3 stopped at the global deadline after **1,035 processed sources**, observed mean CPU fraction **0.01989**.
[Final collector](../../artifacts/rl_campaign_20261102T210735Z/report-final/report.json): 112 job rows, reported best 93,approximately 0.13082 CPU s;
[resource/status CSV](../../artifacts/rl_campaign_20261102T210735Z/report-final/jobs.csv) keeps launcher/solver/control statuses distinct.
Registered-group peak summed RSS was **680,140,800 bytes**, not a process-identity-aware whole-workspace peak.
Dictionary outer rusage 4.593932 s omitted its solver grandchild; **891.78 CPU s** remains separately reconstructed.
Reported CPU totals retain that limitation; summed overlapping job wall times are not campaign duration.
The full **390-test PASS** and frozen **53/55/51 evaluation** above are completed validation, not mathematical-record evidence.
[Final handoff](../../artifacts/rl_campaign_20261102T210735Z/HANDOFF.md) specifies continuation only with a **new authorized budget/deadline and new job IDs**.
[Selective final checksums](../../artifacts/rl_campaign_20261102T210735Z/final_checksums.json) are written after this document's finalization.
The completed campaign found **no improved bound**; its finite negative results do not settle rank 92 existence.
