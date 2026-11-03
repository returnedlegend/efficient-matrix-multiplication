# Reproducing the bounded CPU campaign

The implemented agent is a NumPy actor-critic selecting exact native search
profiles through actual DeepMind `dm_env` reset/step calls. It is a local
operator-search experiment. The official
[AlphaTensor repository](https://github.com/google-deepmind/alphatensor) releases
algorithms and supporting code, but does not publish its complete training
stack or a pretrained policy; see [the source review](DEEPMIND_RESOURCES.md).
The accessible, independently verified starting bound is **93 products for
5×5 multiplication over F₂**. A verified bound of at most 92 would improve this
campaign's baseline. This procedure offers no guarantee of a new record.

The Git publication contains selected evidence and reusable inputs; bulk raw
run trees and native solver payloads remain in the original workspace. See
[publication scope and historical provenance](PUBLISHING.md) before replaying
historical commands or interpreting absolute paths in saved metadata.

## Environment

Use CPython 3.12 on Linux x86_64 and a C++17 compiler (`g++` is the default).
From the repository root, a fresh workspace environment can be prepared with:

```bash
python3.12 -m venv /workspace/rl-venv
/workspace/rl-venv/bin/python -m pip install -r requirements-rl.txt
export PY=/workspace/rl-venv/bin/python
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export PYTHONPATH=.
```

`requirements-rl.txt` reuses the existing NumPy 2.3.5 and SAT/XOR requirements
(python-sat 1.8.dev24, pycryptosat 5.17.0), and pins dm-env 1.6, absl-py 2.5.1,
dm-tree 0.1.10, attrs 26.1.0, wrapt 2.5.2 and six 1.17.0. These versions and
imports were checked in the current campaign, without installing packages.
Its existing pycryptosat wheel lives in `.xor-deps`; when reusing that Python
environment, set `PYTHONPATH=.xor-deps:.` instead. A fresh environment installed
from the requirements does not need that extra path.

Build the generated worker executables from their checked-in sources before
running the complete test suite or the corresponding search commands:

```bash
bash scripts/build_native.sh native/flip_worker_cyclic
for worker in flip_worker_fixed_cubes free_factor_kernel_worker free_factor_kernel_worker_wide free_factor_kernel_worker_longmixed free_factor_pair_block_worker free_factor_pair_block_worker_wide; do
    "${CXX:-g++}" -std=c++17 -O3 -DNDEBUG "native/$worker.cpp" -o "native/$worker"
done
"$PY" -m unittest discover -s tests -q
```

These are local builds, so their hashes can differ from the historical frozen
binaries. The publication includes the small frozen fixed-cube test fixture;
it does not include the generated executables under `native/`.

## Saved code, inputs and resource limits

```bash
export CAMP=artifacts/rl_campaign_20261102T210735Z
```

The historical campaign was authorized for four CPU cores, 8 GiB RAM and six
hours, ending **2026-11-03 03:07:35 UTC**. That deadline is fixed. Do not extend
it or start a duplicate worker in an occupied slot. No paid external compute is
authorized. Finite failures, timeouts and CLI configuration errors are not
lower-bound proofs or evidence that no better algorithm exists.

Before rerunning a job, match its working entrypoint and dependencies against
the SHA-256 manifests under `$CAMP/frozen/`. In particular, v4 is pinned by
`frozen/v4/manifest.json`; the separate random record-only driver is pinned by
`frozen/record-reference-v1/manifest.json`. Run the matching working entrypoint
from the repository root: the frozen copies are evidence of the source bytes,
not a separately installed package. Preserve native binary/source hashes,
pool manifests, seed bytes and seed order, phase manifests and command arrays.
The pool is `hard-pool-frozen-v3-1`, SHA-256
`4c407ce12d57274a150860a1ea6e4a113721a9707ebad54f12b8fd024f2b4a0e`.
Checkpoint and `.schedule.json` must be a coherent pair copied from a stopped
phase; resume checks reject mismatches. Never overwrite a frozen source.

Strict research resume also checks the original resolved pool path, compiled
native binary hash and source identities. A checkout at another path or a
binary rebuilt with another compiler can therefore reject resume even when
the checkpoint and schedule match each other. Preserve the original identities
for strict continuation, or start fresh training under a new configuration
and budget. Frozen policy evaluation below does not constitute training resume.
Do not relax identity checks or rewrite historical checkpoint metadata to make
a different environment appear identical.

For a later reproduction, create a **new** campaign directory with its own
explicitly approved wall budget. For example, after setting `RUN` to a new
absolute workspace path and `BUDGET_SECONDS` to that approved number:

```bash
export RUN=/workspace/rl-reproduction-new
export BUDGET_SECONDS=3600  # Example only; use the user's authorized budget.
"$PY" - <<'PY'
import datetime, json, os
from pathlib import Path
root = Path(os.environ['RUN']); root.mkdir(parents=True, exist_ok=False)
now = datetime.datetime.now(datetime.timezone.utc)
budget = int(os.environ['BUDGET_SECONDS']); assert budget > 0
config = dict(started_utc=now.isoformat(),
              deadline_utc=(now+datetime.timedelta(seconds=budget)).isoformat(),
              max_cpu_cores=4, max_ram_gib=8, target_rank=92, field=2,
              external_paid_compute_authorized=False, publication_authorized=False)
(root/'campaign.json').write_text(json.dumps(config, indent=2)+'\n')
PY
taskset -c 2 nice -n 10 "$PY" scripts/campaign_guard.py "$RUN" &
```

Keep at most four CPU slots active, each pinned to one allowed core (0–3 in
this campaign), including auxiliary work within those slots. All numerical
thread limits above remain one. Launch jobs through `scripts/limited_worker.py`
with `--prefix` directly inside `$RUN`; it reads that directory's global
deadline and clamps the worker's wall budget. The guard watches the registered
process groups, enforces the deadline and stops at a conservative 7 GiB summed
RSS threshold. Aggregate RAM caps must leave headroom under 8 GiB.
The queue supervisor is `scripts/rl_campaign_queue_v2.py`: its queue entries
hold exact command arrays and per-slot budgets; it stops further scheduling
on a reported target, while independent verification remains necessary.

## Exact verification and frozen evaluation

The following verifies all 15,625 tensor coefficients of one supplied rank-93
seed and additionally checks 64 random matrix products:

```bash
"$PY" -m mmsearch.verify \
  "$CAMP/restart93-seeds/seeds/seed01-962b518010483e3a.json" --random-trials 64
```

Expect `valid: true`, field 2 and rank 93. Equality over F₂ does not assert
equality over the integers. Each genuine proposed improvement needs the same
full exact check; retain its candidate, verification report and source hashes.

This bounded example evaluates a saved policy, frozen warm policy and random
control on the predeclared held-out pool without fitting. Use a free CPU slot,
an unused output directory and time remaining in the newly authorized budget:

```bash
"$PY" scripts/limited_worker.py --cpu 0 --memory-mb 1024 --seconds 120 \
  --prefix "$RUN/frozen-eval-job" -- \
  "$PY" scripts/evaluate_tensor_policy.py \
  --checkpoint "$CAMP/final-policy-evaluation-inputs/checkpoint.snapshot.json" \
  --reference "$CAMP/warm/checkpoint.json" \
  --recovery-pool "$CAMP/hard-pool-frozen-v3-1" \
  --outdir "$RUN/frozen-eval" --cpu 0 --seconds 90 --seeds 1 \
  --step-limit 50000 --max-actions 4 --episode-seconds 10
```

Evaluation checks that policy hashes and update counts remain unchanged.
This is the evaluated 02:54:24 snapshot with 22,861 updates; the final
23,790-update checkpoint was not evaluated. The short example above is a
smoke evaluation, not a replay of all 64 published matched triplets.
Reaching known rank 93 is labeled known recovery, not a new record. Small
held-out counts and repeated seeds do not establish broad generalization.

For training replay, recover the exact reviewed argv from the phase/job
manifests, change only new output paths and approved resource budgets, and
resume its matching stopped checkpoint/schedule. V4 learned training requires
`--recovery-fraction 0.2`; `scripts/train_record_reference.py` requires
`--control random --frozen --recovery-fraction 0`. Both preserve the ordered
AE, published-015, published-095, KM rank-93 seed cycle, with external restarts
every 300 measured main CPU seconds. These different recovery allocations are
not a matched causal learning comparison. Native main actions last at most
two seconds; training recovery actions use 50,000 attempted moves and at most
four actions per episode. Changing these identities needs a new reviewed
configuration, not edits to running code or existing manifests.
