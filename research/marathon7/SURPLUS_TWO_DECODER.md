# Exact surplus-two slice-image decoder

`mmsearch/surplus_two7.py` is a separate bounded decoder for CP(R)<=d+2,
where S is the actual matrix image of an unfolding of R and d=dim(S).
It does not change the existing surplus-one or backbone modules. No production
N=5 query is run by this module's controls.

## Cover-space reduction and theorem

CP(R) is the minimum dimension of a matrix space W containing S with a
rank-one basis. A CP decomposition gives such a span; an independent subset
of its original rank-one points is a basis. Conversely, express every raw
slice in a rank-one covering basis and collect coefficients into free factors.

Let B0=span{P in S: matrix_rank(P)=1}, b=dim(B0). First run the existing exact
CP(d+1) decoder. If it succeeds, its original rank-one points cover S. If it
fails and b=d-1, the reviewed arbitrary-surplus backbone identity gives

    CP(R)=b+min{matrix_rank(D):D in S\B0}.

The remaining case is d-b>=2. Suppose a rank-one-generated covering W of
dimension d+2 exists. Extend an original rank-one basis of B0 to a rank-one
basis of W by basis exchange. All remaining d+2-b>=4 basis elements lie outside
S, since every rank-one point of S lies in B0. The quotient W/S has dimension
two and exactly three nonzero cosets. Thus two basis elements P,Q share a
coset. Their difference D=P+Q belongs to S and is not in B0: otherwise the
chosen basis of W would be dependent. D has matrix rank at most two, but
cannot have rank zero or one, so rank(D)=2.

Every rank-two matrix over F2 has exactly three unordered decompositions into
two rank-one matrices. Enumerating every rank-two D in S\B0 and its three
splits therefore finds this pair. Form U=S+<P>; it has dimension d+1 and lies
in W. The existing exact surplus-one decoder applied to the full image U
decides existence of a rank-one-generated cover of dimension d+2. Conversely,
any successful U cover contains S and gives a valid CP<=d+2 certificate.

Since CP<=d+1 was excluded first, every possible CP<=d+2 cover is found by one
branch above. All relevant U must be completely rejected to return LOCAL_UNSAT.
Distinct U are exactly the distinct nonzero residues P modulo S over F2, so
deduplication by that residue is exhaustive.

## Witnesses and limits

Successful child supports are checked to be original nonzero rank-one points.
Gaussian elimination selects an independent subset of those original points;
it never substitutes reduced echelon matrices as factors. Exact coordinates
are recomputed for every ORIGINAL supplied raw slice, including zeros,
duplicates and dependent slices. solve_core expands the products and checks
every original core coefficient.

The reviewed outer image-rank cap is nine. The default vector cap1023 covers
a rank-ten child U, and the default extension cap1533 covers three splits for
each of511 possible nonzero matrices of a rank-nine S. Explicit smaller caps
are supported. Any unvisited U, capped/incomplete child, timeout, cancellation
or deadline exit is UNKNOWN with complete=false. Extension cursors are
diagnostic only and never permit skipping unproved candidates. All completed
positive and negative returns have a final guard check, including post-child,
post-lifting and post-core-expansion barriers. The fixed campaign deadline
2026-11-03T19:24:17Z cannot be extended by a caller.

## Controls

The tests independently enumerate all2892 subspaces of 2x2 and 2x3 matrices
and compare every supported budget against all rank-one-generated covering
spaces. The decisive new positive is S=span(E11+E22,E33+E44): surplus one
fails, the repeated-pair branch produces four original rank-one points.
Additional controls add a nonzero backbone, apply dense invertible changes
of both matrix coordinates, reconstruct full raw cores, exercise corank-one
positive/negative instances, certify a no-rank-two-seed negative using two
disjoint rank-three blocks, and reject late or capped answers as UNKNOWN.
