# Exact Fano quotient branch encoder

This encoder handles the remaining no-repeated-quotient branch for the two
pinned d=11, b=7 residuals `p01-05-17-19` and `p01-06-17-19`. It is separate
from the prior CP<=13 decision and all repeated-pair child decisions. A
`FANO_BRANCH_UNSAT` result alone never excludes CP<=14.

Let S have its recorded 11 independent matrix basis vectors. Choose seven
independent **original rank-one points** spanning its full rank-one backbone
B0. Reduced elimination rows are only membership aids; they are never used as
unit-cost factor points. Extend these original B0 coordinate vectors with four
original S coordinate unit vectors to define a quotient map S -> S/B0.

Seven unknown pair matrices Pi=ui outer vi obey

```
s4=P4+P1+P2, s5=P5+P1+P3, s6=P6+P2+P3,
s7=P7+P1+P2+P3,   each sl=sum_t z[l,t] S[t].
```

A is the 4 by 4 matrix whose columns are the four quotient coordinates of sl.
An existential B is constrained by AB=I. Each multiplication is an exact
three-clause Boolean AND gate; every sum is a native binary XOR constraint.
Invertibility forces the sl to span S/B0, so S is contained in the span of the
seven original B0 rank-one points and the seven unknown rank-one points. SAT
therefore gives CP<=14. No quotient-direction independence or nonzero-factor
constraint is needed for soundness; zero products are omitted.

For completeness of this branch, first suppose a minimal cover has rank 14
(the smaller-rank case is the separate prior decision). Exchange basis points
so its rank-one basis contains the seven original B0 points. The remaining
seven basis points have nonzero classes in the three-dimensional quotient Z/S.
A repeated class is covered by the separate repeated-pair branch. Otherwise
these classes are all seven nonzero vectors of F2^3, and a Fano labeling gives
the four circuit equations above. Their classes modulo B0 are independent:
P4, P5, P6 and P7 each occur uniquely in the respective circuit in the chosen
Z basis. Thus these covers satisfy the encoder. Combining all three complete
negative branches is required for a complete CP<=14 residual negative.

The production formula has 1141 variables: 154 factor bits, 44 S coefficient
bits, 847 pair-matrix AND outputs, 16 A entries, 16 B entries and 64 inverse
AND outputs. It has 2733 CNF clauses and 516 native XORs: 484 matrix circuit
equations, 16 quotient links and 16 AB=I equations. Matrices use row-major
bit index i*columns+j. A's row is a quotient coordinate and its column is a
circuit index; inverse-product output [r,c,k] is A[r,k] AND B[k,c].

Every SAT model is checked against all CNF/XOR constraints, literal outer
products, every original raw slice (including zeros and duplicates), and the
complete compact tensor. Original factors are retained when selecting an
independent support. Full ambient reconstruction, all 15625 coefficient checks,
independent verification and global record publication remain caller gates;
this module always marks SAT as not publication eligible.

The solver uses a fresh spawned process, a hard child address-space limit,
native single-thread CryptoMiniSat, bounded parent polling and forced child
termination/reaping. Signal/case/absolute UTC checks occur before and after
all completed returns and after model/core reconstruction. Late raw solver or
compact witnesses are retained under UNKNOWN. The hard UTC cap is
2026-11-03T19:24:17Z. The parent counts process startup against the case budget. A validated private
deep copy is supplied to the worker and decoder. After every live guard callback,
both that copy and the caller-owned formula are checked against the original
construction hash. Drift returns UNKNOWN, including after model decoding;
late raw witnesses are preserved. The earlier v1 bundle is retained unchanged.
Explicit model assumptions are supported for synthetic controls only; an
unsatisfiable assumed solve returns `FANO_ASSUMPTIONS_UNSAT` with
`fano_branch_complete=false`, never a complete Fano branch exclusion.

`fano_quotient_adapter7.load_pinned_case` accepts only ordinals 2 and 3 from
metadata manifest 959b97aaf3e95df8a0933143bf935bdd1cfae7c625b191c22cad7b75a75cb4d9
and all-nine core receipt
f0487990ecff816bf6f3b51605071f22e35b32c9cc5d0cdfa8b8378daeffb571.
Metadata case bytes are fixed by independent case-02/case-03 SHA256 constants;
core bytes must also match their exact case/ordinal entry inside the pinned
all-nine core manifest. Mutable sibling checksums are not source authority.
It checks exact source core bytes, all raw slice indices, the complete 2047-point
rank-one census and original factor witnesses before constructing the formula.
The standalone preparation CLI calls no solver.

Twelve owner controls pass with real CryptoMiniSat and no skipped tests. They
include all eight AND truth assignments, 625 restricted full models (24 valid
quotient bases), a reduced-backbone counterexample, model corruption, zero
factors, duplicate/zero raw slices, deadline/late-model handling and forced
reaping. The independent synthetic 11^3 d11/b7 fixture has no rank-two directions
outside B0, excludes CP<=13 by the necessary rank-two span bound, and has an
explicit 14-product Fano cover. Its fixed-factor real solver control reconstructs
all 1331 compact coefficients. No N5 source feasibility query was run.
