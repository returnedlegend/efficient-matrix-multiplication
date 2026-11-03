# Fixed-pair, free-factor exact SAT

This branch searches for an exact F2 matrix-multiplication decomposition with
at most 92 nonzero terms. Two factors of each possible term come from a frozen
dictionary; the remaining factor can be any vector in F2^25. This is a broader
search than selecting complete triples from that dictionary.

Implementation: [`mmsearch/free_factor_sat.py`](../../mmsearch/free_factor_sat.py),
[`scripts/campaign_free_factor_sat.py`](../../scripts/campaign_free_factor_sat.py),
and [`tests/test_free_factor_sat.py`](../../tests/test_free_factor_sat.py).
The module, wrapper, and tests were marked READY after 11 passing tests. All
three orientations have queued 600-second trials; this note records preflight
results only, not outcomes from those trials.

## Exact formulation

For one orientation, deduplicate the nonzero fixed pairs `(a_g,b_g)` from the
input mask triples. Zero fixed factors are discarded. The dictionary's third
mask does not constrain the new third factor, even when that input mask is zero.
Every mask and tensor coefficient is an exact integer bit.

Let `A[r,g]` be the coefficient of `a_g ⊗ b_g` at `r = a*25+b`. There are 625
rows and `p` pair columns. Introduce a free vector `x[g,0..24]` and an active
indicator `y[g]` for each group. The tensor equations are native XOR constraints:

```text
XOR_g (A[r,g] AND x[g,c]) = T_orientation[r,c]
```

The fixed coefficients `A[r,g]` select XOR inputs; no Boolean product variable
is needed. The target uses the trace convention
`T[(i,j),(j,k),(k,i)] = 1`, with all other coefficients zero.
CNF clauses enforce both directions of activation:

```text
x[g,c] => y[g]                    for every c
y[g] => OR_c x[g,c]
sum_g y[g] <= 92
```

Thus an inactive group has the zero free vector, and every nonzero vector costs
exactly one term. A cardinality network encodes the bound. Exact forced active
indicators are subtracted from the residual bound; forced zero indicators cost
nothing. Variable IDs are `x[g,c] = g*25+c+1` and `y[g] = p*25+g+1`.

## Packed RREF and orientations

The 25 scalar systems share the same 625-by-`p` coefficient matrix. Elimination
therefore runs once, using a `p`-bit coefficient mask and a packed 25-bit RHS per
row. Each RREF row carries, and checks, its XOR witness in the original 625 row
indices. A zero coefficient row with nonzero packed RHS certifies inconsistency.
A singleton coefficient row fixes an entire free vector: its group is forced
active iff the RHS vector is nonzero. More than 92 forced active groups proves
restricted UNSAT. Passing these bounds does not establish a solution.

| Option | Fixed pair | Free factor | Permuted mode order |
|---|---|---|---|
| `uv` | original U, V | original W | U, V, W |
| `vw` | original V, W | original U | V, W, U |
| `wu` | original W, U | original V | W, U, V |

The target is permuted consistently, and decoding applies the inverse mode
permutation. Matrix coordinates within a factor are not transposed. In
particular, the original output factor remains indexed by `(k,i)`.

Every whole-triple subset using these fixed pairs is included: XOR together
the third factors of selected terms sharing a pair, then discard zero results.
This can only reduce the term count. The new formulation also permits third
vectors absent from the original triple dictionary.

## Controls, verification, and limits

The baseline is independently checked before encoding. Its same-pair factors
are XOR-merged, and the merged candidate is independently checked again. If
that already meets the bound, a `WINNER.json` is frozen immediately, including
during preflight. Otherwise a positive control uses the supplied baseline rank
(93 here), fixes **every** `x` and `y` variable to the baseline values, and must
return SAT before a target search proceeds. Cardinality auxiliaries remain free.

A SAT model must be complete and Boolean and must satisfy every CNF clause,
native XOR, original packed tensor row, active-indicator relation, rank bound,
and control assumption where applicable. The independently implemented
[`mmsearch/verify.py`](../../mmsearch/verify.py) then checks all 15,625 original
tensor entries, including zeros, and 16 random multiplication trials. Candidate,
verification, complete model, and a standalone verifier are saved. Input bytes,
local source bytes and hashes, pair/variable maps, original rows, RREF proofs,
and formula hashes are frozen for audit.

A conservative estimate caps Python formula storage before allocation
(`--max-formula-mb`, default 384 MiB). This estimate is not a solver RSS bound;
native solver memory is additional. The single-threaded solver child has an
address-space limit (`--memory-mb`, default 1536 MiB), a CPU limit, a solver time
limit, and a parent-enforced wall limit including loading. The wrapper reserves
two seconds for cleanup, terminates/joins/kills the child as necessary, and
releases the control formula before building the target formula. Resource
limits and exhausted time produce explicit non-UNSAT statuses.

UNSAT concerns only the supplied fixed-pair dictionary and the requested active
group bound. It does not establish a global lower bound on matrix-multiplication
rank. All equality and search claims are over F2; no integer lift is asserted.

## Recorded preflight

Input: 1,986 mask triples from
`artifacts/rl_campaign_20261102T210735Z/dictionary-new1/frozen/dictionary.json`;
baseline: `artifacts/km93_f2.json`.

| Orientation | Pairs `p` | Common coefficient rank | Nullity | Forced active | Forced zero | Estimated Python formula MiB |
|---|---:|---:|---:|---:|---:|---:|
| uv | 1159 | 378 | 781 | 0 | 0 | 157 |
| vw | 1147 | 365 | 782 | 0 | 0 | 156 |
| wu | 1134 | 371 | 763 | 0 | 0 | 153 |

All three systems are consistent, and the merged baseline rank remains 93.
These ranks/nullities describe the common coefficient matrix; there are 25
free-coordinate systems. Native XOR literal counts are 301,800, 296,425, and
268,475 respectively. The smaller `wu` encoding does not imply an easier solve.

Frozen evidence is in
[`free-factor-preflight-ready`](../../artifacts/rl_campaign_20261102T210735Z/free-factor-preflight-ready/):
`READY.json`, `provenance.json`, `preflight.json`, and `{uv,vw,wu}.system.audit.json`.
The final preflight took 0.207 seconds and the 11 tests took 0.222 seconds,
pinned to CPU 2. No 5-by-5 formula or solver was started during this preparation.

SHA-256 at READY:

```text
dictionary.json                 5bff2158abbbdea2d53a92488db53c2a70973b69d60b809d2f0c4154aca9fd29
km93_f2.json                     56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b
mmsearch/free_factor_sat.py      eb6803fc5d89909fbb3d14839d5222d37f0e48e2eac664957e254b22448cc6b5
scripts/campaign_free_factor_sat.py 556132333672547c3569bc7743e96b1c12c6c75324cd9075e911b2c15ed2cb3f
tests/test_free_factor_sat.py    9708d3a6e321f30616d197759c4b2e0882799ce70be6aff8ba66dfd9aaf000ba
```

Reproduce the brief checks:

```bash
taskset -c 2 env PYTHONPATH=.xor-deps:. python -m unittest tests.test_free_factor_sat
taskset -c 2 env PYTHONPATH=.xor-deps:. python scripts/campaign_free_factor_sat.py \
  --dictionary artifacts/rl_campaign_20261102T210735Z/dictionary-new1/frozen/dictionary.json \
  --baseline artifacts/km93_f2.json --orientation all --preflight \
  --outdir NEW_PREFLIGHT_DIRECTORY --seconds 20
```
