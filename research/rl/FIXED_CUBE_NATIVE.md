# Native cyclic search with a fixed cube count

`native/flip_worker_fixed_cubes.cpp` is a separate copy of the preserved v2
worker with an optional `--fixed-cubes K` constraint. The original source,
binary, and running campaign wrappers are unchanged. The option requires
`--cyclic` and rejects an input whose actual fixed-cube count differs from K.
It constrains the **count**, allowing the fixed cube factors to change.

The state tracks the number of fixed cubes incrementally during additions and
deletions. Before `State::apply` changes any slot, factor index, fingerprint,
or archive, it canonicalizes the full F2 move delta, calculates the projected
cube count, and rejects the whole move if that count differs from K. Rejected
moves therefore leave the state untouched. Archive restarts load previously
verified states satisfying the same constraint. Every checkpoint independently
checks the tensor invariant and the fixed-cube count for best, current, and
dirty archive states. Statistics record the required, best, and current counts.

This addresses the observed failure of the unconstrained polarized branch:
that worker returned to a rank-93 decomposition with three fixed cubes. A
strict two-fixed-cube cyclic state has rank congruent to two modulo three,
allowing the sequence 98, 95, 92 while excluding a three-fixed-cube rank-93
retreat. This arithmetic does not establish existence of a rank-92 algorithm.

`scripts/campaign_fixed_cubes.py` is a separate campaign wrapper. It accepts
independently exact cyclic rank-95 or rank-98 seeds with exactly two fixed
cubes, passes `--fixed-cubes 2` explicitly, and rejects any checkpoint whose
actual profile violates the count, C3 closure, or rank cap. It cycles rank
headroom 3/6/9 above the current phase input, uses at most 32 archive entries,
retains the existing bounded rank-range portfolio, and independently verifies
and drains final targets. The target remains 92. The older polarized wrapper
does not activate this constraint simply by selecting the new binary.

The campaign's `fixed2-seeds/manifest.json` records eight distinct independently
verified sources: four rank-98 and four rank-95 certificates. At collection the
longer `polarized1` campaign had no exported rank-95/two-fixed-cube certificate;
the rank-95 sources came from the earlier `polarized-smoke` campaign. Each source
path and byte checksum is recorded, preserving that distinction. All eight
certificates were checked at all 15,625 coefficients and frozen with independent
verification, full orbit inventory, checksums, and a standalone verifier.

Three native tests cover an exact cyclic 2x2 rank-11 seed reducing to rank 8
while retaining two fixed cubes, rejection of the wrong initial count before
checkpoint creation, and 250 accepted/rejected/restart moves with every traced
state independently checked for exactness, closure, and count. All best,
current, and archive files are also verified. Two wrapper tests cover a fast
successful final drain and rejection of an exact certificate with the wrong
cube count. A one-second full wrapper smoke campaign additionally checks the
actual native flag and checkpoint path.

```sh
taskset -c 0 python -m unittest tests.test_native_fixed_cubes tests.test_campaign_fixed_cubes
```

The frozen source/binary/wrapper and their SHA-256 manifest are under
`artifacts/rl_campaign_20261102T210735Z/frozen/fixed-cubes-worker-v1/`.
