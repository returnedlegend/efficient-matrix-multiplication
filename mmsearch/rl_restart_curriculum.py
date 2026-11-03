"""V4 external main-task restarts, retaining the v3 policy and global state."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import uuid

from mmsearch.native_bridge import canonical_terms as strict_terms
from mmsearch.recovery_pool import checked_terms
from mmsearch.rl_pool_curriculum import PoolRecordController
from mmsearch.rl_search import _write, term_hash

CHECKPOINT_FORMAT = "mmsearch-restart-a2c-v4"
SCHEDULE_FORMAT = "mmsearch-restart-curriculum-schedule-v4"


class RecordSeeds:
    """Independently verify every ordered, immutable F2 restart seed."""
    def __init__(self, paths, *, n=5, known_rank=93):
        self.terms, self.identity = [], []
        for path in paths:
            payload = Path(path).read_bytes()
            value = json.loads(payload)
            if value.get("dimension") != n:
                raise ValueError("record seed dimension mismatch")
            strict_terms(value)  # Strict F2 declaration, no implicit field conversion.
            terms = checked_terms(value, n)
            if len(terms) != known_rank:
                raise ValueError("record seed must have exactly the known essential rank")
            item = {"sha256": hashlib.sha256(payload).hexdigest(),
                    "term_hash": term_hash(terms), "rank": len(terms)}
            if any(item["term_hash"] == old["term_hash"] for old in self.identity):
                raise ValueError("duplicate record restart seed")
            self.terms.append(terms)
            self.identity.append(item)
        if not self.terms:
            raise ValueError("at least one record restart seed is required")


class RestartRecordController(PoolRecordController):
    def __init__(self, initial_terms, *, restart_context=None, **kwargs):
        self.restart_context = copy.deepcopy(restart_context or {})
        super().__init__(initial_terms, **kwargs)

    def bind_restarts(self, seeds, *, interval, record_cpu):
        if not math.isfinite(interval) or interval <= 0 or not math.isfinite(record_cpu) or record_cpu < 0:
            raise ValueError("invalid record restart CPU budget")
        if self.task_kind != "RECORD_SEARCH" or self.target_rank >= len(seeds.terms[0]):
            raise ValueError("record target must be strictly below known restart rank")
        identity = {"seed_order": seeds.identity, "interval_cpu": interval,
                    "dimension": self.n, "known_rank": len(seeds.terms[0])}
        if self.restart_context:
            value = self.restart_context
            if set(value) != set(identity) | {"next_index", "next_cpu", "restarts"}:
                raise ValueError("invalid saved restart state")
            if any(value[key] != expected for key, expected in identity.items()):
                raise ValueError("record restart seed identity/order or interval changed")
            if (type(value["next_index"]) is not int or not 0 <= value["next_index"] < len(seeds.terms)
                    or type(value["restarts"]) is not int or value["restarts"] < 0
                    or value["next_index"] != value["restarts"] % len(seeds.terms)
                    or not isinstance(value["next_cpu"], (int, float))
                    or not math.isfinite(value["next_cpu"]) or value["next_cpu"] < 0
                    or value["next_cpu"] > record_cpu+interval+1e-9):
                raise ValueError("invalid saved restart schedule")
        else:
            # Migration starts with CLI seed zero; later switches spend a full
            # interval of measured main CPU, independent of recovery CPU.
            self.restart_context = dict(identity, next_index=0, next_cpu=record_cpu, restarts=0)
        self.restart_seeds = seeds

    def restart_if_due(self, record_cpu):
        if not math.isfinite(record_cpu) or record_cpu < 0:
            raise ValueError("invalid measured record CPU")
        state = self.restart_context
        if self.terminal or record_cpu < state["next_cpu"]:
            return None
        index = state["next_index"]
        terms = self.restart_seeds.terms[index]
        self._verify(terms, independent=True)
        if len(terms) < len(self.best):
            raise ValueError("external restart must not silently improve global best")
        # Bootstrap/learn from the OLD main state. No rollout may span seeds.
        self._learn()
        previous = term_hash(self.current)
        self.current = terms.copy()
        # Installing a supplied state earns no reward, including novelty.
        self.ledger.seen.add(term_hash(terms))
        self.last_native = None
        state["next_index"] = (index+1) % len(self.restart_seeds.terms)
        state["next_cpu"] = record_cpu+state["interval_cpu"]
        state["restarts"] += 1
        return {"event": "record_restart", "task_kind": "RECORD_SEARCH",
                "restart_index": index, "restart_count": state["restarts"],
                "seed": self.restart_seeds.identity[index], "previous_term_hash": previous,
                "rank": len(self.current), "best_rank": len(self.best), "reward": 0.0,
                "next_restart_cpu": state["next_cpu"]}

    def candidate(self):
        value = super().candidate()
        value["metadata"]["restart_curriculum"] = copy.deepcopy(self.restart_context)
        return value

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = path.with_name("."+path.name+".restart-private-"+uuid.uuid4().hex)
        try:
            super().save(staged)
            value = json.loads(staged.read_text())
            value["format"] = CHECKPOINT_FORMAT
            value["restart_curriculum"] = self.restart_context
            for source in (Path(__file__), Path(__file__).resolve().parents[1]/"scripts/train_restart_tensor_agent.py"):
                value["code_hashes"][source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
            _write(path, value)
        finally:
            staged.unlink(missing_ok=True)
            staged.with_suffix(staged.suffix+".tmp").unlink(missing_ok=True)

    @classmethod
    def load(cls, path, *, native_bridge=None):
        path = Path(path)
        value = json.loads(path.read_text())
        if value["format"] != CHECKPOINT_FORMAT:
            if value["format"] != "mmsearch-context-a2c-v2" or not value.get("pool_curriculum"):
                raise ValueError("v4 migration requires a v3 pool checkpoint")
            return super().load(path, native_bridge=native_bridge)
        if not value.get("restart_curriculum"):
            raise ValueError("v4 checkpoint missing restart state")
        for source in (Path(__file__), Path(__file__).resolve().parents[1]/"scripts/train_restart_tensor_agent.py"):
            if value.get("code_hashes", {}).get(source.name) != hashlib.sha256(source.read_bytes()).hexdigest():
                raise ValueError("v4 restart source identity changed across resume")
        staged = path.with_name("."+path.name+".restart-load-"+uuid.uuid4().hex)
        try:
            translated = dict(value, format="mmsearch-context-a2c-v2")
            _write(staged, translated)
            obj = super().load(staged, native_bridge=native_bridge)
            obj.restart_context = value["restart_curriculum"]
            return obj
        finally:
            staged.unlink(missing_ok=True)
            staged.with_suffix(staged.suffix+".tmp").unlink(missing_ok=True)
