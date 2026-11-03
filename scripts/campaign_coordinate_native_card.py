"""Frozen exact source-column recombination using native Minicard at-mosts.

Default prepare mode starts no solver. Campaign inputs are strictly n=5/F2;
the target is at most 92 products and the fixed-source positive control uses
native bound 93. The mathematical family matches coordinate_stencil_sat.
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
from mmsearch.coordinate_native_card import (SCOPE, FormulaMemoryLimit, VerifiedSources,
    audit, build_family, build_problem, estimate_formula, formula_audit,
    solve, source_assumptions, verify_selection)
from mmsearch.recombine import digest, save
from mmsearch.verify import verify_candidate, write_standalone_verifier


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
        "coordinate_native_card.py", "coordinate_stencil_sat.py", "free_factor_sat.py",
        "recombine.py", "recombine_sat.py", "verify.py", "sat.py", "sat_neighborhoods.py",
        "compact_sat.py", "tensor.py", "__init__.py")]
    hashes = {}
    for path in files:
        raw = path.read_bytes()
        relative = path.relative_to(REPO)
        destination = root/"code"/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        hashes[str(relative)] = hashlib.sha256(raw).hexdigest()
    return hashes


def save_record(root, stem, candidate, verification):
    """Independently recheck exports; create the first winner exclusively."""
    report = verify_candidate(candidate, random_trials=16)
    if (not report["valid"] or not verification["valid"] or
            report["rank"] != verification["rank"] or
            report["exact_entries_checked"] != report["dimension"]**6):
        raise AssertionError("exported candidate failed independent certificate verification")
    save(root/f"{stem}.json", candidate)
    save(root/f"{stem}.verification.json", report)
    record = dict(stem=stem, rank=report["rank"], candidate_sha256=digest(candidate),
        exact_entries_checked=report["exact_entries_checked"], verification=report,
        orientation=candidate.get("metadata", {}).get("orientation"),
        selection=candidate.get("metadata", {}).get("selection"))
    winner = report["dimension"] == 5 and report["field"] == 2 and report["rank"] <= 92
    if winner:
        try:
            with (root/"WINNER.json").open("x") as stream:
                stream.write(json.dumps(candidate, sort_keys=True, indent=2)+"\n")
        except FileExistsError:
            pass
        else:
            save(root/"WINNER.verification.json", report)
            write_standalone_verifier(root/"WINNER.verify.py")
    return record, winner


def write_formula(problem, stem):
    # Native constraints are first-class data, never silently omitted from CNF.
    save(str(stem)+".json", formula_audit(problem))
    with Path(str(stem)+".clauses.cnf").open("x") as stream:
        stream.write("c CNF fragment only; all native at-most constraints are mandatory in the sibling .json\n")
        stream.write(f"p cnf {problem['nv']} {len(problem['clauses'])}\n")
        for clause in problem["clauses"]:
            stream.write(" ".join(map(str, clause))+" 0\n")


def run_sat(family, args, root, deadline, baseline, retain):
    for phase, rank in (("control", 93), ("target", args.rank)):
        if deadline-time.monotonic() <= 2:
            return dict(status="UNKNOWN", phase=phase, reason="total budget exhausted")
        try:
            problem = build_problem(family, rank, args.max_formula_mb, not args.no_reverse_links)
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
            save(root/f"{phase}.model.json", dict(assignment=model,
                formula_sha256=result["formula_sha256"], native_atmost_sha256=result["native_atmost_sha256"],
                layout="index0 unused; all indices 1..nv are Boolean; x/y only, no auxiliary variables"))
        won = retain(candidate, result["verification"]) if candidate is not None else False
        save(root/f"{phase}.result.json", result)
        del problem
        gc.collect()
        if won:
            return dict(result, phase=phase, stopped_on_first_winner=True)
        if phase == "control" and result["status"] != "SAT":
            return dict(status="ERROR", phase="control", reason="known exact fixed-source native control failed",
                control_status=result["status"], control_error=result.get("error"))
    return dict(result, phase="target", control_status="SAT")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, default=[])
    parser.add_argument("--candidate-dir", action="append", type=Path, default=[])
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--orientation", choices=["uv", "vw", "wu", "all"], default="all")
    parser.add_argument("--mode", choices=["prepare", "sat"], default="prepare")
    parser.add_argument("--prepare-only", "--preflight", dest="prepare_only", action="store_true")
    parser.add_argument("--rank", type=int, default=92)
    parser.add_argument("--seconds", type=float, default=600)
    parser.add_argument("--control-seconds", type=float, default=5)
    parser.add_argument("--max-inputs", type=int, default=2048)
    parser.add_argument("--max-formula-mb", type=float, default=384)
    parser.add_argument("--memory-mb", type=int, default=1536)
    parser.add_argument("--no-reverse-links", action="store_true")
    parser.add_argument("--outdir", "--output-dir", dest="outdir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.prepare_only:
        args.mode = "prepare"
    if (not 0 <= args.rank <= 92 or args.max_inputs < 1 or args.memory_mb < 128 or
            any(not math.isfinite(v) or v <= 0 for v in
                (args.seconds, args.control_seconds, args.max_formula_mb))):
        parser.error("invalid bounds; campaign is strictly n=5/F2 with target <=92")
    if args.mode == "sat" and args.orientation == "all":
        parser.error("SAT mode requires a single orientation")
    if not args.input and not args.candidate_dir and not args.baseline:
        parser.error("supply --input, --candidate-dir, or --baseline")
    started, root = time.monotonic(), args.outdir
    deadline = started+args.seconds
    root.mkdir(parents=True, exist_ok=False)
    (root/"inputs").mkdir()
    manifest = dict(method="exact coordinatewise source stencils with native Minicard cardinality", scope=SCOPE,
        mathematical_family="identical to coordinate_stencil_sat; different backend/cardinality representation",
        started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        parameters={key: str(value) if isinstance(value, Path) else [str(x) for x in value] if isinstance(value, list) else value
                    for key, value in vars(args).items()}, code_sha256=freeze_code(root),
        seed=None, randomness="deterministic sorted inputs/choices; Minicard default seed; no rate claim",
        cleanup_reserve_seconds=2, solver_threads=1)
    save(root/"manifest.json", manifest)
    paths = {path.resolve(): True for path in args.input}
    if args.baseline:
        paths[args.baseline.resolve()] = True
    for directory in args.candidate_dir:
        if not directory.is_dir():
            raise ValueError(f"candidate directory does not exist: {directory}")
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
            raise ValueError("input certificate cap exceeded")
        snapshot = root/"inputs"/f"source{len(candidates):04d}.json"
        snapshot.write_bytes(raw)
        provenance.append(dict(path=str(path), snapshot=str(snapshot.relative_to(root)),
            raw_sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)))
        candidates.append(candidate)
    sources = VerifiedSources(candidates, dimension=5, provenance=provenance)
    if min(source["canonical_rank"] for source in sources.sources) > 93:
        raise ValueError("include a verified <=93 source for the native positive control")
    baseline_source = None
    if args.baseline:
        baseline_source = sources.input_sources[next(i for i, entry in enumerate(provenance)
            if entry["path"] == str(args.baseline.resolve()))]["source_index"]
        if sources.sources[baseline_source]["canonical_rank"] > 93:
            raise ValueError("explicit baseline must have canonical rank <=93")
    save(root/"sources.json", dict(source_pool_sha256=sources.sha256, sources=sources.sources,
        inputs=sources.input_sources, skipped=skipped, explicit_baseline_source=baseline_source))
    del candidates
    records, summaries = [], []

    def retain(candidate, verification):
        record, won = save_record(root, f"record{len(records):04d}", candidate, verification)
        records.append(record)
        save(root/"records.json", records)
        return won

    def finish(result):
        result.update(elapsed_seconds=time.monotonic()-started, records=records,
            orientations=summaries, winner=(root/"WINNER.json").exists(), scope=SCOPE)
        save(root/"result.json", result)
        print(json.dumps(result, sort_keys=True), flush=True)
        return 2 if result["status"] == "ERROR" else 0

    orientations = ["uv", "vw", "wu"] if args.orientation == "all" else [args.orientation]
    for orientation in orientations:
        family = build_family(sources, orientation)
        save(root/f"{orientation}.family.audit.json", audit(family))
        baseline = family["metadata"]["baseline_source"] if baseline_source is None else baseline_source
        for source in dict.fromkeys([baseline, family["metadata"]["baseline_source"]]):
            candidate, verification = verify_selection(family, family["source_choices"][source],
                dict(phase="native backend baseline embedding"))
            if retain(candidate, verification):
                return finish(dict(status="SAT", phase="baseline", stopped_on_first_winner=True))
        summary = dict(orientation=orientation, pair_count=len(family["pairs"]), source_count=len(sources.sources),
            retained_stencils_per_coordinate=[len(row) for row in family["choices"]],
            baseline_rank=family["metadata"]["dominance_source_ranks"][baseline],
            pairs_sha256=family["metadata"]["pairs_sha256"], choices_sha256=family["metadata"]["choices_sha256"],
            formula_estimate=estimate_formula(family, args.rank, not args.no_reverse_links))
        if args.mode == "prepare":
            try:
                problem = build_problem(family, args.rank, args.max_formula_mb, not args.no_reverse_links)
            except FormulaMemoryLimit as exc:
                return finish(dict(status="UNKNOWN", phase="prepare", reason=str(exc), resource_limit=True))
            write_formula(problem, root/f"{orientation}.target.problem")
            summary.update(variables=problem["nv"], auxiliary_variables=0,
                cnf_clauses=len(problem["clauses"]), native_atmost_constraints=len(problem["atmosts"]),
                formula_sha256=problem["metadata"]["formula_sha256"],
                native_atmost_sha256=problem["metadata"]["native_atmost_sha256"])
            del problem
        summaries.append(summary)
        save(root/"preflight.json", summaries)
        if args.mode == "sat":
            return finish(run_sat(family, args, root, deadline, baseline, retain))
        del family
        gc.collect()
    return finish(dict(status="PREPARED", no_solver_launched=True))


if __name__ == "__main__":
    raise SystemExit(main())
