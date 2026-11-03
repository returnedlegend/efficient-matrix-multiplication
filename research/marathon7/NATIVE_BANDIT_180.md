# Eight bounded native epochs with online bandit updates

This branch updates a small online bandit policy between native exploration
epochs. It performs no gradient training. The frozen module's short header
"no training" should be read with that distinction; its bytes remain frozen.
New raw state hashes measure observed exploration diversity, not mathematical
novelty. A normal timed exploration completion is not a tensor-rank negative.

The root authorized at most eight epochs, individually queued on CPU2 only
after the local fixed-family retirement. Each uses 180 native seconds, a
210-second outer envelope, 768 MiB, the original exact plus-burst binary,
archive cap16, and a 250 MiB aggregate output cap. The final two-second/native
termination reserve and final verification remain inside the outer envelope.
There is no paid compute or automatic budget expansion.

Epoch one used
`artifacts/marathon7_20261103T122417Z/native-bandit7-ready-v4`.
Its manifest SHA256 is
`3b0fe78cb3052b7a07787e9f6038db81a078b7f10fa6baf8dfdafa7092b1e4a2`.
Adapter SHA256 is
`23688ef3fe4b75380ca8f0ec4ed89e4614b2d8e084d67f49513141f8767a5925`;
proposer SHA256 is
`6c4016e69292151398d3a76dd9b94e2adcacf2521df336e3bed55fb9e9eb81cf`.
The earlier v1–v3 packs remain disabled and preserved. Only v4 epoch1 was
appended. The exact native binary, safe target handoff, and cached guard retain
their previously audited `6e7d…`, `37d8…`, and `09ac…` pins.

All 16 initial training roots come from the approved source-anchor manifest
`26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8`.
Preparation replays the complete pinned source/ancestor/registry closure using
the byte-identical audited source loader, and freezes that proof closure. Only
the 16 initial roots are available as native inputs. Every selected source
receives both complete 15,625-entry verifiers and separate freshness barriers.
Heldout/evaluation or unknown ancestor flags, changed bytes/identities, and a
cyclic arm on an incomplete cyclic source all reject before a native launch.

The frozen comparison contains 2,811 rank93 canonical hashes and 2,547 atoms
from those roots and all six earlier profile runs. Earlier raw states are
conservatively excluded from rewards without asserting that every raw state
already received both full verifiers. Subsequent checkpoints also exclude all
previously observed rank93 raw hashes, including unsampled ones. Only freshly
double-verified selected samples grow rewarded atom coverage.

| Arm | Native mode | K | Reduction dwell | Plus cadence |
|---|---|---:|---:|---:|
| 0 | cyclic C3 | 1 | 0 | 2,000 |
| 1 | cyclic C3 | 4 | 128 | 20,000 |
| 2 | cyclic C3 | 4 | 0 | 200,000 |
| 3 | unrestricted | 1 | 128 | 2,000 |
| 4 | unrestricted | 4 | 128 | 200,000 |
| 5 | unrestricted | 4 | 0 | 20,000 |

Epochs1 and5 reserve cyclic exploration using arms0 and2, ensuring at least
25% exploration across the eight authorized epochs. Other epochs favor arms3
and4, which were the efficient unrestricted profiles in the initial evidence;
arm5 also receives a final untried opportunity. A source context is drawn
before arm selection. Reward UCB combines global and context-specific rewards;
it never chooses by raw CPU rate. Source identities, fresh seeds, context,
counts, reward sums and the complete RNG state are saved, without a causal or
superiority claim across the confounded settings.

At most32 new rank93 samples per epoch are selected in deterministic hash order.
Each must match its raw snapshot/hash and pass both full verifiers across
freshness barriers. Candidate/proof bytes remain hidden. The bounded reward is
`0.5 * new_verified_states / 32 + 0.5 * min(new_atoms, 512) / 512`.
A fresh rank <=92 candidate dominates, uses the unchanged strict target handoff,
and stops the series for the global record guard. No local WINNER is written.

Continuation requires native exit0, complete declared native elapsed budget,
no timeout/interruption/native signal stop, exact bound telemetry, both final
full verifiers, all reward checks, and a fresh checkpoint publication. A late
checkpoint rolls back to hidden raw. UNKNOWN/error/malformed evidence stops
without updating policy or treating the failed native run as a negative.
The eighth checkpoint cannot prepare a ninth epoch. The runner queues one job
at a time from an exact previous checkpoint hash.

Nine new controls plus the seven portfolio and four baseline controls passed
in the final frozen runtime:20 controls, no skips. These cover deterministic
restart and exploration allocation, eligible source bytes, exact rewards and
frozen/observed exclusions, late sampling/checkpoint rollback, premature or
signalled native exits, output holds, and real tiny early/late target returns.
The actual strict six-key queue preview and fresh global/resource checks passed.
The root independently reviewed the core source/command/reward/checkpoint and
operations logic; the final conservative exclusion and graceful-stop checks
are covered by the updated controls. No second approval pause was introduced.

Local explicitly released CPU2 after the final launcher reaped and the complete
111,605-case finite-family retirement succeeded. The first queue receipt
committed at2026-11-03T16:07:49.736845Z. Wrapper39570/native39571 were observed
on CPU2 at nice19, with fresh seed8476781491151793479 and approved source2.
This is a launch observation; outcomes and policy changes are recorded in each
epoch's `outcome.json` and immutable `checkpoint.json` after completion.

Epochs2–8 use the frozen v5 runtime at `native-bandit7-ready-v5`, manifest
`33efd2afe53a71584eea107dc3b0a6e252ee6668579e91e00ded4f816696c41a`.
It fixes the independent review's material disk-budget issue by forcing scans
at non-loop barriers and reserving exact pending bytes for reward groups,
native summaries, checkpoints and final outcomes. The exact epoch1 checkpoint
`108a0dca9908cca9e83c2758561e0835d59a4536266d5b1484e426b8e38c1246`
was carried into v5 without resetting counts, context rewards, RNG state,
accepted or observed hashes, atom coverage or seeds. Only the runtime manifest
binding and explicit migration provenance changed. The new initial checkpoint
is `1ab57006e7f5cb78ffa3008ebcc7edbf1a61b2d956a047954f85cb2347a8f0a2`.

The root allocated an additional aggregate4KiB solely for a compact final
error/stop record, preserving frozen v5 rather than another migration. Normal
output remains bounded by250MiB; the global4-core/8GiB limits are unchanged.
The exact external decision is
`native-bandit7-v5-root-final-metadata-allowance.json`.

The frozen v5 runtime passed24 targeted controls:11 bandit,2 controller,7
portfolio and4 baseline. Those current controls are separate from the earlier
M4 frozen source snapshot's1,128-test regression. Root one-time review accepted
the controller's fresh guards, exact queue argv/checkpoint chain, epoch8 cap
and UNKNOWN halt. The fixed controller queues one job at a time using the
existing append helper, waits for terminal reaping and a verified outcome,
then checks the exact next checkpoint. It performs no ordinary-epoch approval
loop. It is running from `native-bandit7-controller-v5` with its request,
proposal and receipt chain preserved; the log is adjacent to that directory.

Epoch1 completed with32 newly double-verified rank93 samples, no new atoms,
and reward0.5. Epoch2 completed with32 verified samples,13 new atoms, and
reward0.5126953125. Neither emitted a target or stopped a guard. Their aggregate
evidence is `native-bandit7-evidence-e01-e02.json`; later epoch outcomes are
still open. The policy makes online count/reward updates, without gradient
training or a mathematical novelty claim.
