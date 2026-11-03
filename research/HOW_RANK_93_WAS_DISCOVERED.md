# How the 93-product 5×5 matrix multiplication scheme was found

The published 93-product construction was obtained through **symmetry-preserving
flip-graph search**: start with an exact tensor decomposition, rewrite it without
changing the tensor, and look for rewrites that reduce the number of products.
Its companion implementation combines a carefully chosen fixed structure,
cyclic symmetry, randomized flips, occasional expansions, and a fast C++ engine.

This report reconstructs the method from the released code, run configuration,
and explicit coefficients accompanying *Flip Graphs with Symmetry and new Matrix
Multiplication Schemes*, arXiv:2502.04514 (2025). The construction is associated
with Moosbauer–Poole; the implementation explicitly credits Mike Poole and is
released in Jakob Moosbauer's repository. Earlier flip-graph work by Kauers and
Moosbauer is a predecessor, rather than the attribution for this rank-93 result.

An explicit 93-product algorithm establishes **tensor rank at most 93**. It does
not prove that 92 products are impossible. The straightforward algorithm uses
125 products, so the construction saves 32 products, or 25.6%, in this cost model.
Additions and practical execution time are separate considerations.

1. **Represent multiplication by a tensor.**

   For row-major coordinates, the trace-form tensor has
   `T[5*i+j, 5*j+k, 5*k+i] = 1` and all other entries zero. Its shape is
   25×25×25. A decomposition is

   \[
   T=\sum_{r=1}^{R}u_r\otimes v_r\otimes w_r.
   \]

   Each summand specifies one product of an input linear form in A and an input
   linear form in B. The third factor specifies how that product contributes to
   the output entries. It is not a third multiplication performed by the
   algorithm. The search seeks a short exact decomposition.

2. **Exploit cyclic symmetry.**

   The trace identity `tr(ABC) = tr(BCA) = tr(CAB)` makes the tensor invariant
   under cyclic permutation of its three factors. The released 5×5 case sets
   `SYMMETRY: 3`. Generic terms therefore occur in triples:

   \[
   u\otimes v\otimes w,\quad v\otimes w\otimes u,\quad
   w\otimes u\otimes v.
   \]

   The program performs matching rewrites on complete symmetry orbits. This
   reduces the independent choices while maintaining an exact identity. The
   implementation also supports sixfold symmetry, but the supplied rank-93
   configuration uses threefold symmetry.

3. **Choose three special fixed cubes.**

   A cube here means a symmetric rank-one tensor `D⊗D⊗D`, not a numerical cube
   operation on one input. With Eij denoting a matrix unit, the configuration
   specifies

   \[
   D_1=E_{11}+E_{55},\qquad D_2=E_{22}+E_{44},\qquad D_3=E_{33}.
   \]

   These are the input strings `10001`, `01010`, and `00100`. In the trace
   notation, the first cube represents
   `(a11+a55)(b11+b55)(c11+c55)`, and similarly for the other two.

   The routine `standardrun` holds these three cubes outside the mutable search.
   It searches for a decomposition of the residual tensor

   \[
   T+D_1^{\otimes3}+D_2^{\otimes3}+D_3^{\otimes3}
   \quad\text{over }\mathbb F_2,
   \]

   then restores the cubes at the end. This fixes an important part of the
   desired structure before the random walk begins.

   Direct expansion of this released configuration gives 132 residual
   monomials. Adding the three fixed cubes gives a **135-term starting
   decomposition**. This count is a reconstruction from the code and declared
   cubes, not a quoted first-discovery log. The intended final form is
   `3 fixed cubes + 30 cyclic triples = 93 products`.

4. **Walk through exact decompositions using flips and reductions.**

   Over F₂, a shared-factor flip can use the identity

   \[
   a\otimes b\otimes c+a\otimes d\otimes e
   =a\otimes(b+d)\otimes c+a\otimes d\otimes(e+c).
   \]

   The two extra cross terms cancel in characteristic two. Such a move changes
   the factorization while preserving the tensor. If a factor becomes zero,
   its product disappears. Terms sharing two factors can also merge. The
   symmetry-preserving implementation applies these operations in corresponding
   cyclic groups, so a reduction typically removes three mutable products.

   The source credits Kauers–Moosbauer for flips and reductions, and
   Arai–Ichikawa–Hukushima for the plus-transition operation.

5. **Use temporary expansions to escape plateaus.**

   Same-count flips may reach a region with no useful reduction. A plus
   transition replaces two products with three while preserving their sum.
   That temporarily increases the count, within the configured ceiling, and
   creates new routes toward a shorter decomposition.

   The released configuration uses a nominal plus-transition threshold of
   50,000 flips. That is not an unconditional fixed interval: reductions reset
   the threshold, and the code can trigger an expansion early when the walk is
   stuck. The nominal 100-million-flip limit also resets on finding a new best
   count. Consequently it is not a strict 100-million total-flip budget per run.

6. **Make the local search inexpensive.**

   In characteristic two, addition of coefficient vectors is XOR. A 25-entry
   factor vector fits in a machine word. The implementation maintains indexes
   for shared factors so it can select usable pairs and update affected terms
   efficiently, rather than repeatedly reconstructing the full tensor.

   The released program uses a Python driver with an optimized C++ solver.
   The authors' code README reports roughly one successful rank-93 run in 30,
   with runs of about ten seconds depending on hardware. Its seeded example
   uses `3161794629` and is reported to succeed after 11 runs under Python
   3.10.12. These are **reported reproduction figures**, not measurements from
   our campaign and not evidence of the total original discovery cost.

7. **Publish explicit coefficients and lift the result.**

   The repository supplies both `555m93.txt` over F₂ and
   `555m93_lifted.txt` with integer coefficients. An explicit coefficient list
   makes the construction independently checkable: reconstruct every tensor
   coefficient and compare it with the multiplication tensor.

   Our verification confirms the binary scheme has three fixed cubes and 30
   cyclic triples, with all 15,625 coefficients correct over F₂. For this report,
   we also checked the published integer lift: **93 terms, all 15,625 integer
   coefficients correct, zero mismatches**, plus 32 signed-input matrix tests.
   Its coefficients have maximum absolute value 2. The integer identity can be
   used over any field by mapping those integer coefficients into that field.
   The ±2 coefficients explain why this lift was outside our earlier ternary
   factor restriction; they do not invalidate the binary construction.

   The accessible files provide the lift, but do not establish for this report
   the precise procedure originally used to find it. Our later Lean check of
   the F₂ baseline is a separate verification step, not the published discovery
   method.

The important methodological lesson is the combination of **a deliberate fixed
cube structure, symmetry-preserving exact moves, and nonmonotone exploration**.
The released successful structure makes reproduction practical; that does not
measure the effort required to discover the structure and tune the method.

No original first-success runtime log or precise discovery date was found in
the inspected sources. The full arXiv text was unavailable through this
environment's network policy. Accordingly, this is a source-backed account of
the released method and reproducible construction, not an invented narrative
of the first historical run. Our own campaign did not discover the rank-93
bound or improve it.

Sources:

* [2025 paper, arXiv:2502.04514](https://arxiv.org/abs/2502.04514).
* [Released implementation and method credits](https://github.com/jakobmoosbauer/symmetric-flips/blob/3e2d4dd8acf831ef65c7c6b13ed787330e1e3483/code/MatrixMult22.py).
* [Rank-93 run configuration](https://github.com/jakobmoosbauer/symmetric-flips/blob/3e2d4dd8acf831ef65c7c6b13ed787330e1e3483/code/r5-93-1.txt).
* [Seeded reproduction configuration](https://github.com/jakobmoosbauer/symmetric-flips/blob/3e2d4dd8acf831ef65c7c6b13ed787330e1e3483/code/r5-93-seeded.txt).
* [Authors' reproduction instructions and approximate timings](https://github.com/jakobmoosbauer/symmetric-flips/blob/3e2d4dd8acf831ef65c7c6b13ed787330e1e3483/code/README.md).
* [Binary coefficients](https://github.com/jakobmoosbauer/symmetric-flips/blob/3e2d4dd8acf831ef65c7c6b13ed787330e1e3483/schemes/555m93.txt) and [integer lift](https://github.com/jakobmoosbauer/symmetric-flips/blob/3e2d4dd8acf831ef65c7c6b13ed787330e1e3483/schemes/555m93_lifted.txt).
* Independent checks for this report: `artifacts/rank93_report_verification.json`.
