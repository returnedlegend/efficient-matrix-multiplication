# Conditional surplus-three review for the nine d11 packets

The repeated-pair argument is sound for the seven packets whose complete
rank-one backbone B0 has dimension at most6. This note authorizes no decoder,
SAT encoding, or query; the completed job was metadata only.

Let S be the11-dimensional matrix slice image. A cover by at most13 rank-one
matrices is the separate prior CP(d+2) case. Otherwise a minimal cover of at
most14 matrices spans a14-dimensional rank-one-generated space Z containing
S. Choose a basis of B0 consisting of original rank-one points, then extend it
to a rank-one basis of Z using cover points. Every remaining basis point is
outside S: a rank-one point in S belongs to B0 and would be dependent.

If b=dim B0<=6, there are14-b>=8 outside points but only seven nonzero values
in Z/S. Two points P,Q have the same quotient value. Their difference D=P+Q
lies in S and cannot lie in B0, since that would give a relation among the
chosen Z basis points. Since all rank-one points of S are in B0, D has exact
matrix rank two. Enumerating every rank-two D outside B0 and its three binary
rank-one splits therefore includes this pair. Its child S+P has dimension12
and a rank-one cover of size at most14. Conversely any such child cover covers
S. Thus a complete negative requires a completed prior CP<=13 decision and
completed CP<=14 decisions for all distinct child cosets. Capped or late
branches remain UNKNOWN. For b>=7 this pigeonhole argument is insufficient.

The source/core metadata job classified all2047 nonzero matrices of each S,
retained every original rank-one point and factor witness, constructed B0,
enumerated every rank-two difference outside B0 and all three original endpoint
splits, and deduplicated children by exact quotient coset. It verified each
child has dimension12. Results in fixed nine-case order are:

| Case suffix | b | Rank-one points | Relevant rank-two differences | Child cosets | Pair argument complete condition |
| --- | --- | --- | --- | --- | --- |
| p00-05-10-14 | 4 | 4 | 8 | 18 | b<=6 |
| p00-10-14-17 | 5 | 5 | 4 | 12 | b<=6 |
| p01-05-17-19 | 7 | 9 | 9 | 15 | not proved |
| p01-06-17-19 | 7 | 9 | 9 | 15 | not proved |
| p01-10-14-17 | 4 | 5 | 9 | 22 | b<=6 |
| p10-14-15-23 | 0 | 0 | 18 | 40 | b<=6 |
| p10-14-17-19 | 4 | 5 | 9 | 22 | b<=6 |
| p10-14-25-27 | 0 | 0 | 18 | 40 | b<=6 |
| p15-23-25-27 | 0 | 0 | 18 | 40 | b<=6 |

There are194 children in the seven conditionally complete cases, and224 across
all nine. No CP<=13 or CP<=14 query was made. The bounded metadata job used
CPU3 nice10/1024MiB, completed in0.274 seconds with0.264 process CPU seconds,
and released CPU3 to the separately authorized regression job.

## Additional Fano branch for the two b7 cases

The proposed Fano characterization is also sound. After the prior CP<=13 case,
choose a14-point rank-one basis of Z containing seven original rank-one B0
basis points. If outside quotient classes repeat, the repeated-pair branch
applies. Otherwise the remaining seven points realize all nonzero elements of
the three-dimensional quotient Z/S. Label P1,P2,P3 with independent quotient
values and label P4,P5,P6,P7 by their pair/triple sums. Then

    s4=P4+P1+P2, s5=P5+P1+P3, s6=P6+P2+P3,
    s7=P7+P1+P2+P3

lie in S. Their classes modulo B0 are independent: a relation among them and
B0 has unique coefficients at P4,P5,P6,P7 in the Z basis. They therefore form
a basis of S/B0, whose dimension is four.

Conversely impose those four circuit equations with each si in S and their
four quotient-coordinate vectors forming an invertible4x4 matrix. Then all
four complement directions lie in span(B0,P1,...,P7), so that rank-one space
contains S and has a cover of at most14 points. No separate independence or
nonzero constraints on the three quotient directions are required for SAT
soundness; degenerate satisfying models still give a valid cover. A branch
UNSAT is not by itself a complete CP<=14 negative: the prior CP<=13 and
repeated-pair branches must also close completely.

Implementation caution: `backbone_coordinate_basis_hex` stores reduced
elimination vectors, which need not themselves be rank-one matrices. For the
seven fixed unit-cost B0 products, select an independent subset of the
**original** `rankone_points`, retaining their left/right factor witnesses.
Extend those seven coordinate vectors to an11-vector basis to define the four
quotient coordinates, and document whether circuit vectors are matrix columns
or rows. An existential right inverse AB=I is equivalent to invertibility over
F2. This review implemented neither the encoder nor a solver invocation.

Sealed metadata:
`artifacts/marathon7_20261103T122417Z/c3-surplus3-pair-metadata-nine-v1/`.
Manifest SHA256
`959b97aaf3e95df8a0933143bf935bdd1cfae7c625b191c22cad7b75a75cb4d9`;
all-nine source/core authority
`f0487990ecff816bf6f3b51605071f22e35b32c9cc5d0cdfa8b8378daeffb571`.
The two b7 records are `case-02.json` and `case-03.json`.

All scope is local to these exact fixed-outside residuals. No global tensor
rank lower bound follows from this metadata or proof review.
