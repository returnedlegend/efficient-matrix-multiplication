"""Native Minicard encoding of the frozen finite coordinate-stencil family.

Mathematical choices are identical to coordinate_stencil_sat; only the
cardinality representation and SAT backend differ. Restricted UNSAT applies
to this finite family. No performance advantage is assumed.
"""
from __future__ import annotations

import hashlib
import json
import math
import multiprocessing as mp
from pathlib import Path
import tempfile
import time

from .coordinate_stencil_sat import (SCOPE, FormulaMemoryLimit, VerifiedSources,
    audit, build_family, selected_union, source_assumptions, verify_selection)
from .recombine import digest
from .recombine_sat import bits


def code_hash():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
        Path(__file__), Path(__file__).with_name("coordinate_stencil_sat.py"),
        Path(__file__).with_name("free_factor_sat.py"), Path(__file__).with_name("recombine.py"),
        Path(__file__).with_name("recombine_sat.py"), Path(__file__).with_name("verify.py"))}


def estimate_formula(family, rank=92, reverse_links=True):
    if type(rank) is not int or rank < 0 or type(reverse_links) is not bool:
        raise ValueError("nonnegative integer rank and Boolean reverse-links required")
    p = len(family["pairs"])
    count = sum(len(row) for row in family["choices"])
    links = sum(item["mask"].bit_count() for row in family["choices"] for item in row)
    clauses = len(family["choices"])+links+(p if reverse_links else 0)
    literals = count+2*links+(links+p if reverse_links else 0)
    native_literals = count+p
    estimated = clauses*96+literals*40+native_literals*80+(count+p)*80
    return dict(pair_count=p, choice_count=count, variables=count+p, auxiliary_variables=0,
        link_count=links, cnf_clauses=clauses, cnf_literals=literals,
        native_atmost_constraints=len(family["choices"])+1, native_atmost_literals=native_literals,
        estimated_python_formula_bytes=estimated,
        estimated_python_formula_mb=math.ceil(estimated/1024**2),
        policy="conservative Python CNF/native-cardinality storage estimate; native solver/inherited RSS additional; hard child memory limit")


def build_problem(family, rank=92, max_formula_mb=384, reverse_links=True):
    if not math.isfinite(max_formula_mb) or max_formula_mb <= 0:
        raise ValueError("positive finite formula memory cap required")
    estimate = estimate_formula(family, rank, reverse_links)
    if estimate["estimated_python_formula_bytes"] > max_formula_mb*1024**2:
        raise FormulaMemoryLimit(f"estimated formula {estimate['estimated_python_formula_mb']} MiB exceeds {max_formula_mb} MiB cap")
    xs, nv = [], 0
    for row in family["choices"]:
        xs.append(list(range(nv+1, nv+len(row)+1)))
        nv += len(row)
    ys = list(range(nv+1, nv+len(family["pairs"])+1))
    nv += len(ys)
    clauses, atmosts, reverse = [], [], [[] for _ in ys]
    for c, row in enumerate(family["choices"]):
        clauses.append(list(xs[c]))
        atmosts.append(dict(literals=list(xs[c]), bound=1, purpose=f"coordinate {c} at most one"))
        for j, item in enumerate(row):
            for g in bits(item["mask"]):
                clauses.append([-xs[c][j], ys[g]])
                reverse[g].append(xs[c][j])
    if reverse_links:
        clauses.extend([[-y]+reverse[g] for g, y in enumerate(ys)])
    atmosts.append(dict(literals=list(ys), bound=rank, purpose="active pair group count"))
    formula = dict(nv=nv, clauses=clauses, atmosts=atmosts, x_variables=xs, y_variables=ys)
    metadata = dict(family["metadata"], encoding="exact-coordinatewise-stencil-native-minicard-v1",
        rank_bound=rank, variables=nv, auxiliary_variables=0, cnf_clauses=len(clauses),
        native_atmost_constraints=len(atmosts), native_xors=0,
        solver="minicard", solver_threads=1, cardinality_encoding="native Minicard at-most constraints",
        reverse_links=reverse_links, native_code_sha256=code_hash(),
        formula_sha256=digest(formula), native_atmost_sha256=digest(atmosts),
        formula_memory_estimate=estimate, max_formula_mb=max_formula_mb,
        equivalence="same finite coordinate family as sequential-counter CNF; backend/encoding differ; no improved solve-rate claim")
    return dict(family=family, clauses=clauses, atmosts=atmosts, nv=nv, xs=xs, ys=ys, metadata=metadata)


def formula_audit(problem):
    return dict(metadata=problem["metadata"], nv=problem["nv"], clauses=problem["clauses"],
        atmosts=problem["atmosts"], x_variables=problem["xs"], y_variables=problem["ys"],
        variable_layout="x[coordinate][choice], y[pair]; these are all variables; no cardinality auxiliaries",
        native_semantics="for every atmost, count true signed literals <= bound; all coordinate OR clauses must also hold")


def validate_decode(problem, assignment):
    if (not isinstance(assignment, (list, tuple)) or len(assignment) != problem["nv"]+1 or
            any(type(value) is not bool for value in assignment[1:])):
        raise AssertionError("incomplete or non-Boolean solver model")
    for clause in problem["clauses"]:
        if not any(assignment[abs(lit)] == (lit > 0) for lit in clause):
            raise AssertionError("solver model violates CNF clause")
    for constraint in problem["atmosts"]:
        if sum(assignment[abs(lit)] == (lit > 0) for lit in constraint["literals"]) > constraint["bound"]:
            raise AssertionError(f"solver model violates native at-most: {constraint['purpose']}")
    selection = []
    for row in problem["xs"]:
        chosen = [j for j, variable in enumerate(row) if assignment[variable]]
        if len(chosen) != 1:
            raise AssertionError("solver model violates exactly-one choice")
        selection.append(chosen[0])
    union = selected_union(problem["family"], selection)
    if union.bit_count() > problem["metadata"]["rank_bound"]:
        raise AssertionError("solver model violates actual union rank bound")
    for g, variable in enumerate(problem["ys"]):
        if union >> g & 1 and not assignment[variable]:
            raise AssertionError("active stencil group lacks indicator")
        if problem["metadata"]["reverse_links"] and assignment[variable] != bool(union >> g & 1):
            raise AssertionError("indicator disagrees with selected stencil union")
    candidate, verification = verify_selection(problem["family"], selection, dict(
        formula_sha256=problem["metadata"]["formula_sha256"],
        native_atmost_sha256=problem["metadata"]["native_atmost_sha256"],
        solver_variant="minicard native cardinality; exact same finite coordinate family"))
    return candidate, verification, selection


def _worker(problem, seconds, memory_mb, assumptions, result_path):
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (memory_mb*1024**2, memory_mb*1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(seconds)+1, math.ceil(seconds)+2))
        import pysat
        from pysat.solvers import Solver
        with Solver(name="minicard", bootstrap_with=problem["clauses"]) as solver:
            if not solver.supports_atmost():
                raise RuntimeError("Minicard backend lacks native at-most support")
            for constraint in problem["atmosts"]:
                solver.add_atmost(constraint["literals"], constraint["bound"])
            if problem["nv"]:
                solver.add_clause([problem["nv"], -problem["nv"]])
            sat = solver.solve(assumptions=assumptions)
            assignment = None
            if sat:
                model = solver.get_model()
                mapped = {abs(lit): lit > 0 for lit in model}
                if len(model) != problem["nv"] or set(mapped) != set(range(1, problem["nv"]+1)):
                    raise AssertionError("solver returned incomplete or duplicate assignment")
                assignment = [None]+[mapped[i] for i in range(1, problem["nv"]+1)]
            result = dict(status="SAT" if sat is True else "UNSAT" if sat is False else "UNKNOWN",
                assignment=assignment, solver="minicard", pysat_version=pysat.__version__)
    except Exception as exc:
        # Backend availability/load failures are ERROR, never UNSAT.
        result = dict(status="ERROR", error=f"{type(exc).__name__}: {exc}")
    with open(result_path, "w") as stream:
        json.dump(result, stream)


def solve(problem, seconds=10, memory_mb=1536, assumptions=None):
    """Child wall limit includes load/export; terminate, kill and reap on return.

    Caller must reserve two seconds for cleanup. Full model/tensor verification
    is performed after the child is reaped, outside the solver wall budget.
    """
    if not math.isfinite(seconds) or seconds <= 0 or type(memory_mb) is not int or memory_mb < 128:
        raise ValueError("invalid solver resource bounds")
    assumptions = [] if assumptions is None else list(assumptions)
    if any(type(lit) is not int or not 1 <= abs(lit) <= problem["nv"] for lit in assumptions):
        raise ValueError("invalid assumptions")
    context = mp.get_context("fork")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="mmsearch-native-card-") as directory:
        result_path = Path(directory)/"result.json"
        child = context.Process(target=_worker,
            args=(problem, seconds, memory_mb, assumptions, str(result_path)))
        child.start()
        try:
            child.join(timeout=max(0, seconds-(time.monotonic()-started)))
            timed_out = child.is_alive()
        finally:
            if child.is_alive():
                child.terminate()
            child.join(timeout=1)
            if child.is_alive():
                child.kill()
                child.join()
        if timed_out:
            result = dict(status="UNKNOWN", reason="hard wall-clock limit including load/result export")
        else:
            try:
                result = json.loads(result_path.read_text())
            except (OSError, ValueError) as exc:
                result = dict(status="ERROR", error=f"solver worker exited without complete result: {exc}")
    assignment = result.pop("assignment", None)
    result.update(elapsed_seconds=time.monotonic()-started, wall_seconds=seconds, memory_mb=memory_mb,
        threads=1, worker_pid=child.pid, worker_reaped=not child.is_alive(), assumptions=assumptions,
        formula_sha256=problem["metadata"]["formula_sha256"],
        native_atmost_sha256=problem["metadata"]["native_atmost_sha256"], scope=SCOPE)
    if result["status"] == "SAT":
        if (not isinstance(assignment, list) or len(assignment) != problem["nv"]+1 or
                any(assignment[abs(lit)] != (lit > 0) for lit in assumptions)):
            raise AssertionError("solver model violates fixed source assumptions or is incomplete")
        candidate, verification, selection = validate_decode(problem, assignment)
        result.update(candidate=candidate, verification=verification, selection=selection,
            complete_assignment=assignment)
    return result
