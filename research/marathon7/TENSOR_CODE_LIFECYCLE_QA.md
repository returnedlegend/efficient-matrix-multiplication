# TensorCode7 independent lifecycle QA

The independent protocol fixture uses a real exact binary N2 tensor with 93 distinct atoms: schoolbook8 plus one four-point zero-sum circuit and 27 disjoint three-point zero-sum circuits. Its dictionary also includes planted known Strassen7 atoms. All state equations, kernel differences, and both full tensor checks are actual N2 computations. Only the production metadata/source-loading boundary is mocked to enter the N5 runner protocol; no production N5 source or search query is used.

Pre-fix reproduction (`tensorcode-lifecycle-independent-qa-repro2.*`) found three bugs in runner SHA256 `71ed860863e171add62ea7a3d60fbf9bf07d51465f0ea0f2a7559fbe42f6302b`: a cutoff just after move selection still published record evidence; a cutoff after verification still published record evidence; and resuming an eligible best continued search rather than stopping. The first two returned winner=true, while the third called move selection 64 times and returned MAX_RESTARTS/winner=false. These are protocol reproductions, not discovered matrix-multiplication records.

New independent tests live in `tests/test_tensor_code7_lifecycle.py`. They cover late move/verification UNKNOWN status and retained raw evidence, absence of record publication, exact rollback of the consumed RNG and cursor when a move is late, guarded terminal handling of an eligible resumed best, no promotion or search from a late-only resumed best, malformed cursor rejection, cutoff checks between the two independent tensor verifiers and after the second verifier, the fixed marathon UTC ceiling, and deterministic split replay with a four-dimensional kernel and multi-cycle moves.

The owner applied the fixes; the consolidated review is `research/marathon7/TENSOR_CODE_REVIEW.md`. Acceptance below uses the final frozen source pins and the subsequent full regression; intermediate green artifacts do not certify later source edits. Production authorization remains with root.


Final acceptance: **all 9 independent lifecycle controls pass** in the full 866/866 unified regression, together with all 33 TensorCode7 controls. Evidence: `artifacts/marathon7_20261103T122417Z/checks-marathon7-final.{log,result.json}` and `checks-marathon7-final-summary.json`. No existing source changed during the run.

| Final file | SHA256 |
|---|---|
| `scripts/tensor_code7.py` | `b15bf99affff1ca9cad431ce481aa1f4d8043f23ca07f55b6ad365fbc9f3bef9` |
| `mmsearch/tensor_code7.py` | `e5fa2a84c00ee5e10076ff3902963cf27dfe86b43fc4d4ad885cef8f3f7291e1` |
| `tests/test_tensor_code7_lifecycle.py` | `0e5de0432f84f3a9a598ac9a445bf78d6d8edd19a6708efd77cb8fe0d09e889e` |

Late proposals remain UNKNOWN with raw evidence. In-progress iterations restore their exact previous cursor, basis order and RNG, so a late best cannot acquire within-budget eligibility on resume. Explicit late-only terminal checkpoints also stop without search or publication. Eligible terminal checkpoints reverify across publication barriers and stop before selecting any new move. Source/provenance acceptance is covered by the separate consolidated review; this lifecycle acceptance authorizes no production launch.
