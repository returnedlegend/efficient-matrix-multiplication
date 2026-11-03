# Mixed C3 twelve-product packets: 3,744 excluded, 316 retained unqueried

The authorized metadata census covered all **4,060** packets formed from the same approved C3 rank 93 seed's three cubes plus every unordered triple of its 30 nonfixed orbits. Each packet contains **12 distinct literal products**, with local target **11** and **81 outside source products fixed**. No target decoder, SAT solver or necessary-span filter was called.

| Actual common mode rank d | Packets | Preparation disposition |
| --- | ---: | --- |
| 12 | 3,744 | Exact flattening exclusion: rank 12 exceeds target 11 |
| 11 | 226 | Retained, CP(d) route |
| 10 | 88 | Retained, CP(d+1) route |
| 9 | 2 | Retained, CP(d+2) route; separate backend review required |
| ≤8 | 0 | None observed; unsupported higher-surplus cases would remain retained/deferred |

The **316 non-excluded packets remain unqueried**. The previously closed 435 nine-product family is separate and unchanged.

## Exact rank basis and lazy core checks

The sole source byte hash remains `56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b`. Source primary and strict independent full 15,625-entry checks passed. Its three opposite-pair column ranks were verified once as **93,93,93**, with exact pivot-row full-rank minor certificates retained.

Every selected 12-column opposite-pair subset is therefore independent. An unfolding of the packet is its selected single-factor matrix times the transpose of that full-column-rank pair matrix, so its image equals the selected factor span. Complete C3 packets have identical factor sets in all three modes. Thus the computed shared span dimension `d` is the actual unfolding rank, and every d12 exclusion has a valid rank witness. This is an exact exclusion for that chosen residual at local target 11, not a global rank lower bound.

Preparation stored only source references/hashes, orbit and term masks, literal source indices, shared mode bases, rank witnesses and branch/validation metadata. No thousands of decoder models or full core arrays were stored. Indexing is **zero-based original source JSON term order**; cube indices are **90,91,92**. Nonfixed orbits use lexicographically least cyclic representatives, and triples are enumerated lexicographically without repetition.

Actual ambient/core reconstruction was checked for the first three packets at every observed d and for **every proposed pilot packet**. There were **31 distinct full core checks**: all 2 d9 cases, 23 d10 cases, 3 d11 samples and 3 d12 samples. Every checked core lifted to the exact ambient residual and had actual mode ranks `[d,d,d]`. Other retained records explicitly require lazy SourceCache reconstruction and verification before any future decoder call; they are not represented as fully core-checked or negative.

## Small fresh pilot plan, disabled

The frozen plan contains **25 cases**, selected by lowest retained d first and then the source-orbit triple order. It starts with both d9 cases below and continues with the first 23 d10 cases. All 25 selected cores are fully checked. No execution is authorized by the plan.

| Priority | Case | Orbit mask | Source term indices | Route |
| --- | --- | --- | --- | --- |
| 1 | c3-mixed12-p00-10-14 | `0x4401` | 6,7,8,39,40,41,84,85,86,90,91,92 | CP(d+2), d9 |
| 2 | c3-mixed12-p10-14-17 | `0x24400` | 6,7,8,27,28,29,84,85,86,90,91,92 | CP(d+2), d9 |

The exact remaining 23 IDs, source masks, bases and core hashes are in `pilot-proposal.json`. The proposed future envelope is at most 25 cases, 120 seconds overall, 3 seconds per case, CPU0/nice 10/ 512 MiB, under the strict C7 deadline. Root must separately choose and review the backend for each actual surplus before launch. A CP(d+1)-only decoder must not be used to reject the two d9/target 11 cases.

The optional necessary condition `CP≤d+2 => rank span{rank≤2 matrices in the actual image}≥d−1` has mathematical proof and ten-test evidence, but a separate implementation-review clearance was not bound into this runner. The filter was therefore **deferred and uncalled**. Passing such a filter would not prove existence; a stopped or capped scan could not justify an exclusion. No unsupported case was discarded, and no old closure was erased.

## Resources, artifacts and pins

The one census used **1.420153 measured CPU seconds /1.433881 outer wall seconds**, **75,300 KiB** peak RSS, CPU0 at nice 10. It stayed within the authorized 120-second / 512 MiB / 32 MiB limits, with fresh canonical stage barriers, normal inner polling and the strict **2026-11-03T19:24:17Z** clamp. Final metadata output is **8,379,302 bytes**. The tiny triple-family control and actual zero-query frozen CLI preview passed before dispatch.

Sealed preparation: `artifacts/marathon7_20261103T122417Z/c3-mixed12-packets7-prep-001`. Frozen code, configuration, control log and preview: `c3-mixed12-packets7-ready-v1`. The completion seal and all three declared file hashes were rechecked; `UNKNOWN.json` is absent.

| Artifact | SHA-256 |
| --- | --- |
| `catalog.json` | `5262849890715c75042d282fcae02d69103b33b51dbe58d54c6b30eceb1d235a` |
| `manifest.json` | `475c51b3d5b49d6d24ff5458483cc84e972402a715e4ed133d2b106709982f46` |
| Disabled `pilot-proposal.json` | `27b5007f7dc52fad942ef9e17a6ed4500093f7c1f73a64fbd4c69684663b9a35` |
| `COMPLETE.json` | `8bdaf6e42324e49ef028b181849cdcfd7579619dc76a551a2b7287d51bd39b9e` |

Compact evidence: [evidence/c3-mixed12-packets7.json](evidence/c3-mixed12-packets7.json). There were zero target queries, decoder calls, solver calls, private evaluation reads, continuations, paid-compute actions, publication actions or Git operations.
