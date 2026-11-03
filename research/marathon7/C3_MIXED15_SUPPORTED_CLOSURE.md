# Mixed15 supported exact closure (M4)

All 5,181 supported literal 15-to-14 packets from the approved cyclic 93-product source returned complete `LOCAL_UNSAT`, exactly once. No candidate, `UNKNOWN`, error, timeout, or retry occurred. Outside 78 products were fixed. This is a finite local repair result, with no global rank lower bound and no result at or below 92.

| Actual unfolding rank | Packets | Final status |
| --- | ---: | --- |
| 15 | 22,103 | Excluded by flattening |
| 14 | 3,859 | Exact CP(d) local negatives |
| 13 | 1,322 | Exact CP(d+1) local negatives |
| 12 | 112 | Deferred: larger-mode surplus-two protocol not yet queried |
| 11 | 9 | Deferred to separately authorized binary-block work |

The 25-case rank-13 pilot was followed by 21 batches of at most 250 cases. The first batch included 100 rank-14 calibration cases. Each batch used CPU 3 / 1,024 MiB, 20 seconds per case, 500 seconds internally / 530 externally. Only a complete, hash-bound negative predecessor could enable its successor. Scope audits prove that the pilot and bulk are disjoint and exactly cover all 5,181 supported catalog records; every source-index list, orbit mask, shape and target also matches that catalog.

Search jobs used **497.208255 CPU seconds**, with 522.613077 seconds summed outer wall time and peak RSS 36,220 KiB. The last controller observation recorded another 166.88 CPU seconds including its audit subprocesses; that is an observation before process exit, not an exact final total. Logical run/bulk-preparation output was 48,077,352 bytes, below the 500 MiB cap. The observed combined CPU use was well below the 1,800-second authorization.

The unchanged reviewed backend used a 65,535-vector cap, sufficient for ranks 13 and 14. Matching positive controls exercised full N4 replacement at both dimensions, with primary and independent 4,096-coordinate checks. A genuine rank-13 surplus-one gadget required 14 products after CP(13) rejected it. A late positive remained hidden and `UNKNOWN`. The runtime reconstructs and checks every selected ambient/core before decoding, keeps fresh guard barriers, and requires both full N5 verifiers before any candidate handoff. No candidate handoff was needed here.

Source `56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b` is the root-approved training seed. Both full 15,625-coordinate source verifiers passed again during sealing. No private evaluation payload was read. The lossless metadata pin is `b6df6ab005954168bf9a656d5f0c7e4d78fd3c5029a32dfb74f281ea836dc7c5`; source ancestry pins and all 22 exact historical argv lists are included in the approved source/metadata bundle. Historical commands reject existing output directories; they do not authorize a repeat.

Read-only reproduction of the completed result audit (zero decoder calls):

```sh
python3 -B scripts/advance_c3_mixed15_supported7.py \
  --manifest artifacts/marathon7_20261103T122417Z/c3-mixed15-exact7-bulk-ready-v1/manifest.json \
  --expected-manifest-sha256 53e816b757cc711a55a6d947bb66dc37a67d2b27962874e30013ddc10da3f4ef
```

Evidence: `evidence/c3-mixed15-supported-closure7.json` (`40f8c6b4ec56c432f5a8e3356d85447dc7262547083b0e9ee84f0599b38bad2a`). Sealed result summary: `c0ebebcd4ed4de4cc5132b7d5d3c43ee346a57217fafc74e108b9ac451562b7d`; seal: `e00e851bc5977617532e634c723adf2d6a58ba2af32bc274b5c8314e8ea29ca4`. Approved source bundle: `evidence/c3-mixed15-source-bundle-v1.tar.gz` (`8ce4c79bee64c59eff437d1ea27f3c4ed972168f109249c898ec9937966e6319`). Full result pins and runtime hashes are under `c3-mixed15-supported-closure-v1`.

The 121 unsupported packets remain distinct from these negative results. A new larger-mode surplus-two module is being prepared for independent review of the 112 rank-12 cases; no N5 query is authorized by this report.
