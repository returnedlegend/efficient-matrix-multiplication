# Optional native XOR backend

`mmsearch/xor_sat.py` uses the exact compact image encoder with a private CNF
factory. AND gates remain CNF; parity equations become native XOR constraints.
Neither the compact encoder nor existing campaign files were modified.

Dependency: `pycryptosat==5.17.0`, installed from official PyPI over verified TLS
into workspace `.xor-deps` using `python -m pip install --target .xor-deps
--index-url https://pypi.org/simple pycryptosat==5.17.0`. The environment is
Python 3.12.14 on x86_64 Linux; the wheel is manylinux_2_34 cp312. The installed
extension path and SHA256 are recorded in `XOR_BENCHMARK.json`.
`requirements-xor.txt` captures the optional pin and shared scheduler dependency.

Example (from project root):

```
taskset -c 2 env PYTHONPATH=.xor-deps:. python scripts/campaign_xor_sat.py \
  --input artifacts/km93_f2.json --rank 92 --dimension 5 \
  --output-dir research/campaign/xor-sat --seconds 600 \
  --patch-seconds 5 --conflicts 10000 --k-min 7 --k-max 9
```

Use a separate output directory. Each worker sets `threads=1`, a conflict cap,
and an internal time limit. The parent wall timeout includes import and problem
loading; process termination/join overhead and independent candidate verification
follow that budget. Source phases are retained for provenance but are not used
as CryptoMiniSat phase hints. A native solver SAT model is checked against all
CNF gates and XOR equations, decoded in original coordinates, then independently
verified against all ambient tensor entries (15625 for 5x5). Solver UNKNOWN is
preserved; a local UNSAT result is never a global rank lower bound.

The paired short benchmark used identical passing K7 and K9 patches, symmetry
none, 10000 conflicts and at most 5 seconds each on CPU2 shared with the existing
campaign. All four results were UNKNOWN. Native XOR reduced variables/clauses
and consumed its budget faster, but these samples establish no advantage in
finding solutions. See `XOR_BENCHMARK.json` for complete inputs, timings and hashes.

Validation: `taskset -c 2 env PYTHONPATH=.xor-deps:. python -m unittest
 tests.test_xor_sat tests.test_compact_sat -v`. The native backend suite includes
exhaustive parity/AND semantics; original encoder isolation; full 2x2 rank8 to
rank7 and planted rank7 SAT controls with/without symmetry; exact small UNSAT;
zero residual decoding; full 15625-entry accepted-candidate verification;
corrupt-decoding rejection; hard-wall UNKNOWN; and extended DIMACS serialization.
Both module CLI and one-attempt scheduler CLI were exercised successfully.
