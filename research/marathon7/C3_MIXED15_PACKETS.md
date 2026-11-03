# Mixed15 packet metadata

The approved cyclic 93-product source gives 27,405 distinct literal packets: all three cubes and every choice of four of its 30 nonfixed orbits. Each packet has 15 products, a local target of 14, and 78 products held outside. No decoder, solver, or rank-two filter was called.

| Actual unfolding rank d | Count | Status at target 14 |
| --- | ---: | --- |
| 15 | 22,103 | Excluded by flattening |
| 14 | 3,859 | Supported CP(d), unqueried |
| 13 | 1,322 | Supported CP(d+1), unqueried |
| 12 | 112 | Surplus two beyond reviewed rank-9 backend cap; retained |
| 11 | 9 | Surplus three; retained |

The source's three opposite-pair column families each have independent rank 93. Every selected subset therefore keeps independent opposite-pair columns, so its factor span dimension equals its actual unfolding rank. Cyclic closure gives the same factor span in all three modes. Thirty-seven sampled cores were independently rebuilt from the stored basis, expanded to all 15,625 ambient coordinates, and checked in every unfolding: the first three records per dimension and all 25 proposed rank-13 cases. Every future decoder must repeat the lazy full ambient and actual-core checks.

The bounded preparation used CPU 3 at nice 10, 512 MiB, 120 seconds internally and 150 seconds externally. It finished in 16.309 CPU seconds / 16.432 outer wall seconds with peak RSS 157,384 KiB. Its lossless gzip catalog and companion files occupy about 1.65 MB. The original source passed both full 15,625-coordinate verifiers. No held-out or private evaluation payload was read.

The frozen disabled proposal selects 25 supported rank-13 packets. A concrete next exact probe could reuse the reviewed compact CP(d+1) adapter on those cases at CPU 3 / 1,024 MiB, 20 seconds per case, 500 seconds internally / 530 externally. It requires new root authorization. The 121 smaller-rank packets are separately retained for a reviewed higher-surplus or binary-block method; unsupported eligibility is not a negative result.

The catalog keeps source indices, four-orbit masks, common mode bases, independent-rank witnesses and branch metadata; full cores are reconstructed lazily. It matches the new binary-block interface, whose raw compact outputs require lifted primary and strict independent ambient verification before publication. No binary-block target query is enabled here.

Artifacts: `c3-mixed15-packets7-prep-001`. Pins: gzip catalog `b6df6ab005954168bf9a656d5f0c7e4d78fd3c5029a32dfb74f281ea836dc7c5`; manifest `9257959660cc1ec2ebaed56fc73cf9810d274fcfe15eb7293ef1a7b074eff2bc`; seal `c054a84e9f8ff55c82857e98b9b807595cb79840ba0f58cbfb066a21f41750a1`. Small evidence is in `evidence/c3-mixed15-packets7.json`.
