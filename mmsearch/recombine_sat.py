"""Exact subset SAT over a frozen dictionary of F2 rank-one terms.

Each dictionary term has one Boolean selection variable. Linear tensor
equations cover all n**6 entries; no source-algorithm span restriction applies.
UNSAT is scoped only to the supplied finite dictionary and cardinality bound.
"""
from __future__ import annotations

import hashlib
import json
import math
import multiprocessing as mp
from pathlib import Path
import time

from .recombine import canonical_terms, digest, encode
from .verify import verify_candidate


def code_hash():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__), Path(__file__).with_name("recombine.py"), Path(__file__).with_name("verify.py"))}


def bits(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length()-1
        mask ^= bit


def row_reduce(rows, variables):
    """Return independent augmented equations and original-row XOR witnesses."""
    coefficient_mask = (1 << variables)-1
    basis = {}
    for i, original in enumerate(rows):
        row, proof = original, 1 << i
        while row & coefficient_mask:
            pivot = ((row & coefficient_mask) & -(row & coefficient_mask)).bit_length()-1
            if pivot not in basis:
                basis[pivot] = row, proof
                break
            row ^= basis[pivot][0]
            proof ^= basis[pivot][1]
        else:
            if row >> variables:
                # Keep an explicit contradiction and its independently checkable witness.
                return [1 << variables], [proof]
    return [basis[i][0] for i in sorted(basis)], [basis[i][1] for i in sorted(basis)]


def build_system(dictionary, dimension, baseline=None, provenance=None):
    if type(dimension) is not int or dimension < 1 or not isinstance(dictionary, (list, tuple)) or not dictionary:
        raise ValueError("nonempty dictionary and positive dimension required")
    bound = 1 << (dimension*dimension)
    for term in dictionary:
        if not isinstance(term, (list, tuple)) or len(term) != 3 or any(type(x) is not int or not 0 < x < bound for x in term):
            raise ValueError("dictionary entries must be three nonzero in-range integer masks")
    terms = tuple(tuple(t) for t in dictionary)
    if terms != tuple(sorted(set(terms))):
        raise ValueError("dictionary must be sorted and distinct")
    width, count = dimension*dimension, len(terms)
    rows = [0]*(width**3)
    for variable, (u, v, w) in enumerate(terms):
        bit = 1 << variable
        for a in bits(u):
            for b in bits(v):
                offset = (a*width+b)*width
                for c in bits(w):
                    rows[offset+c] ^= bit
    # Target coefficients use the independent trace-index convention.
    for a in range(width):
        i, j = divmod(a, dimension)
        for b in range(width):
            other_j, k = divmod(b, dimension)
            for c in range(width):
                other_k, other_i = divmod(c, dimension)
                if j == other_j and k == other_k and i == other_i:
                    rows[(a*width+b)*width+c] |= 1 << count
    reduced, proofs = row_reduce(rows, count)
    metadata = dict(encoding="fixed-term-dictionary-native-xor-cardinality-v1", dimension=dimension,
        dictionary_size=count, dictionary_sha256=digest(terms), original_equations=len(rows),
        independent_equations=len(reduced), linear_nullity=count-len(reduced),
        original_rows_sha256=digest([hex(r) for r in rows]),
        reduced_rows_sha256=digest([hex(r) for r in reduced]),
        code_sha256=code_hash(), provenance=provenance or {},
        scope="all subsets of this frozen term dictionary; no source-combination restriction; UNSAT is dictionary-only")
    system = dict(dictionary=terms, rows=rows, reduced=reduced, proofs=proofs, metadata=metadata)
    if baseline is not None:
        selected = canonical_terms(baseline)
        report = verify_candidate(baseline, random_trials=0)
        if not report["valid"] or baseline["dimension"] != dimension:
            raise ValueError("baseline must be independently exact in the requested dimension")
        mapping = {t: i for i, t in enumerate(terms)}
        if any(t not in mapping for t in selected):
            raise ValueError("baseline term absent from dictionary")
        witness = sum(1 << mapping[t] for t in selected)
        if not satisfies(rows, witness, count):
            raise AssertionError("independently exact baseline violates encoded tensor equations")
        system["baseline_mask"] = witness
        metadata["baseline"] = dict(rank=witness.bit_count(), selection_hex=hex(witness),
                                    canonical_sha256=digest(encode(selected, dimension)), verification=report)
    return system


def satisfies(rows, selection, variables):
    return all((row & selection).bit_count() % 2 == (row >> variables) for row in rows)


def audit(system):
    return dict(metadata=system["metadata"], dictionary=system["dictionary"],
        augmented_row_layout="bits0..dictionary_size-1 are coefficients; bitdictionary_size is RHS; index=(u*width+v)*width+w",
        original_augmented_rows_hex=[hex(r) for r in system["rows"]],
        independent_augmented_rows_hex=[hex(r) for r in system["reduced"]],
        independent_original_row_xor_witnesses_hex=[hex(r) for r in system["proofs"]])


def build_problem(system, rank=92, encoding="cardnetwrk"):
    if type(rank) is not int or rank < 0 or encoding not in ("cardnetwrk", "totalizer", "seqcounter"):
        raise ValueError("invalid cardinality bound or encoding")
    from pysat.card import CardEnc, EncType
    count = len(system["dictionary"])
    card = CardEnc.atmost(lits=list(range(1, count+1)), bound=min(rank, count),
                         encoding=getattr(EncType, encoding))
    xors, clauses = [], list(card.clauses)
    mask = (1 << count)-1
    for row in system["reduced"]:
        variables, rhs = [i+1 for i in bits(row & mask)], bool(row >> count)
        if variables:
            xors.append((variables, rhs))
        elif rhs:
            clauses.append([])
    metadata = dict(system["metadata"], rank_bound=rank, cardinality_encoding=encoding,
        selection_variable_map="dictionary index i maps to variable i+1", selection_variables=count,
        solver_threads=1, variables=max(count, card.nv), cnf_clauses=len(clauses), native_xors=len(xors))
    metadata["formula_sha256"] = digest(dict(nv=metadata["variables"], clauses=clauses, xors=xors))
    return dict(nv=metadata["variables"], clauses=clauses, xors=xors, metadata=metadata, system=system)


def validate_decode(problem, assignment):
    """Check CNF, independent XOR rows, original n**6 rows and exact tensor."""
    if not isinstance(assignment, (list, tuple)) or len(assignment) <= problem["nv"]:
        raise AssertionError("incomplete solver model")
    if any(not any(bool(assignment[abs(lit)]) == (lit > 0) for lit in clause) for clause in problem["clauses"]):
        raise AssertionError("solver model violates cardinality CNF")
    if any(bool(sum(bool(assignment[v]) for v in variables) % 2) != rhs for variables, rhs in problem["xors"]):
        raise AssertionError("solver model violates native XOR")
    system = problem["system"]
    selection = sum(1 << i for i in range(len(system["dictionary"])) if assignment[i+1])
    if selection.bit_count() > problem["metadata"]["rank_bound"] or not satisfies(system["rows"], selection, len(system["dictionary"])):
        raise AssertionError("solver model violates original exact tensor or rank bound")
    candidate = encode([t for i, t in enumerate(system["dictionary"]) if selection >> i & 1],
        system["metadata"]["dimension"], dict(problem["metadata"], method="fixed-dictionary-exact-F2-subset-SAT", selection_hex=hex(selection)))
    report = verify_candidate(candidate, random_trials=16)
    if not report["valid"]:
        raise AssertionError("SAT subset failed independent exact tensor verification")
    return candidate, report


def _worker(problem, seconds, conflicts, memory_mb, assumptions, sender):
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
        status, assignment = solver.solve(assumptions=assumptions, time_limit=seconds, confl_limit=conflicts)
        sender.send(dict(status="SAT" if status is True else "UNSAT" if status is False else "UNKNOWN",
                         assignment=assignment if status is True else None,
                         pycryptosat_version=pycryptosat.__version__))
    except Exception as exc:
        sender.send(dict(status="ERROR", error=f"{type(exc).__name__}: {exc}"))
    finally:
        sender.close()


def solve(problem, seconds=10, conflicts=100000, memory_mb=2048, assumptions=None):
    if not math.isfinite(seconds) or seconds <= 0 or type(conflicts) is not int or conflicts < 1 or type(memory_mb) is not int or memory_mb < 128:
        raise ValueError("invalid solver resource bounds")
    assumptions = assumptions or []
    if any(type(v) is not int or not 1 <= abs(v) <= problem["nv"] for v in assumptions):
        raise ValueError("invalid assumptions")
    context = mp.get_context("fork")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=_worker, args=(problem, seconds, conflicts, memory_mb, assumptions, sender))
    started = time.monotonic()
    child.start()
    sender.close()
    try:
        if receiver.poll(max(0, seconds-(time.monotonic()-started))):
            try:
                result = receiver.recv()
            except EOFError:
                result = dict(status="ERROR", error="solver worker exited without result")
        else:
            result = dict(status="UNKNOWN", reason="hard wall-clock limit")
    finally:
        if child.is_alive():
            child.terminate()
        child.join(timeout=1)
        if child.is_alive():
            child.kill()
            child.join()
        receiver.close()
    assignment = result.pop("assignment", None)
    result.update(elapsed_seconds=time.monotonic()-started, wall_seconds=seconds,
                  conflict_limit=conflicts, memory_mb=memory_mb, threads=1,
                  formula_sha256=problem["metadata"]["formula_sha256"],
                  scope=problem["metadata"]["scope"], assumptions=assumptions)
    if result["status"] == "SAT":
        candidate, verification = validate_decode(problem, assignment)
        result.update(candidate=candidate, verification=verification)
    return result
