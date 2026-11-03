#!/usr/bin/env python3
"""Read-only scalar status for a bounded exact-F2 RL campaign.

Uses only the standard library. Missing, replaced, and partially written JSON
are reported without failing. JSONL reads are bounded, with incomplete windows
explicitly identified. No policy tensors, RNG states, or certificates are printed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import time

DEFAULT = "artifacts/rl_campaign_20261102T210735Z"
UTC = dt.timezone.utc


def read_json(path, maximum=8*1024*1024):
    try:
        with path.open("rb") as stream:
            raw = stream.read(maximum+1)
        if len(raw) > maximum:
            return {}, "size_limit"
        value = json.loads(raw)
        if not isinstance(value, dict):
            return {}, "not_object"
        return value, "ok"
    except (OSError, ValueError, RecursionError) as exc:
        return {}, type(exc).__name__


def events(path, maximum):
    """Yield complete JSON objects from a bounded snapshot, excluding partial EOF."""
    try:
        with path.open("rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            start = max(0, size-maximum)
            stream.seek(start)
            raw = stream.read(size-start)
        lines = raw.splitlines(keepends=True)
        if start and lines:
            lines = lines[1:]
        result, malformed = [], 0
        for line in lines:
            if not line.endswith(b"\n"):
                malformed += 1
                continue
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    result.append(value)
                else:
                    malformed += 1
            except (ValueError, RecursionError):
                malformed += 1
        return result, {"window_complete": start == 0, "bytes_read": len(raw),
                        "malformed_or_partial_lines": malformed, "read_status": "ok"}
    except OSError as exc:
        return [], {"window_complete": False, "bytes_read": 0,
                    "malformed_or_partial_lines": 0, "read_status": type(exc).__name__}


def scalar(value):
    return isinstance(value, (str, int, float, bool)) or value is None


def file_age(path, now):
    try:
        return round(max(0, now-path.stat().st_mtime), 1)
    except OSError:
        return None


def process_table():
    try:
        result = subprocess.run(["ps", "-eo", "pid=,ppid=,rss=,etimes=,comm="],
                                capture_output=True, text=True, timeout=2, check=True)
        return {int(p): {"parent": int(pp), "rss_kib": int(rss), "age_seconds": int(age), "name": name}
                for p, pp, rss, age, name in (line.split(None, 4) for line in result.stdout.splitlines())}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def descendants(root, table):
    found, todo = set(), [root]
    children = {}
    for pid, row in table.items():
        children.setdefault(row["parent"], []).append(pid)
    while todo:
        pid = todo.pop()
        if pid in found or pid not in table:
            continue
        found.add(pid)
        todo.extend(children.get(pid, ()))
    return found


def timestamp(value):
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, AttributeError):
        return None


def summarize(directory: Path, max_event_bytes=16*1024*1024, *, scan_disk=True):
    now = time.time()
    config, config_status = read_json(directory/"campaign.json")
    deadline = timestamp(config.get("deadline_utc"))
    report = {"utc": dt.datetime.fromtimestamp(now, UTC).isoformat(), "directory": str(directory),
              "config_read_status": config_status, "started_utc": config.get("started_utc"),
              "deadline_utc": config.get("deadline_utc"),
              "remaining_seconds": None if deadline is None else max(0, round(deadline-now)),
              "deadline_reached": None if deadline is None else now >= deadline,
              "field": config.get("field"), "target_rank": config.get("target_rank")}
    table, used, jobs = process_table(), set(), {}
    for path in sorted(directory.glob("*.running.json")):
        job, status = read_json(path)
        pid = job.get("pid")
        row = table.get(pid)
        started = timestamp(job.get("started_utc"))
        live = bool(row and (started is None or abs(now-started-row["age_seconds"]) < 10))
        group = descendants(pid, table) if live else set()
        used.update(group)
        jobs[path.name.removesuffix(".running.json")] = {
            "read_status": status, "pid": pid, "live": live, "cpu": job.get("cpu"),
            "processes": len(group), "rss_bytes": sum(table[p]["rss_kib"]*1024 for p in group),
            "wall_seconds": job.get("wall_seconds")}
    report.update(jobs=jobs, active_jobs=sum(j["live"] for j in jobs.values()),
                  live_worker_tree_rss_bytes=sum(table[p]["rss_kib"]*1024 for p in used),
                  live_worker_tree_processes=len(used))
    guard_count = 0
    for pid, row in table.items():
        if "python" not in row["name"]:
            continue
        try:
            args = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace").split("\0")
            if any(Path(a).name == "campaign_guard.py" for a in args):
                if any(Path(a).resolve() == directory.resolve() for a in args if a):
                    guard_count += 1
        except OSError:
            pass
    report["matching_guard_processes"] = guard_count
    resources, status = read_json(directory/"resource_status.json")
    report["guard_resources"] = {k: v for k, v in resources.items() if scalar(v)}
    report["guard_resources"]["read_status"] = status
    stop, _ = read_json(directory/"guard_stopped.json")
    report["guard_stopped"] = {k: v for k, v in stop.items() if scalar(v)}
    rl, best_ranks = {}, []
    for path in sorted(directory.glob("*/checkpoint.json")):
        checkpoint, status = read_json(path)
        state, policy = checkpoint.get("state", {}), checkpoint.get("policy", {})
        config = checkpoint.get("config", {})
        summary = {"read_status": status, "format": checkpoint.get("format"),
                   "current_rank": len(checkpoint["current"]) if isinstance(checkpoint.get("current"), list) else None,
                   "best_rank": len(checkpoint["best"]) if isinstance(checkpoint.get("best"), list) else None,
                   "steps": state.get("steps"), "updates": policy.get("updates"),
                   "control": config.get("control"), "train": config.get("train"),
                   "checkpoint_age_seconds": file_age(path, now)}
        actions = checkpoint.get("actions", [])
        summary["checkpoint_action_counts"] = dict(zip(actions, state.get("action_counts", [])))
        schedule, schedule_status = read_json(path.with_suffix(".schedule.json"))
        summary["schedule_read_status"] = schedule_status
        for key in ("record_cpu", "recovery_cpu", "recovery_episodes", "recovery_successes"):
            summary[key] = schedule.get(key, state.get("cpu_seconds", 0) if key == "record_cpu" else 0)
        rows, window = events(path.parent/"events.jsonl", max_event_bytes)
        summary["events"] = window
        counts, native_steps, record_successes = Counter(), 0, 0
        transition_cpu = 0.0
        for event in rows:
            if event.get("event") == "transition":
                counts[str(event.get("action", "unknown"))] += 1
                native_event = event.get("native") or {}
                native_steps += native_event.get("attempted_moves", 0) or 0
                transition_cpu += event.get("cpu_seconds", 0) or 0
                record_successes += bool(event.get("record_target_reached", event.get("terminal", False)))
                if event.get("task_kind", "RECORD_SEARCH") == "RECORD_SEARCH":
                    for src, dst in (("rank", "current_rank"), ("best_rank", "best_rank"),
                                     ("step", "steps"), ("updates", "updates")):
                        if src in event:
                            summary[dst] = event[src]
            for key in ("record_cpu", "recovery_cpu", "recovery_episodes", "recovery_successes"):
                if key in event:
                    summary[key] = event[key]
        if not schedule and window["window_complete"] and not any("record_cpu" in e for e in rows):
            summary["record_cpu"] = max(summary["record_cpu"], transition_cpu)
        summary.update(event_window_action_counts=dict(counts), native_moves_event_window=native_steps,
                       record_successes_event_window=record_successes,
                       recovery_successes_event_window=sum(e.get("event") == "recovery_end" and
                                                           bool(e.get("known_recovery_success")) for e in rows))
        rl[path.parent.name] = summary
        if isinstance(summary["best_rank"], int):
            best_ranks.append(summary["best_rank"])
    report["rl"] = rl
    sat = {}
    for path in sorted(directory.glob("*/results.jsonl")):
        rows, window = events(path, max_event_bytes)
        sat[path.parent.name] = {**window, "events_in_window": len(rows),
                                 "status_counts": dict(Counter(str(e["status"]) for e in rows if "status" in e)),
                                 "event_counts": dict(Counter(str(e.get("event", "unknown")) for e in rows))}
    report["sat"] = sat
    native = {}
    for path in sorted(directory.glob("*/phase-*/walk.stats.json")):
        stats, status = read_json(path)
        native[str(path.relative_to(directory))] = {k: stats.get(k) for k in
            ("steps", "current_rank", "best_rank", "elapsed_seconds", "target_reached", "exact")}
        native[str(path.relative_to(directory))]["read_status"] = status
        native[str(path.relative_to(directory))]["stats_age_seconds"] = file_age(path, now)
        if isinstance(stats.get("best_rank"), int):
            best_ranks.append(stats["best_rank"])
    report["native"] = native
    report["native_phase_steps_total"] = sum(row["steps"] or 0 for row in native.values())
    report["best_reported_rank"] = min(best_ranks) if best_ranks else None
    if not scan_disk:
        return report
    size, files, complete = 0, 0, True
    started_scan = time.monotonic()
    for root, _, names in os.walk(directory, followlinks=False):
        for name in names:
            try:
                size += (Path(root)/name).lstat().st_size
                files += 1
            except OSError:
                complete = False
        if time.monotonic()-started_scan > 2:
            complete = False
            break
    report["disk"] = {"file_bytes": size, "files": files, "scan_complete": complete,
                       "measurement": "logical file sizes; two-second traversal limit"}
    return report


def compact_summary(report, directory):
    """Project detailed scalar data without traversing the disk-usage tree."""
    resources = report["guard_resources"]
    arms = {}
    rl_windows = True
    rl_moves = 0
    for name, arm in report["rl"].items():
        if name == "warm":
            continue
        arms[name] = {key: arm.get(key) for key in
                      ("steps", "updates", "best_rank", "current_rank", "recovery_episodes",
                       "recovery_successes", "record_cpu", "recovery_cpu")}
        rl_windows &= arm["events"]["window_complete"]
        rl_moves += arm["native_moves_event_window"]
    sat_counts = Counter()
    for value in report["sat"].values():
        sat_counts.update(value["status_counts"])
    phase_rows = report["native"]
    phase_count = sum(path.is_dir() for path in directory.glob("*/phase-*"))
    phases_complete = (len(phase_rows) == phase_count
                       and all(row["read_status"] == "ok" for row in phase_rows.values()))
    return {
        "utc": report["utc"], "remaining_seconds": report["remaining_seconds"],
        "active_jobs": report["active_jobs"], "global_best_rank": report["best_reported_rank"],
        "rss_bytes": resources.get("rss_bytes"),
        "peak_rss_bytes": resources.get("maximum_observed_rss_bytes"),
        "rl": arms, "sat_status_counts": dict(sat_counts),
        "sat_event_windows_complete": bool(report["sat"]) and all(
            value["window_complete"] and value["malformed_or_partial_lines"] == 0
            for value in report["sat"].values()),
        "native_phase_steps": report["native_phase_steps_total"],
        "native_phase_stats_complete": phases_complete,
        "rl_native_attempts": rl_moves,
        "rl_event_windows_complete": bool(arms) and rl_windows and all(
            arm["events"]["malformed_or_partial_lines"] == 0
            for name, arm in report["rl"].items() if name != "warm"),
        "native_attempts_total": report["native_phase_steps_total"] + rl_moves,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?", default=Path(DEFAULT))
    parser.add_argument("--cpu", type=int, default=2, help="status process CPU affinity")
    parser.add_argument("--max-event-mib", type=int, default=16)
    parser.add_argument("--compact", action="store_true", help="small monitoring summary; skips disk traversal")
    args = parser.parse_args()
    if args.max_event_mib < 1:
        parser.error("--max-event-mib must be positive")
    try:
        os.sched_setaffinity(0, {args.cpu})
        os.nice(19)
    except (OSError, AttributeError):
        pass
    report = summarize(args.directory, args.max_event_mib*1024*1024, scan_disk=not args.compact)
    if args.compact:
        report = compact_summary(report, args.directory)
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
