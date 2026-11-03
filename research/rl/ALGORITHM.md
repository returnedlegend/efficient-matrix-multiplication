# Exact F2 operator actor-critic

This is a small, state-conditioned reinforcement-learning controller for exact
matrix-multiplication decompositions. It learns which search macro to execute.
It is not a reproduction of AlphaTensor's neural tensor-construction agent, its
training run, or its results. The official AlphaTensor release supplies
algorithms and related evaluation/recombination code, rather than the original
training implementation and trained policy weights. This experiment makes no
claim of a new rank until an independently verified certificate is produced.

## State and exact environment

`mmsearch/rl_search.py` represents every factor by a Python integer bit mask.
The tensor is the trace-convention multiplication tensor over **F2**. Zero
products are removed; identical triples cancel in pairs over F2 before rank is
counted. The reported product count is the number of nonzero remaining
rank-one products, an upper bound on tensor rank. An F2 certificate does not
establish an integer lift or a real-arithmetic multiplication algorithm.

Every accepted or rejected proposed transition receives a full exact bit-tensor
coefficient check. Initial states, rank improvements, periodic checkpoints,
persisted checkpoints, and final candidates additionally use the independent
coefficient enumerator in `mmsearch/verify.py`. These checks include expected
zero coefficients. A float reconstruction loss is never a success criterion.

The actor consumes 18 features: constant, dimension, current rank, all-time
best rank, excursion above best, target gap, factor density, shared single
factor pair count, shared double factor pair count, largest sharing bucket,
stagnation, visited-set size, novelty budget left, cyclic closure, restart
archive size, previous plus context, previous restart context, and time-step
progress. Rank features are normalized by the naive product count; other
features have explicit scales or bounds in `features()`.

The discrete actions are flip batches of 8/32/128, plus followed by 16/64
relaxation steps, greedy reduction, restart from a verified seed/archive,
one GL(n,F2)^3 basis transvection, cyclic flip32, and cyclic plus16. Optional
native actions select the verified bridge's `exploit`, `explore`, `long_walk`,
and `cyclic` profiles. The cyclic actions are masked unless the current term
set contains complete C3 orbits. Native execution takes at most five requested
seconds per action. `--native-only` masks all ten Python actions and retains
only the three or four available native actions. Native attempts run in a subprocess and
have their CPU time included in the controller's reward cost.
The trainer defaults to eight representative native archive states per action;
`--native-archive-size` accepts 1 through 64 to keep artifact growth bounded.

GL transformations are known equivalences used for diversification. Distinct
sorted-term hashes indicate different representations only; they do not
certify inequivalence or a mathematically novel multiplication strategy.

## Trainable policy and update

The NumPy network is `18 -> 32 tanh -> 14 softmax logits`, with a linear value
head from the same hidden layer. It uses hand-derived gradients, tested
against central finite differences for every parameter, and Adam with
learning rate 0.001, betas (0.9, 0.999), epsilon 1e-8, global gradient norm cap
5, and entropy coefficient 0.015. Floats occur only in policy features,
weights, gradients, and reward bookkeeping. Certificate coefficients remain
exact binary integers throughout.

The on-policy rollout length is 16 and discount is 0.995. At an update, rewards
are scaled by 1/100, backward bootstrapped returns are computed with the critic
value of the final state, and each actor advantage is `return - stored_value`.
The actor minimizes `-advantage * log probability(action) - 0.015 * entropy`.
The critic minimizes half the squared return error; the advantage and return
are fixed targets during the gradient calculation. Terminal trajectories
bootstrap zero. Partial rollouts survive checkpoints; saving does not force an
extra update. The state-conditioned network and trajectory returns distinguish
this from a random operator portfolio or a stateless bandit.

## Reward and anti-farming rules

For a macro transition, raw reward is:

```
100 * newly_verified_all_time_best_product_reduction
+ 1000 if the verified target is reached
+ novelty_bonus
- min(0.05, 0.01 * measured_CPU_seconds)
- 0.001 * excursion_above_best
- 0.0001 * min(100, consecutive_stagnant_actions)
- 0.01 if rejected for excessive rank
```

The novelty bonus is at most 0.001 for a previously unseen exact term-set hash,
with a **lifetime cap of 0.25** for the entire controller, including restarts
and resume. This is smaller than one percent of the reward for removing one
product. Returning from an inflated rank to an already observed best does not
earn rank reward. Best rank is monotone. Novelty's visited set and consumed
budget survive resume. The default excursion cap is six products above best.

For the 5x5 campaign the target is **at most 92 products**, improving on a
supplied verified 93-product seed. Such a success is independently verified,
then the controller is terminal: further calls return zero reward without
changing terms, policy, counters, or rank. The checkpoint and certificate
must be preserved by the campaign's result-freezing process.

## Curriculum and controls

Before a fresh main run, the CLI trains the same network weights on repeated
2x2 naive rank-8 to target-7 episodes and, every third episode, 3x3 naive
rank-27 to target-at-most-26 episodes. It supplies no rank-7 certificate.
Curriculum uses up to five seconds by default and counts against `--seconds`.
It writes a separate curriculum report. Success on these small tasks is a
control for the search and learning implementation; it does not establish a
held-out advantage over random search or transfer to 5x5.

`--frozen` samples the state-conditioned policy without updating its weights.
`--control random` samples uniformly from available actions and disables
updates. For a fair comparison, start learned, frozen, and random trials from
copies of the same warmed checkpoint and initial seed portfolio, give them
equal measured CPU budgets, and report rank trajectories, verified target
hits, action distributions, and seed identities. Starting separate fresh runs
with and without curriculum is not such a comparison. No measured advantage
is asserted merely because policy parameters changed or a small task solved.

## Running and resuming

From the repository root, for example:

```sh
taskset -c 2 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python scripts/train_tensor_agent.py \
  --initial path/to/verified-rank93.json --dimension 5 --rank 92 \
  --seed 17 --cpu 2 --seconds 300 --native-only --native-seconds 2 \
  --checkpoint artifacts/rl/agent.json --output artifacts/rl/best.json \
  --events artifacts/rl/events.jsonl
```

Repeat `--initial` to supply a diverse verified seed bank. The initial best is
the smallest supplied seed. Explicit invalid seeds are rejected. The CLI
sets all BLAS/OpenMP thread counts to one before loading NumPy, and `--cpu`
pins both the Python process and native children. The campaign manager owns
the global deadline and resource allocation; this CLI starts no background
workers and performs no network or paid-compute calls.

Resume with `--resume artifacts/rl/agent.json`, the desired output/checkpoint
paths, and `--native` when resuming a native-enabled checkpoint. Saved
hyperparameters, model parameters, Adam moments/update count, Python RNG,
partial rollout, exact current/best/archive/seed terms, seed source hashes,
seen hashes, consumed novelty budget, history, and counters are restored.
Source-code SHA256 hashes and native binary/source hashes accompany saves.
The bridge separately freezes native inputs, sources, binaries, outputs, and
independent verification records. Runtime CPU timing is naturally variable;
tests supply `cost_seconds=0` and prove identical resumed actions, rewards,
model/optimizer parameters, RNG, and term states under fixed step budgets.

To create an identical warmed starting checkpoint for A/B trials, use the
same repeated `--initial` seed arguments and `--native-only`, add
`--initialize-only --pretrain-seconds 5 --seconds 10`, and save once. This
performs curriculum training and verifies/saves the main task's initial state
without taking a main-task action. Resume that checkpoint separately for the
learned policy, `--frozen`, and `--control random`; use separate output,
checkpoint, native-output, and event paths for each trial. The saved
`native_only` setting restores the same available native action family.

SIGINT/SIGTERM requests a clean stop after the current bounded action; the
finally block emits the checkpoint, best certificate, independent report,
and standalone verifier. The main budget can overshoot by one bounded action
plus final checkpoint verification. Campaign deadline guards should reserve
that margin. The candidate JSON explicitly labels a verified exact seed that
has not reached the target as `research_checkpoint`.

## Tests

```sh
taskset -c 2 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m unittest tests.test_rl_search -v
```

Coverage includes all manual-gradient finite differences, state dependence
and probability updates, exact Adam/RNG/partial-rollout resume, exact
Python-macro and GL identities at dimensions 2/3/5, zero/duplicate
canonicalization, invalid candidate rejection, a planted reducible exact
decomposition, reward-farming prevention and novelty cap, real naive 2x2
rank-8 to verified rank-7 search, terminal freeze, native-result integration,
and frozen/random parameter controls. Live native CLI smoke tests also exercise
the bridge's real executable; their output is campaign evidence rather than a
claim of a new rank.
