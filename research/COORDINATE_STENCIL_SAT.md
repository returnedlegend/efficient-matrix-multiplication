# Exact coordinatewise algorithm recombination

`mmsearch/coordinate_stencil_sat.py` implements a finite exact family strictly
contained in the unrestricted free-factor family. No global tensor-rank lower
bound or literature novelty claim follows from these experiments.

Choose a mode orientation `uv`, `vw`, or `wu`. Independently verify every full
input algorithm over F2, canonicalize its terms, and XOR-merge the free factors
of equal fixed-factor pairs. Make one global sorted dictionary of these pairs.
For every source and each free coordinate, its stencil is the set of pairs
whose merged free vector has that bit. Each source stencil reconstructs the
same flattened tensor column. Consequently one can select an arbitrary source
independently for every coordinate and obtain an exact full decomposition.
The number of products is the cardinality of the selected stencils' union.

Equal stencils are deduplicated per coordinate with all source indices retained.
If stencil A is a proper subset of B for the same coordinate, B can be removed:
both reconstruct the same column, and replacing B with A never increases any
selected union. Every original stencil has an audited retained subset. Every
source therefore embeds with at most its original merged product count.

The cheap scan uses these dominance-mapped source baselines. For coordinate c,
remove exactly the groups used only by c and OR every retained alternative
stencil. This exhausts every single-coordinate swap from each selected
baseline. These mapped neighborhoods attain a rank no worse than the
corresponding original-source single-coordinate swaps, because every unchanged
column was replaced by a subset. At most 512 baselines and 120 seconds per
scan call are allowed; the runner also enforces a shared wall budget. Scored
unions are not reported as independently checked certificates. Every retained
record is fully verified at all 15,625 coefficients and by 16 direct random
matrix products before export.

The optional pure-CNF model has exactly one choice per coordinate, choice-to-
active-group implications, optional reverse group implications, and a bound on
the number of active groups. Both exactly-one and at-most cardinalities use
PySAT sequential counters. It uses single-threaded CaDiCaL 1.9.5; it needs no
XOR backend. The runner first fixes a verified source embedding as a feasibility
control, then solves the target bound. Every returned model is checked for
completeness, Boolean types, all clauses, exactly-one choices, active-group union,
rank, fixed control assumptions, and independently reconstructed full tensor.

The solver runs in a child with address-space and CPU limits. The parent waits
with a hard wall limit, then terminates/kills and reaps the child. A private
result file is read only after child completion, avoiding partial large-model
pipe reads. Callers reserve two seconds for cleanup. `UNSAT` is restricted to
the frozen source-column family. Timeout is `UNKNOWN`; failures are `ERROR`.
Formula memory is conservatively estimated before construction; solver RSS is
additional. Formula CNF, variable maps, complete models, formula hashes, choices,
pair dictionaries, all raw sources, verification reports, provenance, parameters,
code snapshots, and status results are exported.

The campaign CLI only accepts strict n=5/F2 certificates and target bounds at
most 92. General dimensions are available through the module for tests. A
verified <=93 source must be included. `--baseline` identifies a particular
source to embed and control; the best dominance embedding is also retained.
The first verified n=5/F2 candidate with at most 92 products creates immutable
`WINNER.json`, its verification report, and a standalone verifier. Later
records have separate names. Rank-93 parents and mixes carry no novelty claim.

The default is prepare only; this creates no CNF and launches no solver:

```bash
taskset -c 2 python scripts/campaign_coordinate_stencil_sat.py \
  --candidate-dir artifacts/campaign/public-seeds/fastmatrix-f2/seeds \
  --input artifacts/km93_f2.json \
  --input artifacts/rl_campaign_20261102T210735Z/public/alphaevolve93_f2.json \
  --baseline artifacts/km93_f2.json \
  --orientation all --mode prepare --seconds 20 --outdir NEW_PREPARE_DIRECTORY
```

After a campaign budget is registered, use the same inputs and a new output
directory with `--orientation uv --mode scan --seconds 120` for the cheap scan,
or `--orientation uv --mode sat --seconds 120 --control-seconds 5` for CNF.
Replace `uv` with another orientation as desired. Each run freezes its own
code; its `code/scripts/campaign_coordinate_stencil_sat.py` can be invoked
directly to use that frozen implementation. No campaign search is launched as
part of preparation or tests.

```bash
taskset -c 2 python -m unittest tests.test_coordinate_stencil_sat -v
```

The 11 tests cover exact arbitrary column assembly in all three modes;
duplicate/dominance provenance; strict source validation before deduplication;
same-pair cancellation; planted n=2 parent mixes recovering rank seven; exact
single-coordinate scanning against brute force; formula caps; tiny CNF SAT
controls and family-restricted UNSAT; corrupted/incomplete model rejection;
hard timeout and process reaping; and strict campaign dimensions/JSON handling.

The initial public-corpus prepare check found 308 distinct exact sources, 305
pair groups and 1,364 retained stencil choices in each orientation, with a
32 MiB conservative Python formula estimate per target. Every embedded baseline
still had 93 products. Preparation did not find a <=92 candidate and did not run
a search or 5x5 SAT solve.
