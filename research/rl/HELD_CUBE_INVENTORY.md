# Exact held-cube inventory with a residual native walk

`scripts/campaign_held_cubes.py` keeps the exact source cube factors outside the
native search. For independently verified cyclic KM93, H contains its three
fixed cubes and S contains the other 90 terms. H is immutable. The existing
frozen fixed-cube worker searches S with `--cyclic --fixed-cubes 0
--allow-arbitrary`, so no committed residual state can contain a fixed cube.
This preserves the cube **inventory**, unlike a full-state count-only constraint
that can change cube factors while retaining three cubes.

No C++ was changed or compiled. The validated frozen executable SHA-256 is
`d6d136e1b4539de619da2e7a6358a8425927218ecc2cc46b52e44ca4197211ab`.
Its arbitrary-tensor option bypasses only the initial test against the matrix
multiplication tensor. The code still captures `expected=tensor(best,n)` and
checks best, current, and every dirty archive against that initial residual
tensor at checkpoints. Raw native `exact=false` is therefore expected: S alone
is not a complete matrix multiplication algorithm.

The wrapper independently rejoins H with **every** scanned residual best,
current, and archive state and checks all 15,625 global coefficients before any
full certificate is exported or adjusted statistics are exposed. It rejects
noncyclic residuals, cube-containing residuals, out-of-range/duplicate masks,
rank-limit violations, overlap with H, and invalid full tensor coefficients.
The H/S join uses F2 symmetric difference and asserts no held/residual overlap.
Only full verified algorithms appear under `verified/`, with checksums and
independent reports. Diversity is capped at 32 certificates per actual full rank;
valid targets bypass the cap and freeze a root winner before stopping.

The raw native prefix is always **residual_walk**, preserving raw ranks under
`residual_walk.stats.json`, `.best.txt`, `.current.txt`, and `.archive/`. The
wrapper separately creates `walk.stats.json` only after full verification. Its
best/current/maximum ranks and target are global; its history ranks are also
adjusted, and the raw history and residual ranks remain explicitly labeled.
`exact=true` in this adjusted file refers to independently verified full matrix
algorithms, not the raw residual. Full verified mask shadows are written under
`walk.best.txt` and `walk.current.txt` for existing status/checkpoint tools.
The raw native statistics are retained byte-for-byte and checksummed by the
adjusted report. Final worker exit always triggers another drain.

The global target 92 corresponds to residual target `92−3=89`. Since a cube-free
C3 residual has a term count divisible by three, reaching that target actually
requires residual rank at most 87 and full rank at most 90. This is a restriction
of this held-inventory branch. It says nothing about global feasibility at 92.

```sh
taskset -c 2 python scripts/campaign_held_cubes.py \
  --input artifacts/km93_f2.json --output-dir PATH/new-held-cubes \
  --seconds 1800 --phase-seconds 600 --seed 93030 --headroom 6 \
  --plus-every 50000 --restart-every 100000000 --archive-size 16
```

The main CLI requires exact cyclic 5x5 rank93 with three cubes. An optional
`--pool` may contain further independently verified rank93 sources with the
identical held inventory; the explicit input starts first. The default binary
is the preserved `fixed-cubes-worker-v1` snapshot; any explicit `--binary` must
match its validated bytes. Source/full verification, H inventory, executable,
C++ source, wrapper/dependencies, commands, seeds, and hashes are frozen under a
new output directory. The native residual rank cap is its source rank plus
headroom, with a two-second shutdown reserve in the total wall budget.

Three brief tests use the frozen binary without compilation: an exact cyclic
2x2 full-rank11 source splits into two held cubes and nine residual products,
then reduces to residual6/full8; removing another complete residual orbit is
rejected by full tensor verification; and the published KM93 split verifies
full15625 equality while its residual alone fails matrix multiplication. Tests
also confirm raw rank6 never becomes reported global rank6, adjusted history
starts at full11, raw statistics remain unchanged, and every exported control
certificate verifies independently.

```sh
python -m unittest tests.test_held_cubes
```

No long run was started while preparing this branch. Frozen source/tests/docs
and the worker hash are recorded under
`artifacts/rl_campaign_20261102T210735Z/frozen/held-cube-inventory-v1/`.
