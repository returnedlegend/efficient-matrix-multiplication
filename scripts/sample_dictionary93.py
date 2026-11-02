"""Bounded persistent native-XOR sampling of exact fixed-dictionary algorithms.

All models pass the original-row and independent full tensor verifier before
publication. Enumerated rank-93 seeds are search inputs, never rank records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing as mp
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.recombine import canonical_terms, digest, encode, save
from mmsearch.recombine_sat import build_system, validate_decode
from mmsearch.recombine_sat_preprocessed import build_problem
from mmsearch.verify import verify_candidate, write_standalone_verifier


def worker(problem, seconds, conflicts, memory_mb, max_models, sender):
    started = time.monotonic()
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (memory_mb*1024**2, memory_mb*1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(seconds)+1, math.ceil(seconds)+2))
        import pycryptosat
        solver = pycryptosat.Solver(threads=1, verbose=0, time_limit=seconds, confl_limit=conflicts)
        solver.add_clause([problem["nv"], -problem["nv"]])
        for clause in problem["clauses"]:
            solver.add_clause(clause)
        for variables, rhs in problem["xors"]:
            solver.add_xor_clause(variables, rhs)
        count = problem["metadata"]["selection_variables"]
        for index in range(max_models):
            remaining = seconds-(time.monotonic()-started)
            if remaining <= 0:
                sender.send(dict(event="done", status="UNKNOWN", reason="child wall budget"))
                break
            status, assignment = solver.solve(time_limit=remaining, confl_limit=conflicts)
            if status is not True:
                sender.send(dict(event="done", status="UNSAT" if status is False else "UNKNOWN",
                                 reason="remaining dictionary models under configured limits"))
                break
            selected = [v for v in range(1, count+1) if assignment[v]]
            sender.send(dict(event="model", index=index, assignment=assignment,
                             pycryptosat_version=pycryptosat.__version__, selected_count=len(selected)))
            if len(selected) < problem["metadata"]["rank_bound"]:
                sender.send(dict(event="done", status="IMPROVEMENT", reason="below requested rank; stopped"))
                break
            # With exactly rank_bound selected terms this blocks only the
            # selected set: no proper superset satisfies the cardinality cap.
            solver.add_clause([-v for v in selected])
        else:
            sender.send(dict(event="done", status="LIMIT", reason="model count reached"))
    except Exception as exc:
        sender.send(dict(event="done", status="ERROR", error=f"{type(exc).__name__}: {exc}"))
    finally:
        sender.close()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dictionary", type=Path, required=True)
    p.add_argument("--baseline", type=Path)
    p.add_argument("--source-manifest", type=Path)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--publish-dir", type=Path, required=True)
    p.add_argument("--dimension", type=int, default=5)
    p.add_argument("--rank", type=int, default=93)
    p.add_argument("--seconds", type=float, default=60)
    p.add_argument("--max-models", type=int, default=16)
    p.add_argument("--conflicts", type=int, default=1000000)
    p.add_argument("--memory-mb", type=int, default=2048)
    a = p.parse_args(argv)
    if not math.isfinite(a.seconds) or a.seconds <= 0 or min(a.dimension, a.rank, a.max_models, a.conflicts) < 1 or a.memory_mb < 128:
        p.error("invalid bounded sampler parameters")
    started = time.monotonic()
    deadline = started+a.seconds
    root, published = a.output_dir, a.publish_dir
    if (root/"manifest.json").exists():
        raise ValueError("use a new sampler output directory")
    root.mkdir(parents=True, exist_ok=True)
    published.mkdir(parents=True, exist_ok=True)
    inputs = root/"inputs"
    inputs.mkdir(exist_ok=True)
    source = {}

    def snapshot(path, name):
        raw = path.read_bytes()
        target = inputs/name
        target.write_bytes(raw)
        source[name] = dict(path=str(path), snapshot=str(target.resolve()), raw_sha256=hashlib.sha256(raw).hexdigest())
        return json.loads(raw)

    dictionary = snapshot(a.dictionary, "dictionary.json")
    baseline = snapshot(a.baseline, "baseline.json") if a.baseline else None
    manifest_path = a.source_manifest or a.dictionary.with_name("pool.json")
    if manifest_path.exists():
        source["pool_sha256"] = snapshot(manifest_path, "source-pool.json").get("pool_sha256")
    provenance = dict(inputs=source, sampler_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    system = build_system(dictionary, a.dimension, baseline=baseline, provenance=provenance)
    problem = build_problem(system, rank=a.rank)
    settings = dict(total_wall_seconds=a.seconds, max_models=a.max_models, conflicts_per_solve=a.conflicts,
                    memory_mb=a.memory_mb, solver_threads=1,
                    solver_randomness="CryptoMiniSat default seed; persistent learned state",
                    blocking="negative selected original indicators; exact set exclusion at rank bound")
    save(root/"manifest.json", dict(problem["metadata"], sampling=settings))
    write_standalone_verifier(root/"verify.py")
    context = mp.get_context("fork")
    receiver, sender = context.Pipe(duplex=False)
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        result = dict(status="UNKNOWN", reason="setup exhausted total budget", models=[])
        save(root/"summary.json", result)
        print(json.dumps(result), flush=True)
        return 0
    child = context.Process(target=worker, args=(problem, remaining, a.conflicts, a.memory_mb, a.max_models, sender))
    child.start()
    sender.close()
    records, seen = [], set()
    result = dict(status="UNKNOWN", reason="hard wall-clock limit")
    try:
        while time.monotonic() < deadline:
            if not receiver.poll(max(0, deadline-time.monotonic())):
                break
            try:
                message = receiver.recv()
            except EOFError:
                result = dict(status="ERROR", reason="worker exited without final event")
                break
            if message["event"] == "done":
                result = {k: v for k, v in message.items() if k != "event"}
                break
            candidate, verification = validate_decode(problem, message["assignment"])
            # Explicit publication-time independent check covers all n**6
            # entries and multiplication without relying on worker claims.
            exact = verify_candidate(candidate, random_trials=16)
            if not exact["valid"] or exact["rank"] > a.rank:
                raise AssertionError("sampler model failed independent publication verification")
            sha = digest(encode(canonical_terms(candidate), a.dimension))
            if sha in seen:
                raise AssertionError("persistent solver repeated a blocked canonical set")
            seen.add(sha)
            candidate["metadata"]["sampling"] = dict(settings, model_index=message["index"],
                pycryptosat_version=message["pycryptosat_version"], canonical_sha256=sha,
                sampler_sha256=provenance["sampler_sha256"])
            destination = published/(sha+".json")
            save(root/"models"/(sha+".json"), candidate)
            save(root/"verification"/(sha+".json"), exact)
            record = dict(index=message["index"], rank=exact["rank"], canonical_sha256=sha,
                          path=str(destination), exact_entries_checked=exact["exact_entries_checked"])
            if exact["rank"] < a.rank:
                record["path"] = str(root/"FOUND.json")
                save(root/"FOUND.json", candidate)
                save(root/"FOUND.verification.json", exact)
                write_standalone_verifier(root/"FOUND.verify.py")
                records.append(record)
                result = dict(status="IMPROVEMENT", reason="independently verified rank below requested bound")
                print(json.dumps(dict(event="FOUND_EXACT", **record)), flush=True)
                break
            # Published directory contains only rank-bound seeds, matching the
            # native campaign portfolio schema and automatic consumer filter.
            save(destination, candidate)
            records.append(record)
            save(root/"models.json", records)
            print(json.dumps(dict(event="verified_seed", **record)), flush=True)
    finally:
        if child.is_alive():
            child.terminate()
        child.join(timeout=1)
        if child.is_alive():
            child.kill()
            child.join()
        receiver.close()
    result.update(models=records, model_count=len(records), elapsed_seconds=time.monotonic()-started,
                  dictionary_sha256=system["metadata"]["dictionary_sha256"], formula_sha256=problem["metadata"]["formula_sha256"],
                  scope="exact dictionary search seeds; rank-bound models make no rank-reduction or novelty claim")
    save(root/"summary.json", result)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 2 if result["status"] == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
