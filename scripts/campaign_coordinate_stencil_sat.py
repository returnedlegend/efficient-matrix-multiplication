"""Freeze exact source-column choices; optionally scan or solve their union CNF.

Default mode prepares only. The campaign entrypoint accepts only n=5/F2 and a
rank target <=92. Tiny-dimensional controls belong to the module's tests.
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
from mmsearch.coordinate_stencil_sat import (SCOPE, FormulaMemoryLimit, VerifiedSources,
    audit, build_family, build_problem, estimate_formula, single_coordinate_scan,
    solve, source_assumptions, verify_selection)
from mmsearch.recombine import digest, save
from mmsearch.verify import write_standalone_verifier


def strict_json(raw):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"duplicate JSON key: {key}")
            obj[key] = value
        return obj
    return json.loads(raw, object_pairs_hook=unique)


def freeze_code(root):
    files = [Path(__file__)]+[REPO/"mmsearch"/name for name in (
        "coordinate_stencil_sat.py", "free_factor_sat.py", "recombine.py", "recombine_sat.py",
        "verify.py", "sat.py", "sat_neighborhoods.py", "compact_sat.py", "tensor.py", "__init__.py")]
    hashes = {}
    for path in files:
        raw = path.read_bytes()
        rel = path.relative_to(REPO)
        destination = root/"code"/rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        hashes[str(rel)] = hashlib.sha256(raw).hexdigest()
    return hashes


def write_formula(problem, stem):
    with Path(str(stem)+".cnf").open("x") as stream:
        stream.write(f"p cnf {problem['nv']} {len(problem['clauses'])}\n")
        for clause in problem["clauses"]:
            stream.write(" ".join(map(str, clause))+" 0\n")
    save(str(stem)+".mapping.json", dict(metadata=problem["metadata"],
        x_variables=problem["xs"], y_variables=problem["ys"],
        layout="x[coordinate][choice], y[pair]; remaining variables are sequential cardinality auxiliaries"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, default=[])
    parser.add_argument("--candidate-dir", action="append", type=Path, default=[])
    parser.add_argument("--baseline", type=Path, help="also include and explicitly identify an exact source")
    parser.add_argument("--orientation", choices=["uv", "vw", "wu", "all"], default="all")
    parser.add_argument("--mode", choices=["prepare", "scan", "sat"], default="prepare")
    parser.add_argument("--prepare-only", "--preflight", dest="prepare_only", action="store_true")
    parser.add_argument("--rank", type=int, default=92)
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument("--scan-seconds", type=float, default=120)
    parser.add_argument("--control-seconds", type=float, default=5)
    parser.add_argument("--max-sources", type=int, default=512)
    parser.add_argument("--max-inputs", type=int, default=2048)
    parser.add_argument("--max-formula-mb", type=float, default=384)
    parser.add_argument("--memory-mb", type=int, default=1536)
    parser.add_argument("--outdir", "--output-dir", dest="outdir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.prepare_only:
        args.mode = "prepare"
    if (not 0 <= args.rank <= 92 or not 1 <= args.max_sources <= 512 or args.max_inputs < 1 or
            args.memory_mb < 128 or any(not math.isfinite(v) or v <= 0 for v in
                (args.seconds, args.scan_seconds, args.control_seconds, args.max_formula_mb))):
        parser.error("invalid bounds; campaign is strictly n=5/F2 with target <=92")
    if args.mode == "sat" and args.orientation == "all":
        parser.error("SAT mode requires one orientation")
    if not args.input and not args.candidate_dir and not args.baseline:
        parser.error("supply --input, --candidate-dir, or --baseline")
    started = time.monotonic()
    deadline = started+args.seconds
    root = args.outdir
    root.mkdir(parents=True, exist_ok=False)
    (root/"inputs").mkdir()
    manifest = dict(method="coordinatewise exact source-column recombination", scope=SCOPE,
        started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        parameters={k: str(v) if isinstance(v, Path) else [str(x) for x in v] if isinstance(v, list) else v
                    for k, v in vars(args).items()}, code_sha256=freeze_code(root),
        seed=None, randomness="none; deterministic sorted inputs/choices and CaDiCaL default seed",
        cleanup_reserve_seconds=2)
    save(root/"manifest.json", manifest)
    paths = {p.resolve(): True for p in args.input}
    if args.baseline:
        paths[args.baseline.resolve()] = True
    for directory in args.candidate_dir:
        if not directory.is_dir():
            parser.error(f"candidate directory does not exist: {directory}")
        for path in sorted(directory.rglob("*.json")):
            paths.setdefault(path.resolve(), False)
    candidates, provenance, skipped = [], [], []
    for path, required in sorted(paths.items(), key=lambda item: str(item[0])):
        raw = path.read_bytes()
        candidate = strict_json(raw)
        if not required and (not isinstance(candidate, dict) or "terms" not in candidate):
            skipped.append(dict(path=str(path), reason="not a certificate object"))
            continue
        if len(candidates) >= args.max_inputs:
            raise ValueError("input certificate cap exceeded; narrow input paths or raise --max-inputs")
        snapshot = root/"inputs"/f"source{len(candidates):04d}.json"
        snapshot.write_bytes(raw)
        provenance.append(dict(path=str(path), snapshot=str(snapshot.relative_to(root)),
            raw_sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)))
        candidates.append(candidate)
    sources = VerifiedSources(candidates, dimension=5, provenance=provenance)
    if min(s["canonical_rank"] for s in sources.sources) > 93:
        raise ValueError("include a verified <=93 source to embed the known baseline")
    baseline_source = None
    if args.baseline:
        baseline_source = sources.input_sources[next(i for i, p in enumerate(provenance)
            if p["path"] == str(args.baseline.resolve()))]["source_index"]
    save(root/"sources.json", dict(source_pool_sha256=sources.sha256, sources=sources.sources,
        inputs=sources.input_sources, skipped=skipped, explicit_baseline_source=baseline_source))
    del candidates
    records = []

    def retain(candidate, verification, selection):
        index = len(records)
        stem = f"record{index:04d}"
        save(root/f"{stem}.json", candidate)
        save(root/f"{stem}.verification.json", verification)
        record = dict(stem=stem, rank=verification["rank"], candidate_sha256=digest(candidate),
            orientation=candidate["metadata"]["orientation"], selection=selection,
            exact_entries_checked=verification["exact_entries_checked"])
        records.append(record)
        save(root/"records.json", records)
        if verification["valid"] and verification["dimension"] == 5 and verification["field"] == 2 and verification["rank"] <= 92:
            # Never overwrite a winner. Further records remain separately reviewable.
            winner = root/"WINNER.json"
            try:
                with winner.open("x") as stream:
                    stream.write(json.dumps(candidate, sort_keys=True, indent=2)+"\n")
            except FileExistsError:
                pass
            else:
                save(root/"WINNER.verification.json", verification)
                write_standalone_verifier(root/"WINNER.verify.py")

    summaries = []
    orientations = ["uv", "vw", "wu"] if args.orientation == "all" else [args.orientation]
    for orientation in orientations:
        family = build_family(sources, orientation)
        save(root/f"{orientation}.family.audit.json", audit(family))
        # Baseline embedding is explicitly checked and exported even in prepare mode.
        baseline = family["metadata"]["baseline_source"] if baseline_source is None else baseline_source
        baseline_choice = family["source_choices"][baseline]
        candidate, verification = verify_selection(family, baseline_choice, dict(phase="baseline embedding"))
        retain(candidate, verification, baseline_choice)
        if baseline != family["metadata"]["baseline_source"]:
            choice = family["source_choices"][family["metadata"]["baseline_source"]]
            candidate, verification = verify_selection(family, choice, dict(phase="best dominance baseline"))
            retain(candidate, verification, choice)
        summary = dict(orientation=orientation, pair_count=len(family["pairs"]),
            source_count=len(sources.sources), retained_stencils_per_coordinate=[len(row) for row in family["choices"]],
            baseline_rank=verification["rank"], pairs_sha256=family["metadata"]["pairs_sha256"],
            choices_sha256=family["metadata"]["choices_sha256"], formula_estimate=estimate_formula(family, args.rank))
        summaries.append(summary)
        save(root/"preflight.json", summaries)
        if args.mode == "scan":
            remaining = deadline-time.monotonic()-2
            if remaining <= 0:
                summary["scan"] = dict(status="UNKNOWN", reason="setup exhausted total budget")
            else:
                result = single_coordinate_scan(family, seconds=min(120, args.scan_seconds, remaining),
                    max_sources=args.max_sources, on_improvement=retain)
                result.pop("candidate")
                summary["scan"] = result
                save(root/f"{orientation}.scan.json", result)
        if args.mode == "sat":
            result = run_sat(family, args, root, deadline, baseline, retain)
            save(root/"result.json", dict(result, elapsed_seconds=time.monotonic()-started,
                records=records, scope=SCOPE))
            print(json.dumps(dict(status=result["status"], phase=result.get("phase"),
                baseline_rank=summary["baseline_rank"], winner=(root/"WINNER.json").exists())), flush=True)
            return 2 if result["status"] == "ERROR" else 0
        del family
        gc.collect()
    result = dict(status="PREPARED" if args.mode == "prepare" else "SCAN_FINISHED",
        elapsed_seconds=time.monotonic()-started, orientations=summaries, records=records,
        winner=(root/"WINNER.json").exists(), scope=SCOPE)
    save(root/"result.json", result)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


def run_sat(family, args, root, deadline, baseline, retain):
    control_rank = family["metadata"]["dominance_source_ranks"][baseline]
    for phase, rank in (("control", control_rank), ("target", args.rank)):
        if deadline-time.monotonic() <= 2:
            return dict(status="UNKNOWN", phase=phase, reason="total budget exhausted")
        try:
            problem = build_problem(family, rank, args.max_formula_mb)
        except FormulaMemoryLimit as exc:
            return dict(status="UNKNOWN", phase=phase, reason=str(exc), resource_limit=True)
        write_formula(problem, root/f"{phase}.problem")
        remaining = deadline-time.monotonic()-2
        if remaining <= 0:
            return dict(status="UNKNOWN", phase=phase, reason="formula export exhausted total budget")
        try:
            result = solve(problem, seconds=min(args.control_seconds, remaining) if phase == "control" else remaining,
                memory_mb=args.memory_mb,
                assumptions=source_assumptions(problem, baseline) if phase == "control" else None)
        except Exception as exc:
            return dict(status="ERROR", phase=phase, error=f"{type(exc).__name__}: {exc}")
        candidate = result.pop("candidate", None)
        model = result.pop("complete_assignment", None)
        if model is not None:
            save(root/f"{phase}.model.json", dict(assignment=model, formula_sha256=result["formula_sha256"]))
        if candidate is not None:
            retain(candidate, result["verification"], result["selection"])
        save(root/f"{phase}.result.json", result)
        del problem
        gc.collect()
        if phase == "control" and result["status"] != "SAT":
            return dict(status="ERROR", phase="control", reason="known exact source feasibility control failed",
                control_status=result["status"])
    return dict(result, phase="target", control_status="SAT")


if __name__ == "__main__":
    raise SystemExit(main())
