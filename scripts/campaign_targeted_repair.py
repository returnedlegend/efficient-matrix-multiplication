"""Bounded single-process multi-seed discrete F2 repair campaign.

Run under taskset/resource limits supplied by the campaign supervisor. A small
residual is only a search objective; FOUND requires independent exact equality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.targeted_repair import code_hash, save, search
from mmsearch.verify import verify_candidate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", default=[])
    parser.add_argument("--seed-dir", type=Path, action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--rank", type=int, default=92)
    parser.add_argument("--dimension", type=int, default=5)
    parser.add_argument("--seconds", type=float, default=600)
    parser.add_argument("--slice-seconds", type=float, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-excess", type=int, default=64)
    parser.add_argument("--max-runs", type=int, default=0)
    args = parser.parse_args(argv)
    if any(not math.isfinite(v) or v <= 0 for v in (args.seconds, args.slice_seconds)):
        parser.error("time budgets must be positive and finite")
    if min(args.rank, args.dimension) < 1 or min(args.max_excess, args.max_runs) < 0:
        parser.error("invalid integer bounds")
    if not args.input and not args.seed_dir:
        parser.error("provide --input or --seed-dir")
    started = time.monotonic()
    deadline = started+args.seconds
    root = args.output_dir
    root.mkdir(parents=True, exist_ok=True)
    identity = dict(rank=args.rank, dimension=args.dimension, seed=args.seed,
        max_excess=args.max_excess, slice_seconds=args.slice_seconds,
        code_sha256=dict(code_hash(), campaign_targeted_repair=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    manifest = root/"manifest.json"
    if manifest.exists():
        state = json.loads(manifest.read_text())
        if state["identity"] != identity:
            raise ValueError("campaign parameters or code hashes differ from checkpoint")
    else:
        state = dict(version=1, identity=identity, sources={}, source_cursor=0,
                     attempts=0, counters={}, scope="heuristic residual repair; exact verifier certifies equality")

    def emit(event):
        event["utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with (root/"results.jsonl").open("a") as handle:
            handle.write(json.dumps(event, sort_keys=True)+"\n")
        print(json.dumps(event, sort_keys=True), flush=True)

    def scan():
        paths = list(args.input)
        for directory in args.seed_dir:
            paths.extend(sorted(directory.rglob("*.json")))
        for path in paths:
            if time.monotonic() >= deadline:
                break
            try:
                raw = path.read_bytes()
                sha = hashlib.sha256(raw).hexdigest()
                if sha in state["sources"]:
                    continue
                source = json.loads(raw)
                if (source.get("dimension") != args.dimension or source.get("field") != 2
                        or len(source.get("terms", [])) != args.rank+1):
                    continue
                # Exact source verification occurs immediately before its first
                # search; scanning does not spend the budget verifying all seeds.
                state["sources"][sha] = dict(path=str(path), rounds=0, checked=False)
            except (OSError, ValueError, TypeError, AttributeError):
                continue
        save(manifest, state)

    scan()
    if not state["sources"]:
        raise ValueError("no candidate source of requested dimension and rank+1 found")
    runs = 0
    while not state.get("found") and time.monotonic() < deadline and (
            not args.max_runs or runs < args.max_runs):
        keys = list(state["sources"])
        key = keys[state["source_cursor"] % len(keys)]
        entry = state["sources"][key]
        state["source_cursor"] += 1
        if entry.get("rejected"):
            if all(e.get("rejected") for e in state["sources"].values()):
                break
            continue
        raw = Path(entry["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != key:
            raise ValueError("source file changed after discovery")
        source = json.loads(raw)
        if not entry["checked"]:
            report = verify_candidate(source, random_trials=0)
            if not report["valid"]:
                entry["rejected"] = report["errors"]
                save(manifest, state)
                continue
            entry["checked"] = True
        seconds = min(args.slice_seconds, deadline-time.monotonic())
        if seconds <= 0:
            break
        prefix = root/"sources"/key
        checkpoint = prefix.with_suffix(".checkpoint.json")
        output = prefix.with_suffix(".json")
        previous = entry.get("counters", {})
        result, report = search(source, rank=args.rank, seconds=seconds,
            seed=args.seed ^ int(key[:12], 16), output=output,
            checkpoint=checkpoint, resume=checkpoint.exists(),
            max_excess=args.max_excess, progress=False)
        counters = result["metadata"]["counters"]
        for name, value in counters.items():
            if name != "initial_weight":
                state["counters"][name] = state["counters"].get(name, 0)+value-previous.get(name, 0)
        entry.update(rounds=entry["rounds"]+1, counters=counters,
                     best_residual=report["mismatch_count"])
        state["attempts"] += 1
        runs += 1
        emit(dict(event="slice", attempt=state["attempts"], source_sha256=key,
                  source_path=entry["path"], rounds=entry["rounds"], valid=report["valid"],
                  best_residual=report["mismatch_count"], counters=counters))
        if report["valid"]:
            # Independently verified by search and checked again at publication.
            exact = verify_candidate(result, random_trials=64, seed=args.seed)
            if not exact["valid"] or exact["rank"] != args.rank:
                raise AssertionError("FOUND candidate failed independent exact verification")
            for suffix in (".json", ".verification.json", ".verify.py"):
                shutil.copyfile(prefix.with_suffix(suffix), root/("FOUND"+suffix))
            save(root/"FOUND.verification.json", exact)
            state["found"] = str(root/"FOUND.json")
            emit(dict(event="FOUND_EXACT", path=state["found"], verification=exact))
        save(manifest, state)
        if state["source_cursor"] % len(keys) == 0:
            scan()
    summary = dict(event="summary", sources=len(state["sources"]), attempts=state["attempts"],
                   counters=state["counters"], found=state.get("found"),
                   elapsed_seconds=time.monotonic()-started)
    save(manifest, state)
    save(root/"summary.json", summary)
    emit(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
