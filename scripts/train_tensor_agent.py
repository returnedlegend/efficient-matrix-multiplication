"""Bounded CPU training of an exact-F2 operator actor-critic.

Run from any directory. All persisted candidates are independently checked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

# Set BLAS limits before importing NumPy, including when parent forgot them.
for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_key] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mmsearch.rl_search import OperatorController, TinyActorCritic, _write
from mmsearch.search import decode_candidate, naive_terms
from mmsearch.verify import verify_candidate, write_standalone_verifier


def curriculum(policy, seconds, seed):
    """Train the same neural weights on naive 2x2 -> 7 and 3x3 -> <=26.

    One third of episodes use 3x3 (unknown outcome under the allotted budget).
    The rank-7 solution is never supplied to this curriculum.
    """
    started = time.monotonic()
    episodes = successes = updates = 0
    history = []
    while time.monotonic()-started < seconds:
        n = 3 if episodes % 3 == 2 else 2
        agent = OperatorController(naive_terms(n), n=n, target_rank=7 if n == 2 else 26,
                                   seed=seed+episodes, policy=policy, rollout=8)
        before = policy.updates
        remaining = max(0, seconds-(time.monotonic()-started))
        agent.run(seconds=min(0.5, remaining), steps=80)
        agent._learn()
        episodes += 1
        successes += agent.terminal
        updates += policy.updates-before
        history.append({"n": n, "rank": len(agent.best), "steps": agent.steps,
                        "target_reached": agent.terminal})
    return {"episodes": episodes, "successes": successes, "updates": updates,
            "elapsed_seconds": time.monotonic()-started, "history": history,
            "claim": "curriculum execution only; no held-out learning advantage established"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dimension", type=int, default=5)
    parser.add_argument("--rank", type=int, default=92)
    parser.add_argument("--initial", type=Path, action="append", default=[])
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--steps", type=int, default=10000000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--checkpoint", type=Path, default=Path("artifacts/rl/checkpoint.json"))
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/rl/best.json"))
    parser.add_argument("--events", type=Path)
    parser.add_argument("--pretrain-seconds", type=float, default=5)
    parser.add_argument("--initialize-only", action="store_true", help="warm the policy and save the exact initial main-task checkpoint without a main-task action")
    parser.add_argument("--save-every-seconds", type=float, default=30)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--native-only", action="store_true")
    parser.add_argument("--native-seconds", type=float, default=2)
    parser.add_argument("--native-binary", type=Path)
    parser.add_argument("--native-dir", type=Path)
    parser.add_argument("--native-archive-size", type=int, default=8,
                        help="bounded representative native states retained per action (1..64)")
    parser.add_argument("--frozen", action="store_true", help="hold neural parameters fixed (A/B control)")
    parser.add_argument("--control", choices=("policy", "random"), default="policy")
    args = parser.parse_args(argv)
    if args.seconds < 0 or args.steps < 0 or args.pretrain_seconds < 0 or args.save_every_seconds <= 0:
        parser.error("budgets must be nonnegative and save interval positive")
    if not 1 <= args.native_archive_size <= 64:
        parser.error("--native-archive-size must be between 1 and 64")
    if args.cpu is not None:
        os.sched_setaffinity(0, {args.cpu})
    started = time.monotonic()
    native = None
    if args.native or args.native_only:
        from mmsearch.native_bridge import NativeBridge
        native = NativeBridge(args.native_dir or args.checkpoint.parent/"native",
                              binary=args.native_binary,
                              cpu_affinity=None if args.cpu is None else [args.cpu], max_seconds=5,
                              archive_size=args.native_archive_size)
    training_report = None
    if args.resume:
        agent = OperatorController.load(args.resume, native_bridge=native)
        # CLI controls are deliberate overrides; RNG/model/partial rollout resume.
        agent.train = not args.frozen and args.control != "random"
        agent.control = args.control
    else:
        seeds, provenance = [], []
        for path in args.initial:
            candidate = json.loads(path.read_text())
            if not verify_candidate(candidate, random_trials=0)["valid"]:
                raise ValueError(f"invalid initial candidate: {path}")
            seeds.append(decode_candidate(candidate, args.dimension))
            provenance.append({"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                               "supplied_rank": len(candidate["terms"])})
        if not seeds:
            seeds = [naive_terms(args.dimension)]
            provenance = [{"generator": "naive", "dimension": args.dimension}]
        policy = TinyActorCritic(args.seed)
        if not args.frozen and args.control == "policy" and args.pretrain_seconds:
            training_report = curriculum(policy, min(args.pretrain_seconds, args.seconds), args.seed)
            _write(args.checkpoint.with_suffix(".curriculum.json"), training_report)
        agent = OperatorController(min(seeds, key=len), n=args.dimension, target_rank=args.rank,
                                   seed=args.seed, seed_bank=seeds, provenance=provenance,
                                   policy=policy, native_bridge=native, native_seconds=args.native_seconds,
                                   native_only=args.native_only, train=not args.frozen and args.control != "random",
                                   control=args.control)
    stopping = False
    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, stop)
    stream = None
    if args.events:
        args.events.parent.mkdir(parents=True, exist_ok=True)
        stream = args.events.open("a", buffering=1)
    last_saved = time.monotonic()
    base_steps = agent.steps
    print(json.dumps({"event": "start", "seed": agent.seed, "n": agent.n, "target_rank": agent.target_rank,
                      "initial_best_rank": len(agent.best), "train": agent.train,
                      "control": agent.control, "updates": agent.policy.updates,
                      "curriculum": None if training_report is None else {k: v for k, v in training_report.items() if k != "history"}}), flush=True)
    try:
        while not args.initialize_only and not stopping and not agent.terminal and agent.steps-base_steps < args.steps:
            if time.monotonic()-started >= args.seconds:
                break
            event = agent.step()
            event.update(event="transition", elapsed_seconds=time.monotonic()-started)
            if stream:
                stream.write(json.dumps(event)+"\n")
            if event["improvement"] or agent.steps % 100 == 0:
                print(json.dumps(event), flush=True)
            if time.monotonic()-last_saved >= args.save_every_seconds:
                agent.save(args.checkpoint)
                _write(args.output, agent.candidate())
                last_saved = time.monotonic()
    finally:
        if stream:
            stream.close()
        agent.save(args.checkpoint)
        candidate = agent.candidate()
        _write(args.output, candidate)
        report = verify_candidate(candidate, random_trials=8, seed=agent.seed)
        if not report["valid"]:
            raise AssertionError("independent final candidate rejection")
        _write(args.output.with_suffix(".verification.json"), report)
        write_standalone_verifier(args.output.with_suffix(".verify.py"))
    print(json.dumps({"event": "finish", "checkpoint": str(args.checkpoint), "candidate": str(args.output),
                      "elapsed_seconds": time.monotonic()-started, **candidate["metadata"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
