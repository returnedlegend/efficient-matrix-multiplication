# COMPLETED: six-hour exact 5×5 F₂ RL campaign — budget exhausted

Workspace: `/workspace/efficient-matrix-multiplication`; campaign: `artifacts/rl_campaign_20261102T210735Z`.
Authorized interval: **2026-11-02 21:07:35 UTC–2026-11-03 03:07:35 UTC**.
Limits: **four CPU cores and 8 GiB total RAM**, local CPU work only. Do not extend the deadline or publish results.

**Completed: budget exhausted; global guard stop2026-11-03 03:07:35.972347 UTC. Best verified rank93; no WINNER or verified≤92 result.** Imported/recovered rank93 identities are references or known recoveries, never new records. All coefficient claims concern F₂ unless explicitly labeled integer.

## Final state — authorized budget exhausted

[Final run summary](final_run_summary.json): campaign state **completed**, stop reason **budget_exhausted**; deadline **03:07:35 UTC**, [guard global stop](guard_stopped.json) **2026-11-03 03:07:35.972347 UTC**. Queue stopped for `global campaign deadline reached`; **zero `*.running.json` registrations** remain. No WINNER/new record; best93. [Completed standalone report](../../research/rl/SIX_HOUR_REPORT_20261103.md).

The final learner [checkpoint](learned-v4-10/checkpoint.json) has **6,881 main steps,23,790 updates,best93**, SHA256 `12c12313fe37e18226a0cbc11b4ec4381ea319828cb7ce732864659ef87f6e8c`, with [matching schedule](learned-v4-10/checkpoint.schedule.json). Limiter exit0/`timed_out=true` reflects a clean deadline save. Final core1/core2 native jobs exited0; final UV SAT is UNKNOWN/controlSAT,exit0. The completed frozen evaluation **53/55/51** applies only to the02:54:24 checkpoint with22,861 updates, **not the final learner**. Full390-test validation remains PASS.

Auxiliary V3 stopped for the deadline,1,035 sources processed,observed mean fraction0.01989. Guard registered-group peak RSS **680,140,800 bytes** is not a whole-workspace peak. [Final collector JSON](report-final/report.json)/[CSV](report-final/jobs.csv) contain112 jobs; dictionary grandchild891.78 CPU seconds remains separately reconstructed from outer4.593932. [Selective final checksums](final_checksums.json) are generated after these document edits.

**The completed queue cannot be resumed as-is. New search requires a new explicitly authorized budget and deadline, a new campaign directory/configuration, and new job IDs/output prefixes.** Do not restart watchers against the expired campaign. Once a new interval is authorized and its `campaign.json`/reviewed queue are configured, use the same source-preserving procedures with the NEW path:

```sh
python3 scripts/campaign_guard.py NEW_AUTHORIZED_CAMPAIGN
python3 scripts/rl_campaign_queue_v2.py NEW_AUTHORIZED_CAMPAIGN
```

These are continuation templates, not authorization to launch now. V4 continuation uses the final checkpoint **and its matching schedule**, recovery0.2, identical seed order/pool and a fresh checkpoint/output prefix under the new deadline. Frozen record-only reference continuation uses its own coherent checkpoint/schedule and `train_record_reference.py --recovery-fraction 0 --control random --frozen`. Preserve old result directories and attempted IDs. The exact historical argv extraction below remains read-only; old wall budgets/deadlines must never be replayed as new authorization.

## Historical known results through 03:02 UTC


**No record as of this cutoff; global best93. Do not declare completion before03:07:35 or without the actual stop confirmation.** The [standalone report](../../research/rl/SIX_HOUR_REPORT_20261103.md) now incorporates completed validation/evaluation; only actual deadline outcome, still-running checkpoints and final accounting/checksums remain pending.

[Final frozen evaluation](eval-final-analysis.md) is complete: the **02:54:24** checkpoint (`dc3ef6139dc997472bc28eb47f71406c5549617e23d1316ac8694880c7a104eb`,22,861 updates/6,612 main steps) scored **53/64 learned,55/64 warm,51/64 random** on64 matched triplets. Weights remained `4477d17450eb04afce47212451c66ec014debc7d49f66716b028e232a0d27182`,training=false. Attempts4,385,680/3,634,918/4,141,940 and CPU13.8961/12.2419/12.9518 s include censored episodes. Same four filtered tasks/two hard tasks and base seed721101 provide no convincing gain or dependable regression; later V4-10 training weights are **not evaluated** here.

All three extended1541-pair/9336-circuit cases completed **NO_TARGET**,43,575,780 pairs each. The older13-state batch was COMPLETE with13 NO_TARGET/3 family skips. [H32 postcompression](h32-pair-postprocess1/summary.json) completed all20 eligible rank122–125 inputs:20 DROP, best93/no winner,4.676 CPU/4.684 wall s. [Independent best-source verification](predeadline-best-verification/result.json) at02:55:58 checked KM,AE and three new pair-outsider93 states, all15,625 coefficients plus64 random products each, all valid. **390-test rerun remains PASS** with unchanged lifecycle-fix provenance.

Augmented new93 WU stencil SAT completed UNKNOWN/controlSAT; the UV360-second final query started **03:00:39**, still running at this cutoff. Learned-v4-10 and the final CPU2 native continuation also remain active. Random-record4 ended naturally before02:43, followed by native new93 continuation and short-source allocation. CPU2 fixed2-long4 was **intentionally stopped partially around02:34:47** and reallocated; that is not a mathematical negative. No additional searches or source edits were made for this report update.

At the03:02 historical cutoff, deadline reconciliation remained future work; it is now recorded in the final summary above. No extra search budget is implied.

## Historical state at the 02:35 checkpoint


The bounded [collector snapshot](report-snapshot-0235/report.json) was collected **02:37:55 UTC**,104 job rows, about **0.140 CPU s**, reported best **93**, no verified≤92 result. The new [standalone report draft](../../research/rl/SIX_HOUR_REPORT_20261103.md) is explicitly **IN PROGRESS** with final outcome/evaluation/resources/checksum placeholders; the authorized six hours still end **03:07:35**. Preserve approximately **02:55** for final tests/evaluation.

At this snapshot learned-v4-9 is active onCPU0, frozen random-record4 onCPU1, and **new93-core2-first** onCPU2 since **02:35:19**, replacing a partial stagnant fixed2-long4 segment. Random-record4's natural completion is expected around02:42, with a new93 allocation planned afterward; later native allocations are not matched training-policy experiments. The one-cube-unrestricted segment completed **97→93**,32 distinct retained term sets; its selected16-state pool has16 distinct factor-rank histograms and no matches to the listed references. This establishes new term sets, **not novel algorithms or a better bound**.

Short catalog pair-block trials completed **NO_TARGET on all42,887,691 pairs/source** for KM/AE/public095; wide catalogs also completed NO_TARGET at43,529,115 pairs/source. The **new93-pair-sweep1** batch is already complete at this inspection: **13 NO_TARGET +3 missing-pair family skips**, no winner,22.78 s reported elapsed. Missing-pair skips are not mathematical negatives. The extended1541-pair/rank371/nullity1170 family with five complementary directions (4,4,9,9,9) is prepared/queued; no target query had launched by02:38. [Checked preparation](pair-block-expanded-ready-v2/READY-CHECKED.json).

The first full suite ran387 tests with two timeout cleanup failures; the lifecycle-only correction restores default child signal handlers and0.1 s grace, preserving mathematical encoder/RREF AST and earlier frozen code. The full rerun **passed390 tests**, starting02:33:51 and finishing about14 s later. [Passing log](final-unit-suite-v2-job.log), [lifecycle hashes/provenance](solver-worker-lifecycle-ready-v1/READY.json). Fresh frozen RL evaluation near02:55 and final worker/collector checks remain pending.

The original inverse audit retains posthoc source/input-selection uncertainty. The new explicit24-input audit completed with six expected100→95 control reductions, best95/no winner. Auxiliary V3 cap109 leaves rawH32 rank125 states needing bounded postcompression; that follow-up is pending. No new Lean record proof was triggered. Guard02:37:53 reported164,941,824 bytes registered-group RSS,peak680,140,800; total accounting remains partial as described below. Older status sections are historical.

## Historical state at the 02:00 checkpoint


The [new collector snapshot](report-snapshot-0200/report.json) was taken **02:02:00 UTC**, 93 job rows, about 0.144 CPU s, with global reported best **93** and no verified≤92 result. Hard stop remains **03:07:35 UTC**. Reserve final tests/evaluation from approximately **02:55**, before that deadline; this is not a completed six-hour report.

| CPU | Active registered job at snapshot | Start UTC | Next queued work |
| --- | --- | --- | --- |
| 0 | `learned-v4-8` | 01:57:40 | Learned V4 continuations |
| 1 | `random-record-3` | 01:41:28 | Frozen record-only reference continuations |
| 2 | `fixed1-1` | 01:51:12 | `onecube-unrestricted1`,900 s |
| 3 | `local-fixed-pair-public0951` | 01:57:16 | Frozen pair-block KM93/AE93/public095, then larger local KM/AE |

Guard sample **02:01:40**:440,115,200 bytes summed RSS,631,877,632 peak. Registered caps total **4,096 MiB**; the512 MiB auxiliary watcher shares CPU2. Learned recovery0.2 and frozen-reference recovery0 remain unmatched allocations; fresh audit/evaluation conclusions below are unchanged.

**Primary queued experiment:** [frozen kernel-pair-block-v1](frozen/kernel-pair-block-v1/READY.json), three600-second jobs after the last small local query. Each fixed source (KM93, AlphaEvolve93, public095) requests all **42,887,691 unordered pairs** of9,262 supplied short kernel circuits. Exact optimization over two arbitrary25-bit vector shifts permits joint improvements missed by a strict single-direction move. **No long pair-block run had started at this snapshot.** Native `MODEL_FOUND` requires Python witness agreement and exhaustive full15,625-entry verification before acceptance. `NO_TARGET` means **complete coverage of that exact fixed-baseline finite pair catalog** only when the entire contiguous prefix is covered; wall/signal/pair-limited partial coverage is **UNKNOWN**, never global UNSAT. [Scope and validated resume semantics](../../research/rl/KERNEL_PAIR_BLOCK.md).

[Large local preparation](local-large-ready-v1/READY.json) has KM+AE600-second jobs queued **after those primary pair-block trials**. The prepared64-circuit unions have171–177 free groups and local nullity66–68; the maximum is177 groups/nullity68. Controls are SAT93 with all15,625 coefficients checked. These are necessary/preflight measurements, **not existence evidence**; no rank92 target queries were run during preparation. [Measurements](local-large-ready-v1/measurements.json).

**Small-local results, unique neighborhoods versus solver queries:**

| Source | Planned unique neighborhoods | Unique local UNSAT | Unresolved unique | Solver queries / UNKNOWN query attempts |
| --- | ---: | ---: | ---: | --- |
| [KM93](local-fixed-pair1/result.json) | 156 | 149 | 7 | 170 total /21 UNKNOWN |
| [AE93](local-fixed-pair-ae931/result.json) | **153** | **153** | 0 | 153 total /0 UNKNOWN |
| [public015](local-fixed-pair-public0151/result.json) | **157** | **156** | 1 | 159 total /3 UNKNOWN |
| public095 | 158 planned | Active; final result pending | Pending | Read current `latest.json`/result |

Only unresolved UNKNOWN neighborhoods retry; terminal local UNSAT is never retried. Thus21 UNKNOWN queries on KM do not mean21 unresolved neighborhoods, and3 on public015 mean one unresolved case. AE's final scope is **153**, not a guessed156. [Bounded reconciliation with hashed evidence](report-snapshot-0200/local-query-reconciliation.json). All claims retain the original outside-baseline assumptions; no mathematical rank lower bound follows. All three native-cardinality coordinate orientations completed **UNKNOWN**, controlsSAT, childrenreaped.

**Native/kernel findings:** fixed1-1 has independently verified **100→97** one-cube branch progress, not a global record. [onecube-unrestricted-ready-v1](onecube-unrestricted-ready-v1/manifest.json) selects **16 exact rank97 states with16 distinct factor-matrix-rank histograms** and removes cyclic/fixed-cube restrictions for the next900-second CPU2 segment. Its300-second phases will ordinarily try roughly three sources, not all16. Imported/derived97 seeds remain research inputs.

The completed [KM short walk](kernel-expanded-short1/summary.json) and [AE short walk](kernel-expanded-ae931/summary.json) both retained best93; the [coset94 pilot](kernel-coset94-pilot1/summary.json) retained94. The [wide/full-span walk](kernel-wide1/summary.json) also retained93: **6 accepted long-support moves /29,095,334 long-support attempts**,6,660,810,240 total attempts and41 checked checkpoints. Full span1,165 did not establish useful bounded-rank connectivity or a record. [Actual statistics](kernel-wide1/latest_stats.json).

[Fixed-family coordinate analysis](baseline-alternate-span-analysis-v1/analysis.json): AE93's quotient-direction ranks relative to old1,009/short1,096/full1,165 spans are **25/25/0**. An exact **rank97 KM-short live snapshot** has quotient rank **1 outside the old span**, zero outside the short/full spans: it did leave the old span. These are coordinate differences within the fixed WU dictionary, **not algorithm inequivalence, novelty or bounded-headroom connectivity**.

Auxiliary **V3**, PID129179, launched **01:34:58**, raises its active-state cap to109; stopped V2's **112 processed** status is [preserved](auxiliary_pair_watcher.status.v2-final.json). The02:02 observation measured **33.19 CPU s /1,627.31 elapsed ≈2.04%**, against target2.5%; this is a measured elapsed-window mean, not a universal hard cap or prediction. The exact109→93 nonrecord fixture took approximately0.099 CPU s during preparation. [V3 preparation](auxiliary-pair-watcher-ready-v3/READY.json), [launch](auxiliary_pair_watcher.launch.v3.json), [current status](auxiliary_pair_watcher.json). No winner has been reported.

The [inverse-polarization quick audit](inverse-polarization-audit1/result.json) inspected **65 rank97 states, zero matching explicit inverse patterns**. This is narrow pattern absence, not a lower bound. Root's [exact heredoc source](inverse-polarization-audit1/program.py) was captured **after** the run at 01:59:05, with [snapshot provenance](inverse-polarization-audit1/program.snapshot.json). The [input manifest](inverse-polarization-audit1/reconstructed-input-manifest.json) now exists as a **post-run reconstruction**; it explicitly says historical selection is not independently proven. No negative scan was rerun and the original result was unchanged.

[requirements-rl.txt](../../requirements-rl.txt) and [REPRODUCING.md](../../research/rl/REPRODUCING.md) record the observed nine-package stack/import checks and CPU-only continuation. **No packages were installed** for that audit. Existing collector limits, dictionaryCPU caveat, exact watcher/live-manifest restart commands and historical evidence below remain valid. Pair-block and large-local outcomes, current runs, and final evaluation remain pending.

## Historical state through 01:25 UTC


The campaign is **still running**, global best **93**, no verified≤92 certificate. The six-hour authorization still ends **03:07:35 UTC**, not six hours after any restart. The [bounded snapshot](report-snapshot-0125/README.md) was collected at **01:25:36 UTC**:

| CPU | Active registered job at snapshot | Start UTC | Next queued work |
| --- | --- | --- | --- |
| 0 | `learned-v4-6` | 00:56:11 | Learned V4 continuations |
| 1 | `random-record-2` | 01:10:40 | Frozen record-only reference continuations |
| 2 | `kernel-expanded-short1` | 01:19:47 | `fixed1-1`,900 s from exact rank100/one-cube seeds |
| 3 | `coordinate-native-vw1` | 01:19:25 | Native-cardinality UV, then `local-fixed-pair1` full-tensor local SAT |

Guard sample **01:22:56**: 524,853,248 bytes summed RSS,602,791,936 peak. Registered caps total **4,352 MiB**. The auxiliary watcher shares CPU2, capped 512 MiB; this is not a fifth core. Queued jobs have not completed.

The [coset94 kernel pilot](kernel-coset94-pilot1/summary.json) completed normally after about 298 s with raw/global best **94**,21 verified checkpoints and no winner. The current [expanded-short preparation](kernel-short-expanded-prepared-v1/READY.json) supplies **9,262 circuits spanning 1,096 kernel dimensions**, an87-dimension increase from1,009 but still69 short of1,165. The600-second walk started 01:19:47; its final result is pending. [One-cube preparation](fixed1-ready-v1/READY.json) has six verified rank100 seeds and is queued next for 900 s; one-cube cyclic counts imply a qualifying rank≤91, not evidence that such a state exists.

The [native-cardinality WU trial](coordinate-native-wu1/result.json) completed **UNKNOWN**, controlSAT, workerreaped. VW is active and UV next. All three earlier coordinate-CNF orientations, including [UV](coordinate-sat-uv1/result.json), completed UNKNOWN. The [frozen local fixed-pair repair](local-fixed-pair-ready-v1/READY.json) is ready/queued after native UV: it keeps a **full tensor formula**, fixes outside-group variables by assumptions, and has a checkedSAT93 control covering all 15,625 entries. No target query had run at preparation; pending negatives would remain local to the recorded assumptions. [Frozen local driver](local-fixed-pair-ready-v1/code/scripts/campaign_local_free_factor_sat.py).

Fresh frozen policy evaluation has **64 matched triplets: latest53/64, warm55/64, random51/64** known recoveries, versus earlier learned56/64. The [audit analysis](rl-policy-audit-0100/fresh-eval-analysis.md) supports **no convincing gain or dependable regression** on only four tasks/two hard tasks repeated over 16 seeds. Weights stayed frozen; no fitting. V4 training was retained as the existing portfolio arm. Reward-scale imbalance alone does **not** establish harmful interference or a bad policy; that would need direct attribution. Later live record-only reference allocation remains unmatched to learned recovery0.2.

Auxiliary pair watcher **V1 stopped at01:20:49** after checking 12 sources without a winner. One-second policy rereads accumulated cooldown debt/starved useful work; its intended **2.5% quota was not established**. [V2 preparation](auxiliary-pair-watcher-ready-v2/READY.json) rate-caches policy reads, uses debt-aware cooldown and measures actual CPU. The [V2 launch](auxiliary_pair_watcher.launch.v2.json) subsequently records **01:25:32, PID125897**, so it was newly active by this snapshot; its initial 3-source result has no winner. Its target 2.5% average remains a target, not a demonstrated sustained cap. [Live status](auxiliary_pair_watcher.json) and [new entrypoint](../../scripts/watch_pair_compressions_v2.py) preserve actual timestamps; V1 source was kept unchanged.

A separate [wide-kernel preparation](kernel-wide-prepared-v1/preparation.json) adds 69 directions to span the full 1,165-dimensional kernel. [Initial modal admissibility](kernel-wide-prepared-v1/modal-admissibility.json) admits only **1/69 at headroom6**,29/69 at headroom16. **It is not launched or queued at this snapshot.** Linear span completeness does not prove bounded-rank search connectivity, useful acceptance rates or rank92 feasibility.

The new [collector](../../scripts/collect_rl_campaign_report.py) reads bounded root registrations/results/queue/guard and selected immediate-child summaries/manifests. It performs **no new mathematical verification**, starts no workers and never recursively walks recovery runs. [JSON](report-snapshot-0125/report.json) / [CSV](report-snapshot-0125/jobs.csv) contain 85 rows, distinct launcher/solver/control statuses, limits, rusage and input/code hash references. Collection used about **0.158 CPU s**, CPU2/nice10. The oversized `sat-initial/manifest.json` is explicitly skipped; partial/missing/capped reads and sequential-snapshot races remain visible. Dictionary childCPU891.78 s stays separately reconstructed from outer4.593932 s; running rusage is incomplete, and summed overlapping job wall times are not campaign duration.

```sh
cd /workspace/efficient-matrix-multiplication
taskset -c 2 nice -n 10 python scripts/collect_rl_campaign_report.py \
  artifacts/rl_campaign_20261102T210735Z \
  --output-dir artifacts/rl_campaign_20261102T210735Z/report-snapshot-DEADLINE
```

This collector can be rerun at the deadline. A final standalone six-hour research report is **not yet written or completed**. Exact watcher recovery and live-manifest launch extraction below remain the continuation procedure; older observations are retained as historical evidence.

## Historical update through 01:00 UTC


The **03:07:35 UTC hard deadline is unchanged**. Actual manifests show four active jobs:

| CPU | Job | Start UTC, November 3 | Configuration / requested worker time |
| --- | --- | --- | --- |
| 0 | `learned-v4-6` | 00:56:11 | V4 learned policy, recovery fraction0.2; 1,800 s |
| 1 | `random-record-1` | 00:39:50 | Dedicated frozen random record-only reference, recovery0; 1,800 s |
| 2 | `fixed2-long3` | 00:43:48 | Strict two-cube long profile, different verified95 source; 1,800 s |
| 3 | `coordinate-sat-uv1` | 00:53:33 | Finite coordinate-stencil SAT, rank92 target; 600 s |

Current caps total **4,096 MiB**. Guard sample **00:59:47**: 465,489,920 bytes summed RSS, 602,791,936 peak. Guard PID31616 and V2 supervisor PID50467 remain live; queue stop/error fields are empty. All global best claims remain **93**, with no verified≤92 certificate. Earlier active/pending statements below are retained as **historical 23:27 observations**, superseded here.

**Reference allocation correction.** Learned V4 phases3–5 completed normally; phase6 resumes phase5. Random V4 phases1–4 completed, but **`random-v4-5` through `random-v4-10` each exited2 before search** because their requested `--recovery-fraction 0` violates frozen V4's required0.2. These are CLI/configuration failures, not six completed trials or mathematical negatives. Preserve failed logs and [interventions](interventions.jsonl). A [valid 300-second repair](random-reference-repair-job.result.json) resumed random-v4-4 with recovery0.2, completed exit0, and saved a coherent checkpoint/schedule. The dedicated [train_record_reference.py](../../scripts/train_record_reference.py) then resumed it for `random-record-1` with **`--recovery-fraction 0 --control random --frozen`**. Subsequent reference jobs use this driver, not a modified V4 entrypoint. Since this record-only allocation began, learned/reference CPU schedules are **not matched**; later raw actions, recovery rates or ranks cannot support a causal learning-advantage claim. All keep the four-source/300-main-CPU restart rule and zero reward for seed installation.

**All six free-factor trials completed UNKNOWN**, with independently exact **SAT rank93 controls**, no target model, and `worker_reaped=true`:

| Family / budgets | WU | VW | UV |
| --- | --- | --- | --- |
| Base dictionary,600 s each | [UNKNOWN](free-factor-wu1/result.json) | [UNKNOWN](free-factor-vw1/result.json) | [UNKNOWN](free-factor-uv1/result.json) |
| 1,536-pair closure,900 s each | [UNKNOWN](free-factor-wu-closure1/result.json) | [UNKNOWN](free-factor-vw-closure1/result.json) | [UNKNOWN](free-factor-uv-closure1/result.json) |

The [coordinate-stencil SAT driver](../../scripts/campaign_coordinate_stencil_sat.py) completed [WU](coordinate-sat-wu1/result.json) and [VW](coordinate-sat-vw1/result.json) as **UNKNOWN**, control SAT, solver child reaped. **UV is still active at the 01:00 cutoff**; do not infer its result. These queries restrict source-column choices and prove no global lower bound. Earlier [coordinate scan](coordinate-scan1/result.json) retained rank93; [slice scan](slice-compression-scan1/result.json) processed439 exact certificates with best93 and no winner.

**Native/kernel results.** AlphaTensor96 diversification completed with best95 branch progress; [held-three-cube run](held-cubes1/summary.json) completed with full verified best93 and no winner. Its full/global rank rule remains≤90 for a qualifying held-three cyclic result. The [first kernel walk](kernel-walk1/summary.json) completed 26,080,203,520 attempted moves,109 independently verified checkpoints, raw/derived best93, no winner. Its finite short-circuit span had dimension1,009 versus full kernel 1,165; failure is not UNSAT. Current strict-two-cube long3 best remains95.

**Global active-pair compression and coset check.** [scan_pair_compressions.py](../../scripts/scan_pair_compressions.py) solves dependencies among all active pair columns in each orientation, allowing reductions across shared-factor blocks that the older local slice factorization can miss. This is exact tensor-preserving postprocessing, not a proof of minimality. [pair-compress-quick1](pair-compress-quick1/result.json) processed **58 valid inputs**, best93/no winner. Its overall **ERROR** and15 error rows came from misselected **`verification.json` reports**, lacking certificate terms; they do **not** indicate invalid multiplication identities. The [source records](pair-compress-quick1/source_records.json) also record32 NONCERTIFICATE rows and one duplicate; the20-second budget left some discovered paths unprocessed.

Of16 coset seed inputs, **15 compressed to rank93 and one stayed94**. All15 rank93 outputs deduplicate to canonical hash **`270f411487d4a6b7e22380ea25cd2f26d699c3fea4095a8a9984dfb2f5d9ad2c`**, exactly known KM93/public seed306, verified by canonical hashing at this inspection. The [deduplicated pool manifest](compressed-coset93-pool/manifest.json) therefore contains **one known state**, not15 new rank93 basins. The cheapest [coset seed00](kernel-coset-seeds-v1/seeds/seed-00-rank94/candidate.json) remains94 in its [compression report](pair-compress-quick1/candidates/d3eda639da69ca850756734d3330013aaa3ee032ae4eba8662907727d4a793cb/report.json). A kernel pilot from that94 seed is **proposed next**, not executed by01:00; its recorded nonmembership is only relative to the old circuit span, not full-algorithm inequivalence. [Coset generator](../../scripts/generate_kernel_coset_seeds.py), [preparation result](kernel-coset-seeds-v1/result.json).

For safe continuation, retain the exact live-manifest argv extraction and watcher restart commands below. **V4 resumes require recovery0.2; record-only random resumes require the dedicated frozen reference driver and matching checkpoint/schedule.** Never reuse an attempted ID or overlap a core. No source or running code was changed for this documentation update.

## Historical allocation and evidence at 23:27 UTC

Read [queue.json](queue.json), [queue_state.json](queue_state.json), the root `*.running.json` / `*.result.json`, and [interventions.jsonl](interventions.jsonl) before any intervention. Snapshot timing does not establish future liveness.

| CPU | Registered job | Start UTC | Current purpose / requested worker budget |
| --- | --- | --- | --- |
| 0 | `learned-v4-3-job` | 23:24:05 | Learned V4 phase3, diverse record reseeds; 1,800 s |
| 1 | `random-v4-3-job` | 23:24:13 | Matched random V4 phase3, same reseeds; 1,800 s |
| 2 | `alphatensor96-native1-job` | 23:12:58 | Unrestricted native search from published AlphaTensor96; 1,800 s |
| 3 | `free-factor-vw1-job` | 23:23:46 | Fixed VW pairs, arbitrary U factor exact SAT; 600 s |

Limiter allowances add 15 s; actual results govern. Current worker caps sum to **4,608 MiB**. The 23:26:15 guard sample reported **339,156,992 bytes summed RSS**, peak **602,791,936**. These are partial dated observations. Queue continuations now cover phases through **10**, always clamped to the fixed **03:07:35** deadline; queued jobs are not completed work.

Both V4 phase1 arms completed normally near 22:53 and phase2 near 23:23:51. Phase3 resumed their own phase2 checkpoint/schedule pairs. All retain global best93. V4 preserves policy/optimizer, global best/archive/counters and cycles **AlphaEvolve93 → public015 → public095 → KM93** every **300 measured main-task CPU seconds**; migration immediately installed AlphaEvolve, and supplied-state installation earns **zero reward**. Each arm had ten cumulative external restarts by its phase2 boundary. Preserve seed order, [seed manifest](restart93-seeds/manifest.json), pool identity and checkpoint/schedule companions. Code: [train_restart_tensor_agent.py](../../scripts/train_restart_tensor_agent.py), [frozen V4](frozen/v4/manifest.json).

V3 heldout evaluation is complete: **56/64 learned, 55/64 frozen-warm, 51/64 random** known recoveries, four heldout tasks ×16 seeds and no fitting. All solved the 32 delayed-control episodes; on the two hard-unknown tasks the counts were **24/32, 23/32, 19/32**. The small task set, repeated seeds and descriptive differences do **not** establish a learning/generalization or record-search advantage. No training tasks were evaluated; weights remained unchanged. See [evaluation summary](eval-v3-1/summary.json).

The two completed [strict-two-cube long](frozen/fixed-cubes-long-v1/PROFILE.md) segments still have best **95**. They use unchanged frozen worker, PLUS50,000 / RESET100,000,000 steps, headroom6, archive16 and 600 s phases. CPU2 now diversifies with the published DeepMind **rank96** source through [campaign_variable_rank_native.py](../../scripts/campaign_variable_rank_native.py), using the preserved generic worker **without cyclic/fixed-cube constraints**. Its [best verified pointer](alphatensor96-native1/best_verified.json) is rank95: branch progress from imported96, not a global improvement. Its requested segment runs approximately 23:13–23:43. `fixed2-long3` is queued afterward. See [source note](../../research/ALPHATENSOR_SOURCE.md) and [runner documentation](../../research/rl/VARIABLE_RANK_NATIVE.md).

The restartable C3 orbit-local SAT portfolios both ended with **WALL_BUDGET**, no candidate:

| Directory | Attempts | Local bound rejection | UNKNOWN | Solver local UNSAT |
| --- | ---: | ---: | ---: | ---: |
| [orbit-sat1](orbit-sat1/summary.json) | 776 | 657 | 108 | 11 |
| [orbit-sat-large1](orbit-sat-large1/summary.json) | 63 | 7 | 56 | 0 |

The large phase reconciled completion at **23:10:15**; combined counts are 664 bounds, 164 UNKNOWN, 11 local UNSAT. Duplicate patches were skipped separately (19 small, two large). Every negative concerns selected frozen outside terms, never global rank92 nonexistence. Code: [campaign_cyclic_orbit_sat.py](../../scripts/campaign_cyclic_orbit_sat.py).

CPU3's broader [free-factor SAT](../../research/rl/FREE_FACTOR_SAT.md) fixes two factors from the dictionary while allowing an arbitrary third F₂²⁵ vector. The first WU trial completed with **UNKNOWN**, rank93 positive control SAT, hard wall limit, **worker_reaped=true**; see [result](free-factor-wu1/result.json). VW is active, UV queued next, each 600 s. [campaign_free_factor_sat.py](../../scripts/campaign_free_factor_sat.py) verifies any full candidate independently; current preflight/control outputs are not rank92 candidates.

Exact shared-factor XOR closure built three expanded dictionaries, each **1,536 distinct fixed pairs**, under [factor-pair-closure-v1](factor-pair-closure-v1/result.json). UV/VW/WU common column ranks stayed **378/365/371**; added pair counts are **377/389/402**. Original assignments remain included and every new column has exact old-column XOR witnesses ([UV](factor-pair-closure-v1/uv/witnesses.json), [VW](factor-pair-closure-v1/vw/witnesses.json), [WU](factor-pair-closure-v1/wu/witnesses.json)). This changes available active pair groups; it is **not** a multiplication algorithm or feasibility proof. [augment_factor_pairs.py](../../scripts/augment_factor_pairs.py) prepared the data without solving. Three separate **900 s** closure queries are queued after the three base orientation trials; their results remain pending.

A paper-style wrapper holding **three specific cubes** outside an arbitrary-tensor residual worker is being prepared separately; **it is not running or queued at this inspection**. Residual worker statistics would not describe a full multiplication algorithm. Any candidate must reattach the held cubes and pass exhaustive global tensor verification; the held-three cyclic branch can meet ≤92 only at **full rank≤90**. Worker residual target89 (global92 minus held3) first permits cyclic residual87, giving full90; raw residual90 gives full93 and does not qualify. The planned adjusted `walk.stats.json` must report full rank; raw `residual_walk.stats.json` stays separate. Do not infer success from raw residual counters, global impossibility from the fixed-cube ansatz, or assume unfinished helper paths exist.

The older dictionary phase exhausted its **900 s** budget, outer **BUDGET_EXHAUSTED**, positive control exact SAT at known93, **no final rank92 solver answer**. Outer rusage **4.593932 CPU s** omitted the solver grandchild; [persisted reconstruction](dictionary-new1/resource_reconstruction.json) records **891.78 child CPU s** from zombie `/proc` counters. Keep this separately reconstructed partial value, not an exact campaign total; no live orphan was observed. [Outer result](dictionary-new1/result.json).

## Monitoring, supervisor and recovery after interruption (current procedure)

The running supervisor is **[scripts/rl_campaign_queue_v2.py](../../scripts/rl_campaign_queue_v2.py)** (PID50467 confirmed through 01:00), an adapter over unchanged `rl_campaign_queue.py`. Its additional watch recognizes nested `FOUND.json` and `records/*.json` with canonical essential rank≤92. This stops further scheduling for review; it does not verify candidates or kill running workers. The independent guard remains active (PID31616 confirmed through 01:00).

The monitoring pulse is filesystem-backed, **[scripts/rl_campaign_pulse.py](../../scripts/rl_campaign_pulse.py)**. No `functions.store` state is required:

```sh
cd /workspace/efficient-matrix-multiplication
python3 scripts/rl_campaign_pulse.py artifacts/rl_campaign_20261102T210735Z
python3 scripts/rl_campaign_status.py artifacts/rl_campaign_20261102T210735Z --compact
```

The pulse atomically refreshes `live_status.json` and appends dated scalar `monitor.jsonl` entries. Compact mode avoids disk traversal; event windows can be partial and checkpoints can lag events. Detailed status additionally reports individual jobs and bounded disk scans. CPU accounting is incomplete for the dictionary grandchild as above.

If interrupted, first inspect process identities, manifests, deadline, `guard_stopped.json`, queue stop/error and winner/FOUND files. **Never start duplicate guards/supervisors or overlap a core.** Only if no matching process is live, restart the relevant watcher:

```sh
python3 scripts/campaign_guard.py artifacts/rl_campaign_20261102T210735Z
python3 scripts/rl_campaign_queue_v2.py artifacts/rl_campaign_20261102T210735Z
```

Print the exact current argv and resource configuration without launching anything (authoritative `*.running.json`):

```sh
taskset -c 2 python3 - <<'LIVE'
import json, pathlib, shlex
for path in sorted(pathlib.Path('artifacts/rl_campaign_20261102T210735Z').glob('*.running.json')):
    v = json.loads(path.read_text())
    print(path.name, shlex.join(['python3', 'scripts/limited_worker.py', '--cpu', str(v['cpu']),
        '--memory-mb', str(v['memory_mb']), '--seconds', str(v['wall_seconds']),
        '--prefix', str(path).removesuffix('.running.json'), '--', *v['command']]))
LIVE
```

These reproduce original launches, not safe automatic resumes; use fresh prefixes/directories and remaining time after confirming the old process tree exited.

The supervisor lock, durable attempted IDs and CPU/memory reservations prevent automatic repeat launches. Ambiguous outcomes remain held for review. `--once` can launch jobs and is not a dry run. The guard terminates registered groups at the deadline or above conservative **7 GiB summed RSS**; limiters clamp budgets, pin each process tree to its assigned core and enforce address-space limits. BLAS threads stay at one.

For RL continuation, use the latest role-specific `checkpoint.json` **with matching `checkpoint.schedule.json`**, same control/pool/native settings and V4 seed order, a fresh output/prefix, and only the remaining deadline budget. Do not rerun an already attempted job ID. Preserve frozen V3 checkpoints used by the evaluator. Native walkers need fresh output directories and recorded seeds. The C3 SAT portfolio has a validated `--resume --output-dir EXISTING` API with the same frozen parents/config/code and fresh bounded time; other SAT/native drivers generally do not serialize solver/RNG state. Never infer continuation commands from historical tables; exact argv are in job manifests and queue state.

## Lossless known-recovery archives

[scripts/archive_recovery_runs.py](../../scripts/archive_recovery_runs.py) compressed the first **1,000 completed runs per V3 arm**, excluding record-search targets and genuine ≤92 claims. At 22:25, both immutable archive/manifest pairs existed and all selected original run directories were absent. Archive SHA256 was independently rechecked at the 22:25 inspection; the utility verifies every member before committing and again before deleting unchanged originals. The [archive index](archive_sweeps.json) records both batches: learned 485,393,136 raw bytes →36,282,288 gzip bytes; random 486,987,057 →36,409,267. Remaining V3 runs are raw; newer V4 batches are recorded below. No claim that all recovery data is archived. Known recoveries remain recoveries after archival.

| Arm / directory | Archive basename (matching `.manifest.json`) | SHA256 |
| --- | --- | --- |
| `learned-v3-1/recovery-archives/` | `known-recovery-20261102T222153Z-b9e8cd15f2f7400e969c8963e3ecda90.tar.gz` | `0205c5a6eb7f4929c2be269747a749b52a5751620c69a3404a2b5fbc6cd92b30` |
| `random-v3-1/recovery-archives/` | `known-recovery-20261102T222156Z-56db8f61d9eb4994a7309b7a80a5764f.tar.gz` | `dc23a3371ae7d8c417689a7e5d7be40e9ae37f36cbd49fed579994bf61380dd5` |

Two further capped **1,000-run V4-phase1** batches completed successfully on CPU3 using [archive_recovery_runs_v2.py](../../scripts/archive_recovery_runs_v2.py), SHA256 `e7d4a7cf68c5d31123b6906c8c0392a149a182be96a15da8eff2e1062f037430`. V2 bounds directory selection as well as selected runs. Actual [learned log](archive-learned-v4-1-job.log) / [random log](archive-random-v4-1-job.log) report 1,000 removals each, verified archive/member hashes before deletion, and truncated selection with **2,192 /2,164 unscanned entries**, respectively. Remaining and ongoing runs stay raw.

| Arm / directory | Archive basename (matching `.manifest.json`) | SHA256 |
| --- | --- | --- |
| `learned-v4-1/recovery-archives/` | `known-recovery-20261102T231039Z-548c96eaee3c4d8795608dff062a61e4.tar.gz` | `3dadbe05273e7fd39af9a0577fd3fb4df6d778fcecd9bc1e630a8135d1b0d9c7` |
| `random-v4-1/recovery-archives/` | `known-recovery-20261102T231207Z-4c1b18c3500f4559b4455c69bdcec81c.tar.gz` | `6916878e2c9e90cc22e8883640b0efc2d5b85a0ad1cebf8785ef6fadec88cc55` |

Learned: 481,652,446 raw bytes→35,952,018 gzip; random: 487,239,408→36,385,510. The original [archive index](archive_sweeps.json) lists the first V3 batches; the newer V4 job logs/manifests are authoritative for their batches.

Restore with the matching pair into a destination ending in `known-recovery/runs` (existing differing files fail closed). Restore validates archive and all member checksums before writing:

```sh
python3 scripts/archive_recovery_runs.py restore \
  --archive PATH/known-recovery-BATCH.tar.gz \
  --manifest PATH/known-recovery-BATCH.manifest.json \
  --destination PATH/known-recovery/runs
```

## Provenance and target handling

Primary rank93 references are Moosbauer–Poole (`symmetric-flips` commit `3e2d4dd8acf831ef65c7c6b13ed787330e1e3483`) and AlphaEvolve (`alphaevolve_results` commit `4226acbf237ff9ad10ba7673a2af127a2d8a5971`). Public imports retain sources, licenses, attribution, hashes and verification. AlphaTensor's released 5×5 F₂ baseline is rank96; its full RL pipeline is not public. See [session report](../../research/rl/SESSION_REPORT.md), [DeepMind resource scope](../../research/rl/DEEPMIND_RESOURCES.md) and [bounded record check](../../research/campaign/RECORD_CHECK.md).

Freeze any ≤92 candidate, checkpoint, source/binary hashes and provenance, then independently verify all **15,625 exact F₂ coefficients**; random products are supplementary:

```sh
taskset -c 2 python3 -m mmsearch.verify PATH_TO_CANDIDATE.json \
  --random-trials 64 --seed 20261102 --export-standalone PATH_TO_VERIFIER.py
```

Novelty additionally requires broader publication comparison. SAT timeout/UNKNOWN and local or finite-dictionary UNSAT never establish global rank92 impossibility. This remains an interim campaign handoff until the authorized deadline or an explicitly recorded earlier stop.
