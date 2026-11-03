"""State-conditioned on-policy actor-critic over exact F2 search operators.

Floating point is used only for the controller; all decompositions and moves
are integer bit masks. This is a small operator-learning experiment, not an
AlphaTensor reproduction or a claim of a new multiplication rank.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import time

import numpy as np

from mmsearch.search import (_flip, _plus, _reduction, _toggle, decode_candidate,
                             encode_candidate, is_cyclic, residual)
from mmsearch.verify import verify_candidate

ACTIONS = ("flip8", "flip32", "flip128", "plus_relax16", "plus_relax64",
           "reduce", "restart", "gl_basis", "cyclic_flip32", "cyclic_plus16",
           "native_exploit", "native_explore", "native_long_walk", "native_cyclic")
FEATURES = 18


def canonical_terms(terms, n):
    """Remove zero products and cancel duplicate products over F2."""
    result = set()
    for item in terms:
        if len(item) != 3 or any(type(x) is not int or not 0 <= x < 1 << (n*n) for x in item):
            raise ValueError("factors must be three n*n-bit nonnegative integers")
        _toggle(result, tuple(item))
    return result


def term_hash(terms):
    return hashlib.sha256(json.dumps(sorted(terms), separators=(",", ":")).encode()).hexdigest()


def gl_move(terms, n, rng):
    """One known-equivalent GL(n,F2)^3 elementary transvection."""
    if n < 2:
        return set(terms)
    i, j = rng.sample(range(n), 2)
    group = rng.randrange(3)
    def row(mask):
        return mask ^ (((mask >> (i*n)) & ((1 << n)-1)) << (j*n))
    def column(mask):
        return mask ^ sum(((mask >> (r*n+j)) & 1) << (r*n+i) for r in range(n))
    result = set()
    for a, b, c in sorted(terms):
        if group == 0:
            a, c = row(a), column(c)
        elif group == 1:
            a, b = column(a), row(b)
        else:
            b, c = column(b), row(c)
        _toggle(result, (a, b, c))
    return result


class TinyActorCritic:
    """Shared tanh MLP, softmax actor, linear critic, manual gradients and Adam."""
    def __init__(self, seed=0, hidden=32, learning_rate=0.001, entropy=0.015):
        rng = np.random.default_rng(seed)
        self.hidden, self.learning_rate, self.entropy = hidden, learning_rate, entropy
        self.params = {"W": rng.normal(0, 0.15, (FEATURES, hidden)),
                       "b": np.zeros(hidden),
                       "P": rng.normal(0, 0.08, (hidden, len(ACTIONS))),
                       "p": np.zeros(len(ACTIONS)),
                       "V": rng.normal(0, 0.08, hidden), "v": np.zeros(1)}
        self.m = {k: np.zeros_like(v) for k, v in self.params.items()}
        self.s = {k: np.zeros_like(v) for k, v in self.params.items()}
        self.updates = 0

    def forward(self, features, mask):
        x = np.asarray(features, dtype=np.float64)
        h = np.tanh(x @ self.params["W"] + self.params["b"])
        logits = h @ self.params["P"] + self.params["p"]
        logits = np.where(mask, logits, -1e30)
        exp = np.exp(logits - np.max(logits)) * np.asarray(mask)
        probabilities = exp / exp.sum()
        value = float(h @ self.params["V"] + self.params["v"][0])
        return probabilities, value, h

    def loss_grad(self, samples):
        """Samples contain fixed return and actor advantage for gradient checks."""
        grads = {k: np.zeros_like(v) for k, v in self.params.items()}
        loss = 0.0
        for x, mask, action, target, advantage in samples:
            x = np.asarray(x, dtype=np.float64)
            p, value, h = self.forward(x, mask)
            logp = np.log(np.maximum(p, 1e-300))
            entropy = -float(p @ logp)
            error = value - target
            loss += -advantage*logp[action] + 0.5*error*error - self.entropy*entropy
            dlogits = advantage*p
            dlogits[action] -= advantage
            dlogits += self.entropy*p*(logp + entropy)
            grads["P"] += np.outer(h, dlogits)
            grads["p"] += dlogits
            grads["V"] += error*h
            grads["v"][0] += error
            dh = (self.params["P"] @ dlogits + error*self.params["V"]) * (1-h*h)
            grads["W"] += np.outer(x, dh)
            grads["b"] += dh
        count = max(1, len(samples))
        return loss/count, {k: v/count for k, v in grads.items()}

    def learn(self, samples):
        loss, grads = self.loss_grad(samples)
        norm = float(np.sqrt(sum(np.sum(g*g) for g in grads.values())))
        scale = min(1.0, 5.0/max(norm, 1e-12))
        self.updates += 1
        for k, value in self.params.items():
            g = grads[k]*scale
            self.m[k] = 0.9*self.m[k] + 0.1*g
            self.s[k] = 0.999*self.s[k] + 0.001*g*g
            value -= self.learning_rate*(self.m[k]/(1-0.9**self.updates))/(np.sqrt(self.s[k]/(1-0.999**self.updates))+1e-8)
        return {"loss": float(loss), "gradient_norm": norm, "updates": self.updates}

    def state(self):
        return {"hidden": self.hidden, "learning_rate": self.learning_rate,
                "entropy": self.entropy, "updates": self.updates,
                **{name: {k: v.tolist() for k, v in getattr(self, name).items()}
                   for name in ("params", "m", "s")}}

    @classmethod
    def from_state(cls, state):
        obj = cls(hidden=state["hidden"], learning_rate=state["learning_rate"], entropy=state["entropy"])
        for name in ("params", "m", "s"):
            setattr(obj, name, {k: np.asarray(v, dtype=np.float64) for k, v in state[name].items()})
        obj.updates = state["updates"]
        return obj


def _tuple_tree(value):
    return tuple(_tuple_tree(x) for x in value) if isinstance(value, list) else value


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, sort_keys=True) + "\n")
    temporary.replace(path)


class OperatorController:
    """A2C agent whose action chooses an exact multi-step search operator.

    Rank reward is paid only for a new all-time verified best; novelty has a
    lifetime cap, so neither restarts nor rank excursions can farm that reward.
    ``cost_seconds=0`` makes step-budget replay fully deterministic in tests.
    """
    def __init__(self, initial_terms, *, n=5, target_rank=92, seed=0,
                 seed_bank=None, provenance=None, max_extra=6, rollout=16,
                 gamma=0.995, policy=None, checkpoint_every=128,
                 native_bridge=None, native_seconds=2.0, native_only=False,
                 train=True, control="policy"):
        if n < 1 or target_rank < 1 or max_extra < 0 or rollout < 1 or not 0 <= gamma <= 1:
            raise ValueError("invalid controller configuration")
        self.n, self.target_rank, self.seed = n, target_rank, seed
        self.max_extra, self.rollout, self.gamma = max_extra, rollout, gamma
        self.checkpoint_every = checkpoint_every
        if native_seconds <= 0 or native_seconds > 5 or control not in ("policy", "random"):
            raise ValueError("invalid native budget or control")
        self.native_bridge, self.native_seconds, self.native_only = native_bridge, native_seconds, native_only
        self.train, self.control = train and control == "policy", control
        self.last_native = None
        self.rng = random.Random(seed)
        self.policy = policy or TinyActorCritic(seed)
        self.current = canonical_terms(initial_terms, n)
        self._verify(self.current, independent=True)
        self.best = self.current.copy()
        self.seed_bank = [canonical_terms(t, n) for t in (seed_bank or [self.current])]
        for terms in self.seed_bank:
            self._verify(terms, independent=False)
        self.seed_bank = sorted(self.seed_bank, key=lambda t: (len(t), term_hash(t)))
        self.archive = [self.best.copy()]
        self.provenance = provenance or []
        self.initial_rank = len(self.current)
        self.seen = {term_hash(self.current)}
        self.novelty_paid = 0.0
        self.stagnation = self.steps = self.episodes = 0
        self.total_reward = self.cpu_seconds = 0.0
        self.terminal = len(self.best) <= self.target_rank
        self.pending = []
        self.action_counts = [0]*len(ACTIONS)
        self.history = [{"step": 0, "rank": len(self.best)}]
        self.last_learning = None
        self.last_action = -1

    def _verify(self, terms, independent=False):
        if residual(terms, self.n):
            raise ValueError("invalid candidate: exact tensor coefficients do not match")
        if independent and not verify_candidate(encode_candidate(terms, self.n), random_trials=0)["valid"]:
            raise ValueError("independent exact verifier rejected candidate")

    def features(self):
        size = max(1, len(self.current))
        width = self.n*self.n
        single = Counter((axis, t[axis]) for t in sorted(self.current) for axis in range(3))
        double = Counter((axis, tuple(t[j] for j in range(3) if j != axis))
                         for t in sorted(self.current) for axis in range(3))
        sharing = sum(v*(v-1)//2 for v in single.values())
        reducible = sum(v*(v-1)//2 for v in double.values())
        density = sum(v.bit_count() for t in self.current for v in t)/(size*3*width)
        cyclic = is_cyclic(self.current)
        return [1.0, self.n/5, len(self.current)/max(1, self.n**3),
                len(self.best)/max(1, self.n**3),
                (len(self.current)-len(self.best))/max(1, self.max_extra),
                (len(self.best)-self.target_rank)/max(1, self.n**3), density,
                min(1, sharing/(size*size)), min(1, reducible/size),
                max(single.values(), default=0)/size, min(1, self.stagnation/256),
                min(1, len(self.seen)/10000), max(0, 1-self.novelty_paid/0.25),
                float(cyclic), min(1, len(self.archive)/32),
                float(self.last_action in (3, 4, 9)), float(self.last_action == 6),
                min(1, self.steps/100000)]

    def mask(self):
        cyclic = is_cyclic(self.current)
        python = [True]*8 + [cyclic, cyclic]
        if self.native_only and self.native_bridge is not None:
            python = [False]*10
        return python + [self.native_bridge is not None]*3 + [self.native_bridge is not None and cyclic]

    def _relax(self, terms, count, cyclic=False):
        terms = set(terms)
        best = terms.copy()
        for _ in range(count):
            proposed = _reduction(terms, cyclic)
            if proposed is None:
                proposed = _flip(terms, self.rng, cyclic)
            if proposed is not None and len(proposed) <= len(self.best)+self.max_extra:
                terms = proposed
                if len(terms) < len(best):
                    best = terms.copy()
        # Preserve reductions reached inside a macro rather than losing them
        # when later flips revisit a larger state.
        return best if len(best) < len(self.best) else terms

    def propose(self, action):
        current = self.current.copy()
        if action >= 10:
            if self.native_bridge is None:
                raise ValueError("native action needs bridge")
            profile = ("exploit", "explore", "long_walk", "cyclic")[action-10]
            result = self.native_bridge.run(encode_candidate(current, self.n), action=profile,
                                            seconds=self.native_seconds, seed=self.rng.getrandbits(31),
                                            target_rank=self.target_rank)
            self.last_native = result
            if result.get("status") != "ok":
                return current
            best = canonical_terms(decode_candidate(result["best_candidate"], self.n), self.n)
            self._verify(best, independent=True)
            if len(best) < len(self.best):
                return best
            return decode_candidate(result["current_candidate"], self.n)
        if action in (0, 1, 2):
            return self._relax(current, (8, 32, 128)[action])
        if action in (3, 4, 9):
            cyclic = action == 9
            proposed = _plus(current, self.rng, cyclic)
            if proposed is not None and len(proposed) <= len(self.best)+self.max_extra:
                current = proposed
            return self._relax(current, 64 if action == 4 else 16, cyclic)
        if action == 5:
            for _ in range(self.n**3):
                proposed = _reduction(current, False)
                if proposed is None:
                    break
                current = proposed
            return current
        if action == 6:
            choices = self.archive + [t for t in self.seed_bank if len(t) <= len(self.best)+self.max_extra]
            return self.rng.choice(choices).copy()
        if action == 7:
            return gl_move(current, self.n, self.rng)
        if action == 8:
            return self._relax(current, 32, True)
        raise ValueError("unknown action")

    def _learn(self):
        if not self.pending:
            return
        tail = 0.0 if self.terminal else self.policy.forward(self.features(), self.mask())[1]
        samples = []
        for x, mask, action, reward, value in reversed(self.pending):
            tail = reward/100.0 + self.gamma*tail
            samples.append((x, mask, action, tail, tail-value))
        if self.train:
            self.last_learning = self.policy.learn(list(reversed(samples)))
        self.pending = []

    def step(self, action=None, *, cost_seconds=None):
        if self.terminal:
            return {"terminal": True, "rank": len(self.best), "reward": 0.0, "frozen": True}
        x, mask = self.features(), self.mask()
        probabilities, value, _ = self.policy.forward(x, mask)
        if self.control == "random":
            probabilities = np.asarray(mask, dtype=float)/sum(mask)
        if action is None:
            draw = self.rng.random()
            action = int(np.searchsorted(np.cumsum(probabilities), draw, side="right"))
            action = min(action, len(ACTIONS)-1)
        if not 0 <= action < len(ACTIONS) or not mask[action]:
            raise ValueError("action is unavailable in current state")
        started = time.process_time()
        self.last_native = None
        proposed = canonical_terms(self.propose(action), self.n)
        # Full exact bit-tensor check guards every transition, including moves
        # which would subsequently be rejected for excessive rank inflation.
        self._verify(proposed)
        elapsed = time.process_time()-started if cost_seconds is None else cost_seconds
        if cost_seconds is None and self.last_native is not None:
            elapsed += float(self.last_native.get("cpu_seconds", 0.0))
        if elapsed < 0:
            raise ValueError("negative CPU cost")
        self.cpu_seconds += elapsed
        accepted = len(proposed) <= len(self.best)+self.max_extra
        if accepted:
            self.current = proposed
        improvement = max(0, len(self.best)-len(self.current))
        self.steps += 1
        self.stagnation = 0 if improvement else self.stagnation+1
        if improvement:
            self._verify(self.current, independent=True)
            self.best = self.current.copy()
            self.archive = [t for t in self.archive if len(t) <= len(self.best)+self.max_extra]
            self.archive.append(self.best.copy())
            self.history.append({"step": self.steps, "rank": len(self.best)})
        digest = term_hash(self.current)
        novel = digest not in self.seen
        bonus = min(0.001, max(0, 0.25-self.novelty_paid)) if novel else 0.0
        self.novelty_paid += bonus
        self.seen.add(digest)
        # Bounded reservoir stores distinct exact states for diverse restarts.
        if novel and len(self.current) <= len(self.best)+2:
            if len(self.archive) < 32:
                self.archive.append(self.current.copy())
            elif self.rng.random() < 0.1:
                self.archive[self.rng.randrange(1, len(self.archive))] = self.current.copy()
        self.terminal = len(self.best) <= self.target_rank
        reward = (100.0*improvement + (1000.0 if self.terminal else 0.0) + bonus
                  - min(0.05, 0.01*elapsed)
                  - 0.001*max(0, len(self.current)-len(self.best))
                  - 0.0001*min(100, self.stagnation) - (0.01 if not accepted else 0.0))
        self.total_reward += reward
        self.action_counts[action] += 1
        self.last_action = action
        self.pending.append((x, mask, action, reward, value))
        if len(self.pending) >= self.rollout or self.terminal:
            self._learn()
        if self.checkpoint_every > 0 and self.steps % self.checkpoint_every == 0:
            self._verify(self.current, independent=True)
        event = {"step": self.steps, "action": ACTIONS[action], "rank": len(self.current),
                "best_rank": len(self.best), "improvement": improvement,
                "reward": reward, "novel": novel, "accepted": accepted,
                "terminal": self.terminal, "updates": self.policy.updates,
                "action_probability": float(probabilities[action]),
                "policy_entropy": float(-probabilities @ np.log(np.maximum(probabilities, 1e-300))),
                "value": value, "cpu_seconds": elapsed,
                "learning": self.last_learning}
        if self.last_native is not None:
            event["native"] = {k: self.last_native[k] for k in
                               ("status", "run_dir", "attempted_moves", "best_rank", "current_rank", "cpu_seconds", "wall_seconds")
                               if k in self.last_native}
        return event

    def run(self, *, seconds=60, steps=100000, progress=None):
        if seconds < 0 or steps < 0:
            raise ValueError("negative run budget")
        start = time.monotonic()
        for _ in range(steps):
            if self.terminal or time.monotonic()-start >= seconds:
                break
            item = self.step()
            if progress and (item["improvement"] or self.steps % 100 == 0):
                progress(item)
        # Keep partial on-policy rollout in checkpoints for exact resume.
        return self.candidate()

    def candidate(self):
        self._verify(self.best, independent=True)
        return encode_candidate(self.best, self.n, engine="state_conditioned_actor_critic",
                                rank=len(self.best), target_rank=self.target_rank,
                                exact=True, residual_weight=0, target_reached=self.terminal,
                                status="verified_target" if self.terminal else "research_checkpoint",
                                steps=self.steps, seed=self.seed, history=self.history,
                                updates=self.policy.updates, reward=self.total_reward,
                                novelty_paid=self.novelty_paid, distinct_term_sets=len(self.seen),
                                action_counts=dict(zip(ACTIONS, self.action_counts)),
                                provenance=self.provenance, cpu_seconds=self.cpu_seconds,
                                train=self.train, control=self.control,
                                learning=self.last_learning)

    def save(self, path):
        # Full independent checks at every persisted checkpoint.
        self._verify(self.current, independent=True)
        self._verify(self.best, independent=True)
        files = [Path(__file__), Path(__file__).with_name("search.py"), Path(__file__).with_name("verify.py"),
                 Path(__file__).resolve().parents[1]/"scripts/train_tensor_agent.py"]
        native = None
        if self.native_bridge is not None:
            native = {k: str(getattr(self.native_bridge, k)) for k in
                      ("binary_sha256", "source_sha256", "output_dir", "binary") if hasattr(self.native_bridge, k)}
        data = {"format": "mmsearch-a2c-v1", "actions": ACTIONS,
                "code_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                "config": {k: getattr(self, k) for k in ("n", "target_rank", "seed", "max_extra", "rollout", "gamma", "checkpoint_every", "native_seconds", "native_only", "train", "control")},
                "policy": self.policy.state(), "rng": self.rng.getstate(), "native": native,
                "current": sorted(self.current), "best": sorted(self.best),
                "seed_bank": [sorted(t) for t in self.seed_bank],
                "archive": [sorted(t) for t in self.archive],
                "seen": sorted(self.seen), "pending": self.pending,
                "state": {k: getattr(self, k) for k in ("provenance", "initial_rank", "novelty_paid", "stagnation", "steps", "episodes", "total_reward", "cpu_seconds", "terminal", "action_counts", "history", "last_learning", "last_action")}}
        _write(path, data)

    @classmethod
    def load(cls, path, *, native_bridge=None):
        data = json.loads(Path(path).read_text())
        if data["format"] != "mmsearch-a2c-v1" or tuple(data["actions"]) != ACTIONS:
            raise ValueError("unsupported checkpoint format or action vocabulary")
        if data.get("native") is not None and native_bridge is None:
            raise ValueError("native checkpoint requires native_bridge to preserve action availability")
        obj = cls(data["current"], seed_bank=data["seed_bank"], policy=TinyActorCritic.from_state(data["policy"]), native_bridge=native_bridge, **data["config"])
        for k, value in data["state"].items():
            setattr(obj, k, value)
        obj.best = canonical_terms(data["best"], obj.n)
        obj._verify(obj.best, independent=True)
        if obj.terminal != (len(obj.best) <= obj.target_rank):
            raise ValueError("checkpoint terminal flag disagrees with exact best rank")
        obj.archive = [canonical_terms(t, obj.n) for t in data["archive"]]
        for terms in obj.archive:
            obj._verify(terms)
        obj.seen = set(data["seen"])
        obj.pending = data["pending"]
        obj.rng.setstate(_tuple_tree(data["rng"]))
        return obj
