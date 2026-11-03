# Six bounded native exploration profiles

The root authorized six distinct 120-second native profiles, each on CPU0 with
768 MiB and a 150-second queue envelope. This is bounded exact exploration,
without training or an adaptive continuation. A revisited rank 93 state is not a
new mathematical result.

The frozen bundle is `artifacts/marathon7_20261103T122417Z/native-portfolio7-ready-v1`.
Its manifest SHA256 is
`9882f13aed6d44a92ffbed631613bf0787ddfd37707bbbcb66c5873187758521`.
The configurable adapter is `scripts/campaign_native_portfolio7.py`, SHA256
`88a5608f8a0b8ce3fe246fda2aab9cfa11390bbc285d41510cfb94645020b5a9`.
The query-free proposer is `scripts/prepare_native_portfolio7.py`.

| Profile | Approved train index | Mode | K | Reduction dwell | Plus cadence | Seed suffix |
|---|---:|---|---:|---:|---:|---:|
| p01 | 0 | cyclic C3 | 1 | 0 | 2,000 | 901 |
| p02 | 2 | cyclic C3 | 4 | 128 | 20,000 | 902 |
| p03 | 3 | cyclic C3 | 4 | 0 | 200,000 | 903 |
| p04 | 1 | unrestricted | 1 | 128 | 2,000 | 904 |
| p05 | 5 | unrestricted | 4 | 128 | 200,000 | 905 |
| p06 | 14 | unrestricted | 4 | 0 | 20,000 | 906 |

Full seeds are `20261103140901` through `20261103140906`. All roots are
distinct, exact rank 93 approved training roots. The first three inputs have
complete cyclic orbits. D128 is the original native reduction-dwell option;
it is not the separate hold-rank prototype. All profiles use maximum rank 105,
restart cadence 50,000,000, checkpoints every 3 seconds, archive sampling every
1,000 steps, and at most 16 archive states.

The binary SHA256 is
`6e7d6c63fa262bfc50acfe92fbe9c11adb74426e3868a5a6f7ad8d1bf569ac19`.
The safe baseline handoff remains byte-identical at SHA256
`37d8da3074517dda178b90369fab1817db998a1df6f3d89edcc1b87898bba54d`.
The accepted cached guard is SHA256
`09ac03c4ac1123eeb2ddba8a72653cc299aca052df9ad6c82ad618ed5cbd5cd9`.
The root-approved source-anchor manifest is SHA256
`26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8`.
The bundle includes exact source bytes, source audits, the pinned training plan,
root arm declaration, split registry, and heldout declaration. Eligibility is
closed at the frozen initial 16 training inputs, with no unknown ancestor edges.

Seven new controls and four unchanged baseline controls passed in the frozen
runtime. They include an actual tiny early positive and final drain, a real
native cyclic/dwell telemetry control, late positive retention, independent
false-positive rejection, a prelaunch stop, and budget/argv checks. Six frozen
read-only production-input previews each passed both complete 15,625-entry
verifiers. The actual strict six-key queue helper validated the proposals.
The first combined frozen test invocation omitted the baseline test's explicit
binary environment variable and failed to locate that test binary; rerunning
with both documented binary overrides passed all 11 tests without skips.

All raw snapshots stay in hidden raw storage. Only a fresh rank <=92 candidate
that passes both complete verifiers and the strict independent record gate can
enter `records/` for the global guard. The adapter never writes a local WINNER.
It rechecks live campaign/resource guards and disk reserves throughout the run.
Each profile reserves 22 MiB; aggregate bundle and profile storage is capped at
150 MiB with an early reserve hold. All final best/current states receive both
complete verifiers when fresh. Raw above-best exports are explicitly raw, not
certified improvements.

Metrics include canonical raw hashes and counts, productcount histograms,
above-best native step residency, per-axis equal-factor multiplicity histograms,
final opposite-pair ranks, measured owned-child CPU, and CPU-normalized rates.
These are exploration measurements, not novelty or superiority claims.

The first-five proposal SHA256 is
`33ca1f4bd065f096be2768f1ed0f50d8317c72eaf7c2957ec31a15a4d039213c`.
Its queue receipt committed at 2026-11-03T15:32:07.264807Z; the first wrapper and
native process were observed as PIDs 32870/32871 on CPU0 at nice 19. No outcome
is implied by this launch observation. Profile six remains outside the queue
until the reserved bounded corpus-preparation gap after profile five. Its
disabled proposal SHA256 is
`f4537ea8657a790cde838cd99950b38f2381c64be0b77ff52aa2933507a21e82`.

Each output's `summary.json` records actual process accounting, native stats,
verification completeness, stop reason, and raw exploration data. A bounded
failure to reach rank 92 is not a global tensor-rank lower bound.

All-six results are frozen in `native-portfolio7-evidence-six-complete.json`,
which pins each actual summary. All six exited 0 without a guard stop or outer
timeout; both final best/current states passed both complete verifiers. No
target was emitted. Profile six ran after explicit corpus-prep reaping and
CPU0 release, following the agreed preparation gap.

| Profile | Child CPU seconds | Native steps | Best / final rank | Raw unique snapshots | Above-best steps |
|---|---:|---:|---|---:|---:|
| p01 | 113.743141 | 33,739,264 | 93 / 99 | 57 | 33,465,670 |
| p02 | 112.855110 | 33,534,976 | 93 / 97 | 211 | 28,266,525 |
| p03 | 111.186272 | 26,272,512 | 93 / 93 | 609 | 15,514 |
| p04 | 109.237488 | 74,129,408 | 93 / 93 | 681 | 4,587,452 |
| p05 | 107.798788 | 76,905,728 | 93 / 93 | 679 | 243,049 |
| p06 | 106.516558 | 74,835,968 | 93 / 93 | 681 | 1,353,598 |

The native wall times range 120.015–120.149 seconds. These profiles vary several
settings and inputs together; observed differences are descriptive, without a
causal or superiority claim. A raw rank 93 atom inventory of p01–p04 contains
2,267 whole atoms, of which 1,877 are outside the original 406-atom dictionary.
That inventory does not prepare a dictionary or authorize optimization, and
individual raw exports have not all received the two full final-state checks.
