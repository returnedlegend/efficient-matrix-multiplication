# Final post-M4 targeted source validation

PASS: 111/111 tests across 21 modules; no failures, errors, skips, or unexpected successes. Elapsed 3.509 seconds. Frozen source: 682 files, unchanged before/after and matching live source after the run.

Scope: tiny/planted controls only; no actual N5 target solver search. Native controls used existing C42 binaries read-only. Real CryptoMiniSat and PySAT paths are printed in `targeted-regression.log`. Resource envelope: affinity CPUs [0, 1, 2], 3072 MiB address-space cap, 300 second outer timeout. Spawn-safe main guard.

Campaign UTC guards expired before this validation. Five real-clock guard receipts confirm deadline refusal before solver dispatch. The final unittest run used six module-local time proxies set to one hour before the original campaign deadline; monotonic limits and hard UTC constants remained unchanged. Exact module names and clock epoch are in `summary.json`. The initial harness attempt missed inherited dependency guards and failed; its raw log, runner and summary are preserved in `initial-harness-attempt`. No production source fix was needed or made.

Even-component controller remains prepared only; these tests are not evidence of a production controller run. This validation makes no new search-result claim.

Snapshot manifest SHA256: `d8db8a9d211032918e19ac477d716e819cebf525f7d523d017501c9d15ba2fbe`.

All source-hashes manifest SHA256: `3afbe0c334ebdbcf6224311b3ad1528ad08c3cb50a814aad7ada99ca1eee923a`. Post-M4 changed/added source hashes: `postm4-source-hashes.json` (59 files). Real-clock checks: `real-clock-deadline-controls.json`; final raw output: `targeted-regression.log`; before/after source hashes: `hashes-before.json`, `hashes-after.json`; machine-readable final outcome: `summary.json`.
