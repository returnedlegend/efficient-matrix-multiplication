# Native corpus independent QA: source selection and prep-only code pass

The new native-source selection and preparation contract passed independent
review. This clears preparation from the exact pinned manifest; it does not
authorize optimization, a solver query, a production decoder, or reuse of
rank93-only runtime masks for rank94 sources. The existing affine loader is
unchanged.

Selected-source manifest SHA256 is
`9cdc5193b3fc9be8ff111bf46efd3e7990f7f82d8251fd1914ead556b33c5c51`.
All36 selected exports were freshly checked by primary and strict independent
full-tensor verifiers:1125000 coefficients checked in total. Verified support
counts are32 rank93 and4 rank94. Fresh all-mode opposite-pair ranks are93 for
every rank93 export and94 for every rank94 export. These ranks make future
literal-subset factor-image compactifications valid, but source rank alone
would not establish that precondition.

The independent audit checked163 root, producer, runtime, binary, CPP, registry
and export files with unchanged before/after hashes. The roots matched the
approved32-source authority exactly: base prepared `cf4644...`, anchors
`26d956...`, and root approval `735418...`. Each producer input matched both
its original approved train JSON identity and native text. Native executable,
CPP and runtime code pins, command input/output paths, five explicit producer
branches, export registry membership, JSON parent manifests and prior reports
were reconciled. Heldout/evaluation identities were excluded. All selected
sources are distinct. Their522-atom union shares224 atoms with the old406 and
adds298; these are verified metadata, not evidence of search advantage.

An early review found that final certificate/result writes lacked a final
cutoff check. The frozen implementation now forces pre/post final-result
barriers, hides prepared/certificate views on late or failed completion,
checks UTC on every callback, rechecks code and producer/source pins, and caps
allocated output at32MiB with pre-copy reservation. Primary and independent
source verification occur before the new source receipt can authorize the
whole-atom prepared code. Inventory labels alone do not authorize seed ranks.

The frozen targeted controls passed11/11, zero failures/errors/skips, including
actual tiny `main()` execution and injected late pre/post final-result
barriers. Independent actual-source verification took3.555 seconds; final code
controls ran under CPU1 nice10/1024MiB. No dictionary preparation, solver,
decoder, or optimization was invoked by this independent QA.

| File | SHA256 |
| --- | --- |
| `mmsearch/tensor_code7_native_corpus.py` | `582f56bf82064692382eaf5b48343847ae9882ece1c0127f09b6585de96729db` |
| `scripts/tensor_code7_native_corpus.py` | `845f60721c33749e0a58ab3537a03f99dcef5c39b7b1588a4ea3d8ad8e6881b3` |
| `tests/test_tensor_code7_native_corpus.py` | `9631555b6eb16afb9b9eb0144c8f783fc3603f0b2589dd5662a0d4950c048663` |

Evidence in `artifacts/marathon7_20261103T122417Z/`:
`native-corpus-independent-source-qa-v1.json`,
`native-corpus-independent-source-qa-driver-v1.{log,result.json}`, and
`native-corpus-independent-code-controls-v2.{log,result.json}`. This review
checks the source contract and frozen preparation code; any later prepared
artifact still needs its own completion status and raw hash pinned.
