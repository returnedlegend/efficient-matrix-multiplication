# Exact optimization of three kernel directions

Let the fixed-pair model be `P W = Y` over F2, with each free vector W[g]
an exact integer mask of width n². Three supports S1,S2,S3 satisfy P n_i=0.
A simultaneous update adds n1*d+n2*e+n3*f, so it preserves every original
equation for arbitrary masks d,e,f, including zero.

Partition the union by nonzero membership mask s in F2³. Let C_s[w] count
the groups in that class whose current vector equals w, including w=0.
After the update, the number of zeros in the union is

    score(d,e,f) = sum_{s!=0} C_s[s1*d XOR s2*e XOR s3*f].

The active-count change is initial_zeros − score. Every class lies in one
support, hence has at most128 groups when each support has at most128.
The union may have384 groups; no128-element union array is used.

## Completeness of the finite optimizer

Fix a global optimum x=(d,e,f). Let M be the parity classes with positive
matched frequency at x. Choose an independent basis B of span(M), with
0≤|B|≤3. For each b in B the value b*x occurs in its bag C_b, including
zero when appropriate. Enumerate B and these observed values and solve
the at most3 equations over F2, setting unconstrained parameters to zero.
Every s in M is a linear combination of B, so the resulting solution x'
has s*x'=s*x. It preserves every positive matched contribution of x.
The remaining classes contribute nonnegative counts, so score(x')≥score(x).
Since x was optimal, equality follows. The zero assignment handles an
empty basis. Thus this enumeration attains the global optimum over all
2^(3*n²) direction triples.

Python performs elimination for each constraint assignment. C++ separately
precomputes each independent basis's three output XOR expressions and
enumerates observed values. There are7 rank1,21 rank2,28 rank3 class bases.
The implementation need not enumerate every optimal assignment or return
the globally smallest optimal assignment; only the optimal score matters.

## Safe pruning and interruption

The frequency upper bound is sum_s max_w C_s[w], with empty bags contributing
zero. If baseline_rank+initial_zeros−upper_bound exceeds the target, that
triple cannot reach the target. Zero frequency is included in this bound.

For a disconnected support overlap graph, an isolated direction acts on a
disjoint component. Its optimum is the modal frequency, including zero;
the other two directions are solved independently by the same exact basis
enumeration restricted to their classes. Adding their exact scores gives
the exact disconnected-block optimum. This also supplies a valid independent
component bound. No assumption that individual or pair moves improve is used.

The native worker checks its deadline and signal flag inside observed-value
enumeration. Interrupted triples do not advance the completed-row cursor.
The worker returns UNKNOWN on time, row budget or interruption; NO_TARGET
means the finite supplied catalog suffix was exhausted. ERROR denotes rejected
input, invariant failure, or IO failure. MODEL_FOUND remains provisional until
the Python optimizer and full independent n^6 tensor check accept the witness.

## Finite coverage and reproducibility

The runner freezes dictionary, baseline, kernel circuits, native input,
ordered triple catalog, binary, source snapshots and SHA256 manifest. Its
default subset uses the first5 new directions plus48 local active anchors.
For each anchor it keeps a deterministic promising half of48 neighbors and
a seeded sample for the other half, then forms connected anchor wedges.
Priority tiers are followed by a lexicographic index tie-break. The contiguous
catalog row cursor identifies an exact prefix of this frozen total order.
Resume requires identical input, catalog and binary hashes, and matching
prefix count/cursor. The family is always explicitly described as a subset.
Neither exhausting it nor exhausting one frozen model implies global UNSAT.

The validation controls cover width3 exhaustive8³ assignments, a triple-only
barrier (all single/pair deltas0, triple delta−1), randomized feasible n=2
native witnesses with full64-entry independent checks, invalid Pn/PW,
support129 rejection, finite NO_TARGET, UNKNOWN and suffix cursor behavior.
The campaign runner accepts a winner only after the full15625-entry n=5
verification and an independent exact block optimum check.
