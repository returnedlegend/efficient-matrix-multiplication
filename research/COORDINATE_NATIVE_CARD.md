# Native-cardinality coordinate recombination

`mmsearch/coordinate_native_card.py` uses exactly the same finite source-column
family and audited dominance pruning as `coordinate_stencil_sat.py`. It changes
the SAT backend to PySAT Minicard and represents cardinality constraints natively.
No claim about improved search success follows without an experiment. An old
CNF timeout provides no UNSAT evidence for either representation.

There is one Boolean x per coordinate/stencil choice and one y per fixed-factor
pair. Each coordinate has an OR clause and a native at-most-one constraint.
Each selected stencil implies all its pair indicators. Reverse implications
are enabled by default; `--no-reverse-links` disables them. One native at-most
constraint bounds all pair indicators. There are no cardinality auxiliary
variables and no XOR constraints.

Every supplied source is independently checked at all 15,625 tensor entries
before canonical deduplication. All source bytes, raw/canonical hashes, input
provenance, family choices, pruning maps and code are frozen. The rank-93 control
fixes every choice to the same exact baseline embedding and uses native bound93.
The target uses bound92 or lower. Every SAT model is checked for complete Boolean
values, every clause, every native at-most count, exactly-one choices, indicator
consistency, and actual union rank. The decoded decomposition is independently
checked at all 15,625 entries and by 16 direct random matrix multiplications.

The backend runs with one thread in a child with address-space/CPU limits.
The parent enforces a hard wall limit including load and result export, then
terminates/kills and reaps the child. A private result file avoids partial pipe
reads. Two seconds are reserved for cleanup. Minicard availability/load errors
produce ERROR, never UNSAT. All UNSAT claims concern only the frozen finite
coordinate family over F2.

`*.problem.json` contains the complete clauses, native at-most arrays/bounds,
variable mapping, and hashes. `*.problem.clauses.cnf` is explicitly marked as
only the CNF fragment; it omits mandatory native constraints and must never be
treated as the complete problem. SAT exports include the complete model and
its formula/native-constraint hashes. Independently reverified records are
retained separately. The first verified n=5/F2 candidate with <=92 products
creates an immutable WINNER certificate, verification report and standalone
verifier, then the runner stops.

Preparation exports the family and actual target native formulas without
starting any solver. Use a fresh output directory:

```bash
taskset -c 2 python scripts/campaign_coordinate_native_card.py \
  --candidate-dir artifacts/campaign/public-seeds/fastmatrix-f2/seeds \
  --input artifacts/km93_f2.json \
  --input artifacts/rl_campaign_20261102T210735Z/public/alphaevolve93_f2.json \
  --baseline artifacts/km93_f2.json \
  --orientation all --mode prepare --seconds 20 --outdir NEW_PREPARE_DIRECTORY
```

After the root agent reviews this backend and registers a campaign budget,
run the same input options with `--orientation wu --mode sat --seconds 600
--control-seconds 5 --outdir NEW_SOLVE_DIRECTORY`. The other supported solve
orientations are `vw` and `uv`. Invoke the frozen snapshot's
`code/scripts/campaign_coordinate_native_card.py` to use the reviewed code.
The CLI accepts only n=5/F2 sources and targets <=92; module/helper tests permit
small dimensions.

```bash
taskset -c 2 python -m unittest tests.test_coordinate_native_card -v
```

The 11 tests cover full native descriptions and x/y-only variables; explicit
native at-most model mutations; exactly-one and original-union checks; source
controls, exact tensor decoding and restricted UNSAT in all three orientations;
exhaustive agreement with the old CNF on every n=2 categorical selection at
bounds 0,6,7,8,12; optional reverse links; honest missing-backend ERROR;
hard-timeout reaping; runner bound93 control/formula/model exports; strict CLI
dimensions and certificate export revalidation; and unchanged predecessor
implementation hashes.
