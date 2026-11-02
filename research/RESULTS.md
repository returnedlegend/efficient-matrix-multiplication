# Research run: 5×5 multiplication over F₂

For the subsequent author-published Kauers–Moosbauer seed and bounded local SAT
experiment, see [LOCAL_SAT.md](LOCAL_SAT.md). That source investigation also
established a published rank-93 reference scheme, distinct from our search
outcomes. The runs below describe the earlier AlphaTensor-seeded experiment.

The strict target is **R ≤ 94**. No exact decomposition meeting that target
has been found in these bounded runs. The strongest valid result obtained here
has 95 products, derived from the published AlphaTensor rank-96 seed. It is
not claimed to be novel or to improve the literature. There is no nonexistence
proof for R ≤ 94.

## Search evidence

| Branch | Seed | Budget | Iterations | Best products | Incorrect coefficients |
| --- | --- | --- | --- | --- | --- |
| Exact flips from published 96 | 0 | 120 s | 426,144 | 95 | 0 |
| Exact flips continued from 95 | 1 | 120 s | 397,393 | 95 | 0 |
| Cyclic flips from naive 125 | 0 | 120 s | 300,356 | 125 | 0 |
| Cyclic flips from Strassen 110 | 1 | 60 s | 144,714 | 110 | 0 |
| Rank-94 coordinate residual search | 0 | 120 s | 10,513 sweeps | 94 | 12 |
| Rank-94 coordinate/ALS from 96 | 0 | 60 s | 9,835 | 94 | 2 |
| Rank-94 coordinate/ALS continued | 1 | 120 s | 19,419 | 94 | 2 |
| Rank-94 coordinate/ALS from exact 95 | 2 | 60 s | 11,400 | 94 | 2 |

The 95-product result first appeared at flip step 336,987. Reproduce the
step trajectory with the published seed, `--seed 0 --steps 426144`, and a time
budget sufficient to finish. Default `--max-extra 6 --plus-every 250
--restart-every 5000` were used. Wall-clock timing and step counts depend on
available CPU. The original coordinate-only residual run used random term
deletion; the current implementation subsequently gained a better pair-deletion
initializer, covered by tests. That improvement has not been credited to the
older run.

Checkpoints and their independent verification reports are under `artifacts/`.
The invalid 94-term checkpoints deliberately remain available as search data;
they are not multiplication algorithms. Each emitted search candidate has an
independent standalone verifier. Local improvements in nonzero residual do not
guarantee a path to an exact solution.

## Exact checks

* The target artifact `T_5_5_5.npy` has 15,625 entries and 125 ones, with trace
  coordinates `T[5*i+j,5*j+k,5*k+i] = 1`.
* The published rank-96 baseline passes all 15,625 coefficient checks over F₂.
* `flip-search-seed0.json` passes all 15,625 coefficient checks and 128
  supplementary random matrix multiplication tests. Its literal binary
  coefficients fail integer equality at 1,523 entries. No integer or complex
  lift is claimed.
* The best 94-term checkpoints fail exact equality. The verifier exits 1 for
  those candidates. Two mismatches still invalidate the entire algorithm.
* All **25 tests pass**: tensor indexing, baseline schemes, field specificity,
  corruption rejection, zero coefficients, standalone verifier exit codes,
  exact flip/plus/reduction identities, cyclic closure, reproducible step
  budgets, GF₂ solves and residual calculations.

## Lean evidence

Lean **4.19.0** compiled the general proof in `lean/Certificate.lean` and the
explicit 95-product algorithm in `lean/Rank95Native.lean` with **zero errors**.
The proof covers every pair of 5×5 input matrices over F₂, not only test inputs.
Its structure is:

1. Expand the R products of linear forms using distributivity in F₂.
2. Rearrange finite sums and replace the coefficients by the exact tensor
   certificate.
3. Identify contraction of the trace tensor with standard matrix multiplication.

The explicit coefficient check uses `native_decide`. Its axiom audit lists
`propext`, `Quot.sound`, and **`Lean.ofReduceBool`** (the trusted native
evaluator). It uses no `sorryAx` or custom axioms. The generic theorem needs
only the standard foundational axioms `propext`/`Quot.sound`. Kernel-only
evaluation of the explicit certificate was stopped after about 120 seconds;
no completed kernel-only certificate check is claimed. See the exact command,
compiler exit code 0, and audit in `lean/Rank95Native.log`.

The exported Lean source was regenerated from the exact JSON certificate and
compared byte-for-byte with the successfully compiled source:

| Artifact | SHA-256 |
| --- | --- |
| `artifacts/flip-search-seed0.json` | `859adda16ce65895460c26265ed4a14238dd4a89a9eb3189c25ab99f2b0cfadd` |
| `lean/Rank95Native.lean` | `f3115eae5014098b6da9f4ec02e771950ad23b1747d698b4180c9be413e09fa2` |

## Limits and continuation

The cyclic branch restricts the search space; neither branch is exhaustive.
Product count alone does not establish an improvement in real execution time,
and no hardware speedup was measured. The supplied threshold of 95 is treated
as the target to beat; a current literature review and equivalence analysis
would be necessary before any novelty claim. The initialization, search and
verification code are ready for larger multi-seed experiments, but a successful
strictly-below-95 proof still depends on finding an exact certificate.

Source attribution and the pinned dataset are documented in
[ALPHATENSOR_SOURCE.md](ALPHATENSOR_SOURCE.md). The original archive is retained
as `artifacts/alphatensor_factorizations_f2.npz`; the importer only reads its
numeric 5,5,5 member with pickle disabled.
