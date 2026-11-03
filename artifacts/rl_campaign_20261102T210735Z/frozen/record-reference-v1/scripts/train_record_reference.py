"""Frozen random record-only reference using the unchanged v4 dm_env controller."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time
import uuid

for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mmsearch.native_bridge import NativeBridge
from mmsearch.rl_curriculum import ContextDmEnv, sample_action
from mmsearch.rl_pool_curriculum import HardRecoveryPool
from mmsearch.rl_restart_curriculum import (RestartRecordController, RecordSeeds,
                                             CHECKPOINT_FORMAT, SCHEDULE_FORMAT)
from mmsearch.rl_search import _write
from scripts.train_restart_tensor_agent import read_schedule as read_v4_schedule
from mmsearch.verify import verify_candidate, write_standalone_verifier


def driver_identity():
    return {"format": "mmsearch-record-reference-driver-v1",
            "filename": Path(__file__).name,
            "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "recovery_fraction": 0.0, "control": "random", "train": False}


def read_schedule(checkpoint):
    """Permit one v4 migration; reference resumes require this exact driver."""
    checkpoint = Path(checkpoint)
    schedule = read_v4_schedule(checkpoint)
    value = json.loads(checkpoint.read_text())
    if value["format"] != CHECKPOINT_FORMAT:
        raise ValueError("record reference migration requires a v4 checkpoint")
    if value["config"]["control"] != "random" or value["config"]["train"]:
        raise ValueError("record reference requires an already frozen random checkpoint")
    identity = driver_identity()
    recorded = value.get("record_reference")
    digest = value.get("code_hashes", {}).get(identity["filename"])
    if recorded is None:
        if (digest is not None or schedule.get("record_reference") is not None
                or identity["filename"] in schedule.get("code_hashes", {})):
            raise ValueError("incomplete reference driver identity")
    elif (recorded != identity or digest != identity["sha256"]
          or schedule.get("record_reference") != identity
          or schedule.get("code_hashes", {}).get(identity["filename"]) != identity["sha256"]):
        raise ValueError("reference driver identity changed or schedule mismatched")
    return schedule


def save_reference(agent, path):
    """Publish the controller and actual entrypoint identity in one replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name("."+path.name+".reference-private-"+uuid.uuid4().hex)
    try:
        agent.save(staged)
        value = json.loads(staged.read_text())
        identity = driver_identity()
        value["record_reference"] = identity
        value["code_hashes"][identity["filename"]] = identity["sha256"]
        _write(path, value)
    finally:
        staged.unlink(missing_ok=True)
        staged.with_suffix(staged.suffix+".tmp").unlink(missing_ok=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--resume", type=Path, required=True, help="matched frozen random v4 checkpoint plus schedule")
    p.add_argument("--seconds", type=float, default=600)
    p.add_argument("--steps", type=int, default=10000000)
    p.add_argument("--cpu", type=int, required=True)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--phase-manifest", type=Path, help="default checkpoint directory/phase.manifest.json")
    p.add_argument("--events", type=Path, required=True)
    p.add_argument("--native-dir", type=Path, required=True)
    p.add_argument("--native-binary", type=Path)
    p.add_argument("--native-archive-size", type=int, default=8)
    p.add_argument("--recovery-archive-size", type=int, default=1)
    p.add_argument("--native-seconds", type=float, default=2)
    p.add_argument("--recovery-fraction", type=float, default=0.0)
    p.add_argument("--recovery-seconds", type=float, default=10)
    p.add_argument("--record-segment-steps", type=int, default=64)
    p.add_argument("--known-rank", type=int, default=93)
    p.add_argument("--known-seed", type=Path, action="append", default=[])
    p.add_argument("--record-seed", type=Path, action="append", required=True, help="exact known-rank seed, CLI order defines shared deterministic cycle")
    p.add_argument("--restart-record-cpu", type=float, default=300, help="measured main-task CPU between external restarts")
    p.add_argument("--recovery-pool", type=Path, required=True)
    p.add_argument("--recovery-step-limit", type=int, default=50000)
    p.add_argument("--recovery-max-actions", type=int, default=4)
    p.add_argument("--frozen", action="store_true")
    p.add_argument("--control", choices=("policy", "random"), default="random")
    args = p.parse_args(argv)
    if args.control != "random" or not args.frozen:
        p.error("record reference requires --control random --frozen")
    if args.seconds < 0 or args.steps < 0 or not 0 <= args.recovery_fraction <= 0.5:
        p.error("invalid total budget or recovery fraction (0..0.5)")
    if not 0 < args.native_seconds <= 5 or args.recovery_seconds <= 0 or args.record_segment_steps < 1:
        p.error("invalid action/episode budget")
    if not 1 <= args.native_archive_size <= 64:
        p.error("native archive size must be in 1..64")
    if not 1 <= args.recovery_archive_size <= 8:
        p.error("recovery archive size must be in 1..8")
    import math
    if not math.isfinite(args.restart_record_cpu) or args.restart_record_cpu <= 0:
        p.error("restart record CPU must be finite and positive")
    if args.native_seconds != 2 or args.recovery_step_limit != 50000 or not 1 <= args.recovery_max_actions <= 4:
        p.error("v4 requires 2-second record actions, 50000 recovery steps, and at most 4 recovery actions")
    if args.recovery_fraction != 0 or args.known_rank != 93:
        p.error("record reference requires zero recovery CPU and known rank 93")
    restored = read_schedule(args.resume)
    seeds = RecordSeeds(args.record_seed, n=5, known_rank=args.known_rank)
    os.sched_setaffinity(0, {args.cpu})
    started = time.monotonic()
    bridge = NativeBridge(args.native_dir/"record", binary=args.native_binary, cpu_affinity=[args.cpu],
                          archive_size=args.native_archive_size, max_seconds=5)
    pool = HardRecoveryPool(args.recovery_pool)
    if args.recovery_step_limit != pool.manifest["config"]["probe_steps"] or args.recovery_max_actions < 1:
        p.error("recovery step limit must match frozen pool probe budget; action cap must be positive")
    agent = RestartRecordController.load(args.resume, native_bridge=bridge)
    if hashlib.sha256(args.resume.read_bytes()).hexdigest() != restored["checkpoint_sha256"]:
        raise ValueError("resume checkpoint changed while loading its schedule")
    if agent.n != 5 or agent.target_rank > 92 or agent.record_rank > 92:
        raise ValueError("v4 requires 5x5 record search targeting rank at most 92")
    agent.native_only = True
    agent.native_seconds = args.native_seconds
    agent.train = False
    agent.control = args.control
    if agent.n != pool.manifest["config"]["dimension"] or args.known_rank != pool.manifest["config"]["known_rank"]:
        raise ValueError("pool dimension/known target does not match training task")
    pool_context = {"pool_sha256": pool.sha256, "pool_path": str(pool.directory),
                    "recovery_step_limit": args.recovery_step_limit,
                    "recovery_max_actions": args.recovery_max_actions,
                    "known_rank": args.known_rank, "small_pool": pool.manifest["small_pool"],
                    "heldout_count": len(pool.heldout), "censoring": "fixed native attempts per recovery action",
                    "delayed_controls_max_episode_fraction": 0.2,
                    "record_bridge": {"archive_size": bridge.archive_size,
                                      "binary_sha256": bridge.binary_sha256, "source_sha256": bridge.source_sha256,
                                      "code_hashes": bridge.code_hashes},
                    "recovery_bridge": {"archive_size": args.recovery_archive_size,
                                        "binary_sha256": bridge.binary_sha256,
                                        "source_sha256": bridge.source_sha256,
                                        "code_hashes": bridge.code_hashes}}
    if agent.pool_context and agent.pool_context != pool_context:
        raise ValueError("pool or censoring configuration changed across resume")
    agent.pool_context = pool_context
    main_cpu = recovery_cpu = 0.0
    recovery_episodes = recovery_successes = actions = 0
    delayed_used = 0
    if restored:
        main_cpu, recovery_cpu = restored["record_cpu"], restored["recovery_cpu"]
        recovery_episodes, recovery_successes = restored["recovery_episodes"], restored["recovery_successes"]
        delayed_used = restored["delayed_used"]
        if restored["pool_context"] != pool_context:
            raise ValueError("schedule pool or censoring configuration mismatch")
    agent.bind_restarts(seeds, interval=args.restart_record_cpu, record_cpu=main_cpu)
    identity = driver_identity()
    manifest_path = args.phase_manifest or args.checkpoint.parent/"phase.manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.update(record_reference=identity, actual_entrypoint=str(Path(__file__).resolve()),
                    resume=str(args.resume.resolve()), checkpoint=str(args.checkpoint.resolve()),
                    restart_context=agent.restart_context, pool_context=pool_context)
    _write(manifest_path, manifest)
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
        # The reference has only main-task actions; recovery bookkeeping is retained.
        save_reference(agent, args.checkpoint)
        candidate = agent.candidate()
        candidate["metadata"]["record_reference"] = identity
        _write(args.output, candidate)
        _write(args.checkpoint.with_suffix(".schedule.json"), {
            "format": SCHEDULE_FORMAT, "rng": restored["rng"],
            "record_reference": identity, "code_hashes": {identity["filename"]: identity["sha256"]},
            "restart_context": agent.restart_context,
            "checkpoint_sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
            "record_cpu": main_cpu, "recovery_cpu": recovery_cpu,
            "recovery_episodes": recovery_episodes, "recovery_successes": recovery_successes,
            "pool_context": pool_context, "delayed_used": delayed_used,
            "recovery_fraction": args.recovery_fraction, "known_rank": args.known_rank,
            "record_target_rank": agent.target_rank, "actions_this_invocation": actions,
            "claim": "known recovery successes are not new rank records"})

    emit({"event": "start", "task_kind": "RECORD_SEARCH", "best_rank": len(agent.best),
          "known_rank": args.known_rank, "record_target_rank": agent.target_rank,
          "train": agent.train, "control": agent.control,
          "recovery_fraction": args.recovery_fraction, "pool_context": pool_context,
          "restart_context": agent.restart_context, "record_reference": identity})
    last_saved = time.monotonic()
    try:
        while not stopping and not agent.terminal and actions < args.steps and time.monotonic()-started < args.seconds:
            restarted = agent.restart_if_due(main_cpu)
            if restarted:
                emit(restarted)
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
