# Pure seed-cube-span extensions cannot improve this finite dictionary

The static audit confirms the root's domination proof and strengthens it: **the isolated polarization extension has exactly the base dictionary's optimum, and so does the whole C3 orbit closure whose factors remain in the three-dimensional seed-cube factor span**. The earlier congruence opening is real but supplies only dominated higher-cost solutions. No optimization is needed for this conclusion.

This statement concerns the sealed **275-column finite base dictionary** and the specified additions. It does not determine that base dictionary's unknown minimum weight or establish a global matrix-multiplication rank bound. Extensions that interact through factors outside this span are not ruled out.

## The isolated three-column extension is strictly dominated

Independently projecting the complete 75-vector extended kernel onto the three new coordinates gives rank **1** with image **{000,111}**. The embedded 93-product seed has new-coordinate state 000. Thus every affine solution either uses none of the new columns or uses all three.

The new columns have weights **1,3,3**, totaling **7**. The certified five-orbit zero relation toggles those three new columns plus exactly two old cube columns of total weight **2**. For any solution using new 111, XOR that zero relation. All new columns disappear, and the two old cube bits change at a cost increase of at most 2. The resulting base solution costs **at least 5 products less**. Solutions with new 000 are already base solutions. Since every base solution embeds in the extension, the two finite-dictionary optima are equal.

The audit rechecked the exact old-to-new column embedding, the source-state embedding, the independent rank 75 kernel witnesses and their zero tensor syndromes, the projected image, and the relation's weights and zero syndrome. The new-coordinate weights and the old two-cube bound are essential; parity permission alone does not establish useful coupling. No SAT or decoder run on this isolated extension is proposed.

## The eleven-dimensional space has no additional coupling to the base

Let `a1,a2,a3` be the independent approved cube factors **4096,262208,16777217**, and let `V` be their GF2 span. The C3-invariant tensors in `V⊗V⊗V` form a space `S` of dimension 11. The audit constructed only this basis:

- Three cubes `ai⊗ai⊗ai`.
- Six ordered mixed orbits `Cyc(ai,ai,aj)`, for `i≠j`.
- The two distinct orientations `Cyc(a1,a2,a3)` and `Cyc(a1,a3,a2)`.

A reflection was not identified with a cyclic rotation. Every basis column received independent evaluation of all 15,625 coefficients and a full invariant-coordinate projection/inverse check, totaling **171,875 coefficient checks**. Exact Gaussian elimination against the sealed base span `B` gave:

| Quantity | Rank / dimension |
| --- | ---: |
| Base span `B` | 201 |
| Cube-factor invariant space `S` | 11 |
| Union span `B+S` | 209 |
| Quotient of `S` modulo `B` | 8 |
| Intersection `B∩S` | **3** |

The intersection witnesses use space masks **0x1,0x2,0x4**, exactly the first three cube basis tensors. Each witness includes an explicit base-column mask and its equal full tensor. The three tensor witnesses are independently verified. Since those existing cubes are independent and the intersection has dimension 3, **`B∩S = span{a1³,a2³,a3³}`**. The other eight space basis columns are independent modulo the base. No larger extended dictionary was generated.

## Flattening proves domination of the whole pure-V closure

The multiplication target `T` belongs to `B`, as certified by the original exact 93 seed. In any solution using old columns plus new whole orbits with factors in `V`, let `Y` be the tensor contributed by the new columns. It lies in `S`; also `Y = T + old_part` lies in `B`. Therefore the measured intersection implies

`Y = λ1*a1³ + λ2*a2³ + λ3*a3³`.

Because the factor forms are independent, a matrix flattening of this tensor has rank equal to the number `k` of nonzero cube coefficients. This follows by applying dual factor coordinates: the diagonal core has exactly `k` nonzero diagonal components, with independent left factors and independent right tensor-square factors. Any representation of `Y` costs at least `k` rank-one products. The existing `k` cube columns represent `Y` with exactly that cost. Replacing the new-column part by these old cubes and canceling duplicate old cubes cannot increase the full product count.

Hence every solution from **any** pure-V whole-orbit extension has an old-dictionary solution of no greater cost. The reverse inclusion is immediate. The optimum is unchanged even if every orbit with factors in `V` were made available; this proof does not require materializing that closure. It is stronger than the single-pair strict 5 domination, but still restricted to this approved factor span and base dictionary.

An interacting extension would have to escape this argument, for example by using a different subspace with an intersection containing additional tensors, and then pass the separate weighted-dominance analysis. An intersection larger than the old cube span would show coupling potential only, not an achievable rank reduction. No new such audit or optimization was launched here.

## Evidence and limits

The authorized audit constructed **only 11 basis vectors**, ran on **CPU1 at nice 10** with the original **10-second / 1,024 MiB** limits and strict 19:24:17 UTC/fresh stage guards, and completed in **1.284264 measured CPU seconds /1.299408 outer wall seconds**, at **35,796 KiB** peak RSS. Final output is **76,884 bytes**. Three tiny controls passed: literal tiny-span intersection comparisons, the diagonal-cube flattening count, and dependent-space rejection. Frozen CLI preview passed before the one live audit. No solver, optimization, candidate state or larger dictionary was generated.

Sealed package: `artifacts/marathon7_20261103T122417Z/c3-cube-space7-audit-001`. Its completion seal and all six declared file hashes were rechecked; `UNKNOWN.json` is absent. Frozen runtime, configuration and controls are in the adjacent `c3-cube-space7-ready-v1` package. Old packages remain immutable.

| Artifact | SHA-256 |
| --- | --- |
| `manifest.json` | `53dfd73a0ae36af3029b2f6b46d2fa9ed57c381dcbb7face50b3bd27991ddf5d` |
| `space-basis.json` | `b422c5c3859080cf90d3129f7a9f8cff70931cd05b9181d03a8822b8a667dd36` |
| `rank-intersection-witness.json` | `b6cd946951f251d7ef9df2c7a1fd5b649bfae07a7d8801781f6243166e1528d2` |
| `single-polarization-domination.json` | `1ada9d54a19459a281f948f3ef22f6adc36498e922c895064218a30417a7c22a` |
| `proof.json` | `bfda2cb48060f3242b788a290277473f0d9a12b8e651eb6eb7fc9afeb795ba42` |

Tracked compact evidence: [evidence/c3-cube-space7.json](evidence/c3-cube-space7.json). The weighted-projection helper owned by the NewMoves workstream was not modified. No paid compute, publication, continuation or Git operation was performed.
