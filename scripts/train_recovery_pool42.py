"""Prepare broader frozen recovery tasks from 16 NEW93 states and old sources.

Task generation reuses the frozen exact v3 mixer/prober unchanged. The source
partition is frozen BEFORE probing, and the resulting snapshot uses a source
split rather than splitting correlated variants of the same source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mmsearch.native_bridge import canonical_terms
from mmsearch.recovery_pool import checked_terms
from mmsearch.rl_recovery42 import source_partition, freeze_source_pool42
from mmsearch.rl_search import _write, term_hash
from scripts.build_hard_recovery_pool import main as build_main


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--new93-dir", type=Path, required=True)
    p.add_argument("--record-seed", type=Path, action="append", required=True)
    p.add_argument("--outdir", type=Path, required=True)
    p.add_argument("--cpu", type=int, required=True)
    p.add_argument("--seconds", type=float, default=900)
    p.add_argument("--max-candidates", type=int, default=180)
    p.add_argument("--max-tasks", type=int, default=96)
    p.add_argument("--seed", type=int, default=421103)
    p.add_argument("--freeze-only", action="store_true")
    args = p.parse_args(argv)
    os.sched_setaffinity(0, {args.cpu})
    args.outdir.mkdir(parents=True, exist_ok=True)
    groups, identities, sources = {"new": [], "old": []}, [], []
    for kind, paths in (("new", sorted(args.new93_dir.glob("*.json"))), ("old", args.record_seed)):
        for path in paths:
            payload = path.read_bytes()
            candidate = json.loads(payload)
            canonical_terms(candidate)
            terms = checked_terms(candidate, 5)
            if candidate["dimension"] != 5 or len(terms) != 93:
                raise ValueError("source must be independently exact 5x5 F2 rank93")
            key = term_hash(terms)
            if key in groups["new"]+groups["old"]:
                raise ValueError("duplicate source state")
            groups[kind].append(key)
            sources.append(path.resolve())
            identities.append({"path": str(path.resolve()), "sha256": hashlib.sha256(payload).hexdigest(), "term_hash": key, "kind": kind})
    predeclared = {"format": "predeclared-recovery-sources-v42", "sources": identities,
                   "partition": source_partition(groups["new"], groups["old"]), "seed": args.seed,
                   "probe_steps": 50000, "minimum_progress_step": 100, "minimum_solve_step": 2000,
                   "mix_steps": 10000,
                   "claim": "split chosen before outcomes; no positive one-step recovery tasks"}
    declaration = args.outdir/"sources.json"
    if declaration.exists():
        if json.loads(declaration.read_text()) != predeclared:
            raise ValueError("source declaration changed across preparation resume")
    else:
        _write(declaration, predeclared)
        declaration.chmod(0o444)
    if not args.freeze_only:
        command = ["--output-dir", str(args.outdir/"raw"), "--cpu", str(args.cpu),
                   "--seconds", str(args.seconds), "--max-candidates", str(args.max_candidates),
                   "--max-tasks", str(args.max_tasks), "--mix-steps", "10000", "--probe-steps", "50000",
                   "--minimum-progress-step", "100", "--minimum-solve-step", "2000", "--seed", str(args.seed)]
        for path in sources:
            command += ["--initial", str(path)]
        build_main(command)
    raw = json.loads((args.outdir/"raw/manifest.json").read_text())
    if any(item.get("record") or item.get("status") == "verified_record" for item in raw["entries"]):
        print(json.dumps({"event": "verified_record_during_preparation", "source": str(args.outdir/"raw")}))
        return 0
    try:
        value = freeze_source_pool42(args.outdir/"raw", args.outdir/"frozen", predeclared["partition"])
    except ValueError as error:
        _write(args.outdir/"NOT_READY.json", {"reason": str(error), "action": "continue raw preparation with same source declaration; no training launched"})
        print(json.dumps({"event": "pool_not_ready", "reason": str(error)}), flush=True)
        return 2
    _write(args.outdir/"READY.json", {"manifest_sha256": hashlib.sha256((args.outdir/"frozen/manifest.json").read_bytes()).hexdigest(),
                                     "counts": value["v42_counts"], "small_pool": value["small_pool"]})
    (args.outdir/"NOT_READY.json").unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
