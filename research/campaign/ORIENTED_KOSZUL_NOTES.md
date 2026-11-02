# Complete ordered-mode Koszul filtering

`scripts/campaign_oriented_sat.py` completes the p1/p2 filter by considering
which of the other two factors is dualized, for every exterior factor. The
default therefore covers all six permutations of (A,B,C), rather than only
three choices of A with one fixed ordering of B/C. It uses new helper/wrapper
files and imports all previous frozen modules without changing their sources.

```bash
PYTHONPATH=.xor-deps:. python scripts/campaign_oriented_sat.py \
  --backend xor --symmetry u-lex --koszul-modes all \
  --p2-max-dimension 14 --p2-max-rows 5000 --p2-max-columns 5000 \
  --input artifacts/km93_f2.json \
  --seed-dir artifacts/campaign/public-seeds/fastmatrix-f2/seeds \
  --seed-dir artifacts/campaign_20261102T164324Z/native \
  --output-dir artifacts/campaign_20261102T164324Z/oriented-xor \
  --k-min 7 --k-max 14 --seed 11 --levels 1 \
  --patch-seconds 30 --conflicts 100000 --seconds 1800
```

Use `--backend cadical` for ordinary CNF and a fresh output directory. The
root harness sets CPU/RAM limits. Selecting only one `--koszul-modes` value
tests the two orderings for that exterior mode; the default `all` covers six.

Transposing the residual tensor permutes the three factors of every rank-one
product, preserving its number of products over GF2. Each transposed tensor
therefore satisfies the same proven bounds

    rank(Koszul_p(T_transposed)) <= K * binomial(dim(A)-1,p), p in {1,2}.

Distinct choices of B and C generally give different map ranks. Characteristic
two retains alternating exterior multiplication: repeated indices vanish and
the remaining signs become plus. This step uses no additional coefficient or
support restriction. Bounds remain local to the selected residual.

The cache first computes the original-order p1/p2 bounds. Only survivors incur
the three additional B/C-swapped orientations, and a proof stops further work.
Every p2 map still honors the dimension, row, and column caps; skipped maps
contribute no rejection. The cache retains the core and full reports for
encoding. Extra counters distinguish additional orientation evaluations,
rejections, skipped stages, and elapsed seconds.

Every rejection event records the decisive orientation, exterior degree, map
rank, K-times-per-product threshold, and proof formula. Original-order rejects
receive these fields as well. Detailed reports preserve matrix and transposed
core hashes. Solver SAT candidates still undergo independent verification of
all original multiplication-tensor entries.

Validation includes all six permutations against independent dense p1/p2 maps
and elimination; a p1+p2 original-order survivor rejected by a swapped map;
known K-product positive tensors; explicit cost-cap skips; and a planted 5x5
positive control that verifies all15,625 entries after decoding. No claim of
rank92 success is made by this rank125 positive control.

The fixed first20 p1+p2-surviving patches in `koszul-p2-cadical` yielded8 extra
local rejections. The added orientation stage took0.0585 seconds total; offline
core reconstruction took0.553 seconds and is avoided in the live cache. Those
patches previously consumed80.04 solver-wall seconds. Full patch/source/core
hashes, bounds, decisive orientations, and timing are recorded in
`koszul_orientation_benchmark20.json`. This is an empirical small-sample local
pruning result, not a global lower bound or a prediction of rank92 discovery.
