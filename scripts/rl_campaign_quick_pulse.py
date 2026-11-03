"""Small supervision snapshot from active jobs; no certificate validity claims."""
import datetime as dt
import json
import os
from pathlib import Path
import sys


def read(path, fallback=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {} if fallback is None else fallback


def main():
    os.sched_setaffinity(0, {2})
    os.nice(10)
    root = Path(sys.argv[1])
    campaign = read(root / "campaign.json")
    queue = read(root / "queue_state.json")
    now = dt.datetime.now(dt.timezone.utc)
    deadline = dt.datetime.fromisoformat(campaign["deadline_utc"].replace("Z", "+00:00"))
    jobs = {key: value for key, value in queue.get("jobs", {}).items()
            if value.get("status") == "running"}
    models, local, native = {}, {}, {}
    for name, job in jobs.items():
        command = job["spec"]["command"]
        if "--checkpoint" in command:
            path = Path(command[command.index("--checkpoint") + 1])
            checkpoint = read(path)
            if checkpoint:
                models[name] = dict(steps=checkpoint["state"]["steps"],
                    updates=checkpoint["policy"]["updates"],
                    best_rank=len(checkpoint["best"]))
        output_flag = next((flag for flag in ("--outdir", "--output-dir") if flag in command), None)
        if output_flag:
            output = Path(command[command.index(output_flag)+1])
            if name.startswith(("local-fixed-pair", "local-large")):
                latest = read(output / "latest.json")
                local[name] = dict(counts=latest.get("counts", {}),
                    status=latest.get("result", {}).get("status"),
                    neighborhood=latest.get("query", {}).get("neighborhood_index"))
            elif name.startswith(("kernel-", "fixed", "held", "alpha", "onecube-")):
                phases = sorted(output.glob("phase-*/walk.stats.json"))
                stats = read(phases[-1]) if phases else {}
                native[name] = {key: stats.get(key) for key in ("best_rank", "current_rank", "steps")}
    guard = read(root / "resource_status.json")
    auxiliary = read(root / "auxiliary_pair_watcher.json")
    solvers = {}
    for result in root.glob("coordinate-native-*/result.json"):
        value = read(result)
        solvers[result.parent.name] = {key: value.get(key) for key in
                                     ("status", "control_status", "winner")}
    value = dict(utc=now.isoformat(), remaining_seconds=max(0, int((deadline-now).total_seconds())),
        active_jobs=list(jobs), stop_reason=queue.get("stop_reason"), models=models,
        local=local, native=native,
        rss_bytes=guard.get("rss_bytes"), native_cardinality=solvers,
        auxiliary=dict(state=auxiliary.get("state"), processed=auxiliary.get("processed"),
                       cpu_seconds=auxiliary.get("process_and_child_cpu_seconds"),
                       observed_cpu_fraction=auxiliary.get("observed_average_cpu_fraction")),
        winner_paths=[str(path) for path in root.glob("*/WINNER.json")])
    temporary = root / "quick_status.json.tmp"
    temporary.write_text(json.dumps(value, indent=2)+"\n")
    temporary.replace(root / "quick_status.json")
    with (root / "quick_monitor.jsonl").open("a") as stream:
        stream.write(json.dumps(value)+"\n")
    print(json.dumps(value))


if __name__ == "__main__":
    main()
