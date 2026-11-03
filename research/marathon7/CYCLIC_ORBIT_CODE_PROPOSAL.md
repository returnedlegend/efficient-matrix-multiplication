# Weighted C3 whole-orbit code: prototype and proposed preparation

A separate tiny prototype is implemented in `mmsearch/cyclic_tensor_code7.py`. Seven controls pass, including a planted exact rank11-to-rank8 orbit relation. No n5 dictionary, column matrix, elimination, decoder, solver, or search has been run. The constructor deliberately accepts only n ≤ 3. The unrestricted whole-atom `tensor_code7` modules are unchanged by this work.

This branch uses the paper's C3 symmetry as a restriction of the candidate family. Its binary variables select **entire cyclic orbits of whole triples**. It does not independently choose factors, fix a factor mode, project factor spaces, or reuse the unrestricted 406-atom dictionary as its final variable family. No new rank bound or novelty claim follows from this design.

## Exact columns and weighted objective

For a nonzero literal binary triple `a = (u,v,w)`, define `rho(a) = (v,w,u)` and choose the lexicographically least of its three cyclic rotations as its representative. The orbit is `{a,rho(a),rho²(a)}` with duplicates removed. A reflection `(u,w,v)` is a different orbit unless it is already a cyclic rotation; the prototype does not identify it.

The tensor column is the XOR of the literal outer products of the **distinct** orbit members. Its product-count weight is 3 for a nonfixed orbit and 1 for a cube `(u,u,u)`. Three equal cube outer products would also leave one copy in F2, but the expanded product list contains exactly one cube. Zero factor masks are rejected, rather than silently assigned product cost.

Distinct orbits are disjoint sets of literal triples. Thus for a binary orbit-selection vector `x`, expansion has exactly `sum_j weight_j*x_j` distinct essential products, even if two distinct orbit columns happen to represent the same tensor. The cost is an integer weighted Hamming weight, not parity and not the number of selected orbits. Cube selection remains variable: the known seed has three cubes, but a future search must not freeze that inventory or silently replace the ≤92 target by an orbit-count bound.

Let `A` contain those full orbit columns. The exact condition is `A*x = T` over F2, where coefficient `(a,b,c)` is flattened as `(a*width+b)*width+c`, `width=n²`. The global matrix-multiplication target has one coefficient at `A[i,j], B[j,k], W[k,i]` for every `i,j,k`; `W[k,i]` is the trace-factor convention. Column elimination produces a particular solution and a complete kernel basis with selection-vector witnesses. Every state `x xor z`, for `A*z=0`, preserves the exact full tensor. No heuristic flip, reward or local-factor assumption enters this statement.

The tiny constructor validates full source-orbit closure, forbids duplicate essential triples, rejects missing source orbits, and checks expanded weight against the literal product list. Its candidate helper expands all triples first and compares the entire literal tensor with the full target; it publishes no WINNER and implements no production decoder.

## Why 5,225 invariant coordinates suffice

C3 acts on coefficient coordinates by `(a,b,c) -> (b,c,a)`. There are `width` fixed coordinates `(a,a,a)` and `(width³-width)/3` length-three coordinate orbits. The dimension of the invariant tensor subspace is therefore `(width³+2*width)/3`. At width 25 this is 5,225, compared with 15,625 full coefficients.

Every orbit column is invariant, including fixed cubes. The target is invariant because rotating the three factor coordinates sends the term indexed by `(i,j,k)` to the term indexed by `(j,k,i)`. Define `P` by selecting the coefficient at the least coordinate of each coordinate orbit. Define `L` by copying each selected bit to every coordinate in that orbit. Then `P*L` is the identity on 5,225-bit coordinate vectors and `L*P` is the identity on the invariant subspace. Both maps are linear. Consequently `A*x=T` in all full coordinates **if and only if** `P(A)*x=P(T)`, provided every input column and target is invariant. This is a lossless coordinate restriction with an explicit inverse, not a factor projection.

The prototype verifies invariance before compression and rejects noninvariant tensors. Controls exhaust all 16 invariant tensors at width 2, check complete coordinate partitions through width 25, expand compressed tiny columns and selection sums back to their full tensors, and verify n2/n3 candidate tensors through two implementations. The n5 target constant has 125 full one-bits and 45 selected invariant one-bits; its expansion reconstructs the same constant. No n5 dictionary column was constructed for these checks.

## Eligible known C3 rank93 seed

Read-only eligibility auditing identified all three sources from the prior published C3 branch `native42-cyclic93-001`. Each is already an explicit `native_initial_train` root in the current approved source-anchor manifest. The audit checked the root's approval record and pinned manifest, historical armed native plan, initial-pool membership, authoritative V43 training membership, and both heldout and evaluation identity exclusions **before opening the approved training payloads**. Parent lists are empty at these explicitly authorized training roots; unknown or descendant ancestry is not inferred from publication or exactness.

All three payloads passed both the primary and independent full 15,625-entry tensor checks, with exact rank 93 and complete C3 closure. Each has three cubes and 30 nonfixed orbits, hence 33 selected orbit variables of total weight 93. This is source inspection only; no n5 dictionary or matrix was built.

| Proposed use | Original source byte SHA-256 | Canonical termset SHA-256 |
| --- | --- | --- |
| Initial C3 seed | `56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b` | `270f411487d4a6b7e22380ea25cd2f26d699c3fea4095a8a9984dfb2f5d9ad2c` |
| Eligible alternate | `897eb861a5df9fe79ca8cc875696f5b20afa23800e223e76655e8c437cab583f` | `775365346f21bd2cce41cb81f0753b31fac9e353b5f3cf2805e07709fda049f2` |
| Eligible alternate | `590f4968948970268b17b6dafd6a09534c44638db97ce6d80d6c7f66a2588b73` | `4395f16a1da236cc86c1833f323f6e6ac23ec26e4d376382e6c493829c17d838` |

The source-anchor manifest hash is `26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8`. Root's eligibility approval explicitly grants source eligibility only, not dictionary construction or search. The full source audit pins the three canonical RL source identities, historical branch, registries and original bytes. No heldout or evaluation payload was read.

## Proposed bounded next stage, requiring root review

The concrete proposal is a **dictionary and rank audit only**, with no decoder or SAT call: use the C3 closure of whole atoms from the existing approved training corpus, include the selected known C3 seed, deduplicate canonical whole orbits, and refuse a corpus above 2,000 orbit columns. Every included source and ancestor edge must be replayed through the existing independently reviewed source gate under the same external root-approved manifest hash. An unknown derivation, heldout/evaluation ancestor, changed byte/hash/config, or cap breach returns DEFER without a dictionary. Do not select new payloads by searching directories or using heldout outcomes.

The approved manifest reports 406 distinct whole atoms; that is a metadata count already available from the approved source work, not a count recomputed here. C3 closure of that corpus yields at most 406 orbit representatives and at most 1,218 distinct expanded triples. The selected seed is itself in the approved known-input group. Closure adds only rotations of approved whole atoms; it does not form new combinations of their individual factors. The actual orbit count and kernel dimension remain unknown until a separately approved preparation run.

Suggested preparation envelope: one CPU1 job at nice 10, 1,024 MiB, 30-second wall cap plus the C7 absolute UTC/resource guard, with a new output directory and no solver/search dispatch. Freeze source/config/code pins and a deterministic dictionary before any later search proposal. Check full versus compressed column reconstruction, initial seed membership/cost 93, full target syndrome, rank/nullity and every kernel witness. If the kernel is zero, the seed is the unique representation in this finite dictionary and this branch has no alternative; stop without a decoder. If nonzero, report its size and estimated formula cost before proposing a bounded decoder.

At the hard cap, the raw compressed matrix is `5225*2000/8 = 1,306,250` bytes; the uncompressed matrix is 3,906,250 bytes. Elimination witness masks add at most roughly 0.5 MiB of raw bits, plus Python/object overhead. Column elimination has at most four million pivot-XOR steps at 2,000 columns. For the currently reported 406-atom corpus, the compressed column bits occupy at most about 259 KiB before overhead and there are at most about 165,000 pivot-XOR steps. These are dimension-based estimates, not measured n5 timings. Preparation must retain its hard budget and report UNKNOWN if it cannot complete.

A future weighted SAT bound can repeat each positive selection literal once or three times in an integer at-most encoder. Seven tiny controls include exhaustive truth-table comparisons of PySAT's sequential-counter encoding on repeated literals for weights `(1,3,1)`, `(3,3)` and `(1,3,3)` at every bound. Duplicate literals **must not** be canceled or deduplicated as they are in an XOR equation. This establishes the tested tiny encoder behavior, not production formula size or solver performance. At 406 columns there are at most 1,218 weighted cardinality inputs; a sequential counter at bound 92 is on the order of 112,000 auxiliary cells. Encoding full long parity equations into CNF can dominate this cost, especially at the 2,000-column cap, so no production SAT plan is approved or implemented here. Prefer a separately reviewed native-XOR backend or a rank-reduced exact formulation only after reporting actual matrix/nullity and memory estimates.

Any later candidate must expand the selected whole orbits into distinct literal triples, recompute true essential product count, and pass the primary full 15,625-entry verifier plus the independent exhaustive verifier on persisted bytes. Fresh post-verification guard/deadline checks, immutable proof/source/runtime checksums and marker-last publication remain mandatory. A negative result concerns only this finite approved cyclic dictionary and weighted bound; it does not rule out new atoms, other C3 decompositions or unrestricted rank92.

## Evidence

Prototype controls: `tests/test_cyclic_tensor_code7.py` (seven passed, zero skipped). Source audit: `scripts/audit_cyclic_tensor_code7_sources.py`. Frozen logs, code pins and source results are under `artifacts/marathon7_20261103T122417Z/cyclic-orbit-code7-prototype-v1`; tracked evidence is [evidence/cyclic-orbit-code7.json](evidence/cyclic-orbit-code7.json). This work used CPU1 at nice 10, made no Git operation, and did not modify the generic atom-code branch or the prior frozen campaign.
