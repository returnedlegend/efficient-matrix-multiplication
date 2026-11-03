# DeepMind resources and scope of the RL experiment

Checked 2026-11-02 through the managed proxy with normal TLS verification.
This is a bounded public-source check. Browser tools are unavailable in this
session. The enforced network policy allows GitHub and raw.githubusercontent.com;
arXiv and Nature are outside the configured hosts. No alternate network route
or TLS bypass was used. The earlier arXiv denial and broader record check are
recorded in [RECORD_CHECK.md](../campaign/RECORD_CHECK.md).

## What DeepMind released

The official [AlphaTensor repository](https://github.com/google-deepmind/alphatensor)
still has live `main` at `1949163da3bef7e3eb268a3ac015fd1c2dbfc767`, dated
2022-10-04. Its immutable
[README](https://github.com/google-deepmind/alphatensor/blob/1949163da3bef7e3eb268a3ac015fd1c2dbfc767/README.md)
and root directory tree contain these four components:

| Component | Released resource | Relevance here |
| --- | --- | --- |
| `algorithms` | Published tensor factorizations and inspection notebook | Existing exact 5×5 F₂ rank-96 baseline |
| `benchmarking` | Hardware-tailored algorithms and NVIDIA V100 benchmark | Measures runtime; this is a different objective from reducing F₂ product count |
| `nonequivalence` | 14,236 nonequivalent 4×4 algorithms and invariant notebook | Small-problem diversity and equivalence research |
| `recombination` | Python code combining smaller factorizations | A public construction method; not AlphaTensor's RL training implementation |

There is no complete AlphaTensor TensorGame self-play training pipeline or
pretrained policy/value checkpoint in this release. The existing local
[AlphaTensor source note](../ALPHATENSOR_SOURCE.md) pins the F₂ data hash and
verifies the rank-96 5×5 entry. Its software license is Apache-2.0 and other
materials are CC-BY-4.0.

The public
[recombination implementation](https://github.com/google-deepmind/alphatensor/blob/1949163da3bef7e3eb268a3ac015fd1c2dbfc767/recombination/recombination.py)
uses block decompositions and a table of smaller multiplication costs. Its
[example](https://github.com/google-deepmind/alphatensor/blob/1949163da3bef7e3eb268a3ac015fd1c2dbfc767/recombination/example.py)
combines a rank-23 3×3 factorization into a rank-255 construction for format
⟨10,4,9⟩, equivalent under cyclic format permutation to ⟨4,9,10⟩. No upstream
script was run. This source provides construction ideas, rather than evidence
for a 5×5 bound below 93. The
[benchmark README](https://github.com/google-deepmind/alphatensor/blob/1949163da3bef7e3eb268a3ac015fd1c2dbfc767/benchmarking/README.md)
explicitly targets an NVIDIA V100 and fixing GPU clock frequency; it is not an
appropriate performance test for this CPU-only product-count campaign.

## A concrete AlphaEvolve seed

The official
[AlphaEvolve results repository](https://github.com/google-deepmind/alphaevolve_results)
has live `main` at `4226acbf237ff9ad10ba7673a2af127a2d8a5971`.
Its [README](https://github.com/google-deepmind/alphaevolve_results/blob/4226acbf237ff9ad10ba7673a2af127a2d8a5971/README.md)
explicitly says that it does not contain code to run AlphaEvolve. Its
[published notebook](https://github.com/google-deepmind/alphaevolve_results/blob/4226acbf237ff9ad10ba7673a2af127a2d8a5971/mathematical_results.ipynb)
does contain a **rank-93 5×5 integer decomposition**, besides the widely reported
rank-48 4×4 construction with complex half-integer entries. The latter is a
different field from AlphaTensor's 4×4 F₂ rank-47 construction; their numbers
must not be compared as if they were the same tensor-rank question. Denominators
of two also prevent blindly reducing the complex half-integer data modulo two.

The rank-93 5×5 arrays were safely imported using
`scripts/import_alphaevolve93.py`. The importer checks the entire notebook's
SHA-256, reads only the expected assignment with an AST allowlist, interprets
numeric source tokens as exact fractions, and requires integral entries in
{-1,0,1}. It does not execute notebook cells or evaluate their `np.array` calls.

The resulting files are in
`artifacts/rl_campaign_20261102T210735Z/public/`:

* `alphaevolve93_integer.json`: signed integer identity.
* `alphaevolve93_f2.json`: normalized binary reference for the search seed pool.
* `alphaevolve93_verification.json`: both full coefficient checks, random product
  checks, counts, and coordinate checks.
* `alphaevolve93_source.ipynb`, `alphaevolve93_upstream_README.md`,
  `alphaevolve93_LICENSE`, and `alphaevolve93_ATTRIBUTION.md`: retained source
  and attribution.

Each identity passed all **15,625 exact coefficients** and **64 random matrix
products**. The modulo-two form has **93 distinct nonzero triples** after parity
cancellation, so this is an imported published upper bound, not a new ≤92
discovery. Source W already uses the project's trace coordinates; transposing
it fails 200 coefficient checks. The binary literal coefficients have 1,381
integer mismatches, whereas the separate signed source is an exact integer
identity. A statement about one certificate's field must not be transferred to
the other certificate.

## Available Python RL building blocks

These official public Python projects were inspected as documentation, without
running their upstream scripts:

| Resource | What it supplies | Integration choice under four CPUs, 8 GB, six hours |
| --- | --- | --- |
| [dm_env](https://github.com/google-deepmind/dm_env) | Environment, TimeStep, observation/action specifications, API checks | Suitable lightweight interface for an exact tensor environment |
| [Acme](https://github.com/google-deepmind/acme) | General reusable RL agents and training building blocks; agents require JAX or TensorFlow dependencies | Useful architectural reference; adopting a distributed training stack adds setup and memory cost |
| [Mctx](https://github.com/google-deepmind/mctx) | Batched JAX MCTS, MuZero and Gumbel MuZero policies | Optional small-action search; does not supply a tensor policy/value model or solve the enormous raw action space |

Mctx's README requires root prior logits, values and embeddings, plus a recurrent
function producing transition rewards, discounts, priors and values. Exact
tensor dynamics can be supplied by the environment; values and policy priors
still have to be supplied or learned. Importing the library is not a trained
AlphaTensor agent. The inspected mutable README snapshots are retained in
`/workspace/library-files/alphatensor/` and are documentation references, rather
than pinned installed dependencies.

## Practical design constraints

The following are local design recommendations, not claims that the public
AlphaTensor repository contains or reproduces its full published training
procedure. Fawzi et al., *Discovering faster matrix multiplication algorithms
with reinforcement learning*, Nature 610 (2022), DOI
10.1038/s41586-022-05172-4 is the primary methodological reference; its full text
was not newly retrieved in this restricted session. Exact published training
hyperparameters, symmetry augmentation schedules, and compute consumption
should therefore not be attributed to this source check.

An exact residual game is straightforward to define: state R is a 25×25×25
binary tensor, action is a nonzero triple (u,v,w), and the next state is
`R XOR (u outer v outer w)`. Start at the multiplication tensor and succeed only
at the exact zero residual. A reward of −1 per product makes a successful
undiscounted return equal to minus the product count. A finite horizon must
distinguish exact completion from truncation; zero residual is the algebraic
success test. Residual Hamming weight can aid a heuristic but does not establish
rank and should not be reported as a certificate.

The unrestricted 5×5 F₂ action set has `(2**25 - 1)**3` nonzero triples. Sparse
success rewards and horizons near 93 make learning from scratch unrealistic
within this session's CPU budget. A more practical six-hour experiment learns
a small choice among valid local rewrites, bounded repair neighborhoods, or
proposal heuristics applied to verified 93-term seeds. Reward exact rank
reduction; keep shaping separately labeled and test any apparent success with
the independent verifier. Nonmonotone exact rewrites can cross plateaus without
confusing approximate tensors with valid decompositions.

Safe augmentation can use factor-cycle symmetry and consistent permutations
of the three matrix index sets. General changes of basis require contragredient
factor transformations; arbitrary independent permutations of all 25 entries
do not preserve the multiplication tensor. Generated augmentations should be
verified before contributing to training or seed pools. Training examples from
published seeds remain attributed references, rather than search discoveries.

The companion implementation for arXiv:2502.04514 provides a stronger directly
relevant search prior: cyclic orbit rewrites and three fixed cubes. See
[the reconstruction from released code](../HOW_RANK_93_WAS_DISCOVERED.md).
There is an arithmetic constraint on retaining this structure: three fixed
single cubes plus complete size-three orbits gives a term count `3 + 3k`.
Consequently that exact ansatz cannot produce a 92-term representation unless
additional orbit/cube handling or symmetry breaking changes the structure; it
may instead seek 90 terms. This restriction is not evidence that rank 92 is
impossible in the unrestricted problem.

The appropriate comparison is a paired CPU/time budget against uniform or
fixed heuristic selection on identical verified starting seeds. Save policy
parameters, RNG seeds, reward definitions, episode counts, and exact validity
reports. An unsuccessful RL run measures only that experiment; neither a local
UNSAT result nor lack of reward proves a global tensor-rank lower bound.

## Current benchmark and limits

The current author repository was checked again: `symmetric-flips` remains at
`3e2d4dd8acf831ef65c7c6b13ed787330e1e3483`, with only 5×5 rank-93 and 6×6
rank-153 schemes and their integer lifts in its scheme directory.
`FastMatrixF2` remains at
`5fd32f680acf2a7708ea6a2d40d10f7e7537957c`; the earlier source check records
307 distinct verified rank-93 seeds and its explicit statement that no
published record is improved. The official AlphaEvolve 5×5 source above adds
another verified rank-93 reference, without lowering this accessible bound.

**93 is the best exact 5×5 F₂ upper bound established from the inspected
accessible sources.** This is not an exhaustive live literature review or a
proof that a newer ≤92 certificate does not exist. A claimed new record would
require a broader current publication check in addition to exact verification.
