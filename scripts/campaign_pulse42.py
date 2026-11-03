"""Small read-only progress report; certificate validity comes from the guard."""
import datetime as dt
import json
import os
from pathlib import Path
import sys


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def main():
    os.sched_setaffinity(0, {2})
    os.nice(10)
    root = Path(sys.argv[1])
    now = dt.datetime.now(dt.timezone.utc)
    config = read(root / "campaign.json")
    queue = read(root / "queue_state.json")
    guard = read(root / "operations-v3/state.json")
    jobs = queue.get("jobs", {})
    active = {}
    for name, value in jobs.items():
        if value.get("status") != "running":
            continue
        command = value["spec"]["command"]
        item = {"cpu": value["spec"]["cpu"]}
        if "--checkpoint" in command:
            state = read(Path(command[command.index("--checkpoint") + 1]))
            if state:
                item.update(steps=state.get("state", {}).get("steps"),
                            updates=state.get("policy", {}).get("updates"),
                            best_products=len(state["best"]))
        flag = next((f for f in ("--outdir", "--output-dir") if f in command), None)
        if flag:
            folder = Path(command[command.index(flag) + 1])
            for filename in ("progress.json", "latest_stats.json"):
                state = read(folder / filename)
                if state:
                    state = state.get("stats", state)
                    item[filename] = {k: state[k] for k in (
                        "status", "best_rank", "current_rank", "next_row",
                        "triples_completed", "prefix_completed", "coverage") if k in state}
            pointer = read(folder / "best_verified.json")
            if pointer:
                item["verified_full_products"] = pointer.get("rank")
        active[name] = item
    deadline = dt.datetime.fromisoformat(config["deadline_utc"].replace("Z", "+00:00"))
    value = dict(utc=now.isoformat(), remaining_seconds=max(0, int((deadline-now).total_seconds())),
                 active=active, completed_jobs=sum(v.get("status") == "completed" for v in jobs.values()),
                 stop_reason=queue.get("stop_reason"),
                 guard_updated_utc=guard.get("updated_utc"), rss_bytes=guard.get("rss_bytes"),
                 campaign_allocated_bytes=guard.get("campaign_allocated_bytes"),
                 filesystem_free_bytes=guard.get("filesystem_free_bytes"),
                 stop_marker=read(root / "guard_stopped.json"),
                 winner_paths=[str(p) for p in root.glob("*/WINNER.json")])
    print(json.dumps(value))


if __name__ == "__main__":
    main()
