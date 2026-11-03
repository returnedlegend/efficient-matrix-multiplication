"""V43 immutable target-latency screening, exact V42 replay and fresh mixing.

Never reads a running predecessor: root must finish the V42 preparation first.
No actor is fitted, no worker is launched in the background, and source-heldout
identities stay exactly those predeclared before V42 generation.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import sys
import time

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.native_bridge import NativeBridge, canonical_terms
from mmsearch.recovery_pool import bounded_mix, checked_terms, freeze_json, probe_candidate
from mmsearch.rl_recovery43 import freeze43, screen43, evaluation_sources43
from mmsearch.rl_search import _write, _tuple_tree, term_hash
from mmsearch.search import encode_candidate
from mmsearch.verify import verify_candidate


def replay43(entry, seeds, *, n=5, known_rank=93, record_rank=92, seconds=60):
    """Reproduce exact completed steps and require recorded term/source hashes."""
    source_index = entry["source_index"]
    mixing = entry["mixing"]
    base = seeds[source_index]
    if term_hash(base) != mixing["source_term_hash"] or not mixing.get("term_hash"):
        raise ValueError("replay requires matching recorded source and term hash")
    count = mixing["steps"]
    if type(count) is not int or count < 1:
        raise ValueError("replay needs an exact positive completed-step count")
    terms, replay = bounded_mix(base, n=n, rng=random.Random(entry["mix_seed"]),
                               known_rank=known_rank, record_rank=record_rank, steps=count,
                               max_rank=mixing["cap"], seconds=seconds,
                               reduction_every=mixing.get("reduction_every", 0))
    if (replay["status"] != "mixed" or replay["steps"] != count
            or replay["source_term_hash"] != mixing["source_term_hash"]
            or term_hash(terms) != mixing["term_hash"]):
        raise ValueError("deterministic replay did not reproduce recorded exact state")
    checked_terms(encode_candidate(terms, n), n)
    return terms, replay


def eligible_prior(entry):
    probes = entry.get("probes", [])
    if not probes:
        return False
    first = probes[0]
    return (first.get("status") == "unknown_within_probe"
            or first.get("status") == "known_bound_recovered" and first.get("attempted_moves", 0) >= 2000)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prior-pool", type=Path, required=True)
    p.add_argument("--outdir", type=Path, required=True)
    p.add_argument("--cpu", type=int, required=True)
    p.add_argument("--seconds", type=float, default=900)
    p.add_argument("--max-new-candidates", type=int, default=120)
    p.add_argument("--seed", type=int, default=431103)
    p.add_argument("--freeze-only", action="store_true")
    args = p.parse_args(argv)
    import math
    if not math.isfinite(args.seconds) or args.seconds < 0 or args.max_new_candidates < 0:
        p.error("preparation budget must be finite and nonnegative")
    os.sched_setaffinity(0, {args.cpu})
    started = time.monotonic()
    prior_payload = (args.prior_pool/"raw/manifest.json").read_bytes()
    prior = json.loads(prior_payload)
    prior_declaration_payload = (args.prior_pool/"sources.json").read_bytes()
    prior_declaration = json.loads(prior_declaration_payload)
    # Unknown exploit probes are replayed first; within each class retain trial
    # order. This ordering is declared before new three-profile outcomes.
    queue = sorted((entry for entry in prior["entries"] if eligible_prior(entry)),
                   key=lambda entry:(entry["probes"][0]["status"] != "unknown_within_probe", entry["trial"]))
    declaration = {"format": "predeclared-recovery-v43", "partition": prior_declaration["partition"],
                   "sources": prior["sources"], "prior_manifest_sha256": hashlib.sha256(prior_payload).hexdigest(),
                   "prior_declaration_sha256": hashlib.sha256(prior_declaration_payload).hexdigest(),
                   "replay_order": [entry["trial"] for entry in queue], "new_seed": args.seed,
                   "evaluation_sources": evaluation_sources43(prior_declaration["partition"]),
                   "rule": {"probe_steps": 50000, "profiles": ["exploit", "explore", "long_walk"],
                            "minimum_target_steps_every_profile": 2000, "early_partial_gains_allowed": True,
                            "challenge": "any profile unknown after50000, none early-target", "strict_hard": "all3 profiles unknown after50000",
                            "delayed_control": "all3 recover known93 after>=2000, none early-target"},
                   "gate": {"train_tasks": 8, "heldout_tasks": 4, "train_sources": 4, "heldout_sources": 2,
                            "train_challenges": 2, "heldout_challenges": 2},
                   "claim": "screened finite empirical tasks; exact source split inherited before original outcomes; no impossibility or learning claim"}
    args.outdir.mkdir(parents=True, exist_ok=True)
    declaration_path = args.outdir/"sources.json"
    if declaration_path.exists():
        if json.loads(declaration_path.read_text()) != declaration:
            raise ValueError("v43 predecessor/source/rule declaration changed on resume")
    else:
        _write(declaration_path, declaration)
        declaration_path.chmod(0o444)
    seeds = []
    for source in prior["sources"]:
        payload = Path(source["path"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != source["sha256"]:
            raise ValueError("v43 source bytes changed")
        value = json.loads(payload)
        canonical_terms(value)
        terms = checked_terms(value, 5)
        if len(terms) != 93 or term_hash(terms) != source["term_hash"]:
            raise ValueError("v43 source failed exact identity/rank check")
        seeds.append(terms)
    raw = args.outdir/"raw"
    raw.mkdir(exist_ok=True)
    manifest_path = raw/"manifest.json"
    rng = random.Random(args.seed)
    entries, replay_index, fresh_index = [], 0, 0
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        if previous["declaration"] != declaration:
            raise ValueError("v43 raw declaration changed")
        entries = previous["entries"]
        replay_index, fresh_index = previous["replay_index"], previous["fresh_index"]
        rng.setstate(_tuple_tree(previous["rng"]))
    bridge = NativeBridge(raw/"native", cpu_affinity=[args.cpu], archive_size=1)
    identity = {"binary_sha256": bridge.binary_sha256, "source_sha256": bridge.source_sha256}
    if manifest_path.exists() and previous["native_identity"] != identity:
        raise ValueError("v43 native source/binary changed across preparation resume")
    stopping = False
    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    def save():
        _write(manifest_path, {"format": "raw-exact-recovery-v43", "declaration": declaration,
                              "entries": entries, "rng": rng.getstate(), "replay_index": replay_index,
                              "fresh_index": fresh_index, "wall_seconds_this_invocation": time.monotonic()-started,
                              "native_identity": {"binary_sha256": bridge.binary_sha256, "source_sha256": bridge.source_sha256}})
    def record(candidate, origin):
        report = verify_candidate(candidate, random_trials=8)
        if not report["valid"] or report["rank"] > 92:
            raise ValueError("purported v43 record failed full verification")
        frozen = freeze_json(args.outdir/"records", candidate)
        freeze_json(args.outdir/"records", report)
        entries.append({"status": "verified_record", "origin": origin, **frozen})
        print(json.dumps({"event": "verified_record", "rank": report["rank"], **frozen}), flush=True)
    try:
        while not args.freeze_only and not stopping and time.monotonic()-started < args.seconds:
            if replay_index < len(queue):
                old = queue[replay_index]
                replay_index += 1
                source_index = old["source_index"]
                origin = {"kind": "exact_replay", "prior_trial": old["trial"],
                          "prior_status": old["status"], "mix_seed": old["mix_seed"],
                          "completed_steps": old["mixing"]["steps"], "expected_term_hash": old["mixing"].get("term_hash"),
                          "source_index": source_index, "prior_manifest_sha256": declaration["prior_manifest_sha256"]}
                try:
                    terms, mixing = replay43(old, seeds)
                except (ValueError, RuntimeError) as error:
                    entries.append({"status": "replay_not_reused", "origin": origin, "reason": str(error)})
                    save()
                    continue
                probe_seed = old["probe_seed"]
            elif fresh_index < args.max_new_candidates:
                source_index = fresh_index % len(seeds)
                extra = (1, 3, 7)[fresh_index % 3]
                mix_seed = rng.getrandbits(63)
                terms, mixing = bounded_mix(seeds[source_index], n=5, rng=random.Random(mix_seed),
                                           known_rank=93, record_rank=92, steps=10000, max_rank=93+extra,
                                           seconds=min(10, max(0.001, args.seconds-(time.monotonic()-started))))
                fresh_index += 1
                origin = {"kind": "fresh_mix", "mix_seed": mix_seed, "source_index": source_index,
                          "fresh_index": fresh_index}
                probe_seed = rng.getrandbits(31)
                if mixing["status"] == "verified_record":
                    record(encode_candidate(terms, 5), origin)
                    stopping = True
                    break
            else:
                break
            source_hash = term_hash(seeds[source_index])
            candidate = encode_candidate(terms, 5, task_kind="RECOVERY_CANDIDATE_V43",
                                         source_term_hash=source_hash, mixing=mixing, origin=origin)
            frozen = freeze_json(raw/"candidates", candidate)
            probes = []
            found_record = False
            for profile in ("exploit", "explore", "long_walk"):
                if stopping or time.monotonic()-started >= args.seconds:
                    break
                probe = probe_candidate(candidate, bridge, known_rank=93, record_rank=92,
                                        seed=probe_seed, steps=50000, seconds=2, profile=profile)
                if probe["record"] is not None:
                    record(probe["record"], {"profile": profile, **origin})
                    found_record = stopping = True
                probes.append({key:value for key,value in probe.items() if key != "record"})
                if found_record:
                    break
            label, reason = screen43(probes)
            entry = {"status": "retained" if label else "discarded", "reason": reason,
                     "origin": origin, "source_term_hash": source_hash, "source_index": source_index,
                     "term_hash": term_hash(terms), "probes": probes, "probe_seed": probe_seed,
                     "mixing": mixing, **frozen}
            if label:
                entry.update(label)
            entries.append(entry)
            print(json.dumps({"event": "screened", "status": entry["status"], "reason": reason,
                              "origin": origin, "label": label, "rank": len(terms),
                              "probe_outcomes": [{key:probe.get(key) for key in ("profile", "status", "best_rank", "attempted_moves", "first_improvement_step")} for probe in probes]}), flush=True)
            save()
    finally:
        save()
    if any(entry["status"] == "verified_record" for entry in entries):
        return 0
    try:
        value = freeze43(raw, args.outdir/"frozen", declaration)
    except ValueError as error:
        _write(args.outdir/"NOT_READY.json", {"reason": str(error), "replay_processed": replay_index,
                                            "fresh_processed": fresh_index, "next": "resume identical declaration; no policy training started"})
        print(json.dumps({"event": "pool_not_ready", "reason": str(error)}), flush=True)
        return 2
    _write(args.outdir/"READY.json", {"manifest_sha256": hashlib.sha256((args.outdir/"frozen/manifest.json").read_bytes()).hexdigest(),
                                    "counts": value["counts"], "small_pool": value["small_pool"]})
    (args.outdir/"NOT_READY.json").unlink(missing_ok=True)
    print(json.dumps({"event": "pool_ready", "counts": value["counts"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
