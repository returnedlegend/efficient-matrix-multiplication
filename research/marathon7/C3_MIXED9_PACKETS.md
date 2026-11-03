# Mixed C3 nine-product packets: all 435 closed for this literal family

The authorized preparation classified all **435** packets formed from the approved C3 rank 93 seed's **three cubes plus every unordered pair of its 30 nonfixed orbits**. **426** packets have exact unfolding rank 9, excluding a local rank 8 replacement. The remaining **nine** packets were then queried **once** with the unchanged reviewed decoder; all nine returned **complete LOCAL_UNSAT**, with no UNKNOWN, error or target.

This closes only the specified literal **9-to-8 residual family**, with its **84 outside source products frozen**. It is not a global rank lower bound, a result for arbitrary masks, or a negative for all rank 92 decompositions.

## Preparation and the flattening certificate

The sole input is the approved training root with byte SHA-256 `56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b`. It passed primary and strict independent full 15,625-entry checks. The source's opposite-pair column ranks are **93,93,93**; exact pivot-row full-rank minor witnesses are retained for each orientation. Therefore every selected nine-column opposite-pair subset is independent. In an unfolding `U_selected * pair_selected^T`, this implies the actual mode image equals the selected single-factor span.

Each packet consists of complete cyclic orbits, so the selected factor sets, and hence their spans, agree in all three modes. The measured common dimension `d` is therefore the actual unfolding rank. A packet with `d=9` cannot have CP rank at most 8, even allowing replacement factors outside the selected span. Each of the 426 exclusions has its exact source/orbit masks, nine source indices, shared mode basis and factor-rank pivot witness.

| Common actual mode rank | Packets | Route / result |
| --- | ---: | --- |
| 9 | 426 | Exact flattening exclusion |
| 8 | 6 | Reviewed CP(d), all 6 complete local negatives |
| 7 | 3 | Reviewed CP(d+1), all 3 complete local negatives |
| 6 | 0 | CP(d+2) route not needed |
| ≤5 | 0 | No deferred smaller-image cases |

All nine retained metadata records passed full ambient expansion and actual-core mode-rank reconstruction before freezing: **140,625 ambient coefficient checks**, plus their actual cores. No full cores or candidate tensors were stored by preparation; they are reconstructed from the pinned source, source-order indices and mode bases. The source indices are **zero-based original JSON term order**, not sorted-triple order; the three cube indices are **90,91,92**. Nonfixed orbit numbering uses the lexicographically least cyclic rotation of each literal triple.

Preparation used CPU0/nice 10, **0.946408 CPU seconds /0.953285 outer wall seconds**, **32,356 KiB** peak RSS and **832,775 bytes** of final metadata output, within 60 seconds/512 MiB/32 MiB and the strict C7 deadline. No decoder, Koszul expansion or unreviewed rank2-span lower-bound helper was called during preparation.

## Actual first-nine execution

Root authorized the single queue job `c3-mixed9-packets7-pilot009-001`: CPU3/1,024 MiB, 60-second invocation, 90-second outer limit and 5 seconds per case. It was appended/enabled through the six-key queue helper with a COMMITTED receipt, then launched at **2026-11-03T14:50:53.800842Z**. Both positive n3 control routes restored inflated full-matrix sources to 27 products with all 729 coefficients checked by two implementations. A late SAT control returned UNKNOWN and retained its nested raw return only under a hidden `.raw` path.

The live pilot reused unchanged `SourceCache`, exact core/lift/expand helpers, the reviewed `compact_rank2_edges43.solve_core`, and the approved 50ms `CancelPoller`. Every case had forced fresh pre/post source, solve, full-verifier and publication barriers. The reviewed decoder hash is `40ef2057d481b712040575b663b31585460b2e5addc58a24a5cbf94aa0f686a7`. No unreviewed helper was wired.

| Case | Nonfixed orbit pair | d | Inside rank-one span rank | Complete negative reason |
| --- | --- | ---: | ---: | --- |
| c3-mixed9-p10-14 | 10,14 | 7 | 1 | No single rank2 edge coset spans |
| c3-mixed9-p15-23 | 15,23 | 7 | 1 | No single rank2 edge coset spans |
| c3-mixed9-p25-27 | 25,27 | 7 | 1 | No single rank2 edge coset spans |
| c3-mixed9-p00-10 | 0,10 | 8 | 6 | Inside rank-one deficiency |
| c3-mixed9-p01-17 | 1,17 | 8 | 7 | Inside rank-one deficiency |
| c3-mixed9-p01-19 | 1,19 | 8 | 7 | Inside rank-one deficiency |
| c3-mixed9-p03-04 | 3,4 | 8 | 7 | Inside rank-one deficiency |
| c3-mixed9-p14-17 | 14,17 | 8 | 6 | Inside rank-one deficiency |
| c3-mixed9-p17-19 | 17,19 | 8 | 7 | Inside rank-one deficiency |

The d7 cases each enumerated every one of 127 nonzero slice-image vectors; each had one rank-one point, 12 rank-two vectors, 114 vectors of rank at least 3 and 26 nonzero edge cosets, none satisfying the complete spanning criterion. The d8 cases each enumerated all 255 nonzero image vectors and failed the exact rank-one spanning criterion. These are complete finite residual negatives, not timeout inferences.

All nine calls completed in approximately 0.012–0.032 seconds per case. The queue wrapper measured **0.374902 CPU seconds /1.011555 outer wall seconds**, **21,688 KiB** peak RSS, exit 0, no timeout and no interruption. No global candidate or local WINNER marker was emitted, and no continuation was launched. Any positive result would have been reconstructed into the full source, checked on persisted bytes by both full 15,625-entry verifiers, and exposed to the global guard only across fresh publication barriers; late candidates remain hidden and UNKNOWN.

## Artifacts and pins

Preparation: `artifacts/marathon7_20261103T122417Z/c3-mixed9-packets7-prep-001`; frozen controls/runtime are in `c3-mixed9-packets7-ready-v1`. The retained nine-case proposal was disabled until root's separate execution authorization.

Execution: `artifacts/marathon7_20261103T122417Z/c3-mixed9-packets7-pilot009-001`; frozen runtime/controls are in `c3-mixed9-pilot7-ready-v1`. The receipt is `root-queue-receipts/c3-mixed9-packets7-pilot009-001.json`. All nine actual result files and their complete raw decoder statistics are pinned by [evidence/c3-mixed9-packets7.json](evidence/c3-mixed9-packets7.json).

| Artifact | SHA-256 |
| --- | --- |
| Preparation catalog | `ab52e0debe73b857da75765b196ec64f2bb1497c8092754aa19c56ecdfb3fd31` |
| Preparation manifest | `1566bf4e0a72bb583716578a499bf5f87b0283ab124a1546a22e6f2346d40fc0` |
| Executed nine-case summary | `b05c3969699ed24c796182d25b9f3644cd698767d0094facb281703b2d4583ec` |

The pure cube-span domination result and this mixed nine-product result concern different families. This mixed family introduces noncube directions but still yields no local rank 8 replacement. No paid compute, publication or Git operation was performed.
