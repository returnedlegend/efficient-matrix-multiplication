# DeepMind dm_env API adapter

`mmsearch.dm_tensor_env.DmTensorEnv` uses the official `dm-env` 1.6 Python
package to expose the exact algebraic operator controller through DeepMind's
environment API. This integration uses the API; it does not reproduce
AlphaTensor's original environment, model, or training procedure.

```python
from mmsearch.dm_tensor_env import DmTensorEnv
from mmsearch.rl_search import OperatorController, TinyActorCritic
from mmsearch.search import naive_terms

policy = TinyActorCritic(seed=0)
env = DmTensorEnv(lambda: OperatorController(
    naive_terms(2), n=2, target_rank=7, policy=policy, seed=0))
timestep = env.reset()  # FIRST, exact zero reward, fresh search state
timestep = env.step(5) # Discrete operator index, as listed in ACTIONS
```

The action specification is `DiscreteArray(len(ACTIONS), int32)`. Available
actions also depend on the controller's current action mask; masked actions,
floating indices, booleans, and out-of-range indices raise `ValueError`.
Observations are detached `(18,)` float64 controller feature arrays. Float
features describe integer-bit decompositions; certificate coefficients remain
strict integer bits. `last_transition` exposes the controller's research event
metadata, including terminal verification and certificate checksum when found.

`step` returns MID transitions until the controller reports a terminal state
and an independently exhaustive certificate check confirms the target rank.
Only that verified condition returns LAST. A failed verification raises an
error. After LAST, stepping raises an error until the caller explicitly resets.
There is no automatic reset that can hide a discovered target.

Verified terminal certificates, reports, and SHA-256 checksums are retained as
immutable serialized records internally across resets. `terminal_artifacts`
returns detached JSON records for a driver to write to its artifact store;
the adapter itself does not create files. The driver can serialize `candidate`
using sorted compact JSON plus one newline to reproduce `candidate_sha256`.

The factory must return a new controller on each reset. It may reuse a policy,
as in the example, to retain trained weights and optimizer state while resetting
search state. A factory that creates a new policy also resets learning. Pending
partial controller rollouts belong to the old search episode: callers should
finish or persist those deliberately before resetting early. No controller
checkpoint or native worker implementation is modified by this adapter.

Validation: `python -m unittest tests.test_dm_tensor_env` covers verified rank-7
termination and retention, action/observation contracts, and fresh search state
with a shared trained policy across resets.
