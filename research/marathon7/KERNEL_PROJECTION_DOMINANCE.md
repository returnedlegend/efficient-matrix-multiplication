# Weighted kernel-projection dominance certificate

This new isolated inspector lives in `mmsearch/kernel_projection_dominance7.py`.
It loads no files, selects no atoms and runs no optimization. Tests use tiny
binary linear codes only. No N=5 dataset is inspected without root authority.

## Exact search space and sufficient theorem

Let A be a finite binary column matrix, let E=[A B] preserve A's columns in
exactly the same order, and let t have an explicit feasible base selection s:
A s=t. Binary selection masks use each dictionary coordinate at most once.
Attach fixed nonnegative integer costs to coordinates, with exactly equal old
costs in A and E. Write w_old and w_new for the corresponding weighted Hamming
costs. The minima concern ALL masks satisfying the complete packed equations,
not a local neighborhood, orbit coefficient relaxation, integer lift, or a
subset with extra frozen-coordinate constraints.

Let K=ker(E). Choose zero relations C1,...,Cr whose NEW-coordinate projections
form a basis of pi_new(K). For every extended feasible x, x+(s,0) belongs to K,
so x_new lies in pi_new(K). There is a UNIQUE coefficient vector alpha with

    C = sum(alpha_i C_i),   C_new = x_new.

Then y=x+C has no new coordinates and A y_old=t. Nonnegative weighted Hamming
cost satisfies the triangle inequality, giving

    w(y_old) <= w(x_old) + w(C_old).

If EVERY alpha satisfies w(C_old)<=w(C_new), then

    w(y_old) <= w(x_old)+w(x_new)=w(x).

Thus every extended feasible selection maps to an old feasible selection of
no greater cost. Since every old selection embeds in the extension, the two
GLOBAL finite-dictionary minima are equal. This is a routine exact code
certificate and establishes no global tensor-rank lower bound or novelty.

The test is SUFFICIENT for the chosen lifts. A negative margin
w(C_new)-w(C_old) only disproves that sufficient condition; it does not prove
that the extended minimum improves. Lifts can differ by old-only kernel
relations, so another lift choice can give a stronger certificate. POTENTIAL
returns only a zero-relation counterexample, never an improved feasible state.

## Validation and bounded enumeration

The inspector checks literal integer columns, exact ordered old-prefix
alignment, aligned nonnegative integer costs and the old feasible target mask.
It computes exact extended column rank, checks every supplied kernel vector
is nonzero/null/independent, and requires dimension n-rank(E). Hence the
supplied kernel really is complete. If none is supplied, exact Gaussian
elimination constructs it with full combination witnesses.

It selects ORIGINAL null vectors with independent new projections, or checks
explicit user-provided lifts. Every lift must be null and its projection
nonzero/independent; their span must include every complete-kernel projection.
The projection rank is also checked against

    dim ker(E) - dim ker(A).

This equality uses the exact shared prefix; counting the number of appended
columns or supplied relation witnesses alone is not a valid substitute.

For r<=20 it enumerates all2^r coefficients in Gray order. Weighted costs group
equal coordinate costs into bit masks, retaining exact integer arithmetic.
It records the minimum margin including alpha=0 (therefore zero in every
dominance certificate) AND the minimum among nonzero alpha, which is useful
for a strict positive gap. Zero-cost coordinates and zero binary columns are
permitted. r=0 still checks the single alpha=0 selection and certifies equality.

DOMINATED means complete enumeration with all margins nonnegative and all
input/kernel/projection validations passed. POTENTIAL means complete scan with
a negative sufficient-bound margin, without a solution claim. Rank/state caps,
cancellation, timeout or the hard2026-11-03T19:24:17Z deadline return UNKNOWN.
Even a partial negative scan remains UNKNOWN. Every completed answer has a
final guard barrier; partial observed margins are distinguished from completed
minima and never certify equality.

## Tiny controls and why interactions matter

The weighted single-cycle fixture has old columns1,2 and new columns4,8,15.
Their unique five-term zero relation uses both old coordinates (cost2) and
all three new coordinates (cost3+3+1=7). Its new projection rank is one, its
nonzero margin is5, and brute force confirms equal old/extended minimum2.
This is only a tiny analogue of the described cyclic cost pattern, not an
inspection or new result on that production dataset.

The interaction fixture starts from old columns1,2,4,8 and adds16,32,51,60.
Two five-term zero relations each use old cost2 and new cost3, individually
satisfying the bound. Their XOR cancels two shared new coordinates, leaving
old cost4 versus new cost2. The joint condition fails. At target15 the tiny
extension really improves4 to2; at target0 both minima stay0 despite the same
negative margin. These fixtures show both why interactions matter and why a
negative bound is only potential.

Tests also compare200 random weighted tiny codes against exhaustive complete
fiber minima, reject incomplete/dependent/non-null kernels and incomplete
projection bases, exercise alternate lifts, empty/zero-cost cases, alpha=0,
caps, partial negatives, malformed numeric types and late completed returns.
Production evaluation of any actual extension remains separately authorized.

## Subsequently authorized static N=5 audits

Root explicitly authorized one static audit of each existing extension, without
optimization or target SAT: CPU1 nice10,1GiB address space,30 seconds and32MiB
output per audit, with a fresh canonical C7 guard. Both completed within bounds.
`scripts/audit_kernel_projection_dominance7.py` pins all parent/extended/witness
bytes, reconstructs the existing full columns, verifies the full trace target
and a single old feasible seed, and invokes the inspector with the authenticated
short zero relations. It never forms old-seed/extension combinations or searches
the32 seeds. An additional independent ordinary binary-subset scan repeats the
margin computation without the inspector's Gray implementation.

| Existing dictionary extension |Projection rank |Complete margins |Minimum nonzero margin |Result |
|---|---:|---:|---:|---|
| Generic406/rank309 ->444/rank331 |16 |65,536, checked twice |+1 |DOMINATED |
| C3 orbit275/rank201 ->278/rank203 |1 |2, checked twice |+5 |DOMINATED |

The generic audit used all16 authenticated five-term relations, verified that
their new projections span the WHOLE new kernel image, and did not fill any
missing direction. All weights were one. It ran in1.678s with29,820KiB high-water
RSS and2.61MB output. Its pinned parent was cf4644... and extension8525c790....
The C3 audit verified the physical orbit-ID permutation before aligning the old
prefix, remapped the complete kernel and known five-cycle, and independently
checked old relation cost2/new cost7 with new projection111. It ran in0.110s
with28,596KiB RSS and2.82MB output. The direct relation checks and exhaustive
projected scan agree on the strict gap5.

Both certificates prove exact equality of the parent and extended GLOBAL
finite-dictionary minima. More strongly, every extended feasible state using
any new coordinate maps to an old feasible state at least1 generic product,
or5 C3 weighted products, cheaper. Therefore no minimum-cost selection in
these extensions needs their new coordinates. This does NOT establish either
parent minimum, prove the parent minimum is93, or exclude92 products in the
parents or elsewhere. Parity opening and independent new matrix directions
alone gave no minimum-cost advantage in these two measured extensions.

Complete input/code snapshots, guard/resource observations, checksums and small
zero-relation witnesses are stored in the new read-only-source audit outputs:

* `artifacts/marathon7_20261103T122417Z/kernel-projection-dominance-generic-001/result.json`,
  SHA256 `4e5337451d391558d395779a73256a530df96650c6c72b67ecb90b6abe7cdcbf`.
* `artifacts/marathon7_20261103T122417Z/kernel-projection-dominance-c3-001/result.json`,
  SHA256 `02a3dd4db66083aecf102df4b9af2f4ec14ab08b560506e5dcd63d22d3d92fc6`.

The combined small summary is
`research/marathon7/evidence/kernel-projection-dominance-authorized-audits-v1.json`.
All registered output checksums were reread and verified. Original source
artifacts and helper files were read only; no target optimizer or SAT call ran.
