"""V43 source-heldout matched frozen evaluation with source-cluster reporting."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from mmsearch.native_bridge import NativeBridge
from mmsearch.recovery_pool import freeze_json
from mmsearch.rl_curriculum import (ContextController, ContextDmEnv, NoveltyLedger,
                                    contextual_policy, sample_action)
from mmsearch.rl_pool_curriculum import FixedStepBridge
from mmsearch.rl_recovery43 import SourceRecoveryPool43
from mmsearch.rl_search import TinyActorCritic, _write
from mmsearch.search import decode_candidate
from mmsearch.verify import verify_candidate


def policy_weight_sha256(policy):
    data = {key: value.tolist() for key, value in policy.params.items()}
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load_policy(path):
    payload = Path(path).read_bytes()
    value = json.loads(payload)
    policy = contextual_policy(TinyActorCritic.from_state(value["policy"]))
    if not all(np.isfinite(array).all() for array in policy.params.values()):
        raise ValueError("evaluation policy contains nonfinite weights")
    return policy, {"path": str(Path(path).resolve()), "checkpoint_sha256": hashlib.sha256(payload).hexdigest(),
                    "weight_sha256_before": policy_weight_sha256(policy), "updates_before": policy.updates}


class EvaluationBridge(FixedStepBridge):
    def __init__(self, bridge, step_limit):
        super().__init__(bridge, step_limit)
        self.last_result = None

    def run(self, candidate, action="exploit", **kwargs):
        self.last_result = super().run(candidate, action=action, **kwargs)
        return self.last_result


def genuine_record(result, record_rank):
    if not result or result.get("status") != "ok":
        return None
    values = [result.get("best_candidate"), result.get("current_candidate")]
    for item in result.get("candidates", []):
        if item["rank"] <= record_rank:
            values.append(json.loads(Path(item["path"]).read_text()))
    for candidate in values:
        if candidate is not None and len(candidate["terms"]) <= record_rank:
            report = verify_candidate(candidate, random_trials=0)
            if not report["valid"]:
                raise ValueError("purported evaluation record failed independent verification")
            return candidate
    return None


def evaluate_episode(candidate, policy, bridge, *, arm, seed, known_rank, record_rank,
                     max_actions=4, episode_seconds=10, deadline=None, stopping=lambda: False,
                     event_sink=None, ledger_state=None):
    """One frozen on-policy episode, actual dm_env steps, no training updates."""
    started_cpu, started_wall = time.process_time(), time.monotonic()
    report = verify_candidate(candidate, random_trials=0)
    if not report["valid"]:
        raise ValueError("held-out input failed independent exact verification")
    terms = decode_candidate(candidate, candidate["dimension"])
    if len(terms) <= known_rank:
        raise ValueError("held-out recovery start must exceed known rank")
    policy = contextual_policy(policy)
    weight_before, updates_before = policy_weight_sha256(policy), policy.updates
    controller = ContextController(terms, n=candidate["dimension"], target_rank=known_rank,
                                   record_rank=record_rank, task_kind="KNOWN_RECOVERY",
                                   seed=seed, policy=policy,
                                   ledger=NoveltyLedger.from_state(ledger_state) if ledger_state is not None else NoveltyLedger(paid=25),
                                   native_bridge=bridge, native_seconds=2, native_only=True,
                                   train=False, control="random" if arm == "random" else "policy")
    environment = ContextDmEnv(lambda: controller)
    environment.reset()
    child_cpu = moves = actions = 0
    record = None
    stop_reason = "action_budget"
    while not controller.terminal and actions < max_actions:
        now = time.monotonic()
        if stopping():
            stop_reason = "external_stop"
            break
        if deadline is not None and now >= deadline:
            stop_reason = "global_wall_budget"
            break
        if now-started_wall >= episode_seconds:
            stop_reason = "episode_wall_budget"
            break
        step = environment.step(sample_action(controller))
        event = dict(environment.last_transition)
        actions += 1
        native = event.get("native", {})
        moves += native.get("attempted_moves", 0)
        child_cpu += native.get("cpu_seconds", 0)
        event.update(event="evaluation_transition", arm=arm, seed=seed,
                     action_number=actions, dm_step_type=str(step.step_type), training=False)
        if event_sink:
            event_sink(event)
        record = genuine_record(bridge.last_result, record_rank)
        if record is not None:
            stop_reason = "verified_record"
            break
    output = controller.candidate()
    verification = verify_candidate(output, random_trials=0)
    if not verification["valid"]:
        raise ValueError("evaluation output failed independent exact verification")
    weight_after = policy_weight_sha256(policy)
    if weight_after != weight_before or policy.updates != updates_before:
        raise AssertionError("evaluation fitted or changed a policy")
    effective_rank = min(verification["rank"], len(record["terms"])) if record is not None else verification["rank"]
    success = effective_rank <= known_rank
    if success and stop_reason != "verified_record":
        stop_reason = "known_bound_recovered"
    result = {"arm": arm, "seed": seed, "input_rank": len(terms), "best_rank": effective_rank,
              "known_rank": known_rank, "success": success, "record_target_reached": record is not None,
              "status": "VERIFIED_RECORD" if record is not None else "KNOWN_BOUND_RECOVERED" if success else "UNKNOWN_WITHIN_LIMITS",
              "stop_reason": stop_reason, "actions": actions, "attempted_moves": moves,
              "cpu_seconds": time.process_time()-started_cpu+child_cpu,
              "wall_seconds": time.monotonic()-started_wall,
              "step_limit_per_action": bridge.step_limit, "max_actions": max_actions,
              "policy_sha256_before": weight_before, "policy_sha256_after": weight_after,
              "training": False, "exact": True, "dm_env_steps": actions}
    return result, record


def source_comparisons(rows):
    """Average within sources, then weight sources equally; avoid seed pseudoreplication."""
    sources = sorted({row["source_hash"] for row in rows})
    output = {"source_count": len(sources), "comparisons": {},
              "uncertainty": "source-cluster percentile bootstrap95 is descriptive with few related source states; repeated task seeds are not independent source evidence",
              "budget_scope": "same tasks, seeds, 50000 moves/action and action cap; early success stops so measured moves and CPU can differ; not an equal-main-CPU transfer test"}
    for reference in ("frozenwarm", "random"):
        differences = []
        by_source = []
        for source in sources:
            group = [row for row in rows if row["source_hash"] == source]
            arms = {arm: [row for row in group if row["arm"] == arm] for arm in ("learned", reference)}
            if not all(arms.values()):
                continue
            rates = {arm: sum(row["success"] for row in values)/len(values) for arm, values in arms.items()}
            difference = rates["learned"]-rates[reference]
            differences.append(difference)
            by_source.append({"source_hash": source, "success_rate": rates, "paired_rate_difference": difference,
                              "episodes_per_arm": {arm:len(values) for arm, values in arms.items()}})
        bootstrap = []
        if differences:
            rng = np.random.default_rng(421103)
            bootstrap = np.mean(rng.choice(differences, (4000, len(differences)), replace=True), axis=1)
        output["comparisons"]["learned_vs_"+reference] = {
            "source_equal_weight_rate_difference": float(np.mean(differences)) if differences else None,
            "descriptive_source_bootstrap95": [float(x) for x in np.percentile(bootstrap, [2.5, 97.5])] if len(bootstrap) else None,
            "source_effects": by_source, "claim": "no demonstrated advantage inferred from parameter updates or recovery counts alone"}
    return output


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--recovery-pool", type=Path, required=True)
    p.add_argument("--outdir", type=Path, required=True)
    p.add_argument("--seeds", type=int, default=16)
    p.add_argument("--heldout-subset", choices=("validation", "test"), default="validation", help="test sources stay blind until the predeclared final assessment")
    p.add_argument("--seed", type=int, default=721101)
    p.add_argument("--step-limit", type=int, default=50000)
    p.add_argument("--max-actions", type=int, default=4)
    p.add_argument("--episode-seconds", type=float, default=10)
    p.add_argument("--seconds", type=float, default=600)
    p.add_argument("--cpu", type=int, required=True)
    p.add_argument("--native-binary", type=Path)
    args = p.parse_args(argv)
    if not 0 <= args.seconds <= 600 or args.seeds < 1 or args.max_actions < 1 or args.episode_seconds <= 0:
        p.error("evaluation is finite: seconds0..600, positive seed/action/episode budgets")
    if args.outdir.exists():
        p.error("evaluation outdir must be new")
    os.sched_setaffinity(0, {args.cpu})
    started = time.monotonic()
    deadline = started+args.seconds
    pool = SourceRecoveryPool43(args.recovery_pool)
    reference_state = json.loads(args.reference.read_text())
    shared_ledger = reference_state["context"]["ledger"]
    if not pool.heldout:
        raise ValueError("frozen pool has no held-out tasks")
    if args.step_limit != pool.manifest["config"]["probe_steps"]:
        raise ValueError("evaluation step limit must match frozen pool probe budget")
    known_rank, record_rank = pool.manifest["config"]["known_rank"], pool.manifest["config"]["record_rank"]
    policies, identities, bridges = {}, {}, {}
    for arm, source in (("learned", args.checkpoint), ("frozenwarm", args.reference), ("random", args.reference)):
        policies[arm], identities[arm] = load_policy(source)
        bridges[arm] = EvaluationBridge(NativeBridge(args.outdir/"native"/arm/"known-recovery",
                                                    binary=args.native_binary, cpu_affinity=[args.cpu],
                                                    archive_size=1), args.step_limit)
    args.outdir.mkdir(parents=True, exist_ok=True)
    stopping = False
    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    rows, complete_pairs = [], 0
    record_found = None
    events = (args.outdir/"events.jsonl").open("a", buffering=1)
    def emit(event):
        events.write(json.dumps(event, sort_keys=True, allow_nan=False)+"\n")
    allowed_sources = set(pool.manifest["evaluation_sources"][args.heldout_subset])
    task_keys = sorted(key for key in pool.heldout if pool.entries[key]["source_term_hash"] in allowed_sources)
    if not task_keys:
        raise ValueError("requested v43 heldout reservation has no frozen task")
    arms = ("learned", "frozenwarm", "random")
    try:
        for repeat in range(args.seeds):
            for task_index, key in enumerate(task_keys):
                if stopping or time.monotonic() >= deadline or record_found is not None:
                    break
                evaluation_seed = (args.seed + repeat*104729 + int(key[:8],16)) % (2**31)
                pair_rows = []
                # Rotate order to avoid always giving one arm the first slot.
                offset = (repeat+task_index) % len(arms)
                order = arms[offset:]+arms[:offset]
                for arm in order:
                    if stopping or time.monotonic() >= deadline:
                        break
                    candidate = pool.candidates[key]
                    def sink(event):
                        emit(dict(event, task_hash=key, task_bucket=pool.entries[key]["task_bucket"], repeat=repeat))
                    result, record = evaluate_episode(candidate, policies[arm], bridges[arm], arm=arm,
                                                       seed=evaluation_seed, known_rank=known_rank, record_rank=record_rank,
                                                       max_actions=args.max_actions, episode_seconds=args.episode_seconds,
                                                       deadline=deadline, stopping=lambda: stopping, event_sink=sink, ledger_state=shared_ledger)
                    result.update(task_hash=key, source_hash=pool.entries[key]["source_term_hash"],
                                  strict_all3_unknown=pool.entries[key]["strict_hard"],
                                  task_bucket=pool.entries[key]["task_bucket"], repeat=repeat,
                                  pair_id=key+":"+str(repeat), paired_complete=False)
                    pair_rows.append(result)
                    rows.append(result)
                    if record is not None:
                        report = verify_candidate(record, random_trials=8, seed=evaluation_seed)
                        if not report["valid"] or report["rank"] > record_rank:
                            raise AssertionError("evaluation record failed final independent verification")
                        record_found = {**freeze_json(args.outdir/"records", record), "arm": arm,
                                        "task_hash": key, "rank": report["rank"]}
                        freeze_json(args.outdir/"records", report)
                        emit(dict(record_found, event="verified_record"))
                        break
                common = len(pair_rows) == len(arms) and not any(x["stop_reason"] in ("global_wall_budget", "external_stop") for x in pair_rows)
                for row in pair_rows:
                    row["paired_complete"] = common
                    emit(dict(row, event="evaluation_result"))
                complete_pairs += common
                _write(args.outdir/"results.json", rows)
            if stopping or time.monotonic() >= deadline or record_found is not None:
                break
    finally:
        for arm in arms:
            after = policy_weight_sha256(policies[arm])
            identities[arm].update(weight_sha256_after=after, updates_after=policies[arm].updates,
                                   unchanged=after == identities[arm]["weight_sha256_before"]
                                   and policies[arm].updates == identities[arm]["updates_before"])
            if not identities[arm]["unchanged"]:
                raise AssertionError("evaluation changed a frozen policy")
        matched = [row for row in rows if row["paired_complete"]]
        summary = {"format": "source-heldout-policy-evaluation-v43", "pool_sha256": pool.sha256,
                   "pool_path": str(pool.directory), "small_pool": pool.manifest["small_pool"],
                   "heldout_tasks": len(task_keys), "heldout_hashes": task_keys,
                   "heldout_subset": args.heldout_subset, "reserved_source_hashes": sorted(allowed_sources),
                   "final_source_use_policy": "test subset evaluated once at predeclared end; validation feedback cannot justify an unbiased final claim on validation sources",
                   "shared_ledger_sha256": hashlib.sha256(json.dumps(shared_ledger, sort_keys=True).encode()).hexdigest(),
                   "shared_observation_context": "all arms clone reference novelty ledger; no fitting; depleted cap remains depleted",
                   "source_cluster_comparisons": source_comparisons(matched),
                   "training_tasks_evaluated": 0, "complete_pairs": complete_pairs,
                   "all_rows": len(rows), "policy_identities": identities,
                   "step_limit_per_action": args.step_limit, "max_actions": args.max_actions,
                   "record": record_found, "wall_seconds": time.monotonic()-started,
                   "arms": {arm: {"matched_episodes": sum(x["arm"] == arm for x in matched),
                                  "successes": sum(x["arm"] == arm and x["success"] for x in matched),
                                  "attempted_moves": sum(x["attempted_moves"] for x in matched if x["arm"] == arm),
                                  "cpu_seconds": sum(x["cpu_seconds"] for x in matched if x["arm"] == arm),
                                  "censored": sum(x["arm"] == arm and not x["success"] for x in matched)} for arm in arms},
                   "buckets": {bucket: {arm: {"matched_episodes": sum(x["arm"] == arm and x["task_bucket"] == bucket for x in matched),
                                               "successes": sum(x["arm"] == arm and x["task_bucket"] == bucket and x["success"] for x in matched),
                                               "attempted_moves": sum(x["attempted_moves"] for x in matched if x["arm"] == arm and x["task_bucket"] == bucket),
                                               "cpu_seconds": sum(x["cpu_seconds"] for x in matched if x["arm"] == arm and x["task_bucket"] == bucket)} for arm in arms}
                               for bucket in ("informative_challenge", "delayed_control")},
                   "claim": "descriptive matched finite-budget held-out results; no statistical or generalization claim"}
        _write(args.outdir/"results.json", rows)
        _write(args.outdir/"summary.json", summary)
        emit(dict(summary, event="evaluation_finish"))
        events.close()
    print(json.dumps({"complete_pairs": complete_pairs, "rows": len(rows), "record": record_found,
                      "summary": str(args.outdir/"summary.json")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
