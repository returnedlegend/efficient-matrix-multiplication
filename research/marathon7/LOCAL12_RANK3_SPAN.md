# Necessary rank-three image-span filter

This separate implementation never changes the rank-two classifier or old
lowrank-span threshold. It is applied only to an actual mode image S of
dimension9 at target11. A passing result supplies no decomposition.

Suppose S is contained in a rank-one-generated covering W with independent
rank-one basis P1,...,Pr and r<=11. The isomorphism F2^r -> W identifies S with
a coordinate subspace K of codimension k=r-9<=2. Choose k independent columns
of a matrix for the quotient map F2^r -> W/S. For each remaining column, its
unique dependence on those k pivot columns gives a kernel vector supported on
at most k+1<=3 coordinates. These fundamental kernel vectors form a basis of K
(each has its own distinct nonpivot coordinate). Their images form a basis of
S, each a sum of at most three rank-one matrices and thus of matrix rank<=3.
Therefore failure of all rank<=3 matrices in S to span S excludes CP<=11.

The implementation enumerates all511 nonzero coordinate vectors for a negative.
A pass may stop after nine explicit independent rank<=3 witnesses. It keeps
the actual slice-space basis and original coordinate witnesses. Cancellation
before or after classification is UNKNOWN, never an exclusion. Exhaustive4x4
matrix controls compare the new capped-rank classifier with an independent
scalar row-span oracle. Planted d9 positive and complete negative image controls
verify the span test, and a delayed primitive verifies the final guard.
