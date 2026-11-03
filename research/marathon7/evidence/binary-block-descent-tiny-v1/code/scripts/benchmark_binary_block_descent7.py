#!/usr/bin/env python3
"""Known n2, elementary failure and synthetic compact-block evidence only."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO))
from mmsearch.binary_block_descent7 import optimize, exact_block_update
from mmsearch.tensor import strassen_candidate


def expand(factors, shape):
    core = [0] * math.prod(shape)
    for a in range(shape[0]):
        for b in range(shape[1]):
            for c in range(shape[2]):
                for u, v, w in factors:
                    core[(a * shape[1] + b) * shape[2] + c] ^= ((u >> a) & 1) & ((v >> b) & 1) & ((w >> c) & 1)
    return core


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    os.sched_setaffinity(0, {1})
    if os.getpriority(os.PRIO_PROCESS, 0) < 10:
        os.nice(10 - os.getpriority(os.PRIO_PROCESS, 0))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    started = time.monotonic()
    args.outdir.mkdir(parents=True, exist_ok=False)
    terms = strassen_candidate(2)["terms"]
    known = [tuple(sum(x << i for i, x in enumerate(term[a])) for a in ("u", "v", "w")) for term in terms]
    shape = [4, 4, 4]
    core = expand(known, shape)
    inputs = dict(known_n2_core=core, known_n2_shape=shape, known_strassen7_factors=known)
    results = []
    for axis in range(3):
        corrupted = [list(t) for t in known]
        corrupted[0][axis] ^= 1
        result = optimize(core, shape, 7, initial_factors=corrupted,
                          axis_order=[axis] + [j for j in range(3) if j != axis],
                          max_sweeps=2, max_restarts=0, max_perturbations=0, timeout_seconds=2)
        result.update(fixture="known_strassen7_single_bit", corrupted_axis=axis)
        results.append(result)
    for seed in range(12):
        result = optimize(core, shape, 7, seed=7900 + seed, max_sweeps=30,
                          max_restarts=2, max_perturbations=3, perturb_bits=2, timeout_seconds=1.5)
        result.update(fixture="known_n2_rank7_random_start")
        results.append(result)
    failure = optimize([1, 0, 0, 0, 0, 0, 0, 1], [2, 2, 2], 1, seed=71,
                       max_sweeps=12, max_restarts=2, max_perturbations=3, timeout_seconds=2)
    failure.update(fixture="rank1_cannot_fit_rank2_diagonal_tensor")
    results.append(failure)
    rng = random.Random(7914)
    synthetic_shape = [9, 9, 9]
    synthetic = [rng.randrange(2) for _ in range(math.prod(synthetic_shape))]
    factors = [tuple(rng.randrange(1, 1 << d) for d in synthetic_shape) for _ in range(14)]
    inputs.update(synthetic_core=synthetic, synthetic_shape=synthetic_shape, synthetic_factors=factors)
    block_started = time.perf_counter()
    block = exact_block_update(synthetic, synthetic_shape, factors, 0, timeout_seconds=5)
    block["wall_seconds"] = time.perf_counter() - block_started
    block.update(fixture="synthetic9x9x9_rank14_exact_block")
    results.append(block)
    elapsed = time.monotonic() - started
    raw_exact = sum(r["status"] == "RAW_EXACT_COMPACT" for r in results)
    random_results = [r for r in results if r["fixture"] == "known_n2_rank7_random_start"]
    summary = dict(status="TINY_PLANTED_AND_SYNTHETIC_ONLY", elapsed_seconds=elapsed,
        cpu_affinity=sorted(os.sched_getaffinity(0)), nice=os.getpriority(os.PRIO_PROCESS, 0),
        address_space_limit_bytes=resource.getrlimit(resource.RLIMIT_AS)[0],
        max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        runs=len(results), raw_exact_compact_observations=raw_exact,
        random_rank7_trials=len(random_results),
        random_rank7_exact=sum(r["status"] == "RAW_EXACT_COMPACT" for r in random_results),
        random_rank7_unknown=sum(r["status"] == "UNKNOWN" for r in random_results),
        random_rank7_best_losses=[r["best_loss"] for r in random_results],
        synthetic_block_codewords=block.get("enumerated_codewords"),
        synthetic_block_wall_seconds=block["wall_seconds"],
        synthetic_block_losses=[block.get("loss_before"), block.get("loss_after")],
        raw_only=True, ambient_verification_performed=False, production_n5_target_search=False,
        known_fixture_no_novelty_claim=True,
        module_sha256=hashlib.sha256((REPO / "mmsearch/binary_block_descent7.py").read_bytes()).hexdigest())
    for name, value in [("inputs.json", inputs), ("results.json", results), ("summary.json", summary)]:
        (args.outdir / name).write_text(json.dumps(value, indent=2) + "\n")
    for name in ["mmsearch/binary_block_descent7.py", "scripts/benchmark_binary_block_descent7.py",
                 "tests/test_binary_block_descent7.py"]:
        path = args.outdir / "code" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((REPO / name).read_bytes())
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
