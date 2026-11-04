# Fixed native-corpus sparse-cycle scan

The bounded scan completed without a negative move. This result concerns the listed identity families and the 36 original verified source states; it does not establish the minimum of the 522-atom dictionary.

The input was the separately authenticated native-export corpus: 522 whole rank-one atoms, tensor-column rank 338, nullity 184, and 32 rank-93 plus four rank-94 source states. Its prepared artifact SHA256 is `2302ae5e82fe7afd1845dd50ffd5c12f17e1efb56b8f4adf1ed09bd31a71e886`; the source-manifest SHA256 is `9cdc5193b3fc9be8ff111bf46efd3e7990f7f82d8251fd1914ead556b33c5c51`.

The enumerator exhausted 832,305 declared trials: 999 merge3, 15,420 shared-factor flip4, and 815,886 plus5 paths across all six axis orders. Every required atom had to belong to the fixed dictionary. After deduplication, the catalogue contained 243 cycles, all support-four flip identities, with selector-space rank 123. No merge3 or plus5 cycle was present. Every catalogue cycle was checked against all 15,625 tensor entries.

The optimizer evaluated all 36 original source states against all 243 catalogue cycles, for 8,748 exact weight deltas. It found zero negative deltas, saved no candidate, and fed no new state back into the scan. Neutral or composite moves were outside this run's scope.

The independently reviewed controller used hidden, nested raw staging, immutable input/runtime pins, the canonical fresh campaign guard, and two full tensor checkers before any eligible candidate publication. Independent QA passed 19 targeted controls, including 425 independently generated tiny family cycles and late-result quarantine cases. QA receipt SHA256: `590ca329073c3c4720e068c049091bf3c0f466597b333d957bf16a1bbfb66eb1`.

The actual run used CPU0 at nice 10, a 1,024 MiB address-space limit, 120 seconds inside a 150-second outer limiter, and a 32 MiB output cap. It exited zero and was fully reaped after 12.004 seconds wall time and 11.391 CPU seconds, with peak RSS 42,804 KiB. The frozen output occupied 5,128,192 allocated bytes across 156 files; all 155 registered checksums matched.

Artifacts are under `artifacts/marathon7_20261103T122417Z/tensor-code-sparse-cycles-001/`. The external actual-run receipt is `tensor-code-sparse-cycles-001-receipt.json`, SHA256 `b501e96b1ddced8f4d73649680ef41c2946df5643d23dc32a02795bca68d7694`.

| Artifact | SHA256 |
| --- | --- |
| `result.json` | `38b104cbf44e8d00c4405dbf71e9bb97fc86c54babecbdb8244c049713190478` |
| `catalogue.json` | `0627d5c423099f61711e1c4eeb31e99fddaa7d6ab910671aa6f5ed193153ab98` |
| `scan.json` | `47385539307d2965e6e051879ff596d7b79251b5e362b8666bacafbc7cebb42a` |
| `checksums.json` | `c734795ec068eec02ae8950a5e91f0c4723e8f100d97a8926e9eb99ccb9b1b3e` |
