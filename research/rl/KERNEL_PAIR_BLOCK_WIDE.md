# Exact pair blocks with wide kernel supports

This separate variant accepts `MMKERNELWIDE1` inputs and supports of3–128 groups.
It leaves the primary short worker, wrapper, reference, and frozen binaries
unchanged. The exact optimum-value proof is independent of support size. The
new witness validator uses the wide P*n=0 guard and the unchanged Python exact
optimizer, not the old eight-group validator.

`native/free_factor_pair_block_worker_wide.cpp` uses128-entry category and
partition buffers. Each of A=S1\S2, B=S2\S1, C=S1∩S2 is bounded by128; their union
can have256 groups but is never stored in an eight-entry buffer. Only initialized
prefix entries are read. Unused array tails are not zeroed per pair, preserving
the fast short-support path. Its engine and input magic explicitly identify the
wide version. PW=Y checks, zero-valued d/e, exact objective, safe pruning, cursor,
timeout and resume semantics are unchanged.

The supplied9331-circuit catalog includes the69 wide fundamental complements
and spans all1165 linear kernel dimensions. Each baseline has43,529,115 unordered
pairs. The scan is still only two selected directions around one fixed current
model. Full linear span does not make two directions exhaustive of the full
free-factor family and does not prove bounded-headroom connectivity or global
nonexistence. NO_TARGET names only the exact frozen baseline/catalog family;
UNKNOWN marks incomplete coverage. Catalog, instance, baseline, binary and source
hashes bind that scope explicitly.

The finite candidate set is complete for the optimum **value**, not necessarily
for all parameter pairs attaining that value. This version does not harvest
barrier ties and makes no completeness claim about constrained tie selection.

`scripts/campaign_kernel_pair_block_wide.py` repeats the exact Python optimum,
checks the native model against its witness, and verifies all15,625 global
coefficients before freezing a first target certificate. The three reviewed
600-second CPU2/768MiB jobs for KM93, AE93, and public095 are under
`frozen/kernel-pair-block-wide-v1/jobs/`; each job clips itself at03:07:35UTC.
Native memory remains capped at512MiB, with outer615-second allowance.

Three tests cover exhaustive16² objective checks with9–16-group supports, a
planted exact full2x2 tensor with two9-group kernels where chosen single moves
inflate12→17 but their joint optimum reduces12→8, changed-label native/reference
agreement, and malformed129/nonkernel rejection. A native zero-step5x5 control
also checks all9331 kernels and independently verifies the full15,625 baseline
coefficients. No actual wide block scan was launched during preparation.

```sh
python -m unittest tests.test_kernel_pair_block_wide
```
