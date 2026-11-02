# Optional exact p2 Koszul stage

`scripts/campaign_koszul_p2_sat.py` adds p2 only after a patch passes all enabled
p1 bounds. It imports the frozen p1 scheduler/cache and compact encoder without
modifying their source files. Use a separate output directory. Its flags match
the p1 wrapper, with three additional cost caps:

```bash
PYTHONPATH=.xor-deps:. python scripts/campaign_koszul_p2_sat.py \
  --backend xor --symmetry u-lex --koszul-modes all \
  --p2-max-dimension 14 --p2-max-rows 5000 --p2-max-columns 5000 \
  --input artifacts/km93_f2.json \
  --seed-dir artifacts/campaign/public-seeds/fastmatrix-f2/seeds \
  --seed-dir artifacts/campaign_20261102T164324Z/native \
  --output-dir artifacts/campaign_20261102T164324Z/koszul-p2-xor \
  --k-min 7 --k-max 14 --seed 11 --levels 1 \
  --patch-seconds 30 --conflicts 100000 --seconds 1800
```

Use `--backend cadical` for ordinary CNF. The root harness sets CPU/RAM limits.
The caps are part of the restart identity. Modes are tried by increasing
estimated row-count times column-count; a local rejection stops further p2
work. A mode exceeding a cap is explicitly SKIPPED and contributes no bound.
This permits K10–18 exploration while skipping expensive large-image modes.

For T in A tensor B tensor C, the p2 map is

    exterior^2(A) tensor B* -> exterior^3(A) tensor C.
    (x wedge y) tensor beta |-> sum_i (u_i wedge x wedge y) tensor beta(v_i)w_i.

For one nonzero product, choose a basis whose first vector is its A-factor u.
Wedge multiplication by u is nonzero precisely on pairs not containing u;
its rank is binomial(a-1,2), where a=dim(A). Therefore

    rank(Koszul_p2(T)) <= K * binomial(a-1,2)

for every K-product decomposition. Characteristic two changes all exterior
signs to plus; repeated indices still vanish. The implementation enumerates
distinct input pairs and output triples, with coefficient T[i,v,w] only when
the triple is the pair union the distinct index i. All ranks use exact GF2
integer bit operations. This lower bound applies only to the selected local
residual tensor after exact image compression. It is not a global rank bound.

The higher cache stores both p1 and p2 reports and reuses the already computed
core for CNF or native XOR. Rejection records name the actual exterior degree
and corresponding proof inequality. Extra counters record p2 evaluations,
rejections, skips after a p1 rejection, all-modes-skipped cases, and p2 seconds.

Validation covers rank-one map rank exactly binomial(a-1,2), independent dense
exterior-map construction and elimination, bounded K-product sums including
cancellation, a p1-passing/p2-rejected exact local fixture, explicit cap skips,
and the feasible nontrivial 2x2 rank7 control. Both backends retain independent
full original-coordinate verification for every SAT candidate.

## Fixed twenty-patch benchmark

The first20 completed p1-passing patches in the initial `koszul-cadical` phase
were selected before computing p2. P2 rejected10/20 in0.0238 seconds total;
median0.00058 seconds and maximum0.00493 seconds. The previous p1-only solver
runs consumed74.12 seconds across these20 patches. Offline core reconstruction
took0.695 seconds, recorded separately; a live higher-cache run reuses those
cores. These small, shared-core wall measurements show a useful local pruning
rate and low incremental cost; they do not predict rank92 discovery.

`koszul_p2_benchmark20.json` preserves all20 patch/source/core hashes, exact
indices and dimensions, mode ranks, bounds, costs, statuses, and frozen helper
hashes. Every reported bound was checked to be at most K+1, as each residual
has its known K+1-product source decomposition.
