# Published-record check and public seed import

Checked live on **2026-11-02, approximately 16:44–16:49 UTC**. This is a bounded
source check, not a comprehensive literature review.

The best exact 5×5 F₂ upper bound independently established from the sources
accessible in this check remains **93 products**. No source inspected supplied
a ≤92 certificate. This does **not** establish that no newer publication or
uncatalogued public certificate exists. A successful rank-92 search would still
need a broader current literature comparison before a novelty claim.

## Author repository, checked at its current head

* Author repository: <https://github.com/jakobmoosbauer/symmetric-flips>.
* Current `main`, checked from its live GitHub tree and commit history, remains
  `3e2d4dd8acf831ef65c7c6b13ed787330e1e3483`, dated
  **2025-02-10T01:32:43Z**.
* [Live scheme directory](https://github.com/jakobmoosbauer/symmetric-flips/tree/main/schemes)
  lists only `555m93.txt`, `555m93_lifted.txt`, `666m153.txt`, and
  `666m153_lifted.txt`.
* [Immutable rank-93 source](https://raw.githubusercontent.com/jakobmoosbauer/symmetric-flips/3e2d4dd8acf831ef65c7c6b13ed787330e1e3483/schemes/555m93.txt)
  was fetched again successfully: 5,640 bytes, SHA-256
  `89b86d46243b2245bd6197cd0967fdb5b7c0da0de9ea2fd2b3f5ec2f74c9b804`.
  This matches the existing imported source and independently checked
  `artifacts/km93_f2.json`.
* The current README still identifies the accompanying publication as
  [arXiv:2502.04514](https://arxiv.org/abs/2502.04514), *Flip Graphs with Symmetry
  and new Matrix Multiplication Schemes*.
* The [author's repository list](https://github.com/jakobmoosbauer?tab=repositories)
  showed `flips`, `symmetric-flips`, and `pivots`. The older `flips` current head
  remains `e31a0a0f0d2577cee5da047ca7dcae0c61992e40`; `pivots` is an older
  repository created in 2020, with no newer record claim in its README.

## A newer public experiment supplies useful diversity, not a better bound

GitHub repository search for `matrix multiplication 5x5` found
[Nadim F. Zaru's FastMatrixF2](https://github.com/big-brain-zaru/FastMatrixF2).
Its current head is
`5fd32f680acf2a7708ea6a2d40d10f7e7537957c`, dated
**2026-09-18T07:16:49+03:00**. Its `CITATION.cff` states version 1.0.0,
release date 2026-09-18, concept DOI `10.5281/zenodo.22823114`, and version DOI
`10.5281/zenodo.22823115`. Those DOI records were not independently retrieved.
No peer review or arXiv publication claim was found in the inspected metadata;
treat this as an attributed public computational experiment.

The [immutable README](https://raw.githubusercontent.com/big-brain-zaru/FastMatrixF2/5fd32f680acf2a7708ea6a2d40d10f7e7537957c/README.md)
explicitly says **“No published record is improved.”** It reports 307 distinct
5×5 rank-93 schemes and at least 272 inequivalent classes, together with local
UNSAT searches for rank 92. Its paper source `main.tex`, dated September 9, 2026,
states that those negative results are conditional on symmetry and a stated
rewrite radius. In particular, lines 587–595 state restricted C₃-invariant
orbit-rewrite results. They do not rule out general rank-92 schemes.

The 307 distinct term sets were imported as public reference data to
`artifacts/campaign/public-seeds/fastmatrix-f2/`. No upstream script was executed.
The importer read numeric JSON only, with strict integer/range/rank checks,
duplicate-key rejection, and duplicate-triple rejection. Source masks use the
same row-major trace convention as this project: third-factor coordinate
`k*5+i` contributes to output coordinate `(i,k)`.

* `seeds/seed000.json` through `seeds/seed306.json`: canonical project-schema
  binary certificates. `seed306` is their original Lille rank-93 reference.
* `raw/`: original source JSON for one representative of each distinct term set.
* `manifest.json`: all **1,210** inspected rank-93 source files, each with its
  immutable raw URL, SHA-256, and deduplicated seed ID; attribution-file hashes.
* `verification.json`: every seed independently passed all **15,625** exact F₂
  coefficients, zero mismatches, plus eight supplementary random products.
  There were **4,796,875** exact coefficient checks in total.
* `attribution/`: original MIT `LICENSE`, `README.md`, `CITATION.cff`, and
  `main.tex` retained with authorship and research scope.

The distinct count was independently reproduced by sorting the rank-one triples
and deduplicating the resulting sets. The claimed count of inequivalent classes,
and the source's local UNSAT results, were **not** independently reproduced.
These seeds are imported references, not discoveries of this campaign.

Reproduction uses the new helper, which executes only this project's verifier:

```sh
git clone --depth 1 --filter=blob:none --no-checkout \
  https://github.com/big-brain-zaru/FastMatrixF2.git /tmp/record-check-FastMatrixF2
git -C /tmp/record-check-FastMatrixF2 sparse-checkout set --no-cone \
  '/results/*rank93*.json' '/results/records/*rank93*.json' \
  '/LICENSE' '/CITATION.cff' '/README.md' '/main.tex' '/results/on_dissection.json'
git -C /tmp/record-check-FastMatrixF2 checkout
taskset -c 0 python3 scripts/campaign/import_public_seeds.py \
  /tmp/record-check-FastMatrixF2 artifacts/campaign/public-seeds/fastmatrix-f2
```

The helper requires exactly the pinned commit above and fails on a changed head.
For future reproduction, fetch and check out that commit explicitly if `main`
has advanced.

## Access limits and citation caution

The managed environment's current network policy is enforced and restricted to
the `package_managers` preset. Public GitHub pages, raw files, and Git smart
transport were accessed through the inherited managed proxy with normal TLS
verification. The arXiv abstract request
`https://arxiv.org/abs/2502.04514` was denied with
`Tunnel connection failed: 403 Forbidden`. No proxy bypass, alternate route, or
TLS-verification disablement was used. arXiv search and the Lille FMM database
are outside the configured allowed hosts, so no live comprehensive comparison
against those sources was completed.

GitHub repository searches for `matrix multiplication 92` and
`"matrix multiplication" "93"` returned zero repository results. These searches
cover repository metadata, not general scholarly literature or authenticated
code search, and their negative results carry little evidential weight.
The additional repository `BretjHribar/bilinear-matmul-records` was inspected;
its README lists larger formats, not a 5×5 improvement.

There is a bibliographic discrepancy worth resolving when arXiv access is
available: the newer experiment's citation metadata attributes arXiv:2502.04514
to **Jakob Moosbauer and Michael Poole**, whereas existing local `KM_SOURCE.md`
and the importer call it the same Kauers–Moosbauer authors as the earlier paper.
This check has not independently resolved the original paper's author list;
the source identity is pinned by repository, commit, path, and hash regardless.
