# A cyclic search branch with two fixed cubes

The November 2 campaign snapshot motivated changing the starting algebraic
profile rather than only extending its native time budget. At inspection,
learned-v1 had 150 native calls and 239,096,652 attempted moves, and random-v1
had 149 calls and 236,667,420 attempted moves. Every reported best was rank 93.
The cyclic initial worker had approximately 113.2 million attempted moves;
353 stored cyclic input/best/archive files had rank 93 with three fixed cubes
and 30 three-cycles, and one current file had rank 96 with three fixed cubes
and 31 three-cycles. These are observations at inspection, not final totals.

The exact F2 identity

```
a⊗a⊗a + b⊗b⊗b
  = (a+b)⊗(a+b)⊗(a+b)
    + C3(a⊗a⊗b) + C3(a⊗b⊗b)
```

replaces two distinct fixed cubes with one fixed cube and two three-cycles.
Here `C3` sums the three cyclic rotations. Expanding the right side cancels
all six mixed terms over F2 and leaves the two original cubes. The identity
adds at most five essential products; cancellation can make it cheaper.

Applying it to each of the three pairs among KM93's fixed cube masks
`16777217`, `262208`, and `4096` produces three distinct cyclic rank-98
decompositions. Each has exactly two fixed cubes and 32 three-cycles, no zero
factors, and no duplicate terms. Every resulting certificate was independently
checked at all 15,625 tensor coefficients. Full cube masks and representative
three-cycles are recorded in each candidate's metadata.

With two fixed cubes, a cyclic rank-92 certificate could have 30 three-cycles:
`92 = 2 + 3*30`. With exactly three fixed cubes, the term count is divisible by
three. This arithmetic permits the proposed target; it does not establish its
existence. The preserved C++ worker enforces C3 closure but does **not** constrain
the fixed-cube inventory. The sampled three-fixed-cube profile was empirical.
The new branch starts with two fixed cubes and permits subsequent inventory
changes, reporting the actual inventory rather than assuming an invariant.

`mmsearch/cube_polarization.py` implements the identity and optional simultaneous
GL conjugations. Conjugating all three factors by the same elementary invertible
matrix preserves the trace tensor, C3 closure, term count, and fixed-cube count.
These variants supply coordinate diversity but are mathematically equivalent
algorithms, so they are not claimed as structurally inequivalent discoveries.

The seed generator writes a fresh output directory exclusively, with certificates
under `seeds/`, independent reports and checksums under `verification/`, a
source/code-hash manifest, and a standalone `verify.py`:

```sh
python scripts/prepare_cube_polarization.py --input artifacts/km93_f2.json \
  --output-dir artifacts/new-polarized-seeds --conjugates 0 --seed 917
```

The campaign's three frozen seeds are in
`artifacts/rl_campaign_20261102T210735Z/polarized/seeds/`.
The separate `scripts/campaign_polarized.py` accepts these verified rank-98,
two-fixed-cube sources, cycles maximum rank headroom through 3, 6, and 9 above
the input, and uses at most 32 native archive entries. It retains verified
diversity in the rank 93–95 and 96–98 ranges, records actual orbit inventories,
writes periodic native statistics, and keeps a pointer to the best independently
verified branch certificate. Every target is drained after worker exit, including
a process that succeeds before polling. Target certificates and independent
verification are frozen before handoff. Existing campaign and worker files are
unchanged.

A three-second smoke campaign on CPU 2 completed three bounded phases, exporting
six distinct exact candidates. Its best reached **rank 95 with two fixed cubes
and 31 three-cycles**. This is branch progress from rank 98; the known rank-93
baseline remains better. The smoke files are in
`artifacts/rl_campaign_20261102T210735Z/polarized-smoke/`.

Five focused tests cover all 105 distinct pairs of nonzero four-bit cube
factors, all three KM93 polarized seeds, exact involutory GL conjugations,
successful final target draining, and rejection of a corrupt final checkpoint:

```sh
python -m unittest tests.test_cube_polarization tests.test_campaign_polarized
```
