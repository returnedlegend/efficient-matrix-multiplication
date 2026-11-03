"""Build a finite exact recovery pool, rejecting trivially early native tasks."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import signal
import sys
import time

for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mmsearch.native_bridge import NativeBridge
from mmsearch.recovery_pool import bounded_mix, checked_terms, freeze_json, probe_candidate
from mmsearch.rl_search import _tuple_tree, _write, term_hash
from mmsearch.search import encode_candidate
from mmsearch.verify import verify_candidate


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--initial", type=Path, action="append", required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--dimension", type=int, default=5)
    p.add_argument("--known-rank", type=int, default=93)
    p.add_argument("--record-rank", type=int, default=92)
    p.add_argument("--cpu", type=int, required=True)
    p.add_argument("--seconds", type=float, default=120)
    p.add_argument("--max-candidates", type=int, default=64)
    p.add_argument("--max-tasks", type=int, default=40)
    p.add_argument("--mix-steps", type=int, default=1000)
    p.add_argument("--mix-seconds", type=float, default=10)
    p.add_argument("--max-extra", type=int, default=7)
    p.add_argument("--probe-steps", type=int, default=50000)
    p.add_argument("--probe-seconds", type=float, default=2)
    p.add_argument("--minimum-progress-step", type=int, default=100)
    p.add_argument("--minimum-solve-step", type=int, default=2000)
    p.add_argument("--mix-reduction-every", type=int, default=0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--memory-mb", type=int, default=512)
    args = p.parse_args(argv)
    if (args.seconds < 0 or args.max_candidates < 1 or args.mix_steps < 1 or args.mix_seconds <= 0
            or not 0 < args.probe_seconds <= 5 or args.probe_steps < 2000
            or args.max_extra < 1 or args.minimum_progress_step < 0 or args.minimum_solve_step < 0
            or args.mix_reduction_every < 0):
        p.error("invalid bounded pool budgets")
    os.sched_setaffinity(0, {args.cpu})
    resource.setrlimit(resource.RLIMIT_AS, (args.memory_mb*1024**2, args.memory_mb*1024**2))
    started = time.monotonic()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    seeds, provenance = [], []
    for path in args.initial:
        value = json.loads(path.read_text())
        terms = checked_terms(value, args.dimension)
        if len(terms) != args.known_rank:
            raise ValueError("source rank differs from declared known rank")
        seeds.append(terms)
        provenance.append({"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "term_hash": term_hash(terms)})
    bridge = NativeBridge(args.output_dir/"native", cpu_affinity=[args.cpu], archive_size=1)
    rng = random.Random(args.seed)
    manifest_path = args.output_dir/"manifest.json"
    entries = []
    trial = 0
    if manifest_path.exists():
        saved = json.loads(manifest_path.read_text())
        if saved["sources"] != provenance:
            raise ValueError("pool resume sources changed")
        rng.setstate(_tuple_tree(saved["rng"]))
        entries, trial = saved["entries"], saved["attempted_candidates"]
    stopping = False
    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    def save():
        _write(manifest_path, {"format": "exact-recovery-pool-v3", "seed": args.seed,
                               "sources": provenance, "rng": rng.getstate(),
                               "attempted_candidates": trial, "entries": entries,
                               "config": {k: getattr(args, k) for k in ("dimension", "known_rank", "record_rank", "mix_steps", "max_extra", "probe_steps", "minimum_progress_step", "minimum_solve_step", "mix_reduction_every")},
                               "wall_seconds_this_invocation": time.monotonic()-started,
                               "claim": "bounded empirical recovery probes; no formal hardness claim"})
    def freeze_record(candidate, origin):
        terms = checked_terms(candidate, args.dimension)
        if len(terms) > args.record_rank:
            raise ValueError("purported record is above requested record target")
        frozen = freeze_json(args.output_dir/"records", candidate)
        freeze_json(args.output_dir/"records", verify_candidate(candidate, random_trials=8))
        print(json.dumps({"event": "verified_record", "rank": len(terms), "origin": origin, **frozen}), flush=True)
        return frozen
    try:
        for _ in range(args.max_candidates):
            remaining = args.seconds-(time.monotonic()-started)
            if stopping or remaining <= 0:
                break
            trial += 1
            if sum(e["status"] in ("retained_unknown", "retained_delayed_recovery") for e in entries) >= args.max_tasks:
                trial -= 1
                break
            source_index = (trial-1) % len(seeds)
            # Cycle tight/medium/wide floors to avoid collecting only wide
            # starts with a few immediate algebraic cancellations.
            extra = (1, min(3, args.max_extra), args.max_extra)[(trial-1) % 3]
            mix_seed = rng.getrandbits(63)
            terms, mixing = bounded_mix(seeds[source_index], n=args.dimension, rng=random.Random(mix_seed),
                                        known_rank=args.known_rank, record_rank=args.record_rank,
                                        steps=args.mix_steps, max_rank=args.known_rank+extra,
                                        seconds=min(args.mix_seconds, remaining), reduction_every=args.mix_reduction_every)
            candidate = encode_candidate(terms, args.dimension, task_kind="HARD_RECOVERY_CANDIDATE",
                                         source=provenance[source_index], mixing=mixing,
                                         record_target_rank=args.record_rank, recovery_target_rank=args.known_rank)
            if mixing["status"] == "verified_record":
                frozen = freeze_record(candidate, "bounded_mixing")
                entries.append({"trial": trial, "status": "verified_record", **frozen})
                break
            probe_seed = rng.getrandbits(31)
            exploit = probe_candidate(candidate, bridge, known_rank=args.known_rank,
                                      record_rank=args.record_rank, seed=probe_seed,
                                      steps=args.probe_steps, seconds=args.probe_seconds)
            if exploit["record"] is not None:
                frozen = freeze_record(exploit["record"], "native_exploit_probe")
                entries.append({"trial": trial, "status": "verified_record", **frozen})
                break
            first = exploit.get("first_improvement_step")
            too_early = first is not None and first < args.minimum_progress_step
            hard = exploit["status"] == "unknown_within_probe" and not too_early
            delayed = (exploit["status"] == "known_bound_recovered" and not too_early
                       and exploit["attempted_moves"] >= args.minimum_solve_step)
            retain = hard or delayed
            entry = {"trial": trial, "source_index": source_index, "mixing": mixing,
                     "mix_seed": mix_seed, "probe_seed": probe_seed,
                     "status": "retained_unknown" if hard else "retained_delayed_recovery" if delayed else "discarded_early_progress" if too_early else exploit["status"],
                     "probes": [{k:v for k,v in exploit.items() if k != "record"}]}
            if retain:
                entry.update(freeze_json(args.output_dir/("tasks" if hard else "delayed_controls"), candidate))
                entry["term_hash"] = term_hash(terms)
                for profile in ("explore", "long_walk"):
                    if stopping or time.monotonic()-started >= args.seconds:
                        break
                    probe = probe_candidate(candidate, bridge, known_rank=args.known_rank,
                                            record_rank=args.record_rank, seed=probe_seed, profile=profile,
                                            steps=args.probe_steps, seconds=args.probe_seconds)
                    entry["probes"].append({k:v for k,v in probe.items() if k != "record"})
                    if probe["record"] is not None:
                        entry["record"] = freeze_record(probe["record"], "native_"+profile+"_probe")
                        stopping = True
                        break
                entry["profile_distinction"] = len({(x["status"], x.get("best_rank")) for x in entry["probes"]}) > 1
            entries.append(entry)
            print(json.dumps({"event": "candidate", "trial": trial, "status": entry["status"],
                              "source": source_index, "mixed_rank": len(terms), "mixed_steps": mixing["steps"],
                              "profiles": [{k:x.get(k) for k in ("profile", "status", "best_rank", "first_improvement_step", "attempted_moves")} for x in entry["probes"]],
                              "profile_distinction": entry.get("profile_distinction", False)}), flush=True)
            save()
    finally:
        save()
    print(json.dumps({"event": "finish", "attempted_candidates": trial,
                      "retained": sum(e["status"] == "retained_unknown" for e in entries),
                      "delayed_controls": sum(e["status"] == "retained_delayed_recovery" for e in entries),
                      "profile_distinctions": sum(e.get("profile_distinction", False) for e in entries),
                      "wall_seconds": time.monotonic()-started}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
