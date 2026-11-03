# Joint mixed-S4 static audit

The joint linear span of the same32 previously audited S4 invariant spaces
still intersects the old dictionary span only in the three old cubes. This
closes the cross-direction caveat in `C3_MIXED_S4_STATIC_AUDIT.md` for those32
spaces together. No dictionary extension, solver, decoder, or optimization
was performed.

The input bases are bound by prior manifest
`10fc4f65538ef95ea5920737ac996a0084ea93c5881f586d3133214999d715b9`.
All32 full24-column bases matched their individual hashes before and after.
The768 raw tensor columns have joint rank319. Against the approved old span
of rank201, the union has rank517 and intersection dimension3. Exact
intersection witnesses, independent original-column origins, rank identities,
source seals, and runtime code pins were checked and persisted.

The three intersection basis tensors are exactly the existing cubes at old
orbit indices135,254,274. Their normalized old product weights are1,1,1.
Gaussian elimination's original masks are also preserved; one is a dense
389-product representation of a tensor that is just one old cube. That raw
mask weight is not a minimum-cost claim.

For any whole-C3-orbit extension whose tensors lie in this joint space J, the
sum of new terms in a solution must lie in B intersection J, since the target
and old terms lie in B. It is therefore a sum of old cubes. Their independent
factor forms imply a mode-flattening rank equal to the number of cubes in
that sum. Replacing the new terms by those existing cubes cannot increase
product cost. The finite-dictionary optimum is consequently unchanged for the
joint tested32-space family. This is not a global tensor-rank lower bound.

A metadata-only scan of all factors in the275 approved representatives found
346 distinct external S4 spans modulo the old three-dimensional factor span.
The314 remaining spans were only inventoried; no basis or intersection was
generated for them and no continuation was launched.

The bounded CPU1 nice10/1024MiB job completed in0.133 seconds, with0.129 process
CPU seconds under a30-second outer limit. Live campaign guards, cutoff checks,
input and code rechecks, and guarded publications remained active.

| Artifact | SHA256 |
| --- | --- |
| `c3-joint-s4-space-audit-001/manifest.json` | `4270cc822121e0eb5b136b347cf2769bedf55b29c2f052bfc60da0ff0a888031` |
| `c3-joint-s4-space-audit-001/rank-intersection-witness.json` | `cc4386e90833e2b5e2ec8ccc675f3b1b74a76f9f5483bf702ae05c742f2b4682` |
| `c3-joint-s4-cube-witness-normalization-v1.json` | `619dc3c6d67e171dd62819b9c2b0b508943871fcb861fdbe74f17af5b94e8821` |
| `scripts/audit_c3_joint_s4_space7.py` | `6ffdbb137a9b8ba45edf138ee6fd4e2e7f7bb35586cb8a379c2e484fea52effc` |

All artifact paths are inside
`artifacts/marathon7_20261103T122417Z/`. The raw-column selected basis origins
allow every joint-space witness to be reconstructed from the original sealed
S4 bases. The report scope is the joint span of those32 bases only.
