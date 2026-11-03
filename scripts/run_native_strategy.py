"""Run one bounded, verified native macro action, or benchmark its throughput."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.native_bridge import ACTION_PROFILES, NativeBridge, canonical_terms
from mmsearch.search import flip_search


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--action", choices=ACTION_PROFILES, default="exploit")
    parser.add_argument("--seconds", type=float, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--target-rank", type=int, default=92)
    parser.add_argument("--steps", type=int, default=10**12)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--cpu", help="taskset CPU list inherited by the native child")
    parser.add_argument("--archive-size", type=int, default=64)
    parser.add_argument("--benchmark-python", action="store_true")
    args = parser.parse_args()
    candidate = json.loads(args.input.read_text())
    bridge = NativeBridge(args.output_dir, binary=args.binary, source=args.source,
                          cpu_affinity=args.cpu, archive_size=args.archive_size)
    result = bridge.run(candidate, args.action, seconds=args.seconds, seed=args.seed,
                        target_rank=args.target_rank, step_limit=args.steps)
    summary = {key: result[key] for key in ("status", "action", "run_dir", "best_rank", "current_rank",
               "attempted_moves", "cpu_seconds", "wall_seconds", "novelty") if key in result}
    if args.benchmark_python and result["status"] == "ok":
        profile = ACTION_PROFILES[args.action]
        started = time.monotonic()
        _, stats = flip_search(canonical_terms(candidate), n=candidate["dimension"], rank=args.target_rank,
                               steps=args.steps, seconds=args.seconds, seed=args.seed, cyclic=profile.cyclic,
                               max_extra=profile.rank_headroom, plus_every=profile.plus_every,
                               restart_every=profile.restart_every)
        python_wall = time.monotonic()-started
        summary["benchmark"] = dict(
            native_attempted_moves=result["attempted_moves"], native_child_cpu_seconds=result["cpu_seconds"],
            native_macro_wall_seconds=result["wall_seconds"], python_attempted_moves=stats["steps"],
            python_wall_seconds=python_wall,
            note="Attempted moves in separate exact algorithms; trajectories and accepted transitions differ.")
        with (Path(result["run_dir"])/"benchmark.json").open("x") as stream:
            stream.write(json.dumps(summary, indent=2)+"\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
