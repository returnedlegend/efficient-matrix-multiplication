# Continual known-recovery curriculum, version 2

The v1 implementation remains frozen in `mmsearch/rl_search.py` and
`scripts/train_tensor_agent.py`. Version 2 lives in `mmsearch/rl_curriculum.py`
and `scripts/train_tensor_curriculum.py`; it imports v1 without editing it.

Every action in the v2 driver runs through the installed DeepMind `dm_env`
API: `ContextDmEnv.reset()` produces a FIRST TimeStep, and `.step(action)`
produces MID or LAST TimeSteps with rewards and observations. Event logs record
the actual step types. This is API integration, not the original AlphaTensor
environment or a reproduction of its training.

The 18 v1 features are extended by a binary `KNOWN_RECOVERY` task indicator
and remaining global novelty budget / 25. Checkpoint migration appends two
zero-weight rows to the input matrix and zero Adam moments, preserving the
original policy probabilities and critic values initially. Context weights
then learn through the same actor-critic updates. Parameter dictionary order
is restored explicitly so gradient accumulation, clipping, and resumed
optimization are bit reproducible under fixed injected CPU costs.

The main `RECORD_SEARCH` trajectory and its monotone best decomposition persist
across curriculum episodes. The scheduler targets 20% of measured CPU for
separate `KNOWN_RECOVERY` episodes. Each starts from a supplied exact 93-product
seed, applies exact GL/plus/flip perturbations, and checks that the resulting
start contains 94 through 100 essential products. The recovery target is the
already supplied rank 93. The controller can never infer an improved record
merely from solving this recovery task.

Recovery pays 100 per verified product removed from its episode's best, as v1
does, but the ordinary known-target terminal bonus is removed **before the
gradient update**. All recovery events and certificates identify the task and
mark `record_target_reached=false` unless a genuine record is independently
verified. Recovery episodes have a bounded wall budget (10 seconds by default)
and explicit truncation; partial rollouts are learned with critic bootstrap
before changing tasks. Main rollouts are likewise flushed before recovery
gradients update the shared policy. This avoids mixing stale on-policy
trajectories across intervening policy changes.

If recovery jumps to **92 or fewer**, independent exact verification takes
precedence over the task label. The 1000-point record terminal bonus is retained,
an immutable certificate plus independent report is written under `records/`,
the record is promoted to the main controller, and the main controller freezes.
The general test covers an exact rank-9 2x2 starting state whose recovery target
is 8, then a mocked exact jump to Strassen rank 7: it must be a real record
relative to the declared record target 7. Promotion is dimension independent.

Novelty uses one shared global visited-term-hash set across all tasks and
resumes. It pays at most 0.001 per new hash, at most 0.25 per bounded segment,
and at most **25 over the whole experiment**, less than the 100 reward for one
product improvement. A new main segment starts after a recovery episode or
64 main actions; starting a segment does not reset the exact main trajectory,
best rank, or global uniqueness set. Neither revisiting a known state nor
resetting an episode earns new novelty. Novelty still means a distinct term
representation, not a proof of mathematical inequivalence.

CPU allocation uses parent user/system CPU for the whole environment step,
plus the native child's measured CPU. Preparation of recovery starts is charged
to recovery. Short recovery tasks may finish after one action; this allows many
episodes without exceeding the requested CPU fraction. Fraction tracking is
quantized by a bounded episode, so short trials can deviate. The scheduler
persists cumulative record/recovery CPU and its dedicated RNG in a hashed
`.schedule.json` sidecar. Checkpoints occur at task boundaries; there is no
unserialized active recovery task. The main checkpoint retains any main
partial rollout. Failed or interrupted actions still rely on the bridge's
independent exact verification and bounded execution.

Example, starting from the shared warmed v1 checkpoint used for the v1 A/B:

```sh
taskset -c 0 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python scripts/train_tensor_curriculum.py \
  --resume path/to/warm-v1.json --cpu 0 --seconds 600 \
  --checkpoint artifacts/v2/learned.json --output artifacts/v2/learned-best.json \
  --events artifacts/v2/learned-events.jsonl --native-dir artifacts/v2/learned-native \
  --native-seconds 2 --native-archive-size 8 --known-rank 93 \
  --recovery-fraction 0.2 --recovery-seconds 10
```

Use a separate output/native/event directory and the same warmed input for a
matched `--control random` or `--frozen` run. Both arms retain the same recovery
fraction, perturbation procedure, target, and per-action budgets. Recovery
successes, main best rank, and genuine record events must be reported separately.
An arm can execute different numbers of episodes because actual action costs
differ; compare measured CPU fractions and budgets, rather than raw episode
counts. Curriculum success or changed weights alone does not establish a
learning advantage over the matched control.

Resume a v2 run using its `.json` checkpoint with its `.schedule.json` sidecar
in place. To migrate v1, supply the v1 checkpoint; context and a fresh scheduling
RNG are initialized while retaining policy/RNG/current/best/seed state. The CLI
sets all native action masks explicitly to native only and caps representative
archives at eight states per action by default. It writes main certificates,
independent verification, and a standalone verifier on clean exit. As with v1,
reserve one bounded native action plus verification margin before a hard global
deadline. This driver starts no detached process and uses no paid compute or
network resources.

Publishing a v2 controller checkpoint stages the parent's intermediate payload
under a private random path and atomically replaces the live checkpoint only
after adding the full context and global ledger. An interruption leaves either
the old v2 checkpoint or the complete new v2 checkpoint. The scheduling sidecar
is separately atomic and hashes the controller checkpoint. A missing or stale
sidecar for v2 fails closed before training; the driver does not silently reset
the scheduler or global budget. A crash between the two file publications can
therefore require restoration of a matching saved pair, rather than automatic
continuation from inconsistent state.

Validation:

```sh
taskset -c 2 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m unittest tests.test_rl_curriculum -v
```

Ten tests cover context migration, actual dm_env FIRST/LAST transitions,
known-recovery terminal reward subtraction before learning, record-jump
promotion and bonus retention, exact inflated perturbations at dimensions
2/3/5, shared novelty deduplication/caps across episodes, v1 migration, and
bit-exact v2 optimizer/RNG/partial-rollout resume.
Additionally, interrupted publication tests prove the old-or-final-v2 property,
and missing/mismatched scheduler sidecars fail closed before continuation.
The three-second native smoke
trial executed 25 actual dm_env transitions, recovered 12 known small tasks,
performed 24 updates, and measured 19.2% recovery CPU; its main result remained
an exact research checkpoint, with no claim of a new record. A subsequent native
resume smoke completed successfully from the saved v2 checkpoint and sidecar.
