"""Source-disjoint immutable recovery snapshots, compatible with frozen eval."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

from mmsearch.rl_pool_curriculum import HardRecoveryPool, freeze_pool
from mmsearch.rl_search import _write


def source_partition(new_sources, existing_sources=()):
    """Choose held-out sources before generating or examining task outcomes."""
    new_sources = set(new_sources)
    existing_sources = set(existing_sources)
    if new_sources & existing_sources or len(new_sources) < 8:
        raise ValueError("need >=8 genuinely distinct new source states")
    ordered = sorted(new_sources, key=lambda key: hashlib.sha256(("v42-source:"+key).encode()).hexdigest())
    heldout = ordered[:max(2, round(len(ordered)*0.25))]
    return {"train": sorted((new_sources-set(heldout)) | existing_sources),
            "heldout": sorted(heldout),
            "method": "SHA256(v42-source:term_hash), reserve25% new sources before task generation; supplied old sources train only"}


def freeze_source_pool42(source, destination, partition, *, min_train_hard=8, min_heldout_hard=2):
    """Publish only once all source isolation and exact-certificate checks pass."""
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("frozen v42 destination must be new")
    train_sources, heldout_sources = set(partition["train"]), set(partition["heldout"])
    if train_sources & heldout_sources or not train_sources or not heldout_sources:
        raise ValueError("source split must be nonempty and disjoint")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".v42-freeze-", dir=destination.parent) as temporary:
        staged = Path(temporary)/"snapshot"
        value = freeze_pool(source, staged)
        retained = []
        excluded = []
        for entry in value["entries"]:
            probes = entry.get("probes", [])
            complete = {probe["profile"] for probe in probes
                        if probe["status"] in ("unknown_within_probe", "known_bound_recovered")}
            early = any((probe.get("first_improvement_step") is not None and probe["first_improvement_step"] < 100)
                        or (probe["status"] == "known_bound_recovered" and probe["attempted_moves"] < 2000)
                        for probe in probes)
            if complete != {"exploit", "explore", "long_walk"} or early:
                excluded.append({"term_hash": entry["term_hash"], "reason": "incomplete_three_profile_screen" if not early else "early_progress_or_recovery_in_another_profile"})
            else:
                retained.append(entry)
        value["entries"] = retained
        value["v42_additional_screen_excluded"] = excluded
        split = {"train": [], "heldout": [], "method": partition["method"]}
        source_counts = {"train": set(), "heldout": set()}
        hard_counts = {"train": 0, "heldout": 0}
        for entry in value["entries"]:
            origin = entry["mixing"]["source_term_hash"]
            if origin not in train_sources | heldout_sources:
                raise ValueError("task originates outside the predeclared source universe")
            bucket = "train" if origin in train_sources else "heldout"
            entry["v42_source_hash"] = origin
            split[bucket].append(entry["term_hash"])
            source_counts[bucket].add(origin)
            hard_counts[bucket] += entry["task_bucket"] == "hard_unknown"
        if (hard_counts["train"] < min_train_hard or hard_counts["heldout"] < min_heldout_hard
                or len(source_counts["train"]) < 4 or len(source_counts["heldout"]) < 2):
            raise ValueError(f"insufficient source-disjoint pool: hard={hard_counts}; sources="
                             f"{ {key:len(items) for key,items in source_counts.items()} }")
        value["split"] = split
        value["v42_source_split"] = partition
        value["v42_counts"] = {"hard": hard_counts, "sources": {key:len(items) for key,items in source_counts.items()}}
        value["small_pool"] = hard_counts["heldout"] < 8 or len(source_counts["heldout"]) < 4
        value["claim"] = "known-rank recovery; source-disjoint heldout; finite probes are censored, no impossibility or rank-record claim"
        _write(staged/"manifest.json", value)
        (staged/"manifest.json").chmod(0o444)
        SourceRecoveryPool42(staged)
        staged.rename(destination)
    return value


class SourceRecoveryPool42(HardRecoveryPool):
    def __init__(self, directory, *, expected_sha256=None):
        super().__init__(directory, expected_sha256=expected_sha256)
        partition = self.manifest.get("v42_source_split")
        if not partition:
            raise ValueError("v42 requires a predeclared source-disjoint curriculum")
        train_sources, heldout_sources = set(partition["train"]), set(partition["heldout"])
        if train_sources & heldout_sources:
            raise ValueError("v42 held-out source overlaps training")
        train, heldout = map(set, (self.manifest["split"]["train"], self.manifest["split"]["heldout"]))
        if train | heldout != set(self.entries):
            raise ValueError("every v42 task must belong to exactly one split")
        for key, entry in self.entries.items():
            source = entry["mixing"]["source_term_hash"]
            candidate_source = self.candidates[key].get("metadata", {}).get("source", {}).get("term_hash")
            if candidate_source is not None and candidate_source != source:
                raise ValueError("candidate provenance disagrees with frozen task source")
            if source != entry.get("v42_source_hash"):
                raise ValueError("v42 task source identity mismatch")
            expected = train_sources if key in train else heldout_sources
            if source not in expected:
                raise ValueError("v42 task leaks across source split")
