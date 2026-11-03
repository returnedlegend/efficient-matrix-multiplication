# Fixed-two-cube long profile v1

This separate wrapper keeps the exact worker, 95/98-rank seed checks, cyclic closure, exactly two fixed cubes, independent exact checkpoint verification, immutable certificate hashes, source and worker provenance, bounded archive, periodic scan and unconditional final drain of the original fixed-cube wrapper.

Defaults: PLUS every 50,000 worker steps; RESET every 100,000,000 worker steps; max rank = initial rank + 6 (101 for rank95, 104 for rank98); archive size 16; phase budget 600 wall-clock seconds; target rank92. PLUS/RESET are scheduling intervals, not accepted-move counts or durations. Phases still reinitialize when their wall-clock budget ends; actual RESET counts are determined by worker statistics. These parameters explore longer walks and do not establish better discovery rates.

Bounds: PLUS and RESET integers 1..1,000,000,000,000; headroom integer 1..9, keeping the previous maximum 107; archive size 1..32; finite positive wall-clock budgets. CLI target is fixed to 92. The archive admission/drain policy is otherwise unchanged, including per-bucket verified-certificate caps.

Use the exact preexisting frozen binary: ../fixed-cubes-worker-v1/native/flip_worker_fixed_cubes, SHA256 d6d136e1b4539de619da2e7a6358a8425927218ecc2cc46b52e44ca4197211ab. No worker/source module or prior wrapper was changed. The snapshot wrapper needs repository imports; run from the repository with PYTHONPATH=$PWD if executing the snapshot path.

Launch from repository (fill seed, pool, output and budgets from the controller):

```sh
taskset -c 2 python scripts/campaign_fixed_cubes_long.py --binary artifacts/rl_campaign_20261102T210735Z/frozen/fixed-cubes-worker-v1/native/flip_worker_fixed_cubes --input SEED.json --pool POOL --output-dir NEW_OUTPUT --seconds BUDGET --phase-seconds 600 --seed SEED_NUMBER --plus-every 50000 --restart-every 100000000 --headroom 6 --archive-size 16 --target 92
```

Validation (all pinned CPU2): three unittest cases passed in 0.018s, covering default/custom worker argv and provenance, final drain, invalid CLI bounds, exact positive target drain. Frozen native planted 2x2 control rank11 to rank8 reached target after one step with long-profile intervals; exact independent final drain froze a valid two-cube cyclic target. Worker elapsed 0.000343s. No long search was started by this task.
