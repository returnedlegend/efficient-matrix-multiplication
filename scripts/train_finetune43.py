"""V43 continued A2C with 5% phase-local target-latency-screened frozen-source recovery CPU."""
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
from mmsearch.rl_curriculum import ContextController, ContextDmEnv, sample_action
from mmsearch.rl_pool_curriculum import FixedStepBridge
from mmsearch.rl_recovery43 import SourceRecoveryPool43
from mmsearch.rl_restart_curriculum import RecordSeeds
from mmsearch.rl_finetune43 import (Finetune43Controller, CHECKPOINT_FORMAT, SCHEDULE_FORMAT,
                                    phase_clock, phase_usage, recovery_due)
from mmsearch.rl_search import _tuple_tree, _write
from mmsearch.search import decode_candidate
from mmsearch.verify import verify_candidate, write_standalone_verifier


def read_schedule(checkpoint):
    """Read a coherent v4 migration or complete v43 publication, fail closed."""
    checkpoint = Path(checkpoint)
    payload = checkpoint.read_bytes()
    controller = json.loads(payload)
    expected = {CHECKPOINT_FORMAT: SCHEDULE_FORMAT,
                "mmsearch-restart-a2c-v4": "mmsearch-restart-curriculum-schedule-v4"}
    if controller.get("format") not in expected:
        raise ValueError("v43 requires a v4 or v43 checkpoint")
    sidecar = checkpoint.with_suffix(".schedule.json")
    if not sidecar.exists():
        raise ValueError("checkpoint requires its matching schedule sidecar")
    value = json.loads(sidecar.read_text())
    if value.get("format") != expected[controller["format"]]:
        raise ValueError("unsupported or mismatched schedule format")
    if value.get("checkpoint_sha256") != hashlib.sha256(payload).hexdigest():
        raise ValueError("schedule state does not match controller checkpoint")
    if not controller.get("restart_curriculum") or value.get("restart_context") != controller["restart_curriculum"]:
        raise ValueError("schedule restart state does not match controller checkpoint")
    if controller["format"] == CHECKPOINT_FORMAT:
        if not controller.get("finetune43") or value.get("finetune43") != controller["finetune43"]:
            raise ValueError("schedule phase does not match controller checkpoint")
        phase_usage(value["finetune43"]["clock"], value["record_cpu"], value["recovery_cpu"])
    return value


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--resume", type=Path, required=True, help="matched v4 migration or v43 checkpoint plus schedule")
    p.add_argument("--seconds", type=float, default=600)
    p.add_argument("--steps", type=int, default=10000000)
    p.add_argument("--main-cpu-budget", type=float, default=0, help="per-invocation measured main CPU limit;0unlimited; may overshoot by one bounded action")
    p.add_argument("--cpu", type=int, required=True)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--events", type=Path, required=True)
    p.add_argument("--native-dir", type=Path, required=True)
    p.add_argument("--native-binary", type=Path)
    p.add_argument("--native-archive-size", type=int, default=8)
    p.add_argument("--recovery-archive-size", type=int, default=1)
    p.add_argument("--native-seconds", type=float, default=2)
    p.add_argument("--recovery-fraction", type=float, default=0.05)
    p.add_argument("--recovery-seconds", type=float, default=10)
    p.add_argument("--record-segment-steps", type=int, default=64)
    p.add_argument("--known-rank", type=int, default=93)
    p.add_argument("--phase-id", default="finetune43-v1")
    p.add_argument("--record-seed", type=Path, action="append", required=True, help="exact known-rank seed, CLI order defines shared deterministic cycle")
    p.add_argument("--restart-record-cpu", type=float, default=300, help="measured main-task CPU between external restarts")
    p.add_argument("--recovery-pool", type=Path, required=True)
    p.add_argument("--recovery-step-limit", type=int, default=50000)
    p.add_argument("--recovery-max-actions", type=int, default=4)
    p.add_argument("--frozen", action="store_true")
    p.add_argument("--control", choices=("policy", "random"), default="policy")
    args = p.parse_args(argv)
    import math
    if not math.isfinite(args.seconds) or args.seconds < 0 or args.steps < 0 or not 0 <= args.recovery_fraction <= 0.5:
        p.error("invalid total budget or recovery fraction (0..0.5)")
    if not 0 < args.native_seconds <= 5 or args.recovery_seconds <= 0 or args.record_segment_steps < 1:
        p.error("invalid action/episode budget")
    if not 1 <= args.native_archive_size <= 64:
        p.error("native archive size must be in 1..64")
    if not 1 <= args.recovery_archive_size <= 8:
        p.error("recovery archive size must be in 1..8")
    if not math.isfinite(args.main_cpu_budget) or args.main_cpu_budget < 0:
        p.error("main CPU budget must be finite and nonnegative")
    if not math.isfinite(args.restart_record_cpu) or args.restart_record_cpu <= 0:
        p.error("restart record CPU must be finite and positive")
    if args.native_seconds != 2 or args.recovery_step_limit != 50000 or not 1 <= args.recovery_max_actions <= 4:
        p.error("v43 requires 2-second record actions, 50000 recovery steps, and at most 4 recovery actions")
    if args.recovery_fraction != 0.05 or args.known_rank != 93:
        p.error("v43 requires 5% recovery CPU and known rank 93")
    restored = read_schedule(args.resume)
    seeds = RecordSeeds(args.record_seed, n=5, known_rank=args.known_rank)
    os.sched_setaffinity(0, {args.cpu})
    started = time.monotonic()
    bridge = NativeBridge(args.native_dir/"record", binary=args.native_binary, cpu_affinity=[args.cpu],
                          archive_size=args.native_archive_size, max_seconds=5)
    pool = SourceRecoveryPool43(args.recovery_pool)
    if args.recovery_step_limit != pool.manifest["config"]["probe_steps"] or args.recovery_max_actions < 1:
        p.error("recovery step limit must match frozen pool probe budget; action cap must be positive")
    raw_recovery_bridge = NativeBridge(args.native_dir/"known-recovery", binary=args.native_binary,
                                       cpu_affinity=[args.cpu], archive_size=args.recovery_archive_size,
                                       max_seconds=5)
    recovery_bridge = FixedStepBridge(raw_recovery_bridge, args.recovery_step_limit)
    agent = Finetune43Controller.load(args.resume, native_bridge=bridge)
    if hashlib.sha256(args.resume.read_bytes()).hexdigest() != restored["checkpoint_sha256"]:
        raise ValueError("resume checkpoint changed while loading its schedule")
    if agent.n != 5 or agent.target_rank > 92 or agent.record_rank > 92:
        raise ValueError("v43 requires 5x5 record search targeting rank at most 92")
    agent.native_only = True
    agent.native_seconds = args.native_seconds
    agent.train = not args.frozen and args.control == "policy"
    agent.control = args.control
    if agent.n != pool.manifest["config"]["dimension"] or args.known_rank != pool.manifest["config"]["known_rank"]:
        raise ValueError("pool dimension/known target does not match training task")
    pool_context = {"pool_sha256": pool.sha256, "pool_path": str(pool.directory),
                    "recovery_step_limit": args.recovery_step_limit,
                    "recovery_max_actions": args.recovery_max_actions,
                    "known_rank": args.known_rank, "small_pool": pool.manifest["small_pool"],
                    "heldout_count": len(pool.heldout), "censoring": "fixed native attempts per recovery action",
                    "delayed_controls_max_episode_fraction": 0.2,
                    "archive_hook": "root-queued scripts/recovery_maintenance_v3.py; min_age60s verified lossless batches; records preserved",
                    "record_bridge": {"archive_size": bridge.archive_size,
                                      "binary_sha256": bridge.binary_sha256, "source_sha256": bridge.source_sha256,
                                      "code_hashes": bridge.code_hashes},
                    "recovery_bridge": {"archive_size": raw_recovery_bridge.archive_size,
                                        "binary_sha256": raw_recovery_bridge.binary_sha256,
                                        "source_sha256": raw_recovery_bridge.source_sha256,
                                        "code_hashes": raw_recovery_bridge.code_hashes}}
    migrating = not agent.finetune_context
    if not migrating and agent.pool_context != pool_context:
        raise ValueError("pool or censoring configuration changed across v43 resume")
    agent.pool_context = pool_context
    recovery_rng = random.Random(agent.seed+827319)
    main_cpu = recovery_cpu = 0.0
    recovery_episodes = recovery_successes = actions = 0
    delayed_used = 0
    if restored:
        recovery_rng.setstate(_tuple_tree(restored["rng"]))
        main_cpu, recovery_cpu = restored["record_cpu"], restored["recovery_cpu"]
        recovery_episodes, recovery_successes = restored["recovery_episodes"], restored["recovery_successes"]
        delayed_used = restored["delayed_used"]
        if not migrating and restored["pool_context"] != pool_context:
            raise ValueError("schedule pool or censoring configuration mismatch")
    if migrating:
        agent.finetune_context = {
            "clock": phase_clock(main_cpu, recovery_cpu, fraction=args.recovery_fraction,
                                 phase_id=args.phase_id, episode_origin=recovery_episodes,
                                 delayed_origin=delayed_used),
            "parent_checkpoint_sha256": restored["checkpoint_sha256"],
            "curriculum_sha256": pool.sha256,
            "novelty": "inherited lifetime cap; no new reward or renewed cap",
            "loss": "unchanged inherited actor-critic/Adam; auxiliary share controlled by CPU"}
    clock = agent.finetune_context["clock"]
    if (type(clock["episode_origin"]) is not int or type(clock["delayed_origin"]) is not int
            or not 0 <= clock["episode_origin"] <= recovery_episodes
            or not 0 <= clock["delayed_origin"] <= delayed_used):
        raise ValueError("invalid phase episode origins")
    if (clock["phase_id"] != args.phase_id or clock["recovery_fraction"] != args.recovery_fraction
            or agent.finetune_context["curriculum_sha256"] != pool.sha256):
        raise ValueError("phase identity or allocation changed across v43 resume")
    agent.bind_restarts(seeds, interval=args.restart_record_cpu, record_cpu=main_cpu)
    invocation_main_origin = main_cpu
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
        phase_record, phase_recovery = phase_usage(clock, main_cpu, recovery_cpu)
        event.update(phase_record_cpu=phase_record, phase_recovery_cpu=phase_recovery,
                     elapsed_seconds=time.monotonic()-started,
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
            "format": SCHEDULE_FORMAT, "rng": recovery_rng.getstate(),
            "restart_context": agent.restart_context, "finetune43": agent.finetune_context,
            "checkpoint_sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
            "record_cpu": main_cpu, "recovery_cpu": recovery_cpu,
            "recovery_episodes": recovery_episodes, "recovery_successes": recovery_successes,
            "pool_context": pool_context, "delayed_used": delayed_used,
            "recovery_fraction": args.recovery_fraction, "known_rank": args.known_rank,
            "record_target_rank": agent.target_rank, "actions_this_invocation": actions, "main_cpu_budget": args.main_cpu_budget,
            "invocation_main_cpu": main_cpu-invocation_main_origin,
            "claim": "known recovery successes are not new rank records"})

    emit({"event": "start", "task_kind": "RECORD_SEARCH", "best_rank": len(agent.best),
          "known_rank": args.known_rank, "record_target_rank": agent.target_rank,
          "train": agent.train, "control": agent.control,
          "recovery_fraction": args.recovery_fraction, "pool_context": pool_context,
          "restart_context": agent.restart_context, "finetune43": agent.finetune_context,
          "main_cpu_budget": args.main_cpu_budget, "invocation_main_origin": invocation_main_origin,
          "archive_runs_directory": str(args.native_dir/"known-recovery/runs")})
    last_saved = time.monotonic()
    try:
        while (not stopping and not agent.terminal and actions < args.steps and time.monotonic()-started < args.seconds
               and (not args.main_cpu_budget or main_cpu-invocation_main_origin < args.main_cpu_budget)):
            restarted = agent.restart_if_due(main_cpu)
            if restarted:
                emit(restarted)
            should_recover = recovery_due(clock, main_cpu, recovery_cpu)
            if should_recover:
                # Finish main's rollout before other-task gradients alter weights.
                agent._learn()
                before = time.process_time()
                task_key, task_candidate, task_entry = pool.choose(recovery_rng,
                    episode_index=recovery_episodes-clock["episode_origin"],
                    delayed_used=delayed_used-clock["delayed_origin"])
                terms = decode_candidate(task_candidate, agent.n)
                provenance = {"kind": "KNOWN_RECOVERY", "task_hash": task_key,
                              "task_bucket": task_entry["task_bucket"], "strict_all3_unknown": task_entry["strict_hard"],
                              "pool_sha256": pool.sha256,
                              "known_rank": args.known_rank, "start_rank": len(terms),
                              "training_split": "train", "probe_seed": task_entry.get("probe_seed"),
                              "probe_outcomes": task_entry["probes"],
                              "claim": "known bound recovery; finite empirical difficulty only"}
                delayed_used += task_entry["task_bucket"] == "delayed_control"
                recovery_cpu += time.process_time()-before
                recovery = ContextController(terms, n=agent.n, target_rank=args.known_rank,
                                             seed=recovery_rng.getrandbits(31), seed_bank=[terms],
                                             provenance=[provenance], policy=agent.policy, ledger=agent.ledger,
                                             task_kind="KNOWN_RECOVERY", record_rank=agent.record_rank, native_bridge=recovery_bridge,
                                             native_seconds=args.native_seconds, native_only=True,
                                             train=agent.train, control=agent.control)
                recovery_env = ContextDmEnv(lambda: recovery)
                recovery_env.reset()
                recovery_episodes += 1
                episode_started = time.monotonic()
                episode_actions = 0
                emit({"event": "recovery_start", "episode": recovery_episodes, **provenance})
                while (not stopping and not recovery.terminal and actions < args.steps
                       and episode_actions < args.recovery_max_actions
                       and time.monotonic()-episode_started < args.recovery_seconds
                       and time.monotonic()-started < args.seconds):
                    event, cpu = execute(recovery_env)
                    actions += 1
                    episode_actions += 1
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
                      "record_target_reached": agent.terminal, "updates": agent.policy.updates,
                      "task_hash": task_key, "task_bucket": task_entry["task_bucket"],
                      "episode_actions": episode_actions,
                      "censored": not recovery.terminal})
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
                if not agent.terminal and agent.steps % args.record_segment_steps == 0:
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
