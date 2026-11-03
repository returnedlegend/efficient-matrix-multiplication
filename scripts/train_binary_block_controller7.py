#!/usr/bin/env python3
"""<=120s tiny/planted-only controller training and disjoint-seed comparison."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO))
from mmsearch.binary_block_controller7 import Bandit, run_controller
from mmsearch.binary_block_descent7 import scalar_loss
from mmsearch.tensor import naive_candidate, strassen_candidate


def factors(candidate):
    return [tuple(sum(x << i for i, x in enumerate(t[a])) for a in ("u", "v", "w")) for t in candidate["terms"]]


def expand(terms):
    return [sum(((u >> a) & 1) * ((v >> b) & 1) * ((w >> c) & 1) for u, v, w in terms) % 2
            for a in range(4) for b in range(4) for c in range(4)]


def fixture(index, seed):
    rng = random.Random(seed)
    exact = factors(strassen_candidate(2))
    kind = ("one_bit", "two_bits", "drop_schoolbook", "cold_start")[index % 4]
    if kind == "cold_start":
        initial = None
    elif kind == "drop_schoolbook":
        initial = factors(naive_candidate(2))
        initial.pop(rng.randrange(8))
    else:
        initial = [list(t) for t in exact]
        choices = [(t, a, b) for t in range(7) for a in range(3) for b in range(4)]
        for t, a, b in rng.sample(choices, 1 if kind == "one_bit" else 2):
            initial[t][a] ^= 1 << b
    return kind, expand(exact), initial


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outdir", type=Path, required=True)
    args = p.parse_args()
    os.sched_setaffinity(0, {1})
    if os.getpriority(os.PRIO_PROCESS, 0) < 10:
        os.nice(10 - os.getpriority(os.PRIO_PROCESS, 0))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    args.outdir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    policy = Bandit(71701)
    curves = []
    training_results = []
    for episode in range(96):
        if time.monotonic() - started >= 50:
            break
        kind, core, initial = fixture(episode, 10000 + episode)
        result = run_controller(core, [4, 4, 4], 7, initial_factors=initial,
            source_product_count=8, mode="bandit", policy=policy, training=True,
            seed=11000 + episode, max_actions=16, timeout_seconds=0.4)
        if result["status"] == "RAW_EXACT_COMPACT" and scalar_loss(core, [4, 4, 4], result["best_factors"]) != 0:
            raise AssertionError("training raw exact observation is incorrect")
        curves.append(dict(episode=episode, fixture=kind, actions=result["actions"],
            best_loss=result["best_loss"], exact=int(result["status"] == "RAW_EXACT_COMPACT"),
            reward=result["reward_total"], terminal_reward=result["terminal_reward_total"], updates=policy.updates))
        training_results.append(result)
    checkpoint = policy.checkpoint()
    (args.outdir / "policy-checkpoint.json").write_text(json.dumps(checkpoint, indent=2) + "\n")
    frozen = Bandit.restore(json.loads(json.dumps(checkpoint)))
    frozen_before = json.dumps(frozen.checkpoint(), sort_keys=True)
    evaluations = []
    eval_rows = []
    for episode in range(32):
        if time.monotonic() - started >= 105:
            break
        kind, core, initial = fixture(episode, 20000 + episode)
        for mode in ("fixed", "uniform", "bandit"):
            result = run_controller(core, [4, 4, 4], 7, initial_factors=initial,
                source_product_count=8, mode=mode, policy=frozen if mode == "bandit" else None,
                training=False, seed=21000 + episode, max_actions=24, timeout_seconds=0.4)
            if result["status"] == "RAW_EXACT_COMPACT" and scalar_loss(core, [4, 4, 4], result["best_factors"]) != 0:
                raise AssertionError("held-out planted observation is incorrect")
            evaluations.append(result)
            eval_rows.append(dict(episode=episode, fixture=kind, mode=mode,
                exact=int(result["status"] == "RAW_EXACT_COMPACT"), best_loss=result["best_loss"],
                actions=result["actions"], blocks=result["block_updates"], seconds=result["elapsed_seconds"]))
    if json.dumps(frozen.checkpoint(), sort_keys=True) != frozen_before:
        raise AssertionError("frozen evaluation mutated learned parameters or RNG")
    metrics = {}
    for mode in ("fixed", "uniform", "bandit"):
        rows = [row for row in eval_rows if row["mode"] == mode]
        metrics[mode] = dict(episodes=len(rows), exact=sum(row["exact"] for row in rows),
            total_best_loss=sum(row["best_loss"] for row in rows),
            total_actions=sum(row["actions"] for row in rows), total_blocks=sum(row["blocks"] for row in rows),
            total_seconds=sum(row["seconds"] for row in rows),
            by_fixture={kind: dict(episodes=sum(r["fixture"] == kind for r in rows),
                exact=sum(r["exact"] for r in rows if r["fixture"] == kind),
                total_best_loss=sum(r["best_loss"] for r in rows if r["fixture"] == kind))
                for kind in ("one_bit", "two_bits", "drop_schoolbook", "cold_start")})
    score = lambda mode: (metrics[mode]["exact"], -metrics[mode]["total_best_loss"])
    control = max(("fixed", "uniform"), key=lambda mode: (score(mode), mode == "fixed"))
    full_comparison = all(metrics[mode]["episodes"] == 32 for mode in metrics)
    selected = "bandit" if full_comparison and score("bandit") > max(score("fixed"), score("uniform")) else control
    summary = dict(status="TINY_TRAINING_AND_FROZEN_SEED_EVALUATION", training_episodes=len(curves),
        heldout_planted_episodes_per_policy=metrics["fixed"]["episodes"], training_seed_range=[10000, 10095],
        heldout_planted_seed_range=[20000, 20031], policy_seed=71701,
        frozen_policy_unchanged=True, metrics=metrics, selected_policy=selected,
        decision_rule="Promote bandit only if all32 comparisons finish and its(exact,-total_loss) strictly beats BOTH controls; ties preferfixed",
        learned_advantage_over_both_controls=selected == "bandit", full_comparison=full_comparison,
        elapsed_seconds=time.monotonic() - started, cpu_affinity=sorted(os.sched_getaffinity(0)),
        nice=os.getpriority(os.PRIO_PROCESS, 0), address_space_limit_bytes=resource.getrlimit(resource.RLIMIT_AS)[0],
        raw_only=True, production_n5_inputs_read=False, no_private_evaluation_data=True,
        policy_checkpoint_sha256=sha(args.outdir / "policy-checkpoint.json"))
    for name, value in [("training-results.json", training_results), ("evaluation-results.json", evaluations),
                        ("evaluation-rows.json", eval_rows), ("summary.json", summary)]:
        (args.outdir / name).write_text(json.dumps(value, indent=2) + "\n")
    with (args.outdir / "training-curves.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(curves[0]))
        writer.writeheader()
        writer.writerows(curves)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        xs = list(range(len(curves)))
        success = [sum(r["exact"] for r in curves[max(0, i - 11):i + 1]) / len(curves[max(0, i - 11):i + 1]) for i in xs]
        losses = [sum(r["best_loss"] for r in curves[max(0, i - 11):i + 1]) / len(curves[max(0, i - 11):i + 1]) for i in xs]
        fig, axes = plt.subplots(2, 1, figsize=(7, 4.8), sharex=True)
        axes[0].plot(xs, success); axes[0].set_ylabel("12-episode exact rate"); axes[0].set_ylim(0, 1)
        axes[1].plot(xs, losses); axes[1].set_ylabel("12-episode best loss"); axes[1].set_xlabel("Tiny training episode")
        fig.tight_layout(); fig.savefig(args.outdir / "training-curves.svg"); plt.close(fig)
    except ImportError:
        (args.outdir / "plot-unavailable.txt").write_text("Training curves remain in CSV; matplotlib unavailable.\n")
    for name in ("mmsearch/binary_block_controller7.py", "scripts/train_binary_block_controller7.py"):
        path = args.outdir / "code" / name
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes((REPO / name).read_bytes())
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
