# C3 dictionary audit: 275 orbit columns, rank 201, nullity 74

The single corrected v2 audit completed within its original limits. It prepared a **275-column weighted C3 whole-orbit code**, with full and compressed rank **201** and complete kernel dimension **74**. The known seed expands to **93 products in 33 selected orbits**. No optimization, SAT call, heuristic or decoder search was performed.

| Audited quantity | Result |
| --- | ---: |
| Approved base whole atoms | 406 |
| Replayed approved source states | 32 |
| Distinct C3 orbit columns | 275 |
| Nonfixed orbits / cubes | 272 / 3 |
| Distinct products after orbit expansion | 819 |
| Full / invariant coordinates | 15,625 / 5,225 |
| Full / compressed column rank | 201 / 201 |
| Kernel dimension / independent witness rank | 74 / 74 |
| Known seed orbits: nonfixed / cubes | 30 / 3 |
| Known seed weighted product cost | 93 |
| Individually forced variables / forced cubes | 0 / 0 |
| Independent dictionary coefficient checks | 4,296,875 |
| Dictionary projection/inverse coefficient checks | 4,296,875 |

The 406 approved whole atoms were closed under cyclic rotation and deduplicated into whole-triple orbits. Expansion contains 819 distinct literal products, including 413 rotations beyond the original 406-atom list. No factors were independently recombined. This finite dictionary differs from the unrestricted 406-atom branch: adding rotations and requiring linked whole-orbit selection changes its candidate family, so its smaller rank and nullity do not establish superiority or containment between the two finite codes.

## Parity and cube constraints

Every one of the 74 complete kernel-basis vectors has even popcount. Both allowed product weights, 1 and 3, are odd, so weighted product cost has the same parity as the number of selected orbit variables. Every affine solution therefore has the seed's **odd** weighted-cost parity. The subsequent read-only affine analysis found that the three cube coordinates have projection rank 1: every complete kernel-basis vector projects to 000 or 111. Since the seed has cube state 111, every feasible cube state is either 000 or 111. Product cost is therefore `3*(nonfixed_orbit_count + cube_switch)`, hence divisible by 3. Combining divisibility by 3 with odd parity proves **every feasible cost is 3 modulo 6**, so the campaign bound **≤92 is equivalent here to ≤87**. No minimum weight was computed. This forces at least a six-product improvement from the seed inside this finite code; it is not a negative result for the target or a global rank bound.

The dictionary contains three cube variables, at columns 135, 254 and 274, with factor masks 4096, 262208 and 16777217. Each is selected in the seed, and each appears in at least one kernel-basis support. Thus none is individually forced. Their values are linked: only the all-present and all-absent patterns are allowed by the complete kernel. This was established by rank/projection analysis, without enumerating candidate states. All 275 variables are individually movable in the same coordinate-wise sense.

The seed inventory is **33 orbits = 30 nonfixed × 3 + 3 cubes × 1 = 93 products**, correcting the requested “31-orbit seed” description. Cube inventory was not frozen or removed from the weighted objective.

## Exactness and provenance

The immutable base preparation hash is `cf4644cab66d697f05d6724d919973b9884f17def9586c0e1220b9ea67554e2b`; the approved source-anchor manifest hash is `26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8`; the root source-eligibility record hash is `7354183ab6e9c89f76110e1c916738ced4856499632a2f317508b1d6bea7bb55`. The audit replayed the complete 32-source closure and exact derivations against the base preparation, including historical root approval, native initial-pool membership, training membership and prohibited heldout/evaluation identities. No private evaluation payload was read.

Each orbit column was independently evaluated on all 625 input-basis pairs and their 25 output bits, compared with the literal outer-product construction, compressed only after invariance validation, then expanded back to all 15,625 coordinates. Full and compressed eliminations both gave rank 201. Every kernel witness was checked in both representations, and a second elimination on witness masks verified independence and rank 74. The known seed's expanded triples matched its exact source terms, had weighted cost 93 and zero syndrome in both representations. Persisted seed bytes passed both primary and independent full 15,625-entry verifiers, with fresh forced guard checks after each.

The finished package is `artifacts/marathon7_20261103T122417Z/cyclic-orbit-code7-audit-002`. Acceptance requires `COMPLETE.json`, matching manifest/checksum hashes, and absence of `UNKNOWN.json`; all were rechecked after the run. All nine declared package-file hashes pass. The frozen v2 runtime and eleven passing tiny controls are retained in `cyclic-orbit-code7-audit-ready-v2`. The tiny constructor still rejects n5; the separate wrapper requires explicit audit authorization and immutable root pins.

| Persisted artifact | SHA-256 |
| --- | --- |
| `dictionary.json` | `23ff2b7ef344b79277712731cdc80ecc4b030a82026ca77d9fec32a02ebd047b` |
| `manifest.json` | `eb6337722adaf26ecc3e11795cc94865c2a556db7af70d4efd83b917bb0a392b` |
| `COMPLETE.json` | `4d89a75cacfef8ce26d3a17f0d0d2825f55f05efc51d62775231aac890d4e841` |

## Measured resources and the retained v1 stop

The corrected audit used **5.780331 CPU seconds** (5.201885 user, 0.578446 system), **5.781516 outer wall seconds**, and **42,028 KiB** peak RSS. It ran on CPU1 at nice 10, with a 1,024 MiB address-space limit, 30-second hard audit alarm, 32 MiB aggregate output cap, 2,000-orbit cap, and canonical fresh guard clamped to **2026-11-03T19:24:17Z**. Final output is 1,428,180 bytes. Packed full columns occupy 500,638 bytes; compressed columns 127,768 bytes; kernel witnesses 1,485 bytes. These packed sizes exclude Python/object overhead; peak RSS is the observed process measurement.

The first attempt remains immutable **UNKNOWN_STOPPED_AUDIT** at 29.997572 CPU seconds, 30.060935 outer wall seconds and 45,008 KiB peak RSS. It published no completed dictionary or rank result. A read-only diagnostic showed ten forced guard checks cost 0.304611 CPU seconds at an observed operations-state size of 1,365,618 bytes, versus 0.000277 seconds for ten normal canonical loop checks. Version 1 forced large state reads and recursive output scans throughout inner work. Root explicitly approved exactly one corrected retry after eleven tiny controls passed; no budget was expanded.

Version 2 retained forced fresh checks before/after source replay, full verifiers, the column/rank stage and output publication. Inner loops use normal canonical polling (at most 0.1 seconds for global state) with UTC and signals checked on every call. The deterministic replay-copy peak was bounded before creation; strict stage boundaries check aggregate output. This removed avoidable repeated scans while preserving stop checks. No further unchanged retry is authorized or needed.

## Concrete next proposal; not authorized

The prepared result supports designing an **exact finite weighted-SAT formulation**, rather than lengthening a heuristic walk. A future encoder can use 74 kernel coefficients `z` and constrain 275 selection bits by `x = seed xor K*z`, then require integer product cost `sum weights*x ≤87`, equivalent to ≤92 for this complete affine code. Repeated positive literals supply the 1/3 weights; they must not be deduplicated or canceled as XOR literals. The prototype's repeated-literal sequential-counter truth tables passed tiny exhaustive controls, but no n5 formula has been built or solved.

For this dictionary the integer cardinality list has exactly 819 literals. The saved kernel has 706 dependency incidences across 275 selection rows; 213 rows depend on a single kernel variable and the largest support has 31 variables. A direct affine implementation therefore needs at most 431 binary XOR gates, 369 internal XOR auxiliaries and 2,150 affine clauses, with the selection bits used as output variables. The cardinality constraint dominates: a sequential counter at bound 87 is on the order of 71,253 auxiliary cells. These are counts from the saved supports and an order estimate for cardinality, not measured formula sizes or a solver-performance claim. Any encoder proposal needs strict clause/variable/memory caps, tiny exhaustive witness tests and independent formula/model validation before a separately bounded production solver call.

The accompanying next-stage proposal is disabled and requests **encoder preparation and tiny QA only**, not a solver launch. It retains the immutable dictionary/source/runtime pins, exact weighted objective, fresh guard and deadline, full persisted-byte primary plus independent tensor verification before any record handoff, and UNKNOWN handling for caps or late returns. A future UNSAT statement would apply only to this finite cyclic dictionary at cost ≤87, equivalently ≤92 within its proven modulo6 affine code. It would not exclude new atoms, other C3 decompositions or unrestricted rank92.

The modulo6 proof is covered by three tiny algebra controls, including counterexamples showing that individually movable cubes alone do not imply the linked-triple property. The static analyzer reads only the sealed dictionary/kernel; it builds no tensor columns, formula or candidate search.

Evidence and pins: [evidence/cyclic-orbit-code7-audit.json](evidence/cyclic-orbit-code7-audit.json). The prepared next-stage proposal is `artifacts/marathon7_20261103T122417Z/cyclic-orbit-code7-next-proposal-v2.json` (the v1 proposal is preserved and superseded). No old campaign file or generic atom-code module was modified, and no Git operation was performed.
