Conditional exact surplus-three decoder
======================================

For a matrix slice image S of dimension d, let B0 be the span of all rank-one
matrices inside S and b=dim B0. The new module decides CP(S)<=d+3 when b<=d-5,
subject to explicit finite caps. A cover means a linear space spanned by at most
the requested number of original rank-one matrix points and containing S.
This is equivalent to CP rank for the original tensor when S is its unfolding
slice image: coordinates in a covering basis supply the third factors.

First run the reviewed exact CP(d+2) decoder. Its positives cover S. A complete
negative means that any cover of size at most d+3 must have exactly d+3
independent rank-one basis points. Extend a rank-one basis of B0 to a rank-one
basis of such a cover W by basis exchange. Every remaining basis point is
outside S: every rank-one point in S belongs to B0. There are d+3-b>=8 of these
points and only seven nonzero cosets in the three-dimensional quotient W/S.
Two distinct basis points P,Q therefore share a coset. Their sum D is inside S
but outside B0, since otherwise these basis points and the B0 basis would be
dependent. D has rank two: its matrix rank is at most two, is nonzero, and a
rank-one D inside S would belong to B0.

Enumerate every matrix D in S of rank two outside B0 and all three unordered
rank-one decompositions D=P+Q over F2. Deduplicate by the nonzero coset P mod S.
Each resulting U=S+<P> has dimension d+1. At least one U lies inside W, so the
reviewed exact CP(dim U+2)=CP(d+3) decoder succeeds on it. Conversely any cover
of U covers S. Complete negative prior plus all complete negative children is
therefore equivalent to a negative CP(d+3) answer under b<=d-5. If the bound is
not met, the module returns UNKNOWN after any useful lower-surplus result.

The implementation retains each child's original rank-one points, selects an
independent subset, and reconstructs every supplied original raw slice,
including zeros, duplicates and dependent slices. solve_core independently
expands all returned products to every original coefficient. Neither result
is an ambient matrix-multiplication record; publication remains disabled.

Parent mode rank is capped at11 and LargeS2 child mode rank at12. Enumeration,
child extensions, elapsed time, absolute C7 cutoff and cancellation are bounded.
Every complete return rechecks the guard; solve_core also rechecks after its
whole-core reconstruction. Any incomplete prior or child, unvisited extension,
or late answer is UNKNOWN. Extension cursors describe work and never authorize
skipping an unproved prefix. No N5 queries were used to implement this module.
An UNKNOWN after a returned prior/child preserves that raw nested result for
diagnosis, including a possible late SAT support. A stop while reconstructing a
cover preserves the original raw cover factor points. These diagnostic witnesses
do not authorize publication or skipping unproved work.

The true surplus-three control is the diagonal matrix image of the binary code
ker H, with H columns (1,2,3,4,5,6,7,1). It has d=5, b=0 and full coordinate
support on eight positions. The opposite tensor unfolding has rank eight, and
the eight diagonal coordinate points give a matching cover: CP=8=d+3. The
prior CP7 is negative and the new repeated-pair branch succeeds. H columns
1..9 in F2^4 instead yield d=5, b=0, no weight-two codewords, and full support
on nine positions, proving CP=9>8 and exercising a complete new-branch negative.
Both controls are small diagonal tensors; neither is a matrix multiplication
target. Dense invertible row/column changes test original-point reconstruction.
Adding six independent diagonal coordinate points to the CP8 example gives a
boundary control d11,b6,CP14. It exercises the actual parent11/child12 caps and
the same conditional inequality used for the proposed N5 cases, with no N5
input or matrix-multiplication target. Its opposite unfolding rank14 supplies
an independent matching lower bound.
