# Native macro actions for a learning controller

`mmsearch.native_bridge.NativeBridge` exposes exact native flip/plus walks as
short external actions. The bridge executes actions chosen by a separate
controller; it contains no learning policy. Native attempted moves do not count
as policy updates, unique states, or successful rank reductions.

```python
from mmsearch.native_bridge import NativeBridge

bridge = NativeBridge("artifacts/my-campaign/native", cpu_affinity=0,
                      deadline=campaign_monotonic_deadline)
result = bridge.run(candidate, action="explore", seconds=2,
                    seed=12345, target_rank=92)
if result["status"] == "ok":
    next_candidate = result["current_candidate"]
    best_candidate = result["best_candidate"]
```

Input certificates use the repository's dense `field=2`, `dimension=n`, and
`terms=[{"u": [...], "v": [...], "w": [...]}]` format. Dimensions 2 through 5
are supported. Strict integer bits are required. Zero factors are removed and
duplicate triples cancel over F2 before ranking; the canonical input is checked
against all n^6 matrix multiplication coefficients before native execution.

The four named actions have fixed, explainable parameters:

| Action | Plus frequency | Restart frequency | Maximum rank above input | C3 |
| --- | ---: | ---: | ---: | --- |
| `exploit` | 2,000 | 50,000 | 2 | No |
| `explore` | 100 | 200,000 | 8 | No |
| `long_walk` | 500 | 10,000,000 | 5 | No |
| `cyclic` | 250 | 200,000 | 6 | Yes |

Frequencies count native attempted moves. A noncyclic input skips `cyclic`
cleanly. The controller should mask that action unless the current terms form
complete C3 orbits. `max_seconds` is bounded at five seconds, the default action
budget is two seconds, and `step_limit` independently bounds attempted moves.
Native termination has a one-second grace allowance, followed by termination
and a half-second allowance before killing a stalled worker. Final verification
and artifact writes take additional time. An optional monotonic global deadline
caps the native budget, retaining a small shutdown margin.

One native process serves thousands of moves in each macro action. This avoids
a process launch for each individual move without modifying the preserved C++
worker or claiming a persistent native process. Default binary selection uses
`native/flip_worker_cyclic`, compiled from the preserved v2 source; absent
binaries are built locally from `native/flip_worker_v2.cpp` with the installed
C++ compiler. Explicit binary/source paths support reproducible worker choices.
The exact binary and declared source bytes are frozen under SHA-256 names;
independent candidate verification does not rely on the binary's self-report.

Every call creates a unique run directory. The manifest records input checksum,
canonical input checksum, binary/source/bridge/verifier checksums, seed, command,
budgets, and action parameters. After the child exits, **every final best,
current, and archive file** is read, including a target found before the first
poll. Metadata dimensions, budgets, counts, rank, and exactness flags are
checked. Each distinct decomposition undergoes independent exhaustive tensor
verification. Verified dense certificates, verification reports, and checksum
files are written exclusively and made read-only before returning results.
Certificates meeting the requested target are also frozen under `winners/`.
No prior user artifact is replaced.

The result reports `best_essential_rank`, `best_rank`, `current_rank`, native
`attempted_moves`, and exact child `cpu_seconds` measured with `wait4` rather
than inferred from elapsed time. `wall_seconds` measures child launch through
exit; `total_wall_seconds` includes input verification and final draining.
`best_xor_addition_estimate` counts unshared input linear forms plus output
accumulation additions as a secondary metric. It is an estimate, not an
optimized straight-line circuit. Novelty reports newly seen candidate hashes,
new terms, and current/input term-set Jaccard distance. Novelty sets persist
within the bridge instance; controllers resuming a campaign should restore
their own reward/novelty history instead of treating a reconstructed instance
as unexplored search space.

An external actor can reward essential bilinear count first, XOR additions
second, and capped novelty third. Native search is an exact algebraic operator
portfolio, not a reproduction of AlphaTensor's tensor-game action model or
DeepMind's original training procedure.

For one independently verified action:

```sh
python scripts/run_native_strategy.py --input artifacts/km93_f2.json \
  --output-dir artifacts/native-short-demo --action explore \
  --seconds 2 --target-rank 92 --seed 123 --cpu 0
```

Add `--benchmark-python` to compare attempted-move throughput against the
existing Python `flip_search` under the same time budget and broad parameters.
The algorithms use different move implementations and trajectories; the
benchmark is a throughput measurement, not a controlled comparison of solution
quality. Unit coverage runs with `python -m unittest tests.test_native_bridge`.
