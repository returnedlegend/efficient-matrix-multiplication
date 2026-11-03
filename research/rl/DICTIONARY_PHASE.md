# One bounded dictionary-freeze and SAT phase

`scripts/run_campaign_dictionary_phase.py` prepares a finite dictionary and then
runs the existing exact GF2 preprocessing/subset-SAT driver within one total
wall budget. It is intended to inherit the queued job's CPU affinity and native
XOR dependency `PYTHONPATH`. It does not alter those settings or launch a shell.

```sh
python scripts/run_campaign_dictionary_phase.py \
  --output-dir PATH/new-phase --seconds 900 \
  --candidate artifacts/km93_f2.json \
  --candidate PATH/alphaevolve93_f2.json \
  --candidate-dir PATH/ae-native1/verified \
  --candidate-dir PATH/fixed2-1/verified \
  --extra-dictionary PATH/old-dictionary.json
```

Only immediate `*.json` files at least 30 seconds old are selected from each
directory, reducing the chance of reading a concurrently created exclusive
certificate before its writer finishes. `--minimum-age` changes that threshold.
Explicit `--candidate` files bypass the age threshold. Manifests and verification
reports should not be placed in selected certificate directories. The freezer
rejects any selected malformed or inexact certificate before SAT can start.

Extra dictionary arguments may repeat. Each JSON array of nonzero 25-bit mask
triples is validated and copied with its original checksum, then the sorted
column union is passed to the freezer. No complete algorithm is claimed for
these extra columns.

The phase calls `freeze_campaign_dictionary.py` with the selected explicit file
list. On success it invokes `campaign_dictionary_preprocessed.py` using the
frozen dictionary, minimum-rank baseline, and source-pool manifest. The default
limits are 900 total wall seconds, 1536 MB solver memory, 100 million conflicts,
and a five-second known-baseline feasibility control. The solver receives only
the positive remaining wall budget after all preparation and freezing. It is
never launched when freezing fails or consumes the deadline.

`progress.json` exposes commands and stage status while the phase runs. Final
`manifest.json` records selections, young-file exclusions, extra-input hashes,
code hashes, exact argument arrays, timeouts, and exit codes. `result.json`
records overall status and the solver result checksum. Child stages run in an
owned process group; interruption or timeout terminates that group, with a
short shutdown allowance. Output must be a new directory; no earlier artifact
is deleted or replaced. `frozen/` and `solve/` retain their respective workflows'
full provenance and exact verification outputs.

An UNSAT result applies to the frozen finite dictionary and encoded rank bound.
It is not global nonexistence evidence. Mock tests check sequencing, age and
directory selection, remaining-budget propagation, exhausted-budget refusal,
and freezer-failure refusal without starting a solver:

```sh
python -m unittest tests.test_run_campaign_dictionary_phase
```
