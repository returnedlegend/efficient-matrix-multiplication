# Exact binary block prototype: independent QA

Core module `mmsearch/binary_block_descent7.py` at
`91ab85c2b61b0e914e117b501ed1cc16a0b6a5e2579ebe283c81f941317eb190`
passed independent mathematical and targeted implementation review. This is
clearance of the compact core only, not of an uninspected production adapter,
source pack, global candidate, or performance advantage.

For a fixed choice of two factor blocks, every slice along the third mode is
an independent nearest-codeword problem. The fixed opposite-factor products
are binary code columns; the factor bits in each slice select their XOR.
Enumerating all2^r selections and minimizing Hamming distance separately per
slice therefore globally minimizes the complete third factor block. The code's
Gray traversal enumerates exactly those selections, including duplicate
codewords. It retains an unchanged coefficient row on ties, giving a
nonincreasing exact integer residual loss. Perturbations and restarts may
increase the current loss, while the saved best loss stays nonincreasing.

Five new independent tests plus eight owner tests passed **13/13**, zero
failures/errors/skips, in0.601 seconds under CPU1 nice10/512MiB and a40-second
outer cap. The new exhaustive oracle covered all256 binary2x2x2 cores, three
fixed rank-two slot contexts, and all three update axes:2304 whole-block
updates, each compared against all16 literal possible factor blocks and a
separate scalar full-tensor loss. Contexts include zero factors and dependent
opposite-pair columns. Further controls cover noncubic shapes, zero slots/modes,
twelve seeded searches with monotone best/block losses, fixed hard UTC clamp,
history truncation, literal binary schema, codeword limits, and a final scalar
check finishing late.

Rank is capped at14 slots, mode dimensions at15, codewords at16384, history at
10000 entries, timeout at120 seconds, and finite sweep/restart/perturbation
counts are validated. Guards bracket exact block computation and final raw
checks. Input validation and a single scalar reconstruction are cooperative
operations rather than preemptible units; production needs its own process
memory/time envelope and global guard. A late exact compact witness remains
nested in UNKNOWN with no publication eligibility. Every unsuccessful result
is UNKNOWN, never an infeasibility statement.

RAW_EXACT_COMPACT only asserts equality of the supplied compact tensor's
coefficients. Original image injections, selected residual reconstruction,
whole ambient replacement, persisted primary and independent full checks, and
fresh publication barriers are still required in any production adapter. The
owner's84 single-bit Strassen repairs establish local correctness, not search
advantage; reported cold random and schoolbook-drop failures remain failures.

Evidence: campaign `binary-block-independent-controls-v1.{log,result.json}`.
New independent tests
`tests/test_binary_block_descent7_independent.py` have SHA256
`37efe234590d037103f4fa555d3f91a0a6b1e819464d5c80b5ddc654383ca25b`.
No production N5 read or decoder/optimization call occurred in these tests.
