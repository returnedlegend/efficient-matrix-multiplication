# Local SAT campaign

`scripts/campaign_sat.py` runs a restartable single solver worker. Default target
is 92 terms from exact 93-term 5×5 F2 inputs. The input coefficients must be
integer ternary values; -1 is canonicalized to 1. All 15,625 tensor entries are
encoded, including expected zeros. No integer lift is claimed.

```bash
python scripts/campaign_sat.py \
  --input artifacts/km93_f2.json \
  --seed-dir research/campaign/native \
  --output-dir research/campaign/sat \
  --seconds 6600 --patch-seconds 30 --conflicts 100000
```

The resource harness should pin this command to one core and impose its memory
limit. The script forks only the bounded solver child; the parent waits while
that child solves. Do not run two workers against one output directory.

Patch proposals use K=5–12 retained mutable slots, graph neighbors, randomized
nearby terms, windows, and uniform subsets. Exact GF2 flattening ranks reject
patches whose replacement is impossible. Every third accepted proposal uses full
factor support; others use the union of source supports. These are separate local
branches. No fixed factor conditioning is imposed. UNSAT is explicitly local to
the frozen patch and support branch, not a global rank lower bound.

Each sixth solve can retry an UNKNOWN patch at the next finite level: default
30/60/120 seconds and 100k/300k/900k conflicts. Selection prioritizes lower levels
with more flattening-bound slack, then older patches, with no retries of UNSAT
patches. This slack is a heuristic, not a sufficiency test. Wall limits include solver
startup. Repeated patch identities and identical CNF hashes are skipped.

The manifest records canonical source hashes, original byte hashes and paths,
source proposal cursors, patch identity, selection seed, statuses, and levels.
`results.jsonl` records individual budgets, solver statistics, encoding time,
phase hashes, dependency version, and all patch parameters. `summary.json`
contains aggregate counters. Reusing the output directory resumes the manifest;
identity parameters (rank, dimension, seed, K range) must agree. Source directories
are scanned recursively every 30 seconds; snapshots must independently verify
exactly at rank93 before ingestion. Term-permuted duplicates are collapsed.

At most two CNFs and maps and 256 MiB are retained by default; the metadata and
hashes for deleted CNFs remain in the log and manifest. An exact success is
independently checked against every coefficient and 64 multiplication trials,
then written as `FOUND.json`, `FOUND.verification.json`, and `FOUND.verify.py`.
The worker stops immediately on verified success or solver ERROR.

Smoke tests use a planted one-term reduction and a bounded rank93→92 patch.
No global lower bound follows from UNSAT or budget exhaustion.
