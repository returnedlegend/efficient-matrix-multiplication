"""Immutable, held-out-split empirical recovery tasks for v3 training."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import uuid

from mmsearch.recovery_pool import checked_terms
from mmsearch.rl_search import _write, term_hash
from mmsearch.rl_curriculum import ContextController


class FixedStepBridge:
    """Recovery-only wrapper; record actions retain the original bridge budget."""
    def __init__(self, bridge, step_limit=50000):
        if type(step_limit) is not int or step_limit < 2000:
            raise ValueError("recovery step limit must exercise profile differences")
        self.bridge, self.step_limit = bridge, step_limit

    def __getattr__(self, key):
        return getattr(self.bridge, key)

    def run(self, candidate, action="exploit", **kwargs):
        kwargs["step_limit"] = self.step_limit
        return self.bridge.run(candidate, action=action, **kwargs)


def freeze_pool(source, destination):
    """Freeze a versioned snapshot and predeclare its deterministic held-out set."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError("pool snapshot destination must be new")
    raw_bytes = (source/"manifest.json").read_bytes()
    raw = json.loads(raw_bytes)
    entries = {}
    for item in raw["entries"]:
        if item["status"] not in ("retained_unknown", "retained_delayed_recovery"):
            continue
        path = Path(item["path"])
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != item["sha256"]:
            raise ValueError("source task checksum mismatch")
        candidate = json.loads(payload)
        terms = checked_terms(candidate, raw["config"]["dimension"])
        if not raw["config"]["known_rank"] < len(terms) <= raw["config"]["known_rank"]+raw["config"]["max_extra"]:
            raise ValueError("pool task outside declared rank range")
        digest = term_hash(terms)
        entry = dict(item, term_hash=digest, task_bucket="hard_unknown" if item["status"] == "retained_unknown" else "delayed_control")
        previous = entries.get(digest)
        if previous is None or entry["task_bucket"] == "hard_unknown":
            entries[digest] = entry
    values = list(entries.values())
    hard_count = sum(x["task_bucket"] == "hard_unknown" for x in values)
    if not hard_count:
        raise ValueError("pool has no qualifying unknown recovery task")
    # Hash ordering is fixed at the version boundary. Expanding the source pool
    # requires a NEW version and split; a running version never changes.
    ordered = sorted(values, key=lambda x: hashlib.sha256(("v3-heldout:"+x["term_hash"]).encode()).hexdigest())
    count = len(values)
    heldout_goal = max(2 if count >= 10 else 1 if count >= 3 else 0, round(0.2*count))
    hard_goal = max(2 if hard_count >= 5 else 1 if hard_count >= 2 else 0, round(0.2*hard_count))
    hard_goal = min(hard_count-1, hard_goal)
    heldout_goal = max(heldout_goal, hard_goal)
    hard_ordered = [x for x in ordered if x["task_bucket"] == "hard_unknown"]
    heldout = [x["term_hash"] for x in hard_ordered[:hard_goal]]
    train = []
    hard_heldout = hard_goal
    for entry in ordered:
        if entry["term_hash"] in heldout:
            continue
        may_hold = entry["task_bucket"] != "hard_unknown" or hard_count-hard_heldout > 1
        if len(heldout) < heldout_goal and may_hold:
            heldout.append(entry["term_hash"])
            hard_heldout += entry["task_bucket"] == "hard_unknown"
        else:
            train.append(entry["term_hash"])
    destination.mkdir(parents=True)
    for entry in values:
        original = Path(entry["path"])
        relative = Path("tasks")/(entry["sha256"]+".json")
        target = destination/relative
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(original, target)
        target.chmod(0o444)
        entry["path"] = str(relative)
    manifest = {"format": "frozen-recovery-pool-v3", "source_manifest_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "source_manifest": str(source/"manifest.json"), "sources": raw["sources"], "config": raw["config"],
                "entries": values, "split": {"train": train, "heldout": heldout,
                "method": "SHA256(v3-heldout:term_hash) stratified ordering, 20%, min2 overall if N>=10, min1 hard if H>=2, min2 hard if H>=5; retain >=1 hard training task"},
                "small_pool": hard_count-hard_heldout < 8 or hard_heldout < 2,
                "claim": "finite empirical probes; held-out tasks never used for training; small pool does not establish generalization"}
    _write(destination/"manifest.json", manifest)
    (destination/"manifest.json").chmod(0o444)
    return manifest


def combine_raw_pools(sources, destination):
    """Write a new provenance manifest; never mutate an input pool or version."""
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("combined source destination must be new")
    entries, origins, seed_sources = [], [], []
    config = None
    for source in sources:
        source = Path(source).resolve()
        payload = (source/"manifest.json").read_bytes()
        value = json.loads(payload)
        incoming = value["config"]
        if config is None:
            config = dict(incoming)
        elif any(config[key] != incoming[key] for key in ("dimension", "known_rank", "record_rank", "probe_steps")):
            raise ValueError("pool source dimensions/targets/probe budgets differ")
        config["max_extra"] = max(config["max_extra"], incoming["max_extra"])
        origin = {"manifest": str(source/"manifest.json"), "sha256": hashlib.sha256(payload).hexdigest(),
                  "config": incoming, "attempted_candidates": value["attempted_candidates"]}
        origins.append(origin)
        for seed in value["sources"]:
            if seed not in seed_sources:
                seed_sources.append(seed)
        for item in value["entries"]:
            entry = dict(item, source_pool_sha256=origin["sha256"],
                         source_pool_manifest=origin["manifest"], original_trial=item["trial"],
                         trial=len(entries)+1)
            if "path" in entry and not Path(entry["path"]).is_absolute():
                entry["path"] = str(source/entry["path"])
            entries.append(entry)
    if config is None:
        raise ValueError("no pool sources")
    destination.mkdir(parents=True)
    value = {"format": "combined-exact-recovery-pool-v3", "config": config, "sources": seed_sources,
             "source_pools": origins, "entries": entries, "attempted_candidates": len(entries),
             "claim": "new combined provenance version; all accepted and rejected source trials retained"}
    _write(destination/"manifest.json", value)
    return value


class HardRecoveryPool:
    def __init__(self, directory, *, expected_sha256=None):
        self.directory = Path(directory).resolve()
        payload = (self.directory/"manifest.json").read_bytes()
        self.sha256 = hashlib.sha256(payload).hexdigest()
        if expected_sha256 is not None and self.sha256 != expected_sha256:
            raise ValueError("frozen recovery pool version changed")
        self.manifest = json.loads(payload)
        if self.manifest["format"] != "frozen-recovery-pool-v3":
            raise ValueError("training requires a predeclared frozen pool snapshot")
        train, heldout = self.manifest["split"]["train"], self.manifest["split"]["heldout"]
        if set(train) & set(heldout):
            raise ValueError("held-out tasks overlap training tasks")
        self.entries = {item["term_hash"]: item for item in self.manifest["entries"]}
        self.training = {"hard_unknown": [], "delayed_control": []}
        self.heldout = list(heldout)
        self.candidates = {}
        for key, item in self.entries.items():
            payload = (self.directory/item["path"]).read_bytes()
            if hashlib.sha256(payload).hexdigest() != item["sha256"]:
                raise ValueError("frozen pool task checksum mismatch")
            value = json.loads(payload)
            terms = checked_terms(value, self.manifest["config"]["dimension"])
            if term_hash(terms) != key:
                raise ValueError("frozen task term hash mismatch")
            self.candidates[key] = value
            if key in train:
                self.training[item["task_bucket"]].append(key)
        if not self.training["hard_unknown"]:
            raise ValueError("frozen split has no hard training task")

    def choose(self, rng, *, episode_index, delayed_used):
        # At most one delayed control per five completed/started episodes.
        use_delayed = bool(self.training["delayed_control"]) and delayed_used < (episode_index+1)//5
        bucket = "delayed_control" if use_delayed else "hard_unknown"
        key = rng.choice(self.training[bucket])
        if key in self.heldout:
            raise AssertionError("held-out task reached training sampler")
        return key, self.candidates[key], self.entries[key]


class PoolRecordController(ContextController):
    """Atomically retain pool/censoring identity with the exact main state."""
    def __init__(self, initial_terms, *, pool_context=None, **kwargs):
        self.pool_context = pool_context or {}
        super().__init__(initial_terms, **kwargs)

    def candidate(self):
        value = super().candidate()
        value["metadata"]["pool_curriculum"] = self.pool_context
        return value

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = path.with_name("."+path.name+".pool-private-"+uuid.uuid4().hex)
        try:
            super().save(staged)
            value = json.loads(staged.read_text())
            value["pool_curriculum"] = self.pool_context
            source = Path(__file__)
            driver = source.resolve().parents[1]/"scripts/train_pool_tensor_agent.py"
            for item in (source, driver):
                if item.exists():
                    value["code_hashes"][item.name] = hashlib.sha256(item.read_bytes()).hexdigest()
            _write(path, value)
        finally:
            staged.unlink(missing_ok=True)
            staged.with_suffix(staged.suffix+".tmp").unlink(missing_ok=True)

    @classmethod
    def load(cls, path, *, native_bridge=None):
        obj = super().load(path, native_bridge=native_bridge)
        obj.pool_context = json.loads(Path(path).read_text()).get("pool_curriculum", {})
        return obj
