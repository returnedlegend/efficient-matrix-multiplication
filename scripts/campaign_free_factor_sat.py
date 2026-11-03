"""Bounded exact free-factor SAT, with frozen inputs, code and row/formula maps.

Example: PYTHONPATH=.xor-deps:. taskset -c 2 python scripts/campaign_free_factor_sat.py
 --dictionary PATH/dictionary.json --baseline artifacts/km93_f2.json --orientation uv
 --rank 92 --seconds 600 --memory-mb 1536 --outdir NEW_DIRECTORY
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from mmsearch.free_factor_sat import (FormulaMemoryLimit, audit, baseline_assumptions,
    build_problem, build_system, decode_vectors, estimate_formula, solve)
from mmsearch.recombine import save
from mmsearch.verify import verify_candidate, write_standalone_verifier
from mmsearch.xor_sat import write_problem


def _freeze_code(root):
    files = [Path(__file__), REPO/"mmsearch/free_factor_sat.py", REPO/"mmsearch/recombine.py",
        REPO/"mmsearch/recombine_sat.py", REPO/"mmsearch/verify.py", REPO/"mmsearch/xor_sat.py",
        REPO/"mmsearch/sat.py", REPO/"mmsearch/sat_neighborhoods.py", REPO/"mmsearch/compact_sat.py",
        REPO/"mmsearch/tensor.py", REPO/"mmsearch/__init__.py"]
    result = {}
    for path in files:
        relative = path.relative_to(REPO)
        raw = path.read_bytes()
        destination = root/"code"/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        result[str(relative)] = hashlib.sha256(raw).hexdigest()
    return result


def _save_sat(root, stem, result):
    result = dict(result)
    candidate = result.pop("candidate", None)
    assignment = result.pop("complete_assignment", None)
    if candidate is not None:
        save(root/f"{stem}.json", candidate)
        save(root/f"{stem}.verification.json", result["verification"])
        write_standalone_verifier(root/f"{stem}.verify.py")
    if assignment is not None:
        save(root/f"{stem}.model.json", dict(assignment=assignment,
            formula_sha256=result["formula_sha256"], layout="index0 unused; indices1..nv complete Boolean values"))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--orientation", choices=["uv", "vw", "wu", "all"], default="uv")
    parser.add_argument("--dimension", type=int, default=5)
    parser.add_argument("--rank", type=int, default=92)
    parser.add_argument("--seconds", type=float, default=600)
    parser.add_argument("--control-seconds", type=float, default=10)
    parser.add_argument("--memory-mb", type=int, default=1536)
    parser.add_argument("--max-formula-mb", type=float, default=384)
    parser.add_argument("--conflicts", type=int, default=10000000)
    parser.add_argument("--outdir", "--output-dir", dest="outdir", type=Path, required=True)
    parser.add_argument("--preflight", action="store_true", help="exact row/forced bounds only; never starts a solver")
    args = parser.parse_args(argv)
    if (any(not math.isfinite(v) or v <= 0 for v in (args.seconds, args.control_seconds, args.max_formula_mb)) or
            args.dimension < 1 or args.rank < 0 or args.memory_mb < 128 or args.conflicts < 1):
        parser.error("invalid resource bounds or dimensions")
    if args.orientation == "all" and not args.preflight:
        parser.error("orientation=all is available only with --preflight")
    started = time.monotonic()
    deadline = started+args.seconds
    root = args.outdir
    root.mkdir(parents=True, exist_ok=False)
    (root/"inputs").mkdir()
    provenance = dict(inputs=[], code_sha256=_freeze_code(root))

    def freeze(path, name):
        raw = path.read_bytes()
        snapshot = root/"inputs"/name
        snapshot.write_bytes(raw)
        provenance["inputs"].append(dict(path=str(path.resolve()), snapshot=str(snapshot.resolve()),
            raw_sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)))
        return json.loads(raw)

    dictionary = freeze(args.dictionary, "dictionary.json")
    baseline = freeze(args.baseline, "baseline.json")
    # Capture the known dictionary provenance when supplied next to its JSON.
    for name in ("pool.json", "manifest.json"):
        neighbor = args.dictionary.with_name(name)
        if neighbor.exists():
            freeze(neighbor, f"source-{name}")
    save(root/"provenance.json", provenance)
    orientations = ["uv", "vw", "wu"] if args.orientation == "all" else [args.orientation]
    preflights = []
    preflight_winners = []
    for orientation in orientations:
        system = build_system(dictionary, args.dimension, orientation, baseline, provenance)
        save(root/f"{orientation}.system.audit.json", audit(system))
        summary = dict(orientation=orientation, pair_count=len(system["pairs"]),
            linear_rank=system["metadata"]["linear_rank"], linear_nullity=system["metadata"]["linear_nullity"],
            forced_active=system["metadata"]["forced_active"], forced_zero=system["metadata"]["forced_zero"],
            inconsistent=system["metadata"]["linear_inconsistent"],
            baseline_merged_rank=system["metadata"]["baseline"]["merged_rank"],
            formula_memory_estimate=estimate_formula(system, args.rank))
        preflights.append(summary)
        if args.preflight:
            if summary["baseline_merged_rank"] <= args.rank:
                candidate = decode_vectors(system, system["baseline_vectors"], dict(
                    method="exact-F2-baseline-same-pair-XOR-merge", orientation=orientation,
                    field_claim="F2 only; no integer lift asserted"))
                report = verify_candidate(candidate, random_trials=16)
                if not report["valid"]:
                    raise AssertionError("preflight baseline merge failed independent verification")
                save(root/f"WINNER.{orientation}.json", candidate)
                save(root/f"WINNER.{orientation}.verification.json", report)
                if not preflight_winners or report["rank"] < min(w["rank"] for w in preflight_winners):
                    save(root/"WINNER.json", candidate)
                    save(root/"WINNER.verification.json", report)
                    write_standalone_verifier(root/"WINNER.verify.py")
                preflight_winners.append(dict(orientation=orientation, rank=report["rank"]))
            del system
    save(root/"preflight.json", preflights)
    if args.preflight:
        print(json.dumps(dict(status="PREFLIGHT", orientations=preflights,
            verified_baseline_merge_winners=preflight_winners), sort_keys=True), flush=True)
        return 0
    manifest = dict(system["metadata"], started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        solver_budget=dict(total_wall_seconds=args.seconds, control_wall_seconds=args.control_seconds,
            cleanup_reserve_seconds=2, conflicts=args.conflicts, memory_mb=args.memory_mb,
            max_formula_mb=args.max_formula_mb, threads=1), rank_bound=args.rank)
    save(root/"manifest.json", manifest)

    def finish(result):
        result.update(total_elapsed_seconds=time.monotonic()-started, rank_bound=args.rank,
            orientation=args.orientation, pairs_sha256=system["metadata"]["pairs_sha256"],
            scope=system["metadata"]["scope"])
        save(root/"result.json", result)
        print(json.dumps(result, sort_keys=True), flush=True)
        return 2 if result["status"] == "ERROR" else 0

    # A same-pair merge is itself an exact, independently verified improvement.
    # Freeze it immediately without spending solver resources.
    if system["metadata"]["baseline"]["merged_rank"] <= args.rank:
        candidate = decode_vectors(system, system["baseline_vectors"], dict(
            method="exact-F2-baseline-same-pair-XOR-merge", orientation=args.orientation,
            field_claim="F2 only; no integer lift asserted"))
        report = verify_candidate(candidate, random_trials=16)
        if not report["valid"]:
            raise AssertionError("merged baseline failed independent verification")
        save(root/"WINNER.json", candidate)
        save(root/"WINNER.verification.json", report)
        write_standalone_verifier(root/"WINNER.verify.py")
        return finish(dict(status="SAT", method="baseline pair merge", verification=report))

    # Build, run, save and release the control before constructing the target
    # formula. This avoids retaining two large CNF/native-XOR Python objects.
    try:
        control_problem = build_problem(system, system["metadata"]["baseline"]["supplied_rank"], args.max_formula_mb)
    except FormulaMemoryLimit as exc:
        return finish(dict(status="RESOURCE_LIMIT", phase="control", reason=str(exc),
            formula_memory_estimate=estimate_formula(system, args.rank)))
    write_problem(control_problem, root/"control.problem")
    remaining = deadline-time.monotonic()-2
    if remaining <= 0:
        return finish(dict(status="UNKNOWN", reason="setup exhausted total wall budget"))
    try:
        control = solve(control_problem, seconds=min(args.control_seconds, remaining), conflicts=args.conflicts,
            memory_mb=args.memory_mb, assumptions=baseline_assumptions(control_problem))
    except Exception as exc:
        return finish(dict(status="ERROR", phase="control", error=f"{type(exc).__name__}: {exc}"))
    control = _save_sat(root, "control.candidate", control)
    save(root/"control.result.json", control)
    del control_problem
    gc.collect()
    if control["status"] != "SAT":
        return finish(dict(status="ERROR", error="known exact fixed-baseline SAT feasibility control did not pass",
            control_status=control["status"]))
    # The exact witnesses in the system audit suffice to establish these
    # restricted impossibility bounds, without allocating a target formula.
    if system["metadata"]["linear_inconsistent"] or system["metadata"]["forced_active"] > args.rank:
        return finish(dict(status="UNSAT", method="exact packed-RREF certificate",
            reason="linear inconsistency" if system["metadata"]["linear_inconsistent"] else "forced active groups exceed bound",
            forced_active=system["metadata"]["forced_active"], control_status="SAT"))
    if deadline-time.monotonic() <= 2:
        return finish(dict(status="UNKNOWN", reason="control/setup exhausted total wall budget", control_status="SAT"))
    try:
        problem = build_problem(system, args.rank, args.max_formula_mb)
    except FormulaMemoryLimit as exc:
        return finish(dict(status="RESOURCE_LIMIT", phase="target", reason=str(exc), control_status="SAT",
            formula_memory_estimate=estimate_formula(system, args.rank)))
    write_problem(problem, root/"target.problem")
    remaining = deadline-time.monotonic()-2
    if remaining <= 0:
        return finish(dict(status="UNKNOWN", reason="target encoding exhausted total wall budget", control_status="SAT"))
    try:
        result = solve(problem, seconds=remaining, conflicts=args.conflicts, memory_mb=args.memory_mb)
    except Exception as exc:
        return finish(dict(status="ERROR", phase="target", control_status="SAT", error=f"{type(exc).__name__}: {exc}"))
    result = _save_sat(root, "WINNER", result)
    result["control_status"] = "SAT"
    return finish(result)


if __name__ == "__main__":
    raise SystemExit(main())
