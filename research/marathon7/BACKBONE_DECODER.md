# Rank-one backbone decoder

This is a new bounded research decoder in `mmsearch/backbone7.py`. No production
N=5 case is queried by its tests. Its input must be the **actual complete slice
image** of a tensor unfolding, not an arbitrary factor span or projected list.

## Cover-space identity

Let S be the matrix image of an unfolding of R. Then CP(R) equals the minimum
dimension of a matrix space W containing S that has a rank-one basis. A CP
decomposition supplies a covering span; retaining an independent subset of its
original rank-one points does not increase the count. Conversely, express every
raw slice in a rank-one basis of W and collect its coordinates into the free
factor vectors. This reconstructs all raw slices, including dependent and zero
slices, hence the full tensor.

## Exact arbitrary-surplus theorem when the backbone has corank one

Write B0=span{P in S: rank(P)=1}, b=dim(B0), d=dim(S). If b=d-1, then

    CP(R) = b + min{rank(D): D in S \ B0}.

For the upper bound, take an original rank-one basis of B0 and any exact
matrix-rank factorization of a minimizing D. Their span contains S.

For the lower bound, let W be any covering space with a rank-one basis.
Extend the chosen rank-one basis of B0 to a rank-one basis of W by basis
exchange. A D outside B0 has a nonzero coset representative D+B, B in B0,
which is a sum of at most dim(W)-b remaining basis matrices. Thus its matrix
rank is at most dim(W)-b, proving the lower bound. This argument has no surplus
restriction. If b=d, CP(R)=d. These are global optimum statements only for
quotient dimension zero or one.

The implementation enumerates every nonzero matrix of S, constructs B0,
minimizes matrix rank on the nonzero quotient, and uses exact GF2 row-basis
factorization of the minimizing matrix. It retains original rank-one points
when selecting the final covering basis. Exact coordinate witnesses are
returned for **every supplied target**, followed by full expansion in solve_core.

## General quotient construction: upper bound only

For q=d-b>1, assign each nonzero coset of B0 its minimum matrix rank. A
minimum-weight basis of S/B0 is obtained by binary matroid greedy. Factoring
its chosen representatives and adjoining a rank-one basis of B0 gives a
valid upper bound b+sum(weights). This count is the optimum of that explicitly
restricted, separately factored quotient-basis family. It is **not** claimed
to be the global CP optimum; shared rank-one factors across representatives
can improve the bound. A failed construction returns UNKNOWN, never global
LOCAL_UNSAT. Independent dimension bounds and the rank-equal-budget backbone
criterion remain valid global negative certificates.

## Complete surplus-two extension (theorem prepared, not implemented here)

First run an exact CP(d+1) decoder. For b=d-1, the theorem above decides
CP(d+2). If d-b>=2 and a rank-one-generated covering W of dimension d+2
exists, choose a rank-one basis containing a basis of B0. Its d+2-b>=4
remaining elements occupy only three nonzero cosets of W/S. Two distinct
basis elements P,Q share a coset. Their sum D lies in S but outside B0;
therefore rank(D)=2. Over F2 every rank-two matrix has exactly three unordered
rank-one splits. Enumerate all such D and splits, form U=S+<P>, and run the
existing exact surplus-one decoder on U. At least one succeeds. Conversely,
any successful U cover contains S and is a valid CP(d+2) certificate.

## Controls and stopping

The corank-one control S=span(E11,diag(0,1,1,1,1)) has d=2,b=1 and minimum
outside rank four, hence CP=5; it lies beyond surplus two. The surplus-two
control span(E11+E22,E33+E44) has B0=0 and the restricted construction gives
four products; a failed three-product construction is labeled UNKNOWN here.
Tests also check every 2x2 matrix subspace against exhaustive rank-one covers,
all budgets on the corank-one control, exact rectangular matrix factorizations,
raw zero/duplicate/dependent slices, mode orientations, and guard exits.

All enumeration caps, timeouts, cancellation and deadline stops return UNKNOWN
with complete=false. The hard campaign deadline is 2026-11-03T19:24:17Z;
callers can shorten but cannot extend it. Unit tests freeze only the wall clock
before that deadline so they remain reproducible after the campaign. The
decoder makes no claim about unqueried N=5 residuals or attaining rank 92.
