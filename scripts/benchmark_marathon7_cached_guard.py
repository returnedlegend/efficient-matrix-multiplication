#!/usr/bin/env python3
"""Synthetic1.4MB state benchmark only; never reads live campaign inputs."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.marathon7_local import CampaignGuard as OriginalGuard
from mmsearch.marathon7_cached_guard import CampaignGuard


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 200:
        parser.error("iterations must be1..200")
    pinned = [Path("mmsearch/marathon7_local.py"), Path("mmsearch/local_guard43.py"),
              Path("mmsearch/observed_rank3_lazy42.py"), Path("scripts/tensor_code7.py"),
              Path("mmsearch/tensor_code7.py")]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {str(p): sha(p) for p in pinned}
    with tempfile.TemporaryDirectory(prefix="cached-guard-synthetic-benchmark-") as directory:
        root = Path(directory)
        state = root / "operations-v3/state.json"
        state.parent.mkdir()
        proc = Path("/proc", str(os.getpid()), "stat").read_text().rsplit(")", 1)[1].split()
        value = dict(updated_utc=datetime.now(timezone.utc).isoformat(), pid=os.getpid(),
                     process_identity=dict(start_ticks=int(proc[19])), campaign_allocated_bytes=1024,
                     history=[dict(case=i, status="UNKNOWN", complete=False, detail="x" * 50)
                              for i in range(9000)], padding="")
        raw = json.dumps(value, separators=(",", ":")).encode()
        value["padding"] = "x" * (1400000 - len(raw))
        raw = json.dumps(value, separators=(",", ":")).encode()
        assert len(raw) == 1400000
        state.write_bytes(raw)
        (root / "queue_state.json").write_text("{}")
        observations = {}
        for name, cls in [("original", OriginalGuard), ("cached", CampaignGuard)]:
            guard = cls(120, "2026-11-03T19:24:17Z", campaign_dir=root, guard_state=state)
            times = []
            for _ in range(args.iterations):
                started = time.perf_counter()
                reason = guard.reason(force=True)
                times.append(time.perf_counter() - started)
                if reason:
                    raise AssertionError("synthetic guard unexpectedly held: " + reason)
            observations[name] = dict(iterations=len(times), total_seconds=sum(times),
                                      median_seconds=statistics.median(times),
                                      max_seconds=max(times), first_seconds=times[0],
                                      warm_median_seconds=statistics.median(times[1:] or times),
                                      cache=guard.cache.metrics() if name == "cached" else None)
        speed = observations["original"]["total_seconds"] / observations["cached"]["total_seconds"]
    after = {str(p): sha(p) for p in pinned}
    assert before == after
    result = dict(status="PASS_SYNTHETIC_BENCHMARK", state_bytes=1400000,
                  cpu_affinity=sorted(os.sched_getaffinity(0)), nice=os.getpriority(os.PRIO_PROCESS, 0),
                  observations=observations, total_speedup=speed, unchanged_source_pins=after,
                  prototype_sha256=sha(Path("mmsearch/marathon7_cached_guard.py")),
                  live_campaign_inputs_read=False, production_integration=False,
                  measured_utc=datetime.now(timezone.utc).isoformat())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
