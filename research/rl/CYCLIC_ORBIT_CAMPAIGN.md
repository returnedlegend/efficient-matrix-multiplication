# Restartable C3 orbit-local SAT portfolio

`scripts/campaign_cyclic_orbit_sat.py` uses the frozen C3 encoder in process.
It verifies and freezes eligible parents once, then prepares many local patches
without starting a Python process for each bound rejection. Solver children are
started only for patches that pass the necessary exact lower bound.

```sh
PYTHONPATH=.xor-deps:. taskset -c 3 python scripts/campaign_cyclic_orbit_sat.py \
  --seed-dir PATH/fixed2-1/verified --seed-dir PATH/fixed2-seeds/seeds \
  --output-dir PATH/new-orbit-portfolio --seconds 600 --patch-seconds 10 \
  --k-min 2 --k-max 7 --seed 503 --backend auto \
  --conflicts 100000 --memory-mb 1536
```

`--input` and `--seed-dir` repeat. Directory selection reads only immediate
`*.json` files. Missing inputs, malformed certificates, other ranks/dimensions,
other cyclic/cube profiles, and duplicate canonical parents are skipped with
explicit counts. They are not claimed exact. Accepted parents must be 5x5 F2,
canonical rank 95, cyclic, and have two fixed cubes. Their original and normalized
certificates independently pass all 15,625 coefficient checks before freezing.
The top-level manifest preserves raw source paths and hashes, parent snapshots,
verification reports, and code hashes/snapshots.

A seeded shuffle orders every (parent,k,anchor) configuration. Neighboring orbits
are chosen deterministically from each anchor, prioritizing shared factors.
The cache key is frozen-parent raw hash plus sorted orbit indices. Equivalent
patches arising from different anchors are skipped. Each patch is committed to
an append-only cache journal before encoding, and state, plan cursor, counts,
and RNG state are saved every 30 seconds and at clean exit. Resume also replays
the journal and event log to avoid repeating patches after a stale periodic
state snapshot. UNKNOWN and ERROR patches are cached too; a changed search
policy or larger-budget retry belongs in a new campaign directory.

To resume, use `--resume --output-dir EXISTING` with the same configuration and
a fresh wall budget. Parent checksums and independent verification are checked
again, and changed code or configuration is rejected. The CLI's initial output
directory must be new. The finite anchor/k plan stops when exhausted rather
than looping over unchanged patches indefinitely.

Exact lower-bound rejection is logged as `LOCAL_UNSAT_BOUND`. A solver UNSAT is
`LOCAL_UNSAT`; time/conflict exhaustion is `UNKNOWN`; backend/validation failure
is `ERROR`. Each event records parent/indices, formula and full-problem hashes,
dimension/bounds, variable/clause/XOR counts, budgets, and timing. Full problems
are retained only for the first two, the latest, and SAT cases; other problems
can be regenerated from frozen parents, indices, configuration, and source code.

Every SAT model is independently decoded and exhaustively checked at all 15,625
global coefficients. Candidate/model/report and the full problem are frozen.
Rank≤92 additionally writes a checksummed root `WINNER.json`, report, standalone
verifier, and stops. Local bounds and UNSAT results concern only the selected
frozen outside terms, never global matrix-multiplication rank.

Every solver case reserves two seconds from the remaining total wall budget
for cleanup, decoding, and saving. No case starts inside that reserve. SIGTERM
or SIGINT during encoding/solving unwinds through the existing solver's cleanup,
terminating/reaping its child and saving the interrupted case as UNKNOWN and
the campaign state. During artifact writes, the signal requests a clean stop
after the write rather than interrupting it.

Tests use a planted 2x2 identity only through the internal engine, preserving
the CLI's strict 5x5 parent requirement. They cover real SAT/verification/frozen
target output, cached UNKNOWN replay, cleanup reserve, and local status mapping:

```sh
PYTHONPATH=.xor-deps:. python -m unittest tests.test_campaign_cyclic_orbit_sat
```
