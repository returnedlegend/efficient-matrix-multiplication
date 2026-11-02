# Exact 5×5 matrix multiplication research

The complete historical outputs are supplied in a checksum-verified archive.
Run `python3 scripts/results_archive.py restore` before replaying campaign
reports or using the full seed portfolio. See [archive instructions](research/RESULTS_ARCHIVE.md).

The bounded two-hour record-search campaign is documented in
[the campaign report](research/campaign/REPORT.md); current measurements
are saved under `artifacts/campaign_20261102T164324Z/status.json`. The campaign
targets92 products against the strongest accessible verified93-product scheme.

An executable finite-field search and certificate pipeline targeting **at most
94 bilinear products**. A short heuristic run is not an exhaustive search and
does not establish novelty or nonexistence. Results apply to **F₂**; they do not
automatically extend to the integers, real numbers, or complex numbers.

**Published-result correction:** the Kauers–Moosbauer symmetry dataset already
contains a 93-product F₂ scheme, now imported and independently checked as
reference data. See [source provenance](research/KM_SOURCE.md). The requested
localized SAT experiment starts from their separate 95-product scheme and does
not substitute the published 93-product scheme as a search result.

## Local Kauers–Moosbauer 95→94 SAT experiment

```sh
python3 -m pip install -r requirements-sat.txt
python3 scripts/import_km.py artifacts/km95_source.exp --kind 95 --output artifacts/km95_f2.json
python3 scripts/local_sat_experiment.py
```

The experiment runs a 20-second exact flip search and then 16 small SAT
neighborhoods, each with a 2-second / 5,000-conflict limit. All coefficients
are exact integers in `{-1,0,1}`, canonically represented by bits because
`-1 = 1` in characteristic two. CaDiCaL runs locally. No floating-point
coefficient search is used. CNFs, factor-variable maps and solver outcomes are
saved under `artifacts/km-local-sat/`. See [SAT report](research/LOCAL_SAT.md)
for the precise encoding, limits, and outcomes.

For one configurable neighborhood:

```sh
python3 -m mmsearch.sat --input artifacts/km95_f2.json --rank 94 \
  --drop-term 0 --active-count 4 --support union --seconds 2 --conflicts 5000 \
  --output-prefix artifacts/my-local-patch
```

`UNSAT` applies only to the encoded frozen neighborhood. `UNKNOWN` means that
the resource limit prevented a decision. Every `SAT` model must pass the
independent complete tensor verifier before it is saved as a candidate.

## Tensor and algorithm convention

All factors have 25 row-major coordinates. The trace tensor is

\[
T_{5i+j,\,5j+k,\,5k+i}=1\quad(0\le i,j,k<5),
\]

with all other coefficients zero. It has shape 25×25×25 and 125 nonzero
entries. A certificate contains vectors `u`, `v`, `w` for each product:

\[
p_r=\left(\sum_{ij}u_{r,5i+j}A_{ij}\right)
    \left(\sum_{jk}v_{r,5j+k}B_{jk}\right),\qquad
C_{ik}=\sum_r w_{r,5k+i}p_r.
\]

The third factor uses **transposed output coordinates**. The requested term
count is an upper bound on tensor rank; minimizing additions or actual runtime
is a separate optimization problem.

## Search partition

* **Exact flip graph:** start from an exact decomposition, perform F₂ 2→2
  flips and 2→3 expansions, cancel duplicate terms and merge terms sharing two
  factors. Every accepted identity preserves the tensor. Occasional expansions
  and archive restarts allow escape from fixed-rank plateaus.
* **Cyclic subspace:** perform moves on whole C₃ orbits under
  `(u,v,w) → (v,w,u)`. Its term count is `fixed_cubes + 3*three_cycles`.
  This exploits cyclic invariance of `tr(ABC)` but restricts the admissible
  decompositions; it can exclude the best solutions. The published baseline
  need not be cyclic, so this branch uses an explicitly cyclic seed.
* **Fixed-rank residual searches:** drop terms to 94 slots, then minimize the
  exact Hamming residual over all 15,625 tensor coefficients using coordinate
  descent and GF₂ elimination proposals. For binary tensors the squared
  Euclidean residual of the canonical mismatch vector equals this Hamming
  residual. Inconsistent linear systems supply proposals only; their complete
  residual is measured before acceptance. A nonzero residual is a failed
  candidate, even if random tests happen to pass.

## Run

Use Python 3.12. Flip/ALS searches and verification use the standard library;
SAT solver tests need the separate optional SAT dependency. The published
AlphaTensor importer and `.npy` export need NumPy:

```sh
python3 -m pip install -r requirements-research.txt
python3 scripts/init_tensor.py
python3 -m unittest discover -s tests -v
```

Run from this checkout; an additional Git worktree is unnecessary.

```sh
# Continue the exact 95-product checkpoint toward the target of 94.
python3 -m mmsearch.search --initial artifacts/flip-search-seed0.json \
  --rank 94 --seed 2 --steps 1000000 --seconds 120 \
  --output artifacts/next-flip.json

# Search only cyclic decompositions from the cyclic Strassen seed.
python3 -m mmsearch.search --initial artifacts/cyclic-strassen110.json \
  --cyclic --rank 94 --seed 2 --steps 1000000 --seconds 60 \
  --output artifacts/next-cyclic.json

# Fixed-rank coordinate/ALS search. Exit 1 means exact verification failed.
python3 -m mmsearch.als --input artifacts/als_rank94.json \
  --rank 94 --seed 2 --seconds 120 --output artifacts/next-als.json
```

Wall-clock budgets make iteration counts machine-dependent. Fixed step counts
with sufficient time and a seed support reproducible flip trajectories. These
are bounded local heuristics, not a claim to replicate AlphaTensor training or
to exhaust Brent's equations.

## Verification and formal proof

Each emitted search checkpoint has an independent `.verification.json` report
and a standalone `.verify.py` script. Run a verifier explicitly; the flip CLI
returns successfully when it writes a checkpoint, regardless of target rank.

```sh
python3 -m mmsearch.verify artifacts/flip-search-seed0.json --random-trials 128
python3 artifacts/als_rank94.verify.py artifacts/als_rank94.json
```

The verifier checks **every coefficient**, including all expected zeros, with
exact integer arithmetic followed by reduction in F₂. It separately reports
literal integer equality. Random matrix products are supplemental checks.

`lean/Certificate.lean` proves that exact coefficient equality implies equality
of the bilinear algorithm and tensor contraction, then that contraction of the
5×5 target equals standard matrix multiplication for all input matrices over
F₂ (Bool with xor/and). A generated explicit certificate must discharge the
coefficient premise before this becomes a proof of a particular algorithm.
No rank-94 proof is asserted by the general theorem. See
[Lean instructions](lean/README.md) for installation, export and compilation.

## Evidence and provenance

See [the run report](research/RESULTS.md) for completed searches and proof
status. The starting rank-96 data is a published AlphaTensor decomposition,
not a discovery here; [source, hash and attribution](research/ALPHATENSOR_SOURCE.md)
document its CC-BY-4.0 provenance. Descendant flip checkpoints derive from it.
Meeting a numerical threshold alone would still require a literature review
before making a novelty claim. No comparison against the latest global record
is established by these runs.
