# Exact two-direction kernel blocks

For supports S1,S2, partition A=S1\S2, B=S2\S1, C=S1∩S2. Applying masks d,e
changes free vectors by d on A, e on B, and d^e on C. If the counters include
zero vectors, the final zero count on the union is A[d]+B[e]+C[d^e], and active
delta is initial zeros minus that score.

An optimum with two contributing categories is captured by observed A×B,
A×C (e=a^c), or B×C (d=b^c). If only one contributes, fixing the other parameter
to zero preserves it and cannot subtract another contribution. Include (0,0),
single-category candidates, and all observed values including zero. Thus a
small finite candidate set gives the exact optimum over arbitrary 25-bit d,e.
The independent Python reference is `mmsearch/kernel_pair_block.py`.

ALS optimizes potentially inexact residual proposals and does not implement this
operation. Existing local free-factor SAT permits arbitrary vectors on larger
unions, but is a different solver formulation. This branch reuses fixed-pair
equations, circuit validation, axis decoding, and independent tensor verification;
it does not claim a new mathematical identity.

`native/free_factor_pair_block_worker.cpp` statically scans every unordered pair
of the supplied short3..8 circuits on one fixed baseline W. Disjoint blocks
separate into cached exact single-direction optima. Overlapping blocks are
pruned when maxA+maxB+maxC cannot reach the target; otherwise the exact candidate
optimizer runs. The native model is updated only if the final atomic block
meets the target. Both individual updates preserve PW=Y even if an intermediate
active count inflates. There is no intermediate headroom constraint.

The worker checks every circuit and original PW=Y at start and every model
checkpoint. It records total/considered/disjoint/bound-pruned/exact-evaluated
pairs, minimum single delta, baseline/input hashes, last completed pair and next
lexicographic cursor. MODEL_FOUND is pending independent verification; NO_TARGET
means the finite requested pair suffix completed; UNKNOWN distinguishes wall,
signal, or pair limits. None is a global UNSAT claim. The native guard remains
3..8; a wider adapter is deliberately deferred.

`scripts/campaign_kernel_pair_block.py` freezes inputs, RREF, code, binary and
commands. It repeats the exact Python block optimum and verifies the actual
native model against its witness, then independently checks all15,625 matrix
coefficients before the exclusive first-winner helper can freeze rank≤92.
`--resume-from` verifies identical instance and binary hashes and contiguous
prefix coverage, passes the saved cursor, and accumulates coverage. A NO_TARGET
summary claims full finite-family completion only when that entire exact input
catalog's pair prefix is covered. The root jobs pass `--deadline-utc` to clip
all phases before the global campaign deadline, with cleanup reserve.

All three baselines KM93, AlphaEvolve93 and public095 have their fixed WU pairs
inside the same1536-pair dictionary. Each preflight independently verified the
baseline and all9262 supplied circuits. Each source has42,887,691 unordered
blocks. Frozen600-second job configurations are under
`frozen/kernel-pair-block-v1/jobs/`; no long search was launched in preparation.

Four tests cover independent exhaustive16² mask enumeration with zeros and empty
categories; a globally exact naive9 fixture where neither single direction
strictly reduces but the joint block produces8; native model/reference agreement
under changed labels; timeout/pair-limit cursor resume; and nonkernel rejection.
A separate native zero-step5x5 control verifies all9262 circuit proofs and the
baseline, followed by independent all15,625 global coefficients.

```sh
python -m unittest tests.test_kernel_pair_block
```
