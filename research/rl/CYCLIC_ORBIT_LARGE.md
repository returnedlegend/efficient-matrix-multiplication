# Size-guarded C3 repair with 8–10 old orbits

This separate branch expands the orbit-local neighborhood to k=8,9,10 complete
old three-cycles, replacing them with at most k−1 new orbit slots. For a verified
cyclic rank-95 parent the nominal global cap remains 92. The initial small-patch
pilot's bounded snapshot had many necessary-bound rejections and UNKNOWN cases;
larger unions permit more factors to move together, without implying that they
contain a successful repair.

`mmsearch/cyclic_orbit_large.py` extends only selection and repair preparation.
It calls the unchanged frozen `cyclic_orbit_sat.build_patch_problem` for the
exact shared-E C3 encoder and reuses its model/global verification. Zeros and
fixed-cube slots remain allowed; symmetry remains U≤lexV and U≤lexW only. The
frozen encoder, one-shot CLI, and active small-neighborhood campaign runner are
unchanged.

Before nonlinear encoding, a zero-slot probe obtains the same shared basis,
core, and exact flattening bound. Optional Koszul bounds are compatible with
this core. A necessary bound greater than 3(k−1) yields LOCAL_UNSAT_BOUND. Other
patches receive formula-size and working-memory estimates before gate creation.
The defaults cap 150,000 variables, 600,000 CNF clauses, and 1024 MB estimated
working memory. A guard rejection is **SKIPPED_TOO_LARGE**, never UNSAT. It has
no encoded formula, and its metadata records the estimates, configured limits,
and reasons. Actual encoded variables/clauses are also checked before solving.

For d shared coordinates and m new slots, there are at most m*d^3 shared
three-input AND gates, 3*m*d factor variables, and cyclic parity equations for
(d^3+2*d)/3 independent coordinate orbits. The estimate also includes the exact
upper counts for the lexicographic symmetry auxiliaries. At d=25,m=9 it predicts
142,182 variables, 564,246 CNF clauses, and 5,675 native XOR equations. The RAM
planning estimate is 727 MB, including conservative allowances for Python
clauses/cache, simultaneous JSON serialization, and fork/solver overhead. It is
not measured RAM or a guarantee; the solver retains its actual 1536 MB address
space limit. Guard caps can be reduced through CLI arguments.

`scripts/campaign_cyclic_orbit_sat_large.py` is a separate clone of the tested
restartable portfolio runner with defaults k8..10, 30 solver seconds per patch,
500,000 conflicts, and native-XOR CryptoMiniSat. This variant deliberately accepts
only `--backend CMS` or `cryptominisat`: the estimates assume native XORs and do
not silently undercount a CaDiCaL XOR-to-CNF expansion. Parent verification,
compact events, first-two/latest/SAT full-problem retention, exact global model
verification, immutable winners, two-second cleanup reserve, signal handling,
and journal/RNG/state resume behavior are retained. A fresh directory separates
these larger neighborhoods and budgets from the existing pilot.

```sh
PYTHONPATH=.xor-deps:. taskset -c 3 python scripts/campaign_cyclic_orbit_sat_large.py \
  --seed-dir PATH/completed-fixed2-long1/verified --seed-dir PATH/fixed2-seeds/seeds \
  --output-dir PATH/new-large-orbit-campaign --seconds 600 \
  --k-min 8 --k-max 10 --patch-seconds 30 --backend CMS \
  --conflicts 500000 --memory-mb 1536 --seed 810
```

Optional limits: `--max-variables`, `--max-clauses`, and
`--max-estimated-memory-mb` (the latter cannot exceed `--memory-mb`). Only verified
5x5 cyclic rank-95/two-fixed-cube parents are accepted. Other files are skipped
with counts and no exactness claim.

Four brief CPU-2 tests check estimates against the actual unchanged encoder,
pre-encoding resource rejection without a contradiction/UNSAT claim, a real
planted guarded 2x2 repair with exhaustive global verification, and deterministic
8..10 selection plus rejection of the old CLI k range. No expensive 5x5 solve
was performed while preparing this branch:

```sh
PYTHONPATH=.xor-deps:. python -m unittest tests.test_cyclic_orbit_large
```
