# Fixed-budget empirical recovery pools, version 3

Version 3 adds new files only. The running/frozen v1 and v2 implementations are
unchanged. It replaces trivial freshly split recovery starts with immutable
exact states screened by explicitly bounded native probes. Failure of a probe
means **unknown within that probe**, not a tensor-rank lower bound, inherent
hardness, or a new result.

## Preparing and freezing a pool

`scripts/build_hard_recovery_pool.py` mixes exact verified known-rank seeds.
For the 5x5 campaign, accepted mixing states have 94 through 100 essential
products, with tight/medium/wide caps cycling through 94, 96, and 100. Rank-93
returns are rejected during mixing; a proposed exact state at rank <=92 is
independently verified, frozen, announced, and stops preparation. Mixing uses
10,000 shared-factor flip/plus attempts by default in the campaign command,
with optional greedy-reduction mixing disabled. Every proposal is checked as
an exact integer-bit tensor; independent checks accompany periodic states and
the final task. All terms remain over F2.

Each generated task receives an `exploit` probe targeting the known rank 93,
with an exact budget of 50,000 attempted native moves. The wall cap is an
additional bound; an interrupted probe is `incomplete_probe`, never treated as
an unsolved complete probe. Metadata includes initial/best rank, first
improvement step, attempted moves, fixed step budget, seed, CPU/wall time, and
frozen native artifacts. A first improvement before move 100 is excluded by
the default early-progress filter. This threshold is explicit and adjustable;
it reflects the first profile's plus-schedule difference, rather than a proof
that every other profile has acted differently by that time.

Tasks failing a complete probe without disqualifying early progress enter the
`hard_unknown` bucket. Tasks reaching the known bound after at least 2,000
moves without disqualifying early progress enter a separate `delayed_control`
bucket. Other trials are retained as rejected metadata, with their native
input/output provenance. Every retained task is also probed with `explore` and
`long_walk` from the same exact start and probe seed. Any exact <=92 result in
any best/current/archive output is preserved as a genuine record and stops the
job. A profile-distinction flag compares censored outcomes and achieved ranks;
raw move counts also capture latency differences when all profiles succeed.

For example, under the campaign's registered resource harness:

```sh
python scripts/limited_worker.py --cpu 0 --memory-mb 768 --seconds 615 \
  --prefix artifacts/rl_campaign_20261102T210735Z/hard-pool-gen-job -- \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python scripts/build_hard_recovery_pool.py \
  --initial artifacts/km93_f2.json \
  --initial artifacts/rl_campaign_20261102T210735Z/public/alphaevolve93_f2.json \
  --output-dir artifacts/rl_campaign_20261102T210735Z/hard-pool-v3-build \
  --cpu 0 --seconds 600 --max-candidates 120 --max-tasks 40 \
  --mix-steps 10000 --probe-steps 50000 --seed 751 --memory-mb 512
```

Freeze a completed source manifest at a phase boundary:

```sh
python scripts/freeze_recovery_pool.py SOURCE_POOL_DIR NEW_VERSION_DIR
```

To combine completed wide and tight sources, first create a separate manifest
with `python scripts/combine_recovery_pools.py WIDE_DIR TIGHT_DIR --output-dir
NEW_COMBINED_DIR`, then freeze that new directory. The combined manifest retains
all accepted and rejected trials, original trial identifiers, source-manifest
hashes, and each source's configuration; inputs are never changed.

The snapshot validates independent exactness and task checksums, deduplicates
term sets, copies immutable task payloads, and saves the source manifest hash,
all retained trial/probe metadata, source identities, and split. The source
manifest retains rejected trial metadata. The frozen version is never extended
while being trained; a later larger source requires a new snapshot/version.

Held-out selection is deterministic: sort by SHA256 of
`v3-heldout:` plus the term-set hash and reserve approximately 20%, at least two
when there are at least ten distinct tasks. At least one hard task stays in
training. Stratification reserves at least one hard held-out task when there
are two or more hard tasks, and at least two when there are five or more.
The loader checks disjoint train/held-out sets and task checksums;
the sampler can never select held-out tasks. Small versions with fewer than
eight hard training tasks or two hard held-out tasks explicitly carry
`small_pool=true`, so they cannot substantiate generalization claims.

## Matched training

`scripts/train_pool_tensor_agent.py` starts both arms from the same **original
warmed v1 checkpoint**, not the model trained on trivial v2 recoveries. It uses
the existing contextual actor-critic and actual `dm_env` FIRST/MID/LAST step
API. The main exact trajectory, monotone best, RNG, and archive persist across
recovery tasks.

Only recovery gets a `FixedStepBridge` wrapper with 50,000 attempted moves per
action. Main record-search actions retain their two-second native budget and
large step limit. They use separate native bridges: `native-dir/record` retains
eight archive representatives by default, while `native-dir/known-recovery`
retains one. `--recovery-archive-size` permits 1 through 8 without changing the
record bridge. Both bridges' archive settings and binary/source/code hashes
are part of the checkpoint and scheduler identity. The recovery step limit must equal the frozen pool probe
budget. Recovery episodes stop at success, four actions by default, ten wall
seconds, or the global job budget, whichever occurs first. A truncated episode
is explicitly censored; it does not claim nonexistence or a failed proof.
Delayed controls occupy at most one of every five recovery episodes. The
remaining episodes use hard-filtered tasks. All task hashes, buckets, actual
action attempts, censoring, outcomes, and CPU costs are logged.

Ordinary known-rank recovery rewards and record-discovery promotion follow v2:
rank-93 recovery is labeled, the 1000-point terminal bonus is removed before
learning, and it is not counted as a new record. Any <=92 discovery receives
independent verification, immutable preservation, main-state promotion, and
terminal freeze. Global novelty remains unique across tasks and capped at 25;
reusing a pool task cannot earn repeated novelty for an already seen state.
On-policy rollouts are flushed before another task changes shared weights.

Example:

```sh
python scripts/train_pool_tensor_agent.py \
  --resume artifacts/rl_campaign_20261102T210735Z/warm/checkpoint.json \
  --cpu 0 --seconds 1800 --recovery-pool NEW_VERSION_DIR \
  --recovery-step-limit 50000 --recovery-max-actions 4 \
  --recovery-fraction 0.2 --recovery-seconds 10 --native-seconds 2 \
  --checkpoint ARM/checkpoint.json --output ARM/best.json \
  --events ARM/events.jsonl --native-dir ARM/native
```

The control arm uses the same frozen pool and original warm checkpoint, with
separate paths and `--control random` or `--frozen`. Use the campaign resource
harness for sustained jobs. Pool manifest SHA256, path, known target, fixed
recovery budget, action cap, held-out count, and small-pool label accompany the
atomic main checkpoint and hashed scheduler sidecar. Resume rejects pool or
censoring changes and mismatched/missing scheduler state. Main actions remain
the same three/four native profiles; the action dimension is unchanged.

## Evidence and limits

The first 1,000-step mixing pilot generated 12 tasks; all recovered the known
bound, 11 had initial progress before 100 moves, and no hard task was retained.
The 10,000-step pilot generated ten tasks in 55 seconds: one hard-filtered task
and two delayed controls. On one AE-derived rank-94 task, `exploit` failed all
50,000 moves, while `explore` recovered at 11,340 and `long_walk` at 37,438 under
the same start/seed. This demonstrates a usable finite-budget distinction,
not a statistically established preference or learned advantage.

In a subsequent actual-driver smoke using new seeds, the single hard task
recovered in all six episodes, using 2,900 through 21,025 moves. Thus a task
selected by one failed probe can still be easy under other random seeds.
Repeated-seed screening and held-out evaluation are needed before claiming
useful learning. The source pool and snapshot retain this distinction rather
than labeling empirical failure as intrinsic hardness.

Evaluate frozen learned, random, and original warm policies on the same
held-out starts, independent probe seeds, and fixed move budgets. Compare
censored recovery rates, moves/CPU to known recovery, rank progress, and
main-search record events separately. Weight updates, perfect training-pool
success, and action-probability shifts alone do not establish transfer.

Single-archive recovery calls still emit complete best/current/input/stats and
independent verification. A six-call native smoke measured 473,631 bytes/call
and 0.083 measured CPU seconds/call. At a 20% share of two cores, extrapolation
over six hours gives approximately 49 GB of recovery files; real sizes and
costs depend on tasks. A read-only compression experiment preserved and
hash-checked all 84 files from those calls: 2,841,784 raw bytes became 209,378
bytes in a level-1 gzip tar, with 0.036 CPU seconds for compression plus
verification. Raw files were not deleted. Completed recovery runs can be
losslessly archived at phase boundaries with checksums and path mappings;
the driver itself deletes no artifacts. Keep genuine record/winner artifacts
preserved and reserve disk headroom before sustained jobs.

Tests:

```sh
taskset -c 2 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m unittest tests.test_recovery_pool tests.test_rl_pool_curriculum -v
```

Fifteen tests cover exact bounded mixing, complete-probe censoring, early
progress metadata, genuine record capture, invalid-input rejection, immutable
objects, recovery-only move caps, deterministic held-out isolation and quotas,
checksum/version rejection, and exact checkpoint resume with pool identity.
Separate bridge identity and recovery archive bounds are also checked.
