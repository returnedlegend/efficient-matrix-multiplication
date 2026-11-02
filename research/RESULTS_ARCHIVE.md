# Complete experiment outputs

The full historical output tree is preserved in
`artifacts/research-results-20261102.tar.xz`. Its adjacent manifest records the
archive checksum and the SHA-256 and size of every member. This includes the
public seed portfolio and attribution, raw solver inputs and logs, frozen code
snapshots, checkpoints, and all campaign reports. No experiment results were
deleted from the workspace.

Code, primary reports, Lean proofs, key certificates and campaign job metadata
are also directly browsable in Git. Rebuildable native executables, the installed
Lean toolchain, Python dependencies and compiler caches are not committed.
Historical frozen native binaries remain inside the results archive to preserve
their recorded provenance.

From the repository root, verify or restore all archived paths:

```sh
python3 scripts/results_archive.py verify
python3 scripts/results_archive.py restore
```

Verification checks the archive and every member. Restoration creates missing
files, skips identical files, and refuses to overwrite conflicting local files.
Restoration is safe to repeat. It needs space for approximately 1.1 GB of output.
Restore before replaying historical audits, rebuilding reports, or running
campaign commands that consume the archived seed portfolio.

The original campaign remains closed. Starting another search requires a new
authorized budget; restoring files does not launch any search or service.
