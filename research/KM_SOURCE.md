# Author-published Kauers–Moosbauer datasets

The requested characteristic-two **95-product** seed has been obtained directly
from Jakob Moosbauer's accompanying repository for *Flip Graphs for Matrix
Multiplication*, arXiv:[2212.01175](https://arxiv.org/abs/2212.01175), by
Manuel Kauers and Jakob Moosbauer. It is not the earlier AlphaTensor-derived
checkpoint in this workspace.

* Repository: <https://github.com/jakobmoosbauer/flips>
* Pinned commit: `e31a0a0f0d2577cee5da047ca7dcae0c61992e40`
* Path: `solutions/555-95-mod2.exp`
* SHA-256: `b40354f5ee16172665e9f60a8fa92777f9993ae824aad69d0321c4b11021e13f`
* Imported certificate: `artifacts/km95_f2.json`

Every factor coefficient is 0 or 1, within the requested ternary domain. The
source's third factor already follows the trace convention: output[i,k] uses
w[k,i], with no transpose required during import. Independent verification
checks all 15,625 coefficients exactly over F₂, with zero mismatches, and passes
64 supplementary random products. Its literal binary coefficients do not give
an integer identity (1,330 mismatches); no lift is claimed.

## Newer published result, not a new discovery here

The same authors' *Flip Graphs with Symmetry and new Matrix Multiplication
Schemes*, arXiv:[2502.04514](https://arxiv.org/abs/2502.04514), already supplies a
**93-product** 5×5 characteristic-two scheme. Thus 95 is not the best published
threshold established by the sources inspected during this task. This does not
change the requested localized 95→94 search, but prevents a false novelty claim.

* Repository: <https://github.com/jakobmoosbauer/symmetric-flips>
* Pinned commit: `3e2d4dd8acf831ef65c7c6b13ed787330e1e3483`
* Path: `schemes/555m93.txt`
* SHA-256: `89b86d46243b2245bd6197cd0967fdb5b7c0da0de9ea2fd2b3f5ec2f74c9b804`
* Imported certificate: `artifacts/km93_f2.json`

This imported rank-93 scheme also has only binary factors and independently
passes all 15,625 F₂ coefficient checks plus 64 random products. It is supplied
as **published reference data**, not an outcome of the local SAT search and not
substituted for the requested rank-95 starting point. Literal integer equality
fails at 2,277 coefficients.

The separate upstream `schemes/555m93_lifted.txt` contains **±2 coefficients**
(for example, the term beginning `(-2a41 - a43 + ...`), so it does not satisfy
this task's ternary coefficient restriction. It has not been imported as an
eligible ternary candidate, and no integer verification result is claimed here.

## Reproduction and license

Both raw input files are retained as `artifacts/km95_source.exp` and
`artifacts/km93_source.txt`, respectively. The importer uses strict parsing,
no `eval`, no floating point, pinned source checksums, and mandatory exact
coefficient verification before writing a certificate:

```sh
python3 scripts/import_km.py artifacts/km95_source.exp --kind 95 --output artifacts/km95_f2.json
python3 scripts/import_km.py artifacts/km93_source.txt --kind 93 --output artifacts/km93_f2.json
```

The source repositories' README and LICENSE notices give GPL version 3 or later
for their included program. Their notices and GPL text are retained in
`artifacts/km_upstream_README.md`, `artifacts/km_symmetric_upstream_README.md`,
and `artifacts/km_upstream_LICENSE`. No separate data-specific license was found;
the attribution and upstream notices are preserved rather than asserting a
different license. The importer is a new strict format reader; no upstream
search code was copied into it.
