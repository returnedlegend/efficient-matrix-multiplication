"""Version 2: explicit known-recovery tasks sharing a record-search policy.

The frozen v1 implementation is imported unchanged. Rewards remain exact-rank
rewards. Recovery is labeled and never reported as a new rank record.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import random
import uuid

import numpy as np
from dm_env import specs

from mmsearch.dm_tensor_env import DmTensorEnv
from mmsearch.rl_search import (ACTIONS, FEATURES, OperatorController, TinyActorCritic,
                               _tuple_tree, _write, canonical_terms, gl_move, term_hash)
from mmsearch.search import _flip, _plus, residual

CONTEXT_FEATURES = FEATURES+2


@dataclass
class NoveltyLedger:
    """Global uniqueness, global cap 25, and per-segment cap 0.25."""
    cap: float = 25.0
    paid: float = 0.0
    seen: set = field(default_factory=set)

    def state(self):
        return {"cap": self.cap, "paid": self.paid, "seen": sorted(self.seen)}

    @classmethod
    def from_state(cls, value):
        if not 0 <= value["paid"] <= value["cap"] <= 25:
            raise ValueError("invalid bounded novelty ledger")
        return cls(value["cap"], value["paid"], set(value["seen"]))


def contextual_policy(policy=None, seed=0):
    """Append two zero-weight context features; old probabilities are preserved."""
    policy = policy or TinyActorCritic(seed)
    rows = policy.params["W"].shape[0]
    if rows not in (FEATURES, CONTEXT_FEATURES):
        raise ValueError("unsupported policy feature count")
    if rows == FEATURES:
        for values in (policy.params, policy.m, policy.s):
            values["W"] = np.concatenate((values["W"], np.zeros((2, policy.hidden))), axis=0)
    # JSON sorts object keys. Restore arithmetic accumulation order as well as
    # values, so resumed gradient norms and clipping are bit reproducible.
    for name in ("params", "m", "s"):
        values = getattr(policy, name)
        setattr(policy, name, {key: values[key] for key in ("W", "b", "P", "p", "V", "v")})
    return policy


def make_recovery_seed(seeds, n, rng, *, max_extra=7, flips=48):
    """Exact plus/flip perturbation of a known seed, with no supplied solution.

    The returned start has 1..max_extra more essential products than the known
    seed. The known solution is retained only as the recovery target/provenance.
    """
    if max_extra < 1 or flips < 0:
        raise ValueError("invalid recovery perturbation budget")
    base = set(rng.choice(seeds))
    rank = len(base)
    for _attempt in range(40):
        terms = gl_move(base, n, rng)
        desired = rank+rng.randint(1, max_extra)
        for _ in range(40):
            if len(terms) >= desired:
                break
            proposed = _plus(terms, rng, False)
            if proposed is not None and len(proposed) <= rank+max_extra:
                terms = proposed
        for _ in range(flips):
            proposed = _flip(terms, rng, False)
            if proposed is not None and rank < len(proposed) <= rank+max_extra:
                terms = proposed
        if rank < len(terms) <= rank+max_extra:
            if residual(terms, n):
                raise AssertionError("recovery perturbation changed exact tensor")
            return terms, {"kind": "KNOWN_RECOVERY", "known_rank": rank,
                           "start_rank": len(terms), "source_term_hash": term_hash(base),
                           "start_term_hash": term_hash(terms), "max_extra": max_extra,
                           "flips": flips, "claim": "recovery of a supplied known bound, not a rank record"}
    raise RuntimeError("could not generate a strictly inflated exact recovery task")


class ContextController(OperatorController):
    def __init__(self, initial_terms, *, task_kind="RECORD_SEARCH", ledger=None,
                 record_rank=None, **kwargs):
        if task_kind not in ("RECORD_SEARCH", "KNOWN_RECOVERY"):
            raise ValueError("unknown task kind")
        self.task_kind = task_kind
        self.record_rank = (kwargs.get("target_rank", 92) if task_kind == "RECORD_SEARCH"
                            else kwargs.get("target_rank", 93)-1) if record_rank is None else record_rank
        if self.record_rank < 1:
            raise ValueError("record rank must be positive")
        self.ledger = ledger or NoveltyLedger()
        self.segment = 0
        self.segment_novelty_paid = 0.0
        kwargs["policy"] = contextual_policy(kwargs.get("policy"), kwargs.get("seed", 0))
        super().__init__(initial_terms, **kwargs)
        self.ledger.seen.update(self.seen)
        self.seen = self.ledger.seen

    def features(self):
        return super().features()+[float(self.task_kind == "KNOWN_RECOVERY"),
                                   max(0, self.ledger.cap-self.ledger.paid)/25.0]

    def new_segment(self):
        # Flush while the current policy still owns the on-policy trajectory.
        self._learn()
        self.segment += 1
        self.segment_novelty_paid = 0.0
        self.novelty_paid = 0.0

    def _learn(self):
        # V1 computes a 1000-point target bonus before calling this method.
        # Remove that bonus from the pending return BEFORE any policy update.
        if (self.task_kind == "KNOWN_RECOVERY" and self.terminal and self.pending
                and len(self.best) > self.record_rank):
            x, mask, action, reward, value = self.pending[-1]
            self.pending[-1] = (x, mask, action, reward-1000.0, value)
        super()._learn()

    def step(self, action=None, *, cost_seconds=None):
        if self.terminal:
            event = super().step(action, cost_seconds=cost_seconds)
            event["task_kind"] = self.task_kind
            return event
        # Parent's local 0.25 cap is additionally bounded by the shared ledger.
        remaining = max(0, self.ledger.cap-self.ledger.paid)
        self.novelty_paid = max(self.novelty_paid, 0.25-remaining)
        before = self.novelty_paid
        event = super().step(action, cost_seconds=cost_seconds)
        bonus = max(0, self.novelty_paid-before)
        self.ledger.paid = min(self.ledger.cap, self.ledger.paid+bonus)
        self.segment_novelty_paid += bonus
        record = event["terminal"] and len(self.best) <= self.record_rank
        if self.task_kind == "KNOWN_RECOVERY" and event["terminal"] and not record:
            event["reward"] -= 1000.0
            self.total_reward -= 1000.0
        event.update(task_kind=self.task_kind, novelty_bonus=bonus,
                     global_novelty_paid=self.ledger.paid, segment=self.segment,
                     record_target_reached=record)
        return event

    def candidate(self):
        value = super().candidate()
        record = self.terminal and len(self.best) <= self.record_rank
        value["metadata"].update(task_kind=self.task_kind, record_target_rank=self.record_rank,
                                  record_target_reached=record,
                                  global_novelty_paid=self.ledger.paid,
                                  segment_novelty_paid=self.segment_novelty_paid)
        if self.task_kind == "KNOWN_RECOVERY" and not record:
            value["metadata"]["status"] = "known_recovery_target" if self.terminal else "known_recovery_checkpoint"
        if record:
            value["metadata"].update(status="verified_target", target_rank=self.record_rank,
                                      recovery_target_rank=self.target_rank if self.task_kind == "KNOWN_RECOVERY" else None)
        value["metadata"]["dm_env_integration"] = "ContextDmEnv actual reset/step API"
        return value

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # The parent's payload has v1 format and no global context. Never
        # publish it at the live checkpoint path, even briefly.
        staged = path.with_name("."+path.name+".private-"+uuid.uuid4().hex)
        try:
            super().save(staged)
            data = json.loads(staged.read_text())
            data["format"] = "mmsearch-context-a2c-v2"
            data["context"] = {"task_kind": self.task_kind, "record_rank": self.record_rank, "segment": self.segment,
                               "segment_novelty_paid": self.segment_novelty_paid,
                               "ledger": self.ledger.state()}
            source = Path(__file__)
            driver = source.resolve().parents[1]/"scripts/train_tensor_curriculum.py"
            for item in (source, driver):
                if item.exists():
                    data["code_hashes"][item.name] = hashlib.sha256(item.read_bytes()).hexdigest()
            # One atomic replace exposes the complete final v2 payload.
            _write(path, data)
        finally:
            staged.unlink(missing_ok=True)
            staged.with_suffix(staged.suffix+".tmp").unlink(missing_ok=True)

    @classmethod
    def load(cls, path, *, native_bridge=None):
        data = json.loads(Path(path).read_text())
        if data["format"] not in ("mmsearch-a2c-v1", "mmsearch-context-a2c-v2") or tuple(data["actions"]) != ACTIONS:
            raise ValueError("unsupported context checkpoint")
        if data.get("native") is not None and native_bridge is None:
            raise ValueError("native checkpoint requires native bridge")
        context = data.get("context", {})
        ledger = NoveltyLedger.from_state(context["ledger"]) if "ledger" in context else NoveltyLedger(
            paid=data["state"]["novelty_paid"], seen=set(data["seen"]))
        obj = cls(data["current"], seed_bank=data["seed_bank"],
                  policy=contextual_policy(TinyActorCritic.from_state(data["policy"])),
                  native_bridge=native_bridge, task_kind=context.get("task_kind", "RECORD_SEARCH"),
                  record_rank=context.get("record_rank", data["config"]["target_rank"]),
                  ledger=ledger, **data["config"])
        for key, value in data["state"].items():
            setattr(obj, key, value)
        obj.best = canonical_terms(data["best"], obj.n)
        obj._verify(obj.best, independent=True)
        if obj.terminal != (len(obj.best) <= obj.target_rank):
            raise ValueError("invalid saved terminal flag")
        obj.archive = [canonical_terms(t, obj.n) for t in data["archive"]]
        for terms in obj.archive:
            obj._verify(terms)
        obj.seen = obj.ledger.seen
        obj.pending = data["pending"]
        # A v1 partial rollout lacks context features. A single zero feature
        # preserves its stored logits; known-recovery flag was false there.
        for sample in obj.pending:
            if len(sample[0]) == FEATURES:
                sample[0].extend([0.0, max(0, ledger.cap-ledger.paid)/25])
        obj.rng.setstate(_tuple_tree(data["rng"]))
        obj.segment = context.get("segment", 0)
        obj.segment_novelty_paid = context.get("segment_novelty_paid", obj.novelty_paid)
        return obj


class ContextDmEnv(DmTensorEnv):
    """Actual dm_env steps with explicit task-context observations."""
    def observation_spec(self):
        return specs.Array((CONTEXT_FEATURES,), dtype=np.float64, name="contextual_controller_features")


def sample_action(controller):
    mask = controller.mask()
    probabilities = controller.policy.forward(controller.features(), mask)[0]
    if controller.control == "random":
        probabilities = np.asarray(mask, dtype=float)/sum(mask)
    return min(len(ACTIONS)-1, int(np.searchsorted(np.cumsum(probabilities), controller.rng.random(), side="right")))
