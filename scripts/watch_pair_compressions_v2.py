"""Auxiliary watcher V2: measured CPU debt with ten-second policy cadence.

This does not register a core reservation, alter workers, or inspect residual
walks. Rank93 is a research checkpoint; no-drop results never establish UNSAT.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import sys
import threading
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from mmsearch.auxiliary_pair_watcher import (SourceError, cooldown, cpu_used,
    discover_sources, policy, read_source, run_case, strict_json)
from mmsearch.kernel_coset_seeds import exclusive
from mmsearch.recombine import save
from scripts.rl_campaign_queue import process_identity
from scripts.scan_slice_compressions import _freeze_first_winner, _winner_eligible


def freeze_json(path, value):
    exclusive(path, (json.dumps(value, sort_keys=True, indent=2)+"\n").encode())


class PolicyCache:
    def __init__(self, campaign, *, clock=time.monotonic, reader=policy, cpu=cpu_used):
        self.campaign, self.clock, self.reader, self.cpu = campaign, clock, reader, cpu
        self.checked = -float("inf")
        self.value = (None, None)
        self.last_policy_elapsed = self.last_policy_cpu_seconds = 0.0

    def get(self):
        if self.clock()-self.checked >= 10:
            started, before_cpu = self.clock(), self.cpu()
            try:
                self.value = self.reader(self.campaign)
            except Exception as exc:
                self.value = (None, f"invalid campaign/queue policy: {type(exc).__name__}: {exc}")
            self.checked = self.clock()
            self.last_policy_elapsed = self.clock()-started
            self.last_policy_cpu_seconds = self.cpu()-before_cpu
        return self.value


def cooldown_phase(*, cycle_start, cycle_cpu, interval, quota, deadline, stop,
                   check_policy, heartbeat, clock=time.monotonic, wall=time.time,
                   cpu=cpu_used, sleeper=time.sleep, next_policy_due=lambda:float("inf")):
    """Account policy/heartbeat IO, then sleep toward that measured target.

    A completed short final sleep returns directly, avoiding a self-feeding
    policy/heartbeat loop. Long waits check at most once per ten-second chunk.
    """
    while not stop():
        if wall() >= deadline:
            return "global deadline reached"
        reason = check_policy()
        if reason:
            return reason
        remaining = cooldown(cpu()-cycle_cpu, clock()-cycle_start, interval, quota)
        if remaining <= 0:
            return None
        heartbeat(remaining)
        # Include the policy read AND heartbeat serialization in the target.
        remaining = cooldown(cpu()-cycle_cpu, clock()-cycle_start, interval, quota)
        if remaining <= 0:
            return None
        target = clock()+remaining
        sleep_seconds = min(10.0, remaining, max(0, deadline-wall()),
                            max(0, next_policy_due()-clock()))
        if sleep_seconds <= 0:
            if wall() >= deadline:
                return "global deadline reached"
            continue
        sleeper(sleep_seconds)
        if stop():
            return "self stop requested"
        if wall() >= deadline:
            return "global deadline reached"
        if clock() >= target:
            return None
    return "self stop requested"


def process_sources(sources, root, cache, *, deadline, max_new=4,
                    cycle_cpu_seconds=0.25, per_case_seconds=1,
                    stop=lambda:False, policy_check=lambda:None, runner=run_case,
                    freezer=_freeze_first_winner, implementation_sha256="unversioned"):
    """One measured cycle; never processes a second source after a record."""
    start_cpu, started = cpu_used(), time.monotonic()
    processed, events, winner = 0, [], False
    for source in sources:
        if stop() or time.time() >= deadline or policy_check() is not None:
            break
        remaining_cpu = cycle_cpu_seconds-(cpu_used()-start_cpu)
        if remaining_cpu <= 0 or processed >= max_new:
            break
        raw = None
        try:
            candidate, raw, raw_sha, key, normalization = read_source(source)
        except SourceError as exc:
            key = "parse-error-"+exc.factor_key
            if key in cache:
                continue
            processed += 1
            cache[key] = dict(status="ERROR", error=str(exc))
            event = dict(status="ERROR", error=str(exc), factor_key=key, source=source)
            directory = root/"cases"/implementation_sha256/key
            if getattr(exc, "raw", None) is not None:
                exclusive(directory/"source.raw", exc.raw)
                event["raw_sha256"] = hashlib.sha256(exc.raw).hexdigest()
            freeze_json(directory/"report.json", event)
            events.append(event)
            continue
        except OSError as exc:
            events.append(dict(status="ERROR", error=f"{type(exc).__name__}: {exc}", source=source))
            continue
        if key in cache and cache[key]["status"] not in ("CPU_BUDGET", "TIME_BUDGET", "STOPPED"):
            continue
        processed += 1
        attempt = cache.get(key, {}).get("attempts", 0)+1
        directory = root/"cases"/implementation_sha256/key/f"attempt-{attempt:04d}"
        exclusive(directory/"source.raw", raw)
        freeze_json(directory/"input.json", candidate)
        event = dict(source=source, raw_sha256=raw_sha, full_term_sha256=key,
            normalization=normalization, attempt=attempt, directory=str(directory.resolve()))
        if normalization["canonical_terms"] > 100:
            response = dict(status="SKIPPED", reason="more than100 active full products")
        else:
            remaining_cpu = cycle_cpu_seconds-(cpu_used()-start_cpu)
            response = runner(candidate, wall_seconds=min(per_case_seconds, max(0, deadline-time.time())),
                cpu_seconds=max(0, remaining_cpu), stop=stop)
        result = response.pop("result", None)
        event.update(response)
        if result is not None:
            output = result.pop("candidate")
            freeze_json(directory/"output.json", output)
            freeze_json(directory/"proof.json", result)
            event.update(input_rank=result["source_rank"], output_rank=result["final_rank"],
                exact_entries_checked=result["final_verification"]["exact_entries_checked"],
                output_sha256=hashlib.sha256((directory/"output.json").read_bytes()).hexdigest(),
                fixed_point=result["fixed_point"], scope="derived certificate only; original native group count is unchanged; no UNSAT claim")
            if _winner_eligible(output, result):
                event["winner_checksums"] = freezer(root, output)
                event["winner"] = True
                winner = True
        freeze_json(directory/"report.json", event)
        freeze_json(directory/"checksums.json", {str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file()})
        cache[key] = dict(status=event["status"], attempts=attempt, report=str((directory/"report.json").resolve()),
            output_rank=event.get("output_rank"), raw_sha256=raw_sha)
        events.append(event)
        if winner:
            break
    return dict(events=events, processed=processed, winner=winner,
        cpu_seconds=cpu_used()-start_cpu, wall_seconds=time.monotonic()-started)


def main(argv=None):
    watcher_started, watcher_cpu_start = time.monotonic(), cpu_used()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--cpu", type=int, default=2)
    parser.add_argument("--memory-mb", type=int, default=512)
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--max-new-per-cycle", type=int, default=4)
    parser.add_argument("--cycle-cpu-seconds", type=float, default=0.25)
    parser.add_argument("--per-case-seconds", type=float, default=1)
    args = parser.parse_args(argv)
    if (args.cpu != 2 or not 128 <= args.memory_mb <= 512 or not 1 <= args.max_new_per_cycle <= 4 or
            any(not math.isfinite(v) or v <= 0 for v in (args.interval,args.cycle_cpu_seconds,args.per_case_seconds)) or
            args.per_case_seconds > 1 or args.cycle_cpu_seconds/args.interval > 0.025):
        parser.error("CPU2, memory128..512MiB, <=4cases, <=1s/case and <=2.5% average CPU quota required")
    os.sched_setaffinity(0, {2})
    resource.setrlimit(resource.RLIMIT_AS, (args.memory_mb*1024**2, args.memory_mb*1024**2))
    campaign = args.campaign.resolve()
    lock = (campaign/"auxiliary_pair_watcher.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    root = campaign/"auxiliary-pair-watcher"
    root.mkdir(exist_ok=True)
    stopped = {"reason":None}
    stop_event = threading.Event()
    def terminate(sig, _frame):
        stopped["reason"] = f"self signal {sig}"
        stop_event.set()
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    code = {}
    for name in ("scripts/watch_pair_compressions_v2.py", "scripts/watch_pair_compressions.py", "mmsearch/auxiliary_pair_watcher.py",
        "mmsearch/pair_column_compression.py", "mmsearch/free_factor_sat.py", "mmsearch/slice_compression.py",
        "mmsearch/recombine.py", "mmsearch/recombine_sat.py", "mmsearch/search.py", "mmsearch/verify.py",
        "mmsearch/kernel_coset_seeds.py", "scripts/scan_slice_compressions.py", "scripts/rl_campaign_queue.py",
        "tests/test_auxiliary_pair_watcher.py", "tests/test_auxiliary_pair_watcher_v2.py"):
        raw = (REPO/name).read_bytes()
        code[name] = hashlib.sha256(raw).hexdigest()
    version = hashlib.sha256(json.dumps(code, sort_keys=True).encode()).hexdigest()
    for name in code:
        destination = root/"code"/version/name
        raw = (REPO/name).read_bytes()
        if destination.exists():
            if destination.read_bytes() != raw:
                raise ValueError("frozen watcher code mismatch")
        else:
            exclusive(destination, raw)
    cache_path = root/"cache.json"
    all_cache = strict_json(cache_path.read_bytes()) if cache_path.exists() else {}
    cache = all_cache.setdefault(version, {})
    status = dict(pid=os.getpid(), process_identity=process_identity(os.getpid()), state="starting",
        auxiliary=True, queued_core_reservation=False, cpu=2, affinity=sorted(os.sched_getaffinity(0)),
        memory_mb=args.memory_mb, interval=args.interval, max_new_per_cycle=args.max_new_per_cycle,
        cycle_cpu_seconds=args.cycle_cpu_seconds, per_case_seconds=args.per_case_seconds,
        version=2, policy_poll_seconds=10, cooldown_sleep_chunk_seconds=10,
        code_sha256=code, implementation_sha256=version, cycles=0, processed=0,
        scope="checkpoint/full-global-shadow derived exact certificates; no original worker modification or UNSAT claim")
    status_path = campaign/"auxiliary_pair_watcher.json"
    cached_policy = PolicyCache(campaign)
    try:
        while not stopped["reason"]:
            cycle_start, cycle_cpu = time.monotonic(), cpu_used()
            deadline, reason = cached_policy.get()
            if reason:
                stopped["reason"] = reason
                break
            if (root/"WINNER.json").exists():
                stopped["reason"] = "first winner already frozen"
                break
            status.update(state="running", deadline_unix=deadline, updated_unix=time.time())
            save(status_path, status)
            sources, errors = discover_sources(campaign, REPO, process_identity)
            def check_policy():
                return cached_policy.get()[1]
            remaining_cpu = max(0, args.cycle_cpu_seconds-(cpu_used()-cycle_cpu))
            cycle = process_sources(sources, root, cache, deadline=deadline,
                max_new=args.max_new_per_cycle, cycle_cpu_seconds=remaining_cpu,
                per_case_seconds=args.per_case_seconds, stop=lambda:bool(stopped["reason"]),
                policy_check=check_policy, implementation_sha256=version)
            status["cycles"] += 1
            status["processed"] += cycle["processed"]
            status.update(last_cycle=cycle, discovery_errors=errors, last_sources=sources,
                last_cycle_total_cpu_seconds=cpu_used()-cycle_cpu, process_and_child_cpu_seconds=cpu_used(),
                target_average_cpu_fraction=min(0.025,args.cycle_cpu_seconds/args.interval),
                observed_cpu_seconds_since_main=cpu_used()-watcher_cpu_start,
                observed_elapsed_seconds_since_main=time.monotonic()-watcher_started,
                campaign_raw_sha256=hashlib.sha256((campaign/"campaign.json").read_bytes()).hexdigest(),
                updated_unix=time.time(), state="running")
            save(cache_path, all_cache)
            save(status_path, status)
            with (root/"events.jsonl").open("a") as handle:
                for event in errors+cycle["events"]:
                    handle.write(json.dumps(dict(unix=time.time(), implementation_sha256=version, **event), sort_keys=True)+"\n")
            if cycle["winner"]:
                stopped["reason"] = "first genuine record frozen"
                break
            def heartbeat(remaining):
                elapsed = time.monotonic()-watcher_started
                measured_cpu = cpu_used()-watcher_cpu_start
                status.update(state="cooldown", cooldown_remaining=remaining,
                    last_policy_elapsed=cached_policy.last_policy_elapsed,
                    last_policy_cpu_seconds=cached_policy.last_policy_cpu_seconds,
                    last_policy_age_seconds=time.monotonic()-cached_policy.checked,
                    observed_cpu_seconds_since_main=measured_cpu,
                    observed_elapsed_seconds_since_main=elapsed,
                    observed_average_cpu_fraction=measured_cpu/elapsed if elapsed>0 else None,
                    updated_unix=time.time())
                save(status_path,status)
            reason=cooldown_phase(cycle_start=cycle_start,cycle_cpu=cycle_cpu,
                interval=args.interval,quota=args.cycle_cpu_seconds,deadline=deadline,
                stop=lambda:bool(stopped["reason"]),check_policy=check_policy,
                heartbeat=heartbeat,sleeper=stop_event.wait,
                next_policy_due=lambda:cached_policy.checked+10)
            if reason and not stopped["reason"]:
                stopped["reason"]=reason
    finally:
        status.update(state="stopped", stop_reason=stopped["reason"] or "watcher exception",
            updated_unix=time.time())
        save(status_path, status)
        lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
