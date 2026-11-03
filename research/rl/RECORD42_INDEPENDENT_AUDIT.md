# Independent certificate and explicit Lean audit

The campaign target is an exact 5×5 bilinear construction over F₂ with at most
92 essential scalar products. The new standalone verifier is
`scripts/verify_record42_independent.py`; it imports only Python standard-library
modules and does not import the search, tensor implementation, or older verifier.

It rejects duplicate JSON object keys at any depth, non-JSON numeric constants,
wrong dimensions or fields, noninteger dimensions/fields, and any factor that is
not an array of exactly 25 integer bits. Booleans and floats are rejected. It
removes zero products and cancels equal product triples in characteristic two;
reported R is the resulting essential product count, ignoring rank metadata.

For each of 625 pairs of input basis matrices it directly evaluates every one
of 25 output entries. All 15,625 bits, including the expected zero bits, must
equal ordinary matrix multiplication. The third vector follows the trace
convention: `w[k*5+i]` contributes to output `C[i*5+k]`. Reports include raw
source, canonical certificate, and verifier SHA256 values and explicit proof
scope flags. This is a constructive upper bound, not a global minimum-rank or
integer-lift claim.

Check a candidate without changing campaign state:

```sh
timeout 45s bash -c 'ulimit -t 30; exec taskset -c 2 nice -n 10 python3 scripts/verify_record42_independent.py "$1" --require-record' _ PATH_TO_CANDIDATE
```

The V3 operations guardian calls this checker as a mandatory second check before
publishing its frozen record bundle, repeats the check on persisted bytes, and
includes the standalone checker source and report in that bundle. The guardian
owns campaign termination. The audit script below never signals processes or
edits queues.

After the guardian has preserved a valid candidate and finished all pending
identity-safe process-group stops, run:

```sh
nice -n 10 python3 scripts/audit_record42_lean.py \
  artifacts/rl_campaign42_20261103T033116Z/operations-record/WINNER.json \
  --campaign artifacts/rl_campaign42_20261103T033116Z \
  --audit-root artifacts/rl_campaign42_20261103T033116Z/record-formal-audit \
  --cpus 2,3
```

`audit_record42_lean.py` first exclusively creates a read-only copy of the raw
candidate and its checksum. It then freezes the checker, exporter, generic Lean
core and auditor sources, independently verifies the preserved bytes, and writes
a canonical certificate. Normal mode requires valid canonical R≤92, the V3 stop
marker, a recorded stop reason, and an empty pending-stop list. Rank 93 cannot
reach proof compilation in normal mode.

It exports with the existing `scripts/export_lean.py --native`, rebuilds the
preserved generic core with Lean 4.19.0, and compiles the explicit coefficient and
matrix-product proof. Each child has at most two selected CPUs, niceness
increment 10, a 30-second CPU limit, a 45-second wall limit, and a 4 GiB virtual
address-space limit; Lean explicitly uses two threads. Outputs and return codes
are retained. The source audit rejects proof placeholders and custom axioms;
the output audit requires `#print axioms` for both explicit theorems and rejects
axioms outside `propext`, `Quot.sound`, and `Lean.ofReduceBool`.

The use of `native_decide` trusts Lean's native evaluator through
`Lean.ofReduceBool`; this is not kernel-only reduction. Read-only evidence uses
exclusive creation, SHA256 and filesystem permissions, not an unalterable medium:
the filesystem owner can still change permissions. Each attempt gets its own
directory and is never overwritten.

Readiness was demonstrated only on published KM93 with the explicit
`--published-baseline-control` switch (restricted to R exactly 93):

```sh
nice -n 10 python3 scripts/audit_record42_lean.py artifacts/km93_f2.json \
  --published-baseline-control --cpus 2,3 \
  --audit-root artifacts/rl_campaign42_20261103T033116Z/independent-formal-ready-v1
```

The successful preserved run is
`independent-formal-ready-v1/56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b-1793677567413640341`.
Its generic core and explicit proof compile with exit code 0; their wall times
were 15.704 and 2.990 seconds. The coefficient theorem depends on `propext` and
`Lean.ofReduceBool`; multiplication correctness additionally uses `Quot.sound`.
Earlier failed readiness attempts are retained with failure reports: the initial
2 GiB virtual-memory cap was too small, and the toolchain's documented `-M`
option failed on an unknown `max_memory` setting. The working command uses two
threads and the external 4 GiB virtual-memory bound. No rank-below-93 explicit
proof or new-record result was compiled or claimed during readiness work.

The 18 dedicated tests pass in under one CPU second. Controls cover KM93 and
AlphaEvolve93, all zero/one coefficient bits, a single coefficient corruption,
strict field/dimension/type guards, duplicate keys, non-JSON constants, fake
rank metadata and a missing term, transposed W, canonical duplicate/zero
cancellation, schoolbook n=2 and a planted Strassen7 n=2 reduction, evidence
preservation, axiom auditing, and refusal to compile rank 93 in record mode.

```sh
timeout 45s bash -c 'ulimit -t 30; exec taskset -c 2 nice -n 10 python3 -m unittest discover -s tests -p "test_*record42*.py" -v'
```
