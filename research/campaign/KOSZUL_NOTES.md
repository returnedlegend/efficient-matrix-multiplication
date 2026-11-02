# Exact local Koszul filtering

`scripts/campaign_koszul_sat.py` adds an exact p=1 Koszul bound before CNF/XOR
encoding. It uses the frozen compact encoder and scheduler through a private
function namespace; existing source modules and running processes are unchanged.

```bash
PYTHONPATH=.xor-deps:. python scripts/campaign_koszul_sat.py \
  --backend xor --symmetry u-lex --koszul-modes all \
  --input artifacts/km93_f2.json \
  --seed-dir artifacts/campaign/public-seeds/fastmatrix-f2/seeds \
  --seed-dir artifacts/campaign_20261102T164324Z/native \
  --output-dir artifacts/campaign_20261102T164324Z/koszul-xor \
  --k-min 7 --k-max 12 --seed 11 --levels 1 \
  --patch-seconds 30 --conflicts 100000 --seconds 1800
```

Use `--backend cadical` for ordinary CNF. The root resource harness supplies CPU
affinity and memory limits. Use separate output directories per backend, symmetry,
or mode selection. Reusing a matching directory resumes exact source/patch cursors.
The native XOR backend requires the separately installed optional pycryptosat
dependency. `--koszul-modes 0`, `1`, or `2` selects one axis; the default tries all
three. No p=2 branch is enabled.

## Proof, including characteristic two

Let the selected residual tensor be T in A tensor B tensor C, with a=dim(A).
Define K1(T): A tensor B* -> exterior^2(A) tensor C. For a rank-one tensor
u tensor v tensor w, this map is

    x tensor beta |-> (u wedge x) tensor beta(v) w.

If u,v,w are nonzero, wedge multiplication by u has rank a-1: its kernel on A
is the line spanned by u. Tensoring with the rank-one map beta -> beta(v)w
therefore gives rank a-1. If any factor vanishes, the map has rank zero. Matrix
rank subadditivity implies, for every decomposition into K products,

    rank(K1(T)) <= K (a-1).
    tensor_rank(T) >= ceil(rank(K1(T)) / (a-1)), for a > 1.

Exterior multiplication remains alternating in characteristic two. Repeated
indices vanish; off-diagonal signs both become plus. With columns indexed by
(i,v) and rows by ({i,j},w), the nonzero blocks are T[j,v,w] at column (i,v)
and T[i,v,w] at column (j,v). The implementation omits exterior diagonal
entries and performs all elimination using exact GF2 integer bit operations.
It tries each of the three choices for A, and also computes the ordinary mode
ranks. Ambient dimensions are never substituted for actual flattening ranks.

The tensor first passes through exact multilinear-image compression, whose
projection and expansion preserve local tensor rank. Every original residual
entry is checked before applying the bound. Thus rejecting K < the computed
lower bound proves impossibility only for this selected replacement patch.
It says nothing about a global rank92 decomposition of matrix multiplication.

## Recording and validation

Rejected patches produce `koszul_reject` records with `LOCAL_UNSAT_BOUND`, not a
solver UNSAT claim. Records include source hashes and selected terms, core hash,
matrix hashes, mode dimensions, matrix ranks, per-product contributions, inferred
local lower bounds, and timing. Counters distinguish ordinary flattening rejects,
Koszul checks/rejects/passes, solver statuses, and Koszul preprocessing seconds.
Passing patches retain their bound metadata in the normal solve record and map.
An eight-entry core cache avoids recomputing compression between filtering and
encoding; the private encoder uses the same cached core for either backend.

Tests check rank-one map rank exactly a-1, bounded sums including cancellation,
bitset matrices against an independent dense GF2 elimination, and a strict local
example: three diagonal products plus the all-ones product on 3x3x3 has all
ordinary flattening ranks3, but its Koszul maps have rank8. Thus local target3
passes ordinary flattening and is rejected by 8 > 3*(3-1). The feasible nontrivial
2x2 rank8-to-rank7 SAT control passes the filter and independently verifies.

An initial known93-to92 smoke checked eight flattening-passing patches, rejected
six by Koszul, and sent two to bounded CaDiCaL (both UNKNOWN at1000 conflicts).
Total elapsed time was2.10 seconds; exact preprocessing took0.30 seconds. This
75% rejection is a small initial sample, not an extrapolated success guarantee.
