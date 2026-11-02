# Local SAT audit

Snapshot: 2026-11-02T18:39:10Z. Recognized workers: 12.

There are 3,237 distinct uniform-domain frozen neighborhoods:
2,131 have exact Koszul rejections, 112
have solver UNSAT results, 994 remain UNKNOWN-only, and
0 have SAT results. Bound/UNSAT overlap: 0.
Contradictions: 0. Error-containing neighborhoods: 0.
These counts do not establish a global matrix-multiplication rank bound.

Uniform union, full-coordinate, and exact image-coordinate formulations are
identified: projecting each factor of any K-product residual decomposition
onto the three residual mode images preserves the tensor and number of slots;
the images lie inside the shared source-support union. All mutable slots use
that same union, zeros are allowed, and U-lex only reorders identical-domain
products. Different deleted slots within one selected subset merely relabel
mutable products; the frozen complement and residual remain identical.

Nonuniform supports, guessed factor fixings, dictionary restrictions, and other
recorded conditioning receive separate conditional keys. Unrecognized encoders
are excluded. Conditional groups: 0.
Excluded worker logs: 2. Diagnostics: 0.

Raw result counts are {"BOUND": 3938, "UNKNOWN": 1548, "UNSAT": 112};
these include intentional backend, symmetry, budget, and heuristic repeats.
The companion JSON contains every derived key, contributing patch/worker IDs,
input-log hashes, prefix byte counts, manifest identities/hashes, exclusions,
and diagnostics. Reproduce a live snapshot after workers append more data with
`python scripts/campaign_sat_audit.py CAMPAIGN --replay-snapshot SNAPSHOT.json --output-prefix PREFIX`.
Replay verifies each recorded log prefix against its saved hash and uses the
saved identity rather than a newer manifest. Normal invocation omits the replay
flag and audits all currently recognized worker logs.
