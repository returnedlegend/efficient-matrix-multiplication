# Two-hour F2 matrix multiplication search — INTERIM

No independently verified candidate of rank 92 or lower is recorded; best accessible verified reference remains 93.

Generated 2026-11-02T18:32:57.260299+00:00; campaign state `running`.
Window: 2026-11-02T16:43:24Z to 2026-11-02T18:43:24Z; target ≤92 products.
The experiment concerns exact bilinear 5×5 multiplication over F2.

## Resources and search

Caps: 4 CPU cores, 8 GiB RAM; worker affinity CPUs 0–3 and inherited address-space limits.
Completed tracked worker CPU: 16556.5s across 20 jobs; 6 saved running records.
Largest completed-worker reported RSS: 890.7MiB; guard maximum observed aggregate RSS: 1721.6MiB.
CPU excludes active and unwrapped work. RSS samples can miss peaks; aggregate ps measurements count shared pages repeatedly.
No paid external compute or publication was used.

| Native branch | Saved phases | Steps | Best rank |
|---|---:|---:|---:|
| cyclic | 3 | 305,954,874 | 93 |
| satseed-flips | 8 | 1,619,911,680 | 93 |
| unrestricted | 7 | 2,883,709,599 | 93 |

Finite-pool recombination: 552 source algorithms, 903 columns, 1281100 evaluations, best rank 93; local minimum only.
ALS rank-92 certificate remained invalid (1 coefficient mismatch); targeted repair completed 119 slices without an accepted target certificate.

| Local SAT branch | Attempts | SAT | UNSAT | UNKNOWN | ERROR |
|---|---:|---:|---:|---:|---:|
| compact-lex | 204 | 0 | 82 | 122 | 0 |
| compact-lex-wide | 194 | 0 | 3 | 191 | 0 |
| compact-plain | 51 | 0 | 0 | 51 | 0 |
| koszul-cadical | 77 | 0 | 0 | 77 | 0 |
| koszul-p2-cadical | 269 | 0 | 0 | 269 | 0 |
| koszul-p2-xor | 274 | 0 | 0 | 274 | 0 |
| koszul-wide | 202 | 0 | 0 | 202 | 0 |
| koszul-xor | 127 | 0 | 0 | 127 | 0 |
| oriented-cadical | 52 | 0 | 0 | 52 | 0 |
| oriented-xor | 59 | 0 | 0 | 59 | 0 |
| sat | 48 | 0 | 27 | 21 | 0 |
| xor-lex | 95 | 0 | 0 | 95 | 0 |

These are raw manifest counts; retries/overlaps are not distinct negative neighborhoods. Controls and smoke directories are excluded.
Deduplicated audit `research/campaign/sat_audit_1820.json` (2026-11-02T18:19:51Z): 3006 uniform neighborhoods; 1925 exact-bound rejected, 112 solver UNSAT, 0 overlap, 2037 negative union; 969 UNKNOWN-only.
Conditional models are reported separately in the JSON audit. Audit timestamp can lag this live report.

| Frozen dictionary | Columns | ≤rank | Solver status | Rank 93 control | Forced ones / cardinality constant | Elapsed s |
|---|---:|---:|---|---|---|---:|
| dictionary-gl-expanded | 1812 | 92 | NO_SAVED_RESULT | SAT | 0 / 3 | — |
| dictionary-loop/phase-000/solve | 1491 | 92 | UNKNOWN | SAT | 19 / 37 | 300.1 |
| dictionary-loop/phase-001/solve | 1637 | 92 | NO_SAVED_RESULT | SAT | 17 / 34 | — |
| dictionary-preprocessed-expanded | 1091 | 92 | UNKNOWN | SAT | 43 / 50 | 1800.1 |
| dictionary903 | 903 | 92 | UNSAT | SAT | — | 55.2 |

Basis diversification generated 60 known-equivalent rank-93 transvection variants, independently checking all 15,625 coefficients each. Selected R-2-4, Q-4-2 release all 50 formerly forced choices using 132 new triples relative to the 903-column dictionary.
These are known-equivalent term forms used to broaden the search model; no algorithm novelty or inequivalence is claimed.

Dictionary UNSAT concerns subsets of that frozen column set; no independently checked UNSAT trace or global rank bound is claimed. A stopped dictionary-loop query with no saved solver result is not UNSAT; interventions.jsonl records the interruption.

## Certificates, checks and limits

Imported public reference portfolio: 307 distinct rank-93 term sets, independently checked on all 15,625 coefficients each.
Rank-93 SAT diversification contributed 16 term sets absent from the earlier pool; this is neither a rank improvement nor an inequivalence claim.
Latest saved full-suite log: 118 tests passed; saved exit 0. Rerun after any subsequent code changes.
Lean published rank-93 baseline: exit 0; axioms propext, Lean.ofReduceBool and Quot.sound. Native evaluation trust remains; this does not formalize a new record.
Native final-checkpoint draining was corrected; previous saved runs reported best 93. Code versions, hashes and adaptation history remain under frozen/ and RUNNING_HANDOFF.md.

* UNSAT is local to frozen neighborhoods or dictionaries, never a global rank lower bound.
* Dictionary UNSAT has no independently checked UNSAT trace; rank93 SAT controls are separate.
* UNKNOWN, interruptions and heuristic exhaustion are not UNSAT.
* arXiv access was denied; global literature novelty is unconfirmed (RECORD_CHECK.md).
* F2 results do not establish a literal integer identity or measured matrix-runtime speedup.

## Reproduce and resume

Run from the repository root; these commands preserve search evidence:

```sh
taskset -c 0 python3 scripts/campaign_report.py --markdown research/campaign/REPORT.md --json research/campaign/report.json
taskset -c 0 python3 -m mmsearch.verify artifacts/km93_f2.json --random-trials 64
taskset -c 0 python3 -c "import json,shlex; d=json.load(open('artifacts/campaign_20261102T164324Z/oriented-cadical-job.result.json')); print(shlex.join(d['command']))"
```

The last command only inspects completed-job command provenance; it does not execute a search. Completed jobs retain .result.json, while their .running.json records are removed. If that job is still active, wait for its completed record before using this inspection example.
The original deadline is fixed. Future search requires a separately authorized budget and a new campaign folder; these recorded arguments do not authorize another run or extend this campaign.
SAT restart restores experiment cursors and identity, not solver learned clauses. Native restart from a saved best/current state requires a newly recorded seed; exact replay instead requires the original seed and step schedule. Preserve all original evidence and record new provenance.
Artifacts: `artifacts/campaign_20261102T164324Z`. Per-job commands, budgets, caps, source hashes and compact metadata are retained in the companion JSON; large witness arrays are deliberately omitted.
