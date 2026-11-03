#!/usr/bin/env python3
"""Disabled-by-default preparation/search runner for the exact full-tensor code.

Preparation reads only an explicit hash-pinned approved nonheldout source manifest.
No directory scan, heldout data, evaluations, old artifact mutation, or solver call.
A production search needs both --authorize-search and --qa-approval root-reviewed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import signal
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from mmsearch.tensor_code7 import (SCHEMA, Walk, atom_from_term, checked_candidate, choose_move,
    digest, fundamental_kernel, prepare, rng_restore, strict_load, supports, term_from_atom, validate_kernel,
    validate_prepared, xor_columns)

CODE = ("scripts/tensor_code7.py", "mmsearch/tensor_code7.py", "tests/test_tensor_code7.py", "tests/test_tensor_code7_lifecycle.py", "tests/test_tensor_code7_sources.py", "mmsearch/verify.py",
        "scripts/tensor_code7.schema.json", "research/tensor_code7.md")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, sort_keys=True, indent=2)+"\n").encode()
    if exclusive:
        with path.open("xb") as stream:
            stream.write(raw)
    else:
        tmp = path.with_name(path.name+".tmp")
        with tmp.open("wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        tmp.replace(path)


def code_hashes():
    names = set(CODE)
    # The canonical guard has transitive local imports; bind the actual loaded closure.
    for module in tuple(sys.modules.values()):
        name = getattr(module, "__file__", None)
        if name:
            path = Path(name).resolve()
            if path.is_relative_to(REPO/"mmsearch") and path.suffix == ".py":
                names.add(str(path.relative_to(REPO)))
    return {name: sha((REPO/name).read_bytes()) for name in sorted(names)}


def runtime():
    return {"pid": os.getpid(), "cpu_affinity": sorted(os.sched_getaffinity(0)),
            "nice": os.getpriority(os.PRIO_PROCESS, 0),
            "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "utc": datetime.now(timezone.utc).isoformat(),
            "memory_limit_bytes": resource.getrlimit(resource.RLIMIT_AS)[0]}


class Stop(Exception):
    pass


HARD_UTC = datetime.fromisoformat("2026-11-03T19:24:17+00:00")


class Guard:
    def __init__(self, hard_utc, seconds, campaign_dir=None, guard_state=None, campaign_sha256=None, stop_markers=()):
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("finite positive wall budget required")
        self.started = time.monotonic()
        self.seconds = seconds
        requested = datetime.fromisoformat(hard_utc.replace("Z", "+00:00"))
        if requested.tzinfo is None:
            raise ValueError("hard deadline must include timezone")
        self.hard = min(requested, HARD_UTC)
        self.canonical = None
        self.signal = None
        if campaign_dir is not None:
            config_raw = (Path(campaign_dir)/"campaign.json").read_bytes()
            if not campaign_sha256 or sha(config_raw) != campaign_sha256:
                raise ValueError("campaign config hash differs from root-reviewed pin")
            config = strict_load(config_raw)
            campaign_hard = datetime.fromisoformat(config["deadline_utc"].replace("Z", "+00:00"))
            if campaign_hard.tzinfo is None:
                raise ValueError("campaign deadline timezone required")
            self.hard = min(self.hard, campaign_hard)
            from mmsearch.marathon7_local import CampaignGuard
            self.canonical = CampaignGuard(seconds, self.hard.isoformat(), stop_markers, guard_state,
                                           campaign_dir=campaign_dir)
            if self.canonical.resources is None:
                raise ValueError("production canonical resource guard required")
        signal.signal(signal.SIGTERM, self._signal)
        signal.signal(signal.SIGINT, self._signal)

    def _signal(self, signum, _frame):
        self.signal = signum
        if self.canonical:
            self.canonical.stop()

    def __call__(self, barrier="loop"):
        if self.signal:
            raise Stop(f"signal_{self.signal}:{barrier}")
        if datetime.now(timezone.utc).timestamp() >= self.hard.timestamp()-3:
            raise Stop("hard_utc_deadline_postcheck_reserve:"+barrier)
        if time.monotonic()-self.started >= self.seconds:
            raise Stop("bounded_seconds_elapsed:"+barrier)
        if self.canonical:
            reason = self.canonical.reason(force=barrier != "loop")
            if reason:
                raise Stop(reason+":"+barrier)

    def observation(self):
        return {"hard_utc": self.hard.isoformat(), "elapsed_seconds": time.monotonic()-self.started,
                "canonical": self.canonical.observation() if self.canonical else None}


def snapshot_code(root, hashes):
    for name, expected in hashes.items():
        raw = (REPO/name).read_bytes()
        if sha(raw) != expected:
            raise ValueError("code changed during launch")
        target = root/"code"/name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)


def select(value, selector):
    for key in selector:
        value = value[key]
    return value


def term_identity(candidate):
    if type(candidate.get("dimension")) is not int or candidate["dimension"] != 5 or type(candidate.get("field")) is not int or candidate["field"] != 2:
        raise ValueError("ancestry candidate requires literal n5/F2")
    atoms = sorted(atom_from_term(term, candidate["dimension"]) for term in candidate["terms"])
    if len(set(atoms)) != len(atoms):
        raise ValueError("ancestry candidate contains duplicate atoms")
    return sha("".join(f"{a} {b} {c}\n" for a, b, c in atoms).encode())


def reject_ineligible_metadata(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in ("heldout", "evaluation", "is_heldout", "is_evaluation") and item is True:
                raise ValueError("candidate metadata indicates prohibited split")
            if key.lower() in ("split", "source_split", "dataset_split", "role") and isinstance(item, str) and item.lower() in ("heldout", "evaluation", "eval", "test", "validation"):
                raise ValueError("candidate metadata indicates prohibited split")
            reject_ineligible_metadata(item)
    elif isinstance(value, list):
        for item in value:
            reject_ineligible_metadata(item)


def load_sources(args, root, guard):
    raw = args.manifest.read_bytes()
    if not args.manifest_sha256 or sha(raw) != args.manifest_sha256:
        raise ValueError("source manifest differs from independently root-reviewed hash")
    manifest = strict_load(raw)
    if manifest.get("format") != "tensor-code-source-anchors-v1" or not manifest.get("anchors"):
        raise ValueError("root-pinned source ancestry anchors required; selfattested source flags are insufficient")
    approved = args.approved_root.resolve(strict=True)
    if not args.manifest.resolve().is_relative_to(approved):
        raise ValueError("approved manifest outside explicit approved root")
    (root/"inputs").mkdir(parents=True)
    (root/"inputs"/"sources-manifest.json").write_bytes(raw)
    frozen_lineage = root/"inputs"/"lineage"
    frozen_lineage.mkdir()
    pinned_files = {}

    def pinned(record):
        guard("pre_source")
        path = Path(record["path"]).resolve(strict=True)
        if not path.is_relative_to(approved) or not path.is_file():
            raise ValueError("lineage input outside explicit approved root")
        data = path.read_bytes()
        if sha(data) != record["sha256"]:
            raise ValueError("lineage/source raw hash mismatch")
        if record.get("origin_sha256", record["sha256"]) != record["sha256"]:
            raise ValueError("lineage source differs from frozen origin")
        target = frozen_lineage/(record["sha256"]+".json")
        if target.exists() and target.read_bytes() != data:
            raise ValueError("hash alias collision")
        if not target.exists():
            target.write_bytes(data)
        pinned_files[str(path)] = record["sha256"]
        return strict_load(data), data

    registries = {}
    for key, record in manifest["registries"].items():
        registries[key], _ = pinned(record)
    prohibited = set(manifest["prohibited_identities"]["heldout"]) | set(manifest["prohibited_identities"]["evaluation"])
    if not prohibited:
        raise ValueError("explicit heldout/evaluation identity exclusions required")
    nodes = manifest["nodes"]
    node_candidates = {}
    for identity, node in nodes.items():
        if node["id"] != identity or node.get("heldout_excluded") is not True or node.get("evaluation_excluded") is not True or node.get("root_approved_train") is not True or node.get("split") not in ("train", "train_descendant"):
            raise ValueError("ineligible ancestry node")
        candidate, _ = pinned(node)
        reject_ineligible_metadata(candidate.get("metadata", {}))
        rl_identity = digest(sorted(atom_from_term(t, 5) for t in candidate["terms"]))
        if rl_identity != node["identity"]["rl_source_sha256"]:
            raise ValueError("ancestor RL identity mismatch")
        if term_identity(candidate) != node["identity"]["term_set_sha256"]:
            raise ValueError("ancestor term identity mismatch")
        if any(value in prohibited for value in node["identity"].values()):
            raise ValueError("heldout/evaluation node or descendant rejected")
        if {p["id"] for p in node["parent_files"]} != set(node["parent_ids"]):
            raise ValueError("parent file registry differs from parent edges")
        for parent in node["parent_files"]:
            if parent["id"] not in nodes or parent["sha256"] != nodes[parent["id"]]["sha256"]:
                raise ValueError("unknown or mismatched parent edge")
        node_candidates[identity] = candidate

    def replay(node):
        if not node["parent_ids"]:
            return
        if len(node["parent_ids"]) != 1:
            raise ValueError("unsupported multiple-parent affine derivation")
        parent = {atom_from_term(t, 5) for t in node_candidates[node["parent_ids"][0]]["terms"]}
        child = {atom_from_term(t, 5) for t in node_candidates[node["id"]]["terms"]}
        derivation = node.get("derivation") or {}
        kind = derivation.get("type")
        if kind == "canonical_terms_preserved_root_copy":
            if parent != child:
                raise ValueError("root copy changed canonical terms")
            return
        if kind not in ("affine_move_exact_replay", "affine_move_exact_replay_no_compression_change"):
            raise ValueError("unknown source derivation; defer")
        proof = derivation.get("move", derivation.get("proof"))
        a, b, free = proof["orientation"]
        if sorted((a, b, free)) != [0, 1, 2]:
            raise ValueError("invalid affine orientation")
        delta, coordinates = proof["delta"], proof["coordinate_mask"]
        if type(delta) is not int or not 0 < delta < 1 << 25 or type(coordinates) is not int:
            raise ValueError("invalid affine literal witness")
        neutral = tuple(proof["neutral_term"])
        selected = sorted(t for t in parent if t[free] == delta)
        if len(selected) < 2 or neutral not in parent or neutral[free] == delta or coordinates < 0 or coordinates >> len(selected) or coordinates.bit_count() < 2:
            raise ValueError("invalid affine selected slice")
        if [list(t) for t in selected] != proof["selected_terms"]:
            raise ValueError("affine selected terms do not match actual parent")
        represented = 0
        changed_selected = set()
        for i, term in enumerate(selected):
            if coordinates >> i & 1:
                represented ^= term[a]
                changed_selected.add(term)
        if represented != neutral[a]:
            raise ValueError("affine coordinate dependency fails")
        proposed = set()
        for original in parent:
            term = list(original)
            if original in changed_selected:
                term[b] ^= neutral[b]
            if original == neutral:
                term[free] ^= delta
            term = tuple(term)
            if all(term):
                if term in proposed:
                    proposed.remove(term)
                else:
                    proposed.add(term)
        if proposed != child:
            raise ValueError("exact affine ancestor replay differs from child")

    for node in nodes.values():
        guard("pre_ancestry_replay")
        replay(node)
    memo = {}
    def closure(identity, active=()):
        if identity in active or identity not in nodes:
            raise ValueError("cyclic or missing source ancestor")
        if identity in memo:
            return memo[identity]
        node = nodes[identity]
        ancestors = {identity}
        if node["parent_ids"]:
            for parent in node["parent_ids"]:
                ancestors |= closure(parent, active+(identity,))
        else:
            if node.get("node_type") != "native_initial_train" or node["root_id"] != identity:
                raise ValueError("unknown source eligibility root")
            evidence = node["root_training_evidence"]
            if evidence.get("approval_owner") != "root":
                raise ValueError("native training root lacks historical root authorization")
            for key, hashkey in (("approval_registry", "approval_sha256"), ("plan_registry", "plan_sha256")):
                if manifest["registries"][evidence[key]]["sha256"] != evidence[hashkey]:
                    raise ValueError("root training evidence config pin mismatch")
            pool = select(registries[evidence["plan_registry"]], evidence["selector"])
            if pool.get("sha256") != node["sha256"] or pool.get("term_hash") != node["identity"]["term_set_sha256"] or pool.get("rl_source_hash") != node["identity"]["rl_source_sha256"]:
                raise ValueError("root absent from approved native initial pool")
            armed = registries[evidence["approval_registry"]]
            if armed.get("owner") != "root" or armed.get("armed") is not True or armed.get("plan_sha256") != evidence["plan_sha256"]:
                raise ValueError("native initial plan lacks historical root arm/config binding")
            if evidence["train_identity"] != node["identity"]["rl_source_sha256"]:
                raise ValueError("root train identity differs from source")
            train = select(registries[evidence["split_registry"]], evidence["train_selector"])
            if evidence["train_identity"] not in train:
                raise ValueError("root absent from authoritative train split")
        if node["root_id"] not in ancestors:
            raise ValueError("claimed training root not reached through exact parent edges")
        memo[identity] = ancestors
        return ancestors

    candidates, records = [], []
    selected = [("bfs_descendant", anchor) for anchor in manifest["anchors"]]
    selected += [("native_initial_train", source) for source in manifest.get("known_input_train_states", [])]
    for index, (source_group, anchor) in enumerate(selected):
        if (source_group == "bfs_descendant" and anchor.get("eligibility") not in ("ELIGIBLE_PENDING_ROOT_REVIEW", "ELIGIBLE_ROOT_APPROVED")) or anchor.get("heldout_excluded") is not True or anchor.get("evaluation_excluded") is not True or anchor.get("root_approved_train") is not True:
            raise ValueError("deferred or ineligible source anchor")
        ancestors = closure(anchor["id"])
        if ancestors != set(anchor.get("ancestor_ids", [anchor["id"]])) or anchor["root_id"] not in ancestors:
            raise ValueError("source ancestor closure differs from reviewed anchor")
        candidate, data = pinned(anchor)
        if term_identity(candidate) != anchor["identity"]["term_set_sha256"] or anchor["identity"] != nodes[anchor["id"]]["identity"]:
            raise ValueError("anchor/source canonical identity mismatch")
        if source_group == "bfs_descendant":
            export = select(registries[anchor["export_registry"]], anchor["export_selector"])
            if export.get("sha256") != anchor["origin_sha256"] or export.get("term_hash") != anchor["identity"]["term_set_sha256"]:
                raise ValueError("source absent from approved BFS export registry")
        elif anchor["id"] != anchor["root_id"] or nodes[anchor["id"]]["node_type"] != "native_initial_train":
            raise ValueError("known training input is not a catalog-bound native root")
        reject_ineligible_metadata(candidate.get("metadata", {}))
        if type(candidate.get("dimension")) is not int or candidate.get("dimension") != 5 or type(candidate.get("field")) is not int or candidate.get("field") != 2 or len(candidate.get("terms", [])) != 93:
            raise ValueError("production preparation accepts literal F2 dimension5 rank93 sources only")
        frozen = root/"inputs"/f"seed-{index:03d}.json"
        frozen.write_bytes(data)
        candidates.append(candidate)
        records.append({"path": str(Path(anchor["path"]).resolve()), "sha256": sha(data),
                        "snapshot": str(frozen.relative_to(root)), "anchor_id": anchor["id"], "source_group": source_group,
                        "ancestor_ids": sorted(ancestors), "root_id": anchor["root_id"],
                        "identity": anchor["identity"], "provenance": {"heldout": False, "evaluation": False,
                        "approval_manifest_sha256": args.manifest_sha256}})
    guard("post_source")
    write_json(root/"inputs"/"lineage-files.json", pinned_files, exclusive=True)
    return candidates, records, sha(raw)


def verify_source_binding(args, document, guard):
    """Reconstruct from independently root-pinned approved sources, not self hashes."""
    import tempfile
    if document.get("source_manifest_sha256") != args.manifest_sha256:
        raise ValueError("prepared approval manifest differs from root-reviewed pin")
    frozen_root = args.prepared.resolve().parent
    frozen_manifest = frozen_root/"inputs"/"sources-manifest.json"
    if sha(frozen_manifest.read_bytes()) != args.manifest_sha256:
        raise ValueError("frozen approved manifest hash mismatch")
    with tempfile.TemporaryDirectory(prefix="tensor_code7-source-recheck-", dir=args.outdir) as directory:
        candidates, records, manifest_sha = load_sources(args, Path(directory), guard)
        observed_lineage = strict_load((Path(directory)/"inputs"/"lineage-files.json").read_bytes())
        if strict_load((frozen_root/"inputs"/"lineage-files.json").read_bytes()) != observed_lineage:
            raise ValueError("frozen source lineage file registry differs")
        for expected in observed_lineage.values():
            frozen = frozen_root/"inputs"/"lineage"/(expected+".json")
            if sha(frozen.read_bytes()) != expected:
                raise ValueError("frozen ancestry or approval registry hash mismatch")
        if records != document.get("sources"):
            raise ValueError("prepared source records differ from independently approved lineage")
        for record in records:
            guard("pre_frozen_source")
            path = (frozen_root/record["snapshot"]).resolve(strict=True)
            if not path.is_relative_to(frozen_root) or sha(path.read_bytes()) != record["sha256"]:
                raise ValueError("frozen source bytes mismatch")
        reconstructed = prepare(candidates, cap=document["seed_parameters"]["cap"], guard=guard)
        for key, value in reconstructed.items():
            if document.get(key) != value:
                raise ValueError("prepared dictionary/state differs from approved source reconstruction: "+key)
        if manifest_sha != document["source_manifest_sha256"]:
            raise ValueError("manifest hash changed during reconstruction")
    guard("post_source_reconstruction")


def lifecycle_config(args, guard):
    return {"source_manifest_sha256": args.manifest_sha256,
            "campaign_sha256": args.campaign_sha256,
            "campaign_dir": str(args.campaign_dir.resolve()),
            "guard_state": str(args.guard_state.resolve()),
            "deadline_utc": guard.hard.isoformat(),
            "stop_markers": sorted(str(p.resolve()) for p in args.stop_marker)}


def prep_main(args, root, guard, hashes):
    candidates, records, manifest_sha = load_sources(args, root, guard)
    document = prepare(candidates, cap=args.cap, guard=guard)
    if any(weight != 93 for weight in document["seed_weights"]):
        raise ValueError("production source contains cancelling duplicate atoms; expected exact state weight93")
    document.update(sources=records, source_manifest_sha256=manifest_sha, code_sha256=hashes,
                    lifecycle_config=lifecycle_config(args, guard),
                    runtime=runtime(), seed_parameters={"cap": args.cap})
    # Serialize and rehydrate so the on-disk format itself is validated.
    document = strict_load(json.dumps(document))
    validate_prepared(document, guard)
    guard("post_preparation_validation")
    write_json(root/"prepared.json", document, exclusive=True)
    return {"status": "PREPARED_NO_SEARCH", "search_called": False, "rank": document["rank"],
            "nullity": document["nullity"], "dictionary_size": document["dictionary_size"],
            "tensor_entries": document["tensor_entries"], "prepared_sha256": sha((root/"prepared.json").read_bytes()),
            "packed_columns_bytes": sum((int(c, 16).bit_length()+7)//8 for c in document["columns_hex"]),
            "packed_kernel_bytes": sum((int(c, 16).bit_length()+7)//8 for c in document["kernel_hex"]),
            "memory_measurement": "max_rss_kib in runtime is observed process high-water RSS; packed bytes exclude Python overhead"}


def save_candidate(root, name, atoms, state, n, evidence, guard=None):
    """Retain raw evidence on a late return; publish only across strict barriers."""
    raw_candidate = {"field": 2, "dimension": n,
                     "terms": [term_from_atom(atoms[i], n) for i in supports(state)]}
    staging = root/".raw-candidates"/f"witness-{time.monotonic_ns()}"
    staging.mkdir(parents=True, exist_ok=False)
    raw_envelope = {"status": "UNKNOWN", "complete": False, "after_cutoff": False,
                    "no_within_budget_claim": True, "raw": {"candidate": raw_candidate}}
    write_json(staging/"raw-candidate.json", raw_envelope, exclusive=True)
    write_json(staging/"evidence.json", evidence, exclusive=True)
    try:
        if guard:
            guard("pre_full_tensor")
        candidate, checks = checked_candidate(atoms, state, n, guard=guard)
        write_json(staging/"candidate.json", candidate, exclusive=True)
        write_json(staging/"verification.json", checks, exclusive=True)
        (staging/"verify.py").write_bytes((REPO/"mmsearch/verify.py").read_bytes())
        frozen = strict_load((staging/"candidate.json").read_bytes())
        if frozen != candidate:
            raise AssertionError("saved candidate differs")
        if guard:
            guard("prepublication_views")
            guard("premarker")
        destination = root/name
        if destination.exists():
            raise ValueError("immutable candidate destination already exists")
        staging.rename(destination)
        try:
            if guard:
                guard("postmarker")
        except Stop:
            destination.rename(staging)
            raise
        return {"directory": str(destination), "rank": state.bit_count(),
                "candidate_sha256": sha((destination/"candidate.json").read_bytes()),
                "full_entries_checked_by_each_checker": n**6}
    except Stop as exc:
        raw_envelope.update(after_cutoff=True, stop_reason=str(exc))
        write_json(staging/"raw-candidate.json", raw_envelope)
        write_json(staging/"after-cutoff-status.json", {"status": "UNKNOWN", "complete": False,
                   "after_cutoff": True, "no_within_budget_claim": True, "stop_reason": str(exc)}, exclusive=True)
        raise


def search_main(args, root, guard, hashes):
    raw = args.prepared.read_bytes()
    if not args.prepared_sha256 or sha(raw) != args.prepared_sha256:
        raise ValueError("prepared bytes differ from root-reviewed hash")
    document = strict_load(raw)
    if type(document.get("dimension")) is not int or document["dimension"] != 5 or type(document.get("field")) is not int or document["field"] != 2:
        raise ValueError("production prepared input requires literal n5/F2 before tensor construction")
    atoms, columns, seeds, cycles = validate_prepared(document, guard)
    if any(weight != 93 for weight in document["seed_weights"]):
        raise ValueError("production prepared seeds must have exact state weight93")
    if document["dimension"] != 5:
        raise ValueError("production search requires n5; planted controls belong in tests")
    if document.get("code_sha256") != hashes:
        raise ValueError("prepared code differs from reviewed running code; reprepare required")
    if not document.get("sources") or any(s.get("provenance", {}).get("heldout") is not False or s.get("provenance", {}).get("evaluation") is not False for s in document["sources"]):
        raise ValueError("prepared production provenance missing")
    verify_source_binding(args, document, guard)
    if document.get("lifecycle_config") != lifecycle_config(args, guard):
        raise ValueError("prepared campaign/deadline/resource/source approval configuration differs")
    prepared_sha = sha(raw)
    (root/"inputs").mkdir()
    (root/"inputs"/"prepared.json").write_bytes(raw)
    params = {"seed": args.seed, "temporary_excess": args.temporary_excess,
              "samples": args.samples, "restart_after": args.restart_after,
              "max_restarts": args.max_restarts, "winner_weight": 92}
    rng = random.Random(args.seed)
    source = seeds[0]
    walk = Walk(source, source)
    order = list(range(len(columns)))
    saved = []
    resumed = False
    terminal_late = False
    if args.resume:
        checkpoint = strict_load(args.resume.read_bytes())
        if checkpoint["schema"] != SCHEMA or checkpoint["prepared_sha256"] != prepared_sha or checkpoint["code_sha256"] != hashes or checkpoint["parameters"] != params:
            raise ValueError("checkpoint input/code/parameter mismatch")
        if checkpoint.get("lifecycle_config") != document.get("lifecycle_config"):
            raise ValueError("checkpoint lifecycle configuration differs")
        walk = Walk.from_json(checkpoint["cursor"])
        rng = rng_restore(checkpoint["rng_state"])
        order = checkpoint["basis_order"]
        cycles, rank = fundamental_kernel(columns, order, guard)
        if rank != document["rank"]:
            raise AssertionError("reordered rank changed")
        terminal_late = checkpoint.get("publication_eligibility") == "late_raw_only"
        if walk.best.bit_count() <= 92 and checkpoint.get("publication_eligibility") not in ("eligible_within_budget", "late_raw_only"):
            raise ValueError("terminal checkpoint lacks explicit publication eligibility")
        resumed = True
    target = int(document["target_hex"], 16)
    if xor_columns(columns, walk.state) != target or xor_columns(columns, walk.best) != target:
        raise ValueError("checkpoint state failed exact equations")
    ceiling = min(x.bit_count() for x in seeds)+args.temporary_excess
    if walk.state.bit_count() > ceiling:
        raise ValueError("checkpoint exceeds temporary bound")
    last_checkpoint = 0.0
    winner = False
    status = "UNKNOWN"
    stop_reason = None
    pending_cursor = pending_rng = pending_order = None

    def checkpoint():
        if xor_columns(columns, walk.state) != target or xor_columns(columns, walk.best) != target:
            raise AssertionError("checkpoint invariant failure")
        write_json(root/"checkpoint.json", {"schema": SCHEMA, "prepared_sha256": prepared_sha,
            "code_sha256": hashes, "parameters": params, "cursor": walk.to_json(), "basis_order": order,
            "rng_state": rng.getstate(), "runtime": runtime(), "resumed": resumed, "lifecycle_config": document.get("lifecycle_config"),
            "publication_eligibility": "eligible_within_budget" if winner else "late_raw_only" if (terminal_late or stop_reason is not None) and walk.best.bit_count() <= 92 else "pending"})

    try:
        checkpoint()
        if walk.best.bit_count() <= 92:
            if terminal_late:
                raise Stop("terminal_late_raw_witness_no_publication")
            guard("terminal_resume")
            saved.append(save_candidate(root, "first-record-evidence", atoms, walk.best, 5,
                         {"schema": SCHEMA, "terminal_resume": True, "cursor": walk.to_json(),
                          "prepared_sha256": prepared_sha, "novelty_claim": False}, guard=guard))
            winner = True
            status = "FROZEN_DOUBLE_CHECKED_LE92_STOP"
        while not winner and walk.restart < args.max_restarts:
            guard()
            pending_cursor = walk.to_json()
            pending_order = list(order)
            pending_rng = rng.getstate()
            rng_before = pending_rng
            move = None
            try:
                move, kind = choose_move(walk.state, cycles, rng, ceiling, args.samples, guard=guard)
                guard("post_solve")
            except Stop as exc:
                rng.setstate(rng_before)
                write_json(root/f"after-cutoff-raw-move-{walk.step:08d}.json", {
                    "status": "UNKNOWN", "complete": False, "after_cutoff": True,
                    "no_within_budget_claim": True, "stop_reason": str(exc),
                    "state_before_hex": hex(walk.state), "proposed_move_hex": hex(move) if move else None,
                    "proposed_state_hex": hex(walk.state^move) if move else None}, exclusive=True)
                raise
            walk.step += 1
            walk.no_improvement += 1
            if move is not None:
                # All basis combinations have Az=0; check before applying too.
                if xor_columns(columns, move):
                    raise AssertionError("proposed move is outside full tensor kernel")
                walk.state ^= move
                walk.moves += 1
                if walk.state.bit_count() > ceiling:
                    raise AssertionError("temporary bound violated")
                guard("post_exact_move")
            if walk.state.bit_count() < walk.best.bit_count():
                walk.best = walk.state
                walk.no_improvement = 0
                evidence = {"schema": SCHEMA, "prepared_sha256": prepared_sha, "state_hex": hex(walk.best),
                            "cursor": walk.to_json(), "move_kind": kind, "code_sha256": hashes,
                            "runtime": runtime(), "novelty_claim": False}
                name = "first-record-evidence" if walk.best.bit_count() <= 92 else f"improvement-{len(saved):04d}"
                saved.append(save_candidate(root, name, atoms, walk.best, 5, evidence, guard=guard))
                if walk.best.bit_count() <= 92:
                    winner = True
                    status = "FROZEN_DOUBLE_CHECKED_LE92_STOP"
                    pending_cursor = pending_rng = pending_order = None
                    checkpoint()
                    break
            if move is None or walk.no_improvement >= args.restart_after:
                walk.restart += 1
                walk.state = seeds[rng.randrange(len(seeds))]
                walk.no_improvement = 0
                rng.shuffle(order)
                cycles, rank = fundamental_kernel(columns, order, guard)
                if rank != document["rank"]:
                    raise AssertionError("reorder rank changed")
                validate_kernel(columns, cycles)
            guard("post_iteration")
            pending_cursor = pending_rng = pending_order = None
            if time.monotonic()-last_checkpoint >= 5:
                checkpoint()
                last_checkpoint = time.monotonic()
        if not winner:
            stop_reason = "MAX_RESTARTS"
    except Stop as exc:
        stop_reason = str(exc)
        if pending_cursor is not None:
            walk = Walk.from_json(pending_cursor)
            rng.setstate(pending_rng)
            order = pending_order
    finally:
        checkpoint()
    # Postchecks after a hold are diagnostic only and cannot create eligibility.
    _candidate, postcheck = checked_candidate(atoms, walk.best, 5)
    write_json(root/"postcheck.json", postcheck, exclusive=True)
    return {"status": status, "stop_reason": stop_reason, "complete": winner, "winner": winner, "search_called": True, "saved": saved,
            "best_weight": walk.best.bit_count(), "final_weight": walk.state.bit_count(),
            "cursor": walk.to_json(), "parameters": params, "rank": document["rank"],
            "nullity": document["nullity"], "dictionary_size": len(atoms), "prepared_sha256": prepared_sha,
            "resumed": resumed, "postcheck_passed": True, "novelty_claim": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "search"))
    parser.add_argument("--authorize-preparation", action="store_true")
    parser.add_argument("--authorize-search", action="store_true")
    parser.add_argument("--qa-approval", choices=("root-reviewed",))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--prepared-sha256")
    parser.add_argument("--campaign-dir", type=Path)
    parser.add_argument("--campaign-sha256")
    parser.add_argument("--guard-state", type=Path)
    parser.add_argument("--stop-marker", type=Path, action="append", default=[])
    parser.add_argument("--approved-root", type=Path)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--hard-utc", required=True)
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument("--cpu", type=int, choices=(3,), default=3)
    parser.add_argument("--memory-mib", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--cap", type=int, default=5000)
    parser.add_argument("--temporary-excess", type=int, default=8)
    parser.add_argument("--samples", type=int, default=256)
    parser.add_argument("--restart-after", type=int, default=64)
    parser.add_argument("--max-restarts", type=int, default=10000)
    args = parser.parse_args(argv)
    enabled = args.authorize_preparation if args.mode == "prepare" else args.authorize_search and args.qa_approval == "root-reviewed"
    if not enabled:
        print(json.dumps({"schema": SCHEMA, "status": "DISABLED_PENDING_ROOT_QA", "mode": args.mode,
                          "production_inputs_read": False, "search_called": False}, sort_keys=True))
        return 0
    if not math.isfinite(args.seconds) or args.seconds <= 0 or args.memory_mib < 128 or args.memory_mib > 1024 or args.temporary_excess < 0 or not 0 <= args.samples <= 4096 or args.restart_after < 1 or args.max_restarts < 1:
        parser.error("invalid resource/search bounds; memory must be 128..1024 MiB")
    if args.mode == "prepare" and (args.manifest is None or args.approved_root is None):
        parser.error("preparation needs --manifest and --approved-root")
    if args.mode == "search" and args.prepared is None:
        parser.error("search needs --prepared")
    guard = Guard(args.hard_utc, args.seconds, args.campaign_dir, args.guard_state, args.campaign_sha256, args.stop_marker)
    try:
        guard()
    except Stop as exc:
        print(json.dumps({"schema": SCHEMA, "status": "UNKNOWN", "stop_reason": str(exc), "complete": False, "search_called": False}))
        return 0
    if args.campaign_dir is None or args.guard_state is None or not args.campaign_sha256:
        parser.error("production requires root-pinned --campaign-dir --campaign-sha256 and --guard-state")
    if args.manifest is None or args.approved_root is None or not args.manifest_sha256:
        parser.error("both modes require --manifest --manifest-sha256 and --approved-root")
    if args.mode == "search" and not args.prepared_sha256:
        parser.error("search requires --prepared-sha256 bound by root QA")
    os.sched_setaffinity(0, {args.cpu})
    if os.getpriority(os.PRIO_PROCESS, 0) < 10:
        os.nice(10-os.getpriority(os.PRIO_PROCESS, 0))
    bound = args.memory_mib*1024*1024
    resource.setrlimit(resource.RLIMIT_AS, (bound, bound))
    root = args.outdir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    hashes = code_hashes()
    snapshot_code(root, hashes)
    write_json(root/"launch.json", {"schema": SCHEMA, "arguments": {k: str(v) if isinstance(v, Path) else [str(x) for x in v] if isinstance(v, list) else v for k, v in vars(args).items()},
               "runtime": runtime(), "code_sha256": hashes}, exclusive=True)
    try:
        result = prep_main(args, root, guard, hashes) if args.mode == "prepare" else search_main(args, root, guard, hashes)
    except Stop as exc:
        result = {"status": "UNKNOWN", "stop_reason": str(exc), "search_called": False, "complete": False}
    except Exception as exc:
        result = {"status": "FAILED_CLOSED", "error_type": type(exc).__name__, "error": str(exc), "complete": False}
        write_json(root/"result.json", dict(schema=SCHEMA, runtime=runtime(), code_sha256=hashes, **result), exclusive=True)
        raise
    result.update(schema=SCHEMA, runtime=runtime(), code_sha256=hashes, elapsed_seconds=time.monotonic()-guard.started)
    write_json(root/"result.json", result, exclusive=True)
    write_json(root/"checksums.json", {str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file()}, exclusive=True)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
