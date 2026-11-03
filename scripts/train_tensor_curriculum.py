"""Bounded v2 dm_env training with separately labeled known-rank recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import sys
import time

for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mmsearch.native_bridge import NativeBridge
from mmsearch.rl_curriculum import (ContextController, ContextDmEnv, make_recovery_seed,
                                    sample_action)
from mmsearch.rl_search import _tuple_tree, _write
from mmsearch.search import decode_candidate
from mmsearch.verify import verify_candidate, write_standalone_verifier


def read_schedule(checkpoint):
    """Reject incomplete/torn v2 checkpoint+schedule publications before steps."""
    checkpoint = Path(checkpoint)
    sidecar = checkpoint.with_suffix(".schedule.json")
    version = json.loads(checkpoint.read_text())["format"]
    if not sidecar.exists():
        if version == "mmsearch-context-a2c-v2":
            raise ValueError("v2 scheduler checkpoint requires its matching schedule sidecar")
        return None
    value = json.loads(sidecar.read_text())
    if value.get("format") != "mmsearch-curriculum-schedule-v2":
        raise ValueError("unsupported schedule format")
    if value.get("checkpoint_sha256") != hashlib.sha256(checkpoint.read_bytes()).hexdigest():
        raise ValueError("schedule state does not match controller checkpoint")
    return value


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--resume", type=Path, required=True, help="warmed v1 or v2 main-task checkpoint")
    p.add_argument("--seconds", type=float, default=600)
    p.add_argument("--steps", type=int, default=10000000)
    p.add_argument("--cpu", type=int, required=True)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--events", type=Path, required=True)
    p.add_argument("--native-dir", type=Path, required=True)
    p.add_argument("--native-binary", type=Path)
    p.add_argument("--native-archive-size", type=int, default=8)
    p.add_argument("--native-seconds", type=float, default=2)
    p.add_argument("--recovery-fraction", type=float, default=0.2)
    p.add_argument("--recovery-seconds", type=float, default=10)
    p.add_argument("--record-segment-steps", type=int, default=64)
    p.add_argument("--known-rank", type=int, default=93)
    p.add_argument("--known-seed", type=Path, action="append", default=[])
    p.add_argument("--frozen", action="store_true")
    p.add_argument("--control", choices=("policy", "random"), default="policy")
    args = p.parse_args(argv)
    if args.seconds < 0 or args.steps < 0 or not 0 <= args.recovery_fraction <= 0.5:
        p.error("invalid total budget or recovery fraction (0..0.5)")
    if not 0 < args.native_seconds <= 5 or args.recovery_seconds <= 0 or args.record_segment_steps < 1:
        p.error("invalid action/episode budget")
    if not 1 <= args.native_archive_size <= 64:
        p.error("native archive size must be in 1..64")
    os.sched_setaffinity(0, {args.cpu})
    started = time.monotonic()
    bridge = NativeBridge(args.native_dir, binary=args.native_binary, cpu_affinity=[args.cpu],
                          archive_size=args.native_archive_size, max_seconds=5)
    agent = ContextController.load(args.resume, native_bridge=bridge)
    agent.native_only = True
    agent.native_seconds = args.native_seconds
    agent.train = not args.frozen and args.control == "policy"
    agent.control = args.control
    seeds = [set(t) for t in agent.seed_bank if len(t) == args.known_rank]
    for path in args.known_seed:
        value = json.loads(path.read_text())
        if not verify_candidate(value, random_trials=0)["valid"]:
            raise ValueError(f"invalid known seed: {path}")
        terms = decode_candidate(value, agent.n)
        if len(terms) != args.known_rank:
            raise ValueError("known seed has wrong supplied rank")
        seeds.append(set(terms))
    if args.recovery_fraction and not seeds:
        raise ValueError("no seed of declared known rank available for recovery")
    restored = read_schedule(args.resume)
    recovery_rng = random.Random(agent.seed+827319)
    main_cpu = recovery_cpu = 0.0
    recovery_episodes = recovery_successes = actions = 0
    if restored:
        recovery_rng.setstate(_tuple_tree(restored["rng"]))
        main_cpu, recovery_cpu = restored["record_cpu"], restored["recovery_cpu"]
        recovery_episodes, recovery_successes = restored["recovery_episodes"], restored["recovery_successes"]
    env = ContextDmEnv(lambda: agent)
    env.reset()
    stopping = False
    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    args.events.parent.mkdir(parents=True, exist_ok=True)
    stream = args.events.open("a", buffering=1)

    def emit(event):
        event.update(elapsed_seconds=time.monotonic()-started,
                     record_cpu=main_cpu, recovery_cpu=recovery_cpu)
        stream.write(json.dumps(event, allow_nan=False)+"\n")

    def execute(environment):
        before = time.process_time()
        step = environment.step(sample_action(environment.controller))
        event = environment.last_transition
        cpu = time.process_time()-before + float(event.get("native", {}).get("cpu_seconds", 0))
        event["dm_step_type"] = str(step.step_type)
        event["measured_total_cpu_seconds"] = cpu
        return event, cpu

    def persist():
        # Checkpoint at a task boundary: no recovery rollout can be silently lost.
        agent.save(args.checkpoint)
        _write(args.output, agent.candidate())
        _write(args.checkpoint.with_suffix(".schedule.json"), {
            "format": "mmsearch-curriculum-schedule-v2", "rng": recovery_rng.getstate(),
            "checkpoint_sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
            "record_cpu": main_cpu, "recovery_cpu": recovery_cpu,
            "recovery_episodes": recovery_episodes, "recovery_successes": recovery_successes,
            "recovery_fraction": args.recovery_fraction, "known_rank": args.known_rank,
            "record_target_rank": agent.target_rank, "actions_this_invocation": actions,
            "claim": "known recovery successes are not new rank records"})

    emit({"event": "start", "task_kind": "RECORD_SEARCH", "best_rank": len(agent.best),
          "known_rank": args.known_rank, "record_target_rank": agent.target_rank,
          "train": agent.train, "control": agent.control,
          "recovery_fraction": args.recovery_fraction})
    last_saved = time.monotonic()
    try:
        while not stopping and not agent.terminal and actions < args.steps and time.monotonic()-started < args.seconds:
            total_cpu = main_cpu+recovery_cpu
            should_recover = args.recovery_fraction and total_cpu > 0 and recovery_cpu/total_cpu < args.recovery_fraction
            if should_recover:
                # Finish main's rollout before other-task gradients alter weights.
                agent._learn()
                before = time.process_time()
                terms, provenance = make_recovery_seed(seeds, agent.n, recovery_rng)
                recovery_cpu += time.process_time()-before
                recovery = ContextController(terms, n=agent.n, target_rank=args.known_rank,
                                             seed=recovery_rng.getrandbits(31), seed_bank=[terms],
                                             provenance=[provenance], policy=agent.policy, ledger=agent.ledger,
                                             task_kind="KNOWN_RECOVERY", record_rank=agent.record_rank, native_bridge=bridge,
                                             native_seconds=args.native_seconds, native_only=True,
                                             train=agent.train, control=agent.control)
                recovery_env = ContextDmEnv(lambda: recovery)
                recovery_env.reset()
                recovery_episodes += 1
                episode_started = time.monotonic()
                emit({"event": "recovery_start", "episode": recovery_episodes, **provenance})
                while (not stopping and not recovery.terminal and actions < args.steps
                       and time.monotonic()-episode_started < args.recovery_seconds
                       and time.monotonic()-started < args.seconds):
                    event, cpu = execute(recovery_env)
                    actions += 1
                    recovery_cpu += cpu
                    emit({"event": "transition", "episode": recovery_episodes, **event})
                    if event["record_target_reached"]:
                        # A curriculum trajectory can discover a real record.
                        # Independently verify and promote it to the frozen main
                        # result before any task switch or further learning.
                        value = recovery.candidate()
                        report = verify_candidate(value, random_trials=0)
                        if not report["valid"] or report["rank"] > agent.record_rank:
                            raise AssertionError("recovery record promotion failed independent check")
                        payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()+b"\n"
                        digest = hashlib.sha256(payload).hexdigest()
                        record_dir = args.output.parent/"records"
                        record_dir.mkdir(parents=True, exist_ok=True)
                        record_path = record_dir/(digest+".json")
                        try:
                            with record_path.open("xb") as frozen:
                                frozen.write(payload)
                        except FileExistsError:
                            if record_path.read_bytes() != payload:
                                raise RuntimeError("record hash collision")
                        _write(record_dir/(digest+".verification.json"), report)
                        agent._verify(recovery.best, independent=True)
                        agent.best = recovery.best.copy()
                        agent.current = recovery.best.copy()
                        agent.terminal = True
                        agent.history.append({"step": agent.steps, "rank": len(agent.best),
                                              "source": "recovery_record_promotion"})
                        agent.provenance.append({"record_promoted_from": "KNOWN_RECOVERY",
                                                 "path": str(record_path), "sha256": digest})
                        emit({"event": "verified_record", "record_target_reached": True,
                              "rank": len(agent.best), "candidate": str(record_path),
                              "candidate_sha256": digest, "source_task": "KNOWN_RECOVERY"})
                        break
                recovery._learn()
                recovery_successes += recovery.terminal
                emit({"event": "recovery_end", "episode": recovery_episodes,
                      "known_recovery_success": recovery.terminal, "best_rank": len(recovery.best),
                      "record_target_reached": agent.terminal, "updates": agent.policy.updates})
                # Reset main's bounded novelty segment without resetting its
                # exact trajectory or monotone best rank.
                if not agent.terminal:
                    agent.new_segment()
            else:
                event, cpu = execute(env)
                actions += 1
                main_cpu += cpu
                emit({"event": "transition", **event})
                if event["improvement"] or agent.steps % 50 == 0:
                    print(json.dumps(event), flush=True)
                if agent.steps % args.record_segment_steps == 0:
                    agent.new_segment()
            if time.monotonic()-last_saved > 30:
                persist()
                last_saved = time.monotonic()
    finally:
        persist()
        report = verify_candidate(agent.candidate(), random_trials=8, seed=agent.seed)
        _write(args.output.with_suffix(".verification.json"), report)
        write_standalone_verifier(args.output.with_suffix(".verify.py"))
        emit({"event": "finish", "record_target_reached": agent.terminal,
              "best_rank": len(agent.best), "recovery_episodes": recovery_episodes,
              "recovery_successes": recovery_successes, "updates": agent.policy.updates,
              "global_novelty_paid": agent.ledger.paid})
        stream.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
