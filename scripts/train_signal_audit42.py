"""Read-only fixed-main-CPU reward audit; no policy or active artifact changes."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import statistics


def audit(path, budget, capture):
    origin = None
    rows, prefix = [], bytearray()
    observed_end = None
    with Path(path).open("rb") as stream:
        for line in stream:
            if not line.endswith(b"\n"):
                break
            value = json.loads(line)
            if origin is None:
                if value.get("event") != "start":
                    raise ValueError("event log must begin with a start event")
                origin = value["record_cpu"]
            prefix.extend(line)
            observed_end = value["record_cpu"]-origin
            if observed_end > budget:
                break
            rows.append(value)
    capture.write_bytes(gzip.compress(prefix, compresslevel=1, mtime=0))
    output = {"events": str(Path(path).resolve()), "main_cpu_budget": budget,
              "record_cpu_origin": origin, "captured_prefix_sha256": hashlib.sha256(prefix).hexdigest(),
              "captured_prefix_gzip": str(capture.resolve()),
              "budget_reached": observed_end is not None and observed_end > budget,
              "selection": "complete event lines with cumulative measured main CPU minus invocation origin <= budget; crossing action excluded"}
    for kind in ("RECORD_SEARCH", "KNOWN_RECOVERY"):
        selected = [row for row in rows if row.get("event") == "transition" and row.get("task_kind") == kind]
        rewards = [row["reward"] for row in selected]
        entropy = [row["policy_entropy"] for row in selected]
        output[kind] = {"actions": len(selected), "exact_rank_improvement_events": sum(row["improvement"] > 0 for row in selected),
                        "new_best_product_reductions": sum(row["improvement"] for row in selected),
                        "record_target_events": sum(row.get("record_target_reached", False) for row in selected),
                        "positive_reward_actions": sum(value > 0 for value in rewards),
                        "reward_sum": sum(rewards), "rank_reward_sum": sum(100*row["improvement"] for row in selected),
                        "novelty_reward_sum": sum(row.get("novelty_bonus", 0) for row in selected),
                        "reward_min": min(rewards, default=None), "reward_max": max(rewards, default=None),
                        "reward_mean": statistics.mean(rewards) if rewards else None,
                        "policy_entropy_mean": statistics.mean(entropy) if entropy else None,
                        "action_counts": dict(Counter(row["action"] for row in selected)),
                        "best_rank_counts": dict(Counter(row["best_rank"] for row in selected)),
                        "native_attempted_moves": sum(row.get("native", {}).get("attempted_moves", 0) for row in selected),
                        "measured_action_cpu": sum(row.get("measured_total_cpu_seconds", 0) for row in selected)}
    recovery_ends = [row for row in rows if row.get("event") == "recovery_end"]
    output["auxiliary_episodes"] = {"completed": len(recovery_ends),
                                   "known93_recoveries": sum(row.get("known_recovery_success", False) for row in recovery_ends),
                                   "censored": sum(row.get("censored", False) for row in recovery_ends)}
    output["interpretation"] = "descriptive correlated search exposure; known93 auxiliary gains are not rank92 progress; no independent-trial confidence bound or learned advantage claimed"
    return output


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events", action="append", required=True, help="label=path")
    p.add_argument("--main-cpu", type=float, default=300)
    p.add_argument("--outdir", type=Path, required=True)
    args = p.parse_args(argv)
    args.outdir.mkdir(parents=True, exist_ok=False)
    results = {}
    for item in args.events:
        label, path = item.split("=", 1)
        if not label.replace("-", "").replace("_", "").isalnum():
            raise ValueError("unsafe audit label")
        results[label] = audit(path, args.main_cpu, args.outdir/(label+".events-prefix.jsonl.gz"))
    value = {"format": "fixed-main-cpu-signal-audit-v42", "arms": results,
             "comparison_scope": "separate descriptive windows, not randomized matched controls; policies and starting states can differ"}
    (args.outdir/"result.json").write_text(json.dumps(value, indent=2)+"\n")
    print(json.dumps({label:{kind:result[kind] for kind in ("RECORD_SEARCH", "KNOWN_RECOVERY", "auxiliary_episodes")} for label,result in results.items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
