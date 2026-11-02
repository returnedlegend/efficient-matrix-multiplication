# Local rank-94 SAT search from Kauers–Moosbauer 95

The requested exact characteristic-two seed is
`artifacts/km95_f2.json`, from the authors' `555-95-mod2.exp` file. All 15,625
tensor coefficients and 64 supplementary matrix products pass verification.
[KM_SOURCE.md](KM_SOURCE.md) records pinned commits, checksums, and notices.
This seed is distinct from the earlier AlphaTensor-derived rank-95 checkpoint.

## Discrete model

Coefficients must be integers in **{-1,0,1}**. Decimal values (including `1.0`),
booleans, and integers outside this domain are rejected. In characteristic two,
-1 and 1 represent the same field element, so every mutable coefficient is
encoded by one Boolean variable with canonical representatives {0,1}. No
floating-point coefficient optimization is performed. Wall-clock budgets and
elapsed-time measurements do not participate in the algebra.

Starting with 95 products, delete one and leave 94 slots. Choose K of those
slots to mutate and freeze the other 94−K products. Define the residual tensor

\[
S_{abc}=T_{abc}+\sum_{r\text{ frozen}}u_{ra}v_{rb}w_{rc}\quad\text{in }\mathbb F_2.
\]

The Boolean constraints are **all 15,625 equations**

\[
\bigoplus_{r\text{ active}}(u_{ra}\land v_{rb}\land w_{rc})=S_{abc}.
\]

An AND gate uses a Tseitin equivalence; parity is encoded with XOR equivalences
and a final unit clause. Constants are simplified without dropping any
nontrivial equation, including equations for expected zero coefficients.
`union` mode permits coordinates appearing in the active or deleted products;
`full` mode permits all 25 coordinates of each active factor. Frozen products
remain fixed in both modes.

Subsequent projection analysis established that these particular shared-union,
full-coordinate, and compact-image modes have equivalent rank feasibility:
the residual lies in the shared coordinate spaces, and projecting each factor
onto its residual mode image preserves the tensor without increasing product
count. This equivalence relies on identical allowed domains for every mutable
slot and permitting zero products; individual per-product support masks would
not have the same guarantee.

`mmsearch/sat.py` exports DIMACS and a map from primary variables to factor
coordinates. The local solver is **CaDiCaL 1.9.5**, bundled with pinned
`python-sat==1.8.dev24`. Solving runs in a child process with both a conflict
budget and a hard wall-clock limit. SAT models are decoded and checked by the
independent exact tensor verifier before candidate files can be saved.

## First low-compute run

Command: `python3 scripts/local_sat_experiment.py`.

* Exact flip search: **20 seconds, 89,159 accepted moves**, best count 95.
  The saved minimum-rank representative has the original factors in canonical
  order; it is not claimed to be a newly improved scheme. The ordering changes
  tie-breaking for neighborhood selection.
* SAT: **16 patches**, active counts 2–5; 12 union-support and 4 full-support
  problems. Each has a 2-second / 5,000-conflict limit.
* Results: **12 UNSAT, 4 UNKNOWN, 0 SAT**. UNKNOWN reports remain UNKNOWN;
  they are not converted to solver UNSAT results.
* End-to-end measured wall time: approximately **26.27 seconds** on this
  instance. This is a local experiment, not an exhaustive rank-94 search.

Artifacts: `artifacts/km-local-sat/summary.json`, `patch-*.cnf`,
`patch-*.map.json`, `patch-*.result.json`, the seed and exact flip checkpoint,
and the checkpoint's standalone verifier.

## Algebraic pruning

For K mutable products, every matrix flattening of their residual tensor has
rank at most K: each product contributes one rank-one matrix to that
flattening. Exact GF₂ elimination found a flattening rank greater than K in
**all 16 initial neighborhoods**, independently ruling out those frozen local
models. See `artifacts/km-local-sat/flattening_checks.json`. For example, a
five-product patch had residual flattening ranks (6,5,6), so five products
cannot represent it even with unrestricted coordinate supports. This explains
why broader neighborhood selection matters more than increasing those solver
budgets.

`mmsearch/sat_neighborhoods.py` selects overlapping or sampled patches and
rejects this obstruction before building their CNFs. A seeded selection
checked 54 distinct patches in approximately 0.005 seconds: 50 were rejected,
and four passed the necessary bound. Passing it does not guarantee a solution.
The selected patches are recorded in `artifacts/sat_neighborhood_selection.json`.

The four filtered patches (K=5,5,7,8) were then solved with the same 2-second /
5,000-conflict limits. **All four returned UNKNOWN** at their conflict limits;
none produced a candidate. CNFs, variable maps, statistics, and input checksum
are saved under `artifacts/km-filtered-sat/`. Across the two batches, the solver
returned **12 local UNSAT and 8 UNKNOWN results** from 20 attempts. No rank-94
algorithm was found. All searches have stopped.

All **37 tests pass**, including gate truth tables, zero-equation coverage,
domain rejection, exact SAT model verification, solver limits, and exact
flattening-rank pruning.

Reproduce the selection, then solve a listed neighborhood:

```sh
python3 -m mmsearch.sat_neighborhoods --input artifacts/km95_f2.json \
  --attempts 30000 --seconds 30 --seed 0 --output artifacts/selection.json
python3 -m mmsearch.sat --input artifacts/km95_f2.json --rank 94 \
  --drop-term 72 --active-terms 1,5,14,21,65 --support union \
  --seconds 2 --conflicts 5000 --output-prefix artifacts/filtered-example
```

## Scope and published context

There is no global nonexistence result here. A local UNSAT result only rules
out its frozen terms and support constraints. No rank-94 Lean proof is claimed
without a verified SAT candidate. Saved solver outcomes are not independently
checked UNSAT proof traces.

The authors' newer symmetry dataset already contains a **published rank-93 F₂
scheme**, independently checked and retained as `artifacts/km93_f2.json`.
It is reference data, not a discovery or an outcome of this SAT experiment.
The separate integer lift contains ±2 coefficients and is excluded from this
ternary-restricted experiment. See [author dataset provenance](KM_SOURCE.md).
