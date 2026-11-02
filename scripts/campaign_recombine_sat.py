"""Single-process bounded native-XOR SAT over a frozen term dictionary.

Example: PYTHONPATH=.xor-deps:. taskset -c 1 python scripts/campaign_recombine_sat.py
 --dictionary PATH/dictionary.json --baseline PATH/best.json --output-dir PATH/sat
 --seconds 600 --conflicts 10000000
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.recombine import digest, save
from mmsearch.recombine_sat import audit, build_problem, build_system, solve
from mmsearch.verify import write_standalone_verifier
from mmsearch.xor_sat import write_problem


def load_extra(path, dimension):
    raw = Path(path).read_bytes()
    terms = [tuple(map(int, line.split())) for line in raw.decode().splitlines() if line.strip()]
    if any(len(t) != 3 or any(not 0 < x < 1 << (dimension*dimension) for x in t) for t in terms):
        raise ValueError("extra terms must be nonzero in-range integer mask triples")
    return terms, raw


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dictionary", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--source-manifest", type=Path)
    p.add_argument("--extra-terms", type=Path, action="append", default=[])
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--dimension", type=int, default=5)
    p.add_argument("--rank", type=int, default=92)
    p.add_argument("--seconds", type=float, default=600)
    p.add_argument("--conflicts", type=int, default=10000000)
    p.add_argument("--memory-mb", type=int, default=2048)
    p.add_argument("--encoding", choices=["cardnetwrk", "totalizer", "seqcounter"], default="cardnetwrk")
    p.add_argument("--control-seconds", type=float, default=2)
    a = p.parse_args(argv)
    if any(not math.isfinite(x) or x <= 0 for x in (a.seconds, a.control_seconds)) or a.rank < 0 or a.dimension < 1 or a.conflicts < 1 or a.memory_mb < 128:
        p.error("invalid solver bounds")
    started = time.monotonic()
    deadline = started+a.seconds
    root = a.output_dir
    if (root/"manifest.json").exists():
        raise ValueError("choose a new output directory to preserve frozen solver provenance")
    root.mkdir(parents=True, exist_ok=True)
    inputs = root/"inputs"
    inputs.mkdir(exist_ok=True)
    provenance = dict(wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), inputs=[])

    def freeze(path, name):
        raw = path.read_bytes()
        snapshot = inputs/name
        snapshot.write_bytes(raw)
        provenance["inputs"].append(dict(path=str(path), snapshot=str(snapshot.resolve()),
                                          raw_sha256=hashlib.sha256(raw).hexdigest()))
        return raw

    raw = freeze(a.dictionary, "dictionary.json")
    dictionary = json.loads(raw)
    # Validate the supplied base before canonicalizing the union with extra terms.
    base = build_system(dictionary, a.dimension)
    provenance["original_dictionary_sha256"] = base["metadata"]["dictionary_sha256"]
    provenance["original_dictionary_size"] = len(dictionary)
    del base
    baseline = json.loads(freeze(a.baseline, "baseline.json"))
    source_manifest = a.source_manifest or a.dictionary.with_name("pool.json")
    if source_manifest.exists():
        raw = freeze(source_manifest, "source-pool.json")
        provenance["source_pool_sha256"] = json.loads(raw).get("pool_sha256")
    for i, path in enumerate(a.extra_terms):
        raw = freeze(path, f"extra-terms-{i}.txt")
        extra = [tuple(map(int, line.split())) for line in raw.decode().splitlines() if line.strip()]
        if any(len(t) != 3 or any(not 0 < x < 1 << (a.dimension*a.dimension) for x in t) for t in extra):
            raise ValueError("extra terms must be nonzero in-range integer mask triples")
        dictionary = sorted(set(tuple(t) for t in dictionary) | set(extra))
    provenance["extra_terms_policy"] = "legitimate nonzero rank-one columns; no full source-algorithm exactness is asserted"
    system = build_system(dictionary, a.dimension, baseline=baseline, provenance=provenance)
    save(root/"dictionary.json", system["dictionary"])
    save(root/"system.audit.json", audit(system))
    setup = time.monotonic()
    problem = build_problem(system, rank=a.rank, encoding=a.encoding)
    problem["metadata"]["cardinality_build_seconds"] = time.monotonic()-setup
    write_problem(problem, root/"problem")
    manifest = dict(problem["metadata"], solver_budget=dict(total_wall_seconds=a.seconds,
        conflicts=a.conflicts, memory_mb=a.memory_mb, threads=1), started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    save(root/"manifest.json", manifest)
    # Feasibility control fixes every dictionary indicator to the known exact
    # baseline, at its original rank. Auxiliary cardinality variables remain free.
    control_problem = build_problem(system, rank=system["metadata"]["baseline"]["rank"], encoding=a.encoding)
    witness = system["baseline_mask"]
    fixed = [i+1 if witness >> i & 1 else -(i+1) for i in range(len(dictionary))]
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        control = dict(status="UNKNOWN", reason="setup exhausted total wall budget")
    else:
        control = solve(control_problem, seconds=min(a.control_seconds, remaining), conflicts=a.conflicts,
                        memory_mb=a.memory_mb, assumptions=fixed)
    if "candidate" in control:
        save(root/"control.candidate.json", control.pop("candidate"))
    save(root/"control.result.json", control)
    remaining = deadline-time.monotonic()
    if control["status"] != "SAT":
        result = dict(status="ERROR", error="known exact baseline SAT feasibility control did not pass", control_status=control["status"])
    elif remaining <= 0:
        result = dict(status="UNKNOWN", reason="control/setup exhausted total wall budget")
    else:
        result = solve(problem, seconds=remaining, conflicts=a.conflicts, memory_mb=a.memory_mb)
    if "candidate" in result:
        candidate = result.pop("candidate")
        save(root/"FOUND.json", candidate)
        save(root/"FOUND.verification.json", result["verification"])
        write_standalone_verifier(root/"FOUND.verify.py")
    result.update(total_elapsed_seconds=time.monotonic()-started,
        dictionary_sha256=system["metadata"]["dictionary_sha256"], dictionary_size=len(dictionary),
        rank_bound=a.rank, linear_rank=len(system["reduced"]), linear_nullity=len(dictionary)-len(system["reduced"]),
        formula_sha256=problem["metadata"]["formula_sha256"],
        control_status=control["status"], scope=system["metadata"]["scope"])
    save(root/"result.json", result)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 2 if result["status"] == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
