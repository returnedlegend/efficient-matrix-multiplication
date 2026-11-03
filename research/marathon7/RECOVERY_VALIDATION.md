# Recovery validation — 2026-11-03

**Latest unified regression: 866/866 passed, with zero failures, errors, skips, expected failures, or unexpected successes.** This includes all 33 TensorCode7 controls and the latest local/backbone/native tests. The bounded helper ran on CPU2, nice 10, with 3072 MiB address space and a 900 s ceiling; actual wrapper wall time was 67.02 s, CPU time 52.37 s; unittest time 65.823 s, and peak RSS 250972 KiB. Real XOR dependencies were enabled. Evidence: `checks-marathon7-final.{log,result.json}`, `checks-marathon7-final-summary.json`, and its before/after SHA256 manifests under `artifacts/marathon7_20261103T122417Z/`.

No existing source changed during that run. The only manifest delta was the newly created `scripts/marathon7_local_surplus_two_review.py`; that later script is outside this regression snapshot. TensorCode7 final runner/module/lifecycle-test pins match the independently reviewed owner release. No production N5 search query was made by this validation worker.

The first green recovered snapshot had 829/829 passes, with no failures/errors/skips. Run finished at approximately 12:33 UTC using real `.xor-deps/pycryptosat` 5.17.0 and installed PySAT. Resource wrapper: CPU1, nice 10, 3072 MiB address space, 900 s wall ceiling; actual unittest 47.14 s. See `artifacts/marathon7_20261103T122417Z/checks-recovered-code-final.log`, `checks-recovered-code-final-summary.json`, and `.result.json` for exact timing and counts.

The four portable-fixture modules passed in both green runs: `test_campaign_native_dwell42`, `test_campaign_native_plus_burst42`, `test_audit_burst_long42`, and all 8 `test_compact_rank2_edges43` tests. Existing native ONECOSET43, DWELL42, and BURST42 release binaries were reused through their documented environment overrides. The optional compact8 native preprocessor was built locally under CPU2/nice 10/512 MiB/60 s, enabling its actual Python/native equivalence test; no optional test was skipped in either green unified run.

Two earlier unsuccessful runs remain intact. Initial 799-test run: 794 pass, 4 fail, 0 errors, 1 skip; the harness had inserted `.xor-deps` into `sys.path` without exporting `PYTHONPATH` to CLI subprocesses. Correcting that environment fixed the hyperplane CLI failure. An 803-test run then had 799 pass, 3 fail, 0 errors, 1 skip. A separate diagnostic 806-test run had 803 pass, 3 fail, 0 errors, 0 skips and exposed the remaining cause: `tests/test_local_ten_guard43.py::invoke` ran a resource-limiting CLI directly in the unittest process, permanently lowering its hard address-space limit to 1 GiB. Later 1536 MiB/2048 MiB solver requests failed with `ValueError: not allowed to raise maximum limit` despite passing individually in fresh processes.

The harness now mocks only the CLI's `resource.setrlimit` call during in-process lifecycle controls. Production resource limits are unchanged. A new actual subprocess control executes the CLI with 128 MiB, verifies `effective_AS_limit_bytes == 128*1024**2`, verifies successful exact small-tensor reconstruction, and confirms the parent limits are unchanged. No mathematical assertion was removed or loosened. Root approved this isolation fix.

Every unified run records SHA256 before/after manifests for Python/C++ sources in `mmsearch`, `scripts`, `tests`, and `native`. The first green 829-test run captured ongoing independent work: `mmsearch/backbone7.py` and `scripts/tensor_code7.py` changed and `tests/test_backbone7.py` appeared during the run. Its 829 count describes that discovery snapshot, not a claim that all later edits have been tested. The later 866-test run includes the stable updated modules; independent local/lifecycle QA is documented below and in the linked reports.

## Rank-two decoder independent QA

Reviewed `mmsearch/compact_rank2_edges43.py` against the frozen independent proof/oracle in `artifacts/rl_campaign42_20261103T033116Z/compact-rank2-edge-independent-review-v1/`. The implementation satisfies the old one-quotient-coset criterion: `B0=S` or a **single** nonzero quotient class has `span(B0,E_q)=S`. It retains B0, does not combine distinct quotient classes, enumerates all three unordered GL(2,F2) splits per rank-two matrix, and selects an independent subset of the **original rank-one endpoints**, preserving factorizability. Every original raw slice receives coordinates; zero, repeated, and dependent free slices are restored before core expansion. Complete negatives apply only to the exact residual and supported bound `d` or `d+1`; caps/cancellation/unsupported surplus return UNKNOWN. This is an implementation of the existing finite-field criterion, not a new rank bound or novelty claim.

Independent standalone run: **8/8 pass**, zero skips/failures/errors, 1.27 s unittest time; bounded CPU2/nice 10/512 MiB/120 s. Coverage includes 2892 exhaustive independent 2x2/2x3 subspaces, 1472 positive cases with proper nonzero B0, all 256 binary 2x2x2 tensors/all three axes against exact CP distance, 180 random literal-coset comparisons, all small matrix classifiers/splits, d10/d12 known pencils, cross-coset/rank-three negatives, cancellation/caps, and a padded 5x20x24 tensor with every raw slice reconstructed. The portable oracle copy is byte-identical to the frozen independent oracle. Both later green unified runs reran the portable 8-test module successfully.

Evidence: `rank2-independent-qa.log`, `.result.json`, and `.json`. The JSON preserves original point witnesses, target-coordinate masks, explicit raw zero/repeated/dependent slices, and the full padded control core; no production N5 search query was made by this QA. Original frozen artifacts were read only.

Pinned SHA256:

| File | SHA256 |
|---|---|
| `mmsearch/compact_rank2_edges43.py` | `40ef2057d481b712040575b663b31585460b2e5addc58a24a5cbf94aa0f686a7` |
| Portable `tests/test_compact_rank2_edges43.py` | `71a04e4dcd5f4f2930dcae0721c10998572221ed90d4738e3e1581bfbd5a123d` |
| Independent oracle / portable oracle fixture | `f9b00ed3873abe61ce4456cfbf51f04bf9fd9342978d04cbd4b804231b4d40e8` |
| Frozen independent `PROOF.md` | `5927b94653747483164c5881bebf5d05790ff3f57f475565586072a07cd86bf0` |
| Resource-isolated `tests/test_local_ten_guard43.py` | `1489a51479f26604946e8902bb44d458d47c8dfe4ebdc19ab059194aea647823` |

No staging, commits, pushes, production search dispatch, or edits to old frozen artifacts were performed by this validation worker.

## Local bulk v2 independent acceptance

Both new frozen `marathon7-local-{local10,extension8}-ready-v2` bundles pass independent validation: **14/14 controls, zero failures/errors/skips, zero production decoder queries**. This includes 9 frozen lifecycle controls plus 5 independently authored controls. Verified every file in both manifests, pending scope counts 111593/5929, the exact decoder pin, the UTC hard clamp, malformed canonical states, incomplete/UNKNOWN journal rejection, changed completed-result rejection, storage holds, and exact negative-census compaction. Read-review confirmed resource freshness and process identity checks, all raw late witnesses retained as UNKNOWN without cursor advance, and full 15625-entry plus independent verification before final WINNER publication.

The v1 review identified that resumed WINNER bytes were independently verified but not bound to their immutable proof. The owner preserved v1 and froze v2 with byte/hash bindings through the WINNER proof, immutable candidate, all three report views, core input/math, selected configuration/case, and path confinement. The added tamper control passes. Evidence: `localbulk-independent-qa-v2.{json,log,result.json}`.

| Final v2 artifact | SHA256 |
|---|---|
| Runner | `1123b7d3a5504cfd3fefce84e7e819930698d07bec4e00cbb292ea56d7933843` |
| Guard/metadata module | `94834fe263b3bb3f62145a3415e520f8918c366b2f608138df29fb918435ac53` |
| Local10 manifest | `224d6a052b3253edd11077da6edbe8f2ec20856fde6a16ab131531d7b8c462af` |
| Extension8 manifest | `1e455dd9439a7e2a4f68ac308de2b87391ae4e15f97ad31ddad9f0972eac3371` |

This accepts implementation and lifecycle controls; root owns any production launch and resulting scientific claims. No production run was launched by this worker.

The initial v2 runtime acceptance did not exercise the queue's strict six-key job schema. Root caught the extra advisory `nice` field before queue mutation. A separate immutable overlay now removes only `nice:10`; niceness remains inherited from the queue parent. Follow-up independent QA imported the **actual** `scripts.phase_coordinator42_v2.validate_job` and successfully checked every proposal: 224 local10 plus 12 extension8, with complete overlay-manifest and original-job hash comparisons. No other field changed. Evidence: `localbulk-job-schema-independent-qa.{json,log,result.json}`. Corrected overlay manifest pins: local10 `f773127d8ebc06bb1bd5453e057c5da03c3137396785bf5dd98e1e5943c6bdbd`; extension8 `8deda98e81792a936857222fa175dfc91e3cb1053878e0d3076e0778a86c1a3a`.
