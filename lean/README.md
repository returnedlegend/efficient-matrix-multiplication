# Lean 4 verification

The checked core is `Certificate.lean`, using Lean 4.19.0 and its bundled `Std` only.
Run `bash lean/install.sh` to reproduce toolchain installation, then `bash lean/check.sh` from the repository. Set `LEAN_BIN` if Lean is elsewhere.
The official prebuilt toolchain was downloaded over verified HTTPS from:
https://github.com/leanprover/lean4/releases/download/v4.19.0/lean-4.19.0-linux.tar.zst
It is stored in ignored `lean/.toolchain/`; no Mathlib download is needed.

The core proves, for arbitrary input matrices with entries in F2 (Bool with
xor addition and and multiplication), that an exact coefficient tensor certificate
implies correctness of the bilinear algorithm, and that the target trace tensor
contracts to ordinary 5x5 multiplication. The proof contains no `sorry` or custom
axioms. This generic implication does not certify any particular decomposition.
The trace convention is T[(i,j),(j,k),(k,i)]=1, so output[i,k] uses W[k,i].

Reproduce the successfully checked rank-95 certificate-specific proof:

```
python3 scripts/export_lean.py --native artifacts/flip-search-seed0.json lean/Rank95Native.lean
bash lean/check.sh lean/Rank95Native.lean
```

The exporter defaults to Lean's kernel-evaluated `decide`, which may be expensive
for 1.5 million Boolean coefficient contributions. `--native` instead uses
`native_decide`; this additionally trusts Lean's native evaluator (`Lean.ofReduceBool`),
which is printed in the theorem's axiom audit. Keep these validation levels distinct.
Both routes require the explicit coefficient equality; neither assumes it.
The existing public rank-96 schema is a harness baseline and is not a rank-below-95
research result. A future rank-94 certificate must be exported and compiled separately.
The theorem only addresses F2 and does not establish an integer or complex algorithm.

## Current checked result

`Rank95Native.lean` was generated from `artifacts/flip-search-seed0.json`
(rank 95) and compiled successfully with Lean 4.19.0, zero errors. It proves the
explicit coefficient identity and applies the generic theorem to all F2 matrices.
The compiler's axiom audit reports `propext`, `Quot.sound`, and `Lean.ofReduceBool`.
The last is the trusted native-evaluator route, not a kernel-only computation.
A one-bit-corrupted copy was independently compiled and correctly rejected.
Reproduce this checked result with:

```
python3 scripts/export_lean.py --native artifacts/flip-search-seed0.json lean/Rank95Native.lean
bash lean/check.sh lean/Rank95Native.lean
```

This rank-95 result does not meet the requested strict rank-below-95 target.
`Rank95.lean` is the corresponding kernel-`decide` source. Its compilation was
stopped after approximately 120 seconds to respect the research compute budget;
no successful compiler result is claimed for that source. See `Rank95Kernel.log`.
The successful native proof and exact compiler exit code are in `Rank95Native.log`.
