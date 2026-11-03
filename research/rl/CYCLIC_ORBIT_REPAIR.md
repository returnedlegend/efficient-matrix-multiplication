# Exact C3 orbit-local SAT repair

`mmsearch/cyclic_orbit_sat.py` replaces a selected patch of k complete nonfixed
three-cycles by at most k−1 cyclic orbit slots, freezing all outside terms and
the source's two fixed cubes. For a verified cyclic rank-95 source, the nominal
product cap is `95 − 3k + 3(k−1) = 92`. Actual essential rank is counted after
zero terms are removed and duplicate terms cancel over F2. New orbit slots may
be zero or fixed cubes; these are deliberately allowed. Canonical cancellation
with frozen outside terms is also allowed and can reduce the actual count.

All patch factor vectors span one shared subspace E over GF2. The same linear
retraction P onto E is used in all three modes. Since the patch belongs to
E⊗E⊗E, P⊗P⊗P fixes its tensor and commutes with cyclic rotation. Projecting any
ambient solution therefore produces a solution in E, allowing zero orbits and
cubes. Consequently this shared-space compression loses no C3-slot feasibility
for the chosen patch. It is distinct from projecting each mode into unrelated
spaces, which would generally lose the shared C3 parameterization.

For each new slot, factor coefficients U,V,W lie in GF2^d with d=dim(E). For
one representative of each cyclic coordinate-index orbit (i,j,k), the encoder
constrains the XOR of

```
U[i] V[j] W[k] + U[k] V[i] W[j] + U[j] V[k] W[i]
```

across all slots to the selected patch coefficient. Shared CNF AND gates encode
the monomials, and native XOR constraints enforce exact parity. Duplicate
monomials cancel modulo two: a diagonal cube repeats three times and leaves
one copy. It must not vanish. Every coordinate orbit has exactly one equation;
the full target is cyclic by construction.

Each slot can be rotated so its first factor is lexicographically minimal,
allowing the safe symmetry breaks U≤lexV and U≤lexW. The encoder does not force
V≤lexW, because reflection is not a C3 symmetry. Zero coefficients, zero factors,
zero slots, and fixed-cube slots are not prohibited.

Exact GF2 flattening ranks provide a cheap necessary lower bound before
nonlinear gates are built. A bound greater than 3(k−1) rejects the patch without
running SAT. Optional p=1 Koszul bounds use the existing exact implementation
on the same shared core. Passing either bound is necessary, not sufficient,
and is never reported as a successful repair.

The native-XOR backend uses one CryptoMiniSat thread with wall/conflict/memory
bounds. If it is unavailable, an explicit or automatic CaDiCaL fallback expands
the XORs into ordinary CNF. The parent enforces the hard wall bound. Returned
models must satisfy every original CNF gate and native parity before lifting.
The lifted replacement must reproduce the full ambient patch tensor exactly.
A complete candidate then undergoes the independent full n^6 verifier and the
nominal global term-count check before it can be handed off or frozen as a
winner. SAT is a result for this patch; UNSAT freezes this exact chosen outside.
Neither local UNSAT nor lower-bound rejection is a global nonexistence proof.

`scripts/repair_cyclic_orbits.py` prepares or solves one bounded neighborhood.
It selects k=2..7 nearby orbits using shared factors first, then support overlap.
Explicit sorted orbit indices may be supplied for exact replay.

```sh
PYTHONPATH=.xor-deps:. python scripts/repair_cyclic_orbits.py \
  --input PATH/verified-cyclic95-two-fixed.json --output-dir PATH/new-repair \
  --k 4 --anchor 0 --seconds 10 --conflicts 100000 --memory-mb 1536
```

`--prepare-only` freezes input, code, full problem, shared basis, selected outside,
lower bounds, source/checksum manifest, and metadata without starting a solver.
The output directory must be new. Normal solving additionally freezes the
validated model, exact candidate/report, and target artifacts when rank≤92.
The CLI subtracts preprocessing time from the solver wall budget.

Six small tests cover a planted exact C3 plus replacement (three mutable orbits back
to two, giving a complete 2x2 rank-11→rank-8 algorithm), 1D cube parity, genuine
solver UNSAT for a nonzero patch and zero slots, early flattening rejection,
allowed zero orbits, corrupted shared-AND model rejection, CaDiCaL fallback,
and the planted identity embedded into a complete 5x5 multiplication algorithm
whose decoded repair is independently checked at all 15,625 coefficients:

```sh
PYTHONPATH=.xor-deps:. python -m unittest tests.test_cyclic_orbit_sat
```

One actual rank-95 source was prepared without solving in
`artifacts/rl_campaign_20261102T210735Z/orbit-repair-prepared-k3/`. Its chosen
orbit indices [0,25,27] span dimension 8 and all three flattening ranks are 8,
exceeding the six-product replacement cap. It was correctly rejected by the
necessary lower bound. This is a local negative result for that patch, not an
UNSAT result from a solver and not a global obstruction.
