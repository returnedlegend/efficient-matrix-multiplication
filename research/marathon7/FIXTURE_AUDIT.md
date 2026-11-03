# Portable fixture audit

Four recovered test modules depended on campaign-local artifacts. Their fixture paths now point to unchanged copies under `tests/fixtures`; no assertions were removed and no skips were introduced. The higher-rank audit control reads the actual rank-96 certificate directly instead of following an absolute path in a large runtime summary. `EDGE_ORACLE` remains available as an explicit override.

| Curated fixture | Bytes | Original source / purpose |
| --- | ---: | --- |
| `tests/fixtures/native_campaign42_rank93.json` | 84,171 | Actual breadth/dwell rank-93 input; those two old source copies were byte-identical |
| `tests/fixtures/native_campaign42_rank96.json` | 19,312 | First higher-rank export selected by the old burst summary |
| `tests/fixtures/compact_rank2_edges43_oracle.py` | 7,150 | Unchanged independent stdlib tiny-control oracle |
| `tests/fixtures/marathon7-fixtures.provenance.json` | See file | Source paths, byte hashes, independent checks and before/after test hashes |
| `tests/fixtures/README.marathon7.md` | See file | Fixture meaning and limits |
| `tests/fixtures/held_inventory42_rank113.txt` | 2,277 | Existing untracked actual held-inventory control required by continuation/mutable-cube tests |
| `tests/fixtures/held_inventory42_rank113.provenance.json` | 411 | Existing provenance for that rank-113 control; its source path is descriptive, not read by tests |

Both copied n=5 F2 certificates passed the independent exhaustive 15,625-entry verifier. Their essential ranks are 93 and 96; neither is a record at the campaign's target. The copied oracle imports no production implementation. Its SHA-256 remains `f9b00ed3873abe61ce4456cfbf51f04bf9fd9342978d04cbd4b804231b4d40e8`.

Explicit test files for the portability change:

- `tests/test_campaign_native_dwell42.py`
- `tests/test_campaign_native_plus_burst42.py`
- `tests/test_audit_burst_long42.py`
- `tests/test_compact_rank2_edges43.py`

The provenance JSON records all four tests' hashes before and after the path edits. A unified regression launched before these edits covers its recorded source snapshot; the verification agent was asked to rerun the affected modules after the edits. Do not describe an earlier run as testing the later bytes.

Other new tests read `artifacts/km93_f2.json`, `artifacts/rl_campaign_20261102T210735Z/public/alphaevolve93_f2.json`, and `artifacts/campaign_20261102T164324Z/control-strassen7.candidate.json`; all three are already tracked. They need no extra campaign-wide staging. Existing native tests still require their locally built workers. In particular, `test_rl_operator44.py` accepts the audited binary at `native/flip_worker_plus_burst42` and only falls back to the old campaign binary; no campaign binary should be committed as a fixture. Reproducing that control requires building the audited native source with an appropriate toolchain.

For the initial milestone, explicitly select the seven fixture files above, the four changed tests, this audit, and `RECOVERED_RESULTS.md`, alongside root's reviewed pre-recovery source/test selection. Select prepared infrastructure files individually if publishing them: `campaign.json`, initial `queue.json`, `guard-policy.json`, `launch-plan.json`, `recovery-report.json`, `recovered-rank3-closure.json`, `recovery-read-only-audit.py`, `validation.json`, `README.md`, and `manifest.json` beneath `artifacts/marathon7_20261103T122417Z`. Runtime queue files can change after launch and require a new explicit review.

Do not add all campaign 42 or all new campaign contents. The old duplicate rank-93 files, burst summary, raw native outputs, lossless archives, model caches and old absolute-path certificate tree are no longer fixture dependencies of these four tests. Root owns all Git staging, commits and pushes.
