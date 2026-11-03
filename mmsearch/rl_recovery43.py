"""V43 source-disjoint recovery tasks: target latency, not partial-gain latency."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from mmsearch.native_bridge import canonical_terms
from mmsearch.recovery_pool import checked_terms
from mmsearch.rl_search import _write, term_hash

FORMAT = "frozen-source-recovery-pool-v43"
PROFILES = {"exploit", "explore", "long_walk"}


def evaluation_sources43(partition):
    ordered = sorted(partition["heldout"], key=lambda key:hashlib.sha256(("v43-final:"+key).encode()).hexdigest())
    if len(ordered) < 4:
        raise ValueError("v43 validation/test split needs four predeclared heldout sources")
    return {"test": sorted(ordered[:len(ordered)//2]), "validation": sorted(ordered[len(ordered)//2:]),
            "method": "SHA256(v43-final:source_hash); half heldout sources reserved for one final frozen evaluation"}


def screen43(probes, *, known_rank=93, step_limit=50000, minimum_target_steps=2000):
    if len(probes) != 3 or {probe.get("profile") for probe in probes} != PROFILES:
        return None, "incomplete_three_profile_screen"
    unknown = 0
    for probe in probes:
        status, attempts = probe.get("status"), probe.get("attempted_moves")
        if status not in ("unknown_within_probe", "known_bound_recovered"):
            return None, "incomplete_or_record_probe"
        if probe.get("step_budget") != step_limit or type(attempts) is not int or not 0 < attempts <= step_limit:
            return None, "inconsistent_fixed_probe_budget"
        if status == "known_bound_recovered":
            if probe.get("best_rank", known_rank+1) > known_rank:
                return None, "inconsistent_target_outcome"
            if attempts < minimum_target_steps:
                return None, "early_target_recovery"
        else:
            if attempts != step_limit or probe.get("best_rank", 0) <= known_rank:
                return None, "incomplete_unknown_probe"
            unknown += 1
    return {"task_bucket": "informative_challenge" if unknown else "delayed_control",
            "strict_hard": unknown == 3,
            "unknown_profile_count": unknown}, None


def pool_counts(entries, split):
    result = {}
    for name in ("train", "heldout"):
        keys = set(split[name])
        selected = [entry for entry in entries if entry["term_hash"] in keys]
        result[name] = {"tasks": len(selected), "challenge": sum(entry["task_bucket"] == "informative_challenge" for entry in selected),
                        "strict_all3_unknown": sum(entry["strict_hard"] for entry in selected),
                        "delayed": sum(entry["task_bucket"] == "delayed_control" for entry in selected),
                        "sources": len({entry["source_term_hash"] for entry in selected})}
    return result


def require_counts(counts):
    if any(counts[name][metric] < minimum for name, metric, minimum in
           (("train", "tasks", 8), ("heldout", "tasks", 4), ("train", "sources", 4),
            ("heldout", "sources", 2), ("train", "challenge", 2), ("heldout", "challenge", 2))):
        raise ValueError(f"v43 insufficient predeclared source/task/challenge coverage: {counts}")


def freeze43(raw_directory, destination, declaration):
    raw_directory, destination = Path(raw_directory).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError("v43 frozen destination must be new")
    raw_payload = (raw_directory/"manifest.json").read_bytes()
    raw = json.loads(raw_payload)
    partition = declaration["partition"]
    source_sets = {name:set(partition[name]) for name in ("train", "heldout")}
    if source_sets["train"] & source_sets["heldout"]:
        raise ValueError("heldout sources overlap training")
    entries = {}
    for entry in raw["entries"]:
        if entry.get("status") != "retained":
            continue
        label, reason = screen43(entry["probes"])
        if reason or any(entry.get(key) != value for key,value in label.items()):
            raise ValueError("retained v43 task violates predeclared probe rule")
        source = entry["source_term_hash"]
        if source not in source_sets["train"] | source_sets["heldout"]:
            raise ValueError("task source absent from predeclared universe")
        path = Path(entry["path"])
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ValueError("raw v43 task checksum mismatch")
        candidate = json.loads(payload)
        canonical_terms(candidate)
        terms = checked_terms(candidate, 5)
        key = term_hash(terms)
        if key != entry["term_hash"] or not 93 < len(terms) <= 100:
            raise ValueError("raw v43 task hash/rank mismatch")
        name = "train" if source in source_sets["train"] else "heldout"
        item = dict(entry, split=name)
        if key in entries:
            if entries[key]["split"] != name:
                raise ValueError("duplicate exact state would leak across source split")
        else:
            entries[key] = item
    values = list(entries.values())
    split = {name:sorted(key for key,entry in entries.items() if entry["split"] == name) for name in ("train", "heldout")}
    counts = pool_counts(values, split)
    require_counts(counts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".v43-freeze-", dir=destination.parent) as temporary:
        staged = Path(temporary)/"frozen"
        staged.mkdir()
        for entry in values:
            relative = Path("tasks")/(entry["sha256"]+".json")
            target = staged/relative
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(entry["path"], target)
            target.chmod(0o444)
            entry["path"] = str(relative)
        manifest = {"format": FORMAT, "entries": values, "split": split, "counts": counts,
                    "v43_source_split": partition, "evaluation_sources": evaluation_sources43(partition),
                    "declaration": declaration,
                    "source_manifest_sha256": hashlib.sha256(raw_payload).hexdigest(),
                    "config": {"dimension": 5, "known_rank": 93, "record_rank": 92, "probe_steps": 50000, "max_extra": 7},
                    "small_pool": counts["heldout"]["sources"] < 4 or counts["heldout"]["challenge"] < 8,
                    "claim": "known93 recovery; any-profile finite UNKNOWN defines challenge, all3UNKNOWN alone defines strict_hard; no lower-bound proof or rank record"}
        _write(staged/"manifest.json", manifest)
        (staged/"manifest.json").chmod(0o444)
        SourceRecoveryPool43(staged)
        staged.rename(destination)
    return manifest


class SourceRecoveryPool43:
    def __init__(self, directory, *, expected_sha256=None):
        self.directory = Path(directory).resolve()
        payload = (self.directory/"manifest.json").read_bytes()
        self.sha256 = hashlib.sha256(payload).hexdigest()
        if expected_sha256 is not None and expected_sha256 != self.sha256:
            raise ValueError("frozen v43 pool version changed")
        self.manifest = json.loads(payload)
        if self.manifest.get("format") != FORMAT:
            raise ValueError("v43 requires its predeclared source-disjoint pool")
        partition = self.manifest["v43_source_split"]
        if self.manifest["evaluation_sources"] != evaluation_sources43(partition):
            raise ValueError("v43 validation/test source reservation changed")
        source_sets = {name:set(partition[name]) for name in ("train", "heldout")}
        train, heldout = (set(self.manifest["split"][name]) for name in ("train", "heldout"))
        if train & heldout or source_sets["train"] & source_sets["heldout"]:
            raise ValueError("v43 source/task heldout overlap")
        self.entries = {entry["term_hash"]:entry for entry in self.manifest["entries"]}
        if len(self.entries) != len(self.manifest["entries"]) or train | heldout != set(self.entries):
            raise ValueError("v43 duplicate or unassigned task")
        self.heldout, self.candidates = sorted(heldout), {}
        self.training = {"informative_challenge": [], "delayed_control": []}
        for key, entry in self.entries.items():
            name = "train" if key in train else "heldout"
            if entry["source_term_hash"] not in source_sets[name] or entry["split"] != name:
                raise ValueError("v43 task leaks across source split")
            label, reason = screen43(entry["probes"])
            if reason or any(entry.get(k) != v for k,v in label.items()):
                raise ValueError("v43 task outcome labels violate fixed screening rule")
            payload = (self.directory/entry["path"]).read_bytes()
            if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                raise ValueError("v43 frozen task checksum mismatch")
            value = json.loads(payload)
            canonical_terms(value)
            terms = checked_terms(value, 5)
            if term_hash(terms) != key or not 93 < len(terms) <= 100:
                raise ValueError("v43 exact task hash/rank mismatch")
            if value.get("metadata", {}).get("source_term_hash") != entry["source_term_hash"]:
                raise ValueError("v43 candidate source provenance mismatch")
            self.candidates[key] = value
            if name == "train":
                self.training[entry["task_bucket"]].append(key)
        counts = pool_counts(list(self.entries.values()), self.manifest["split"])
        require_counts(counts)
        if counts != self.manifest["counts"]:
            raise ValueError("v43 pool counts changed")

    def choose(self, rng, *, episode_index, delayed_used):
        use_delayed = bool(self.training["delayed_control"]) and delayed_used < (episode_index+1)//5
        bucket = "delayed_control" if use_delayed else "informative_challenge"
        key = rng.choice(self.training[bucket])
        if key in self.heldout:
            raise AssertionError("heldout v43 task reached training sampler")
        return key, self.candidates[key], self.entries[key]
