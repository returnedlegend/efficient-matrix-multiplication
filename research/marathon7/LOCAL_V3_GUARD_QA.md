# Local10 v3 guard overlay independent QA

**Accepted for root's first500-case launch decision.** Independent targeted rerun passed22 frozen controls with zero failures/errors/skips, plus all21 independent cached-guard cases. No N5 decoder query was performed. Evidence: `local-v3-independent-qa.json` and `local-v3-independent-qa-final.{log,result.json}` under the C7 artifact directory.

Verified both complete v2/v3 manifests. Every existing Python runtime file is byte-identical except the two runner copies, each changed by exactly one import from the old guard to the cached guard. Source JSON, small controls, prior exclusions, lazy controls and rank-two decoder are byte-identical. The actual imported guard is the frozen v3 `b995d4a3ac668e2da3fc37482782eb86d5d11a0ae00165c52b32500b09d1bd2d` module. Cached data remains subject to fresh link/target signatures, process identity/liveness, heartbeat age, storage, stop markers, canonical stops and final clock checks. Tests cover stable-read races, symlink replacement, same-inode rewrites, malformed state and late I/O.

Independently checked all10205 reused negative result files against their raw hashes, exact source/mask/model bindings, complete255-vector/rank-two-split census, and core input/math hashes. Reconstructed all21 completion-journal chains from their original config digests and matched cursors, result counts and final chains. The negative ledger is exactly the union of those committed complete negatives; no late or UNKNOWN result is included.

Independently decoded every original/new catalogue chunk and verified hashes/counts/uniqueness. The new catalogue is the exact **ordered** set difference:111593 old pending−10205 closed=101388 pending cases in203 chunks. Prior old009 case `s1-07000f800000000001000040` remains present exactly once, is not in the closure ledger, and is the first new case. Its UNKNOWN result hash and retained after-cutoff raw artifact hash are unchanged. Necessary-survivor status does not imply an existing solution, and old negatives retain only their exact residual scope.

All203 disabled proposals passed the actual strict six-key queue validator; first500 proposal matches the root pin. No queue write occurred.

| Artifact | SHA256 |
|---|---|
| v3 full manifest | `3501d7ce5041fe95b3ec6712848c1a5bf86e63c3c9ff1bfe6127459b54a47a77` |
| First500 proposal | `b60c1a5777a7a5f39e9583a183e18afebf1d56610222b1e218ff515b3d82ba5c` |
| Closed-negative ledger | `4d842b812fb649e628136b76911b9b5eb23ddc1f618956ce8d1ab586b54b1dad` |
| Closure inputs | `c2d03a0eda66938f66277eabd2cffcb516e9a3e296efb08aa8b20050fd76cd4f` |
| Unchanged rank-two decoder | `40ef2057d481b712040575b663b31585460b2e5addc58a24a5cbf94aa0f686a7` |

The audit is query-free apart from synthetic/tiny controls and does not establish new N5 search results. Root owns production dispatch and subsequent throughput allocation.
