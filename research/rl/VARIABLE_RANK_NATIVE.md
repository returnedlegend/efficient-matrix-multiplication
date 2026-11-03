# Native diversification from the published AlphaTensor96 baseline

`scripts/campaign_variable_rank_native.py` is a separate bounded native runner
accepting independently verified 5x5 F2 seeds of canonical essential rank
93 through 100. Its explicit input always starts phase zero; remaining pool
files are shuffled reproducibly afterward. Thus selecting AlphaTensor96 starts
that actual source basin instead of silently preferring a rank-93 incumbent.

The published source is `artifacts/alphatensor_5x5_f2_rank96.json`, attributed
and described in `research/ALPHATENSOR_SOURCE.md`. It is an imported rank-96
baseline, not a new result. Reaching rank95 or the already known rank93 from it
is branch progress. Only an independently verified rank≤92 certificate meets
the campaign target. The input bytes and source note are frozen with the run.

```sh
taskset -c 2 python scripts/campaign_variable_rank_native.py \
  --input artifacts/alphatensor_5x5_f2_rank96.json --pool PATH/seed-pool \
  --output-dir PATH/new-alphatensor96-native --seconds 1800 --phase-seconds 600 \
  --headroom 6 --plus-every 50000 --restart-every 100000000 \
  --archive-size 16 --seed 9601
```

The default binary is the preserved v2 `native/flip_worker_cyclic`, used without
`--cyclic` by default and without any fixed-cube constraint. `--binary` can select
an explicitly frozen generic worker. `--cyclic` is optional and requires complete
source orbits. The maximum rank is each source's essential rank plus headroom;
sources/configurations exceeding 109 are rejected. Frequencies are fixed by the
CLI rather than silently cycling profiles. A two-second cleanup reserve is
subtracted from each phase's available global wall budget.

Source certificates undergo independent exhaustive verification before native
execution. Zero products are removed and duplicate products cancel over F2
before essential rank is checked. The output directory must be new. Source raw
bytes/reports, the actual executable bytes, C++ source, wrapper/dependency code,
commands, seeds, and hashes are frozen. A unique phase directory holds each
input-mask file, manifest, worker log, native checkpoints, and immutable final
statistics. Periodic top-level statistics and the best verified certificate
pointer support monitoring.

The wrapper reads best, current, and every archive at checkpoints and again
after worker exit. Every newly reported decomposition is independently checked
at all 15,625 coefficients. Higher excursion states are checked but do not enter
the retained portfolio. At most 32 distinct certificates per essential rank at
or below that phase's input rank are retained, with checksums and independent
reports. Target certificates bypass this diversity cap, freeze a root winner
and standalone verifier, and stop. Fast success before polling is handled by
the final drain. Invalid final coefficients cannot become a claimed result.

Four brief tests cover published96 seed verification and invalid-source rejection,
a real 2x2 native fast-success/final-drain control, rank reduction classified as
branch progress with a bounded per-rank portfolio, and corruption rejection:

```sh
python -m unittest tests.test_variable_rank_native
```

The CLI remains strict 5x5; the 2x2 controls call only the testable helper/native
worker. No long run was started while preparing this runner.
