"""Exact F2 group-sparsity SAT with two fixed factors and one free factor.

A group is a distinct nonzero pair of factor masks from the input dictionary.
Its remaining factor is an arbitrary vector, including zero. UNSAT applies
only to these fixed pairs and the requested number of nonzero groups.
"""
from __future__ import annotations

import hashlib
import math
import multiprocessing as mp
from pathlib import Path
import signal
import time

from .recombine import canonical_terms, digest, encode
from .recombine_sat import bits
from .verify import verify_candidate

ORIENTATIONS = {"uv": (0, 1, 2), "vw": (1, 2, 0), "wu": (2, 0, 1)}


def code_hash():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
        Path(__file__), Path(__file__).with_name("recombine.py"),
        Path(__file__).with_name("recombine_sat.py"), Path(__file__).with_name("verify.py"))}


def canonical_pairs(dictionary, dimension, orientation="uv"):
    """Deduplicate fixed pairs; discard pairs with a zero fixed factor.

    The input third mask does not restrict the free factor. In particular a
    zero input third mask is permitted. All masks must be strict integers.
    """
    if type(dimension) is not int or dimension < 1 or orientation not in ORIENTATIONS:
        raise ValueError("positive dimension and valid orientation required")
    if not isinstance(dictionary, (list, tuple)):
        raise ValueError("dictionary must be an array of triples")
    bound = 1 << (dimension*dimension)
    first, second, _ = ORIENTATIONS[orientation]
    pairs = set()
    for term in dictionary:
        if (not isinstance(term, (list, tuple)) or len(term) != 3 or
                any(type(x) is not int or not 0 <= x < bound for x in term)):
            raise ValueError("dictionary entries must be three in-range integer masks")
        pair = term[first], term[second]
        if all(pair):
            pairs.add(pair)
    return tuple(sorted(pairs))


def packed_rref(coefficients, right_sides, variables, width):
    """Reduce common GF2 coefficients once, with packed vector right sides.

    Every returned row includes an XOR witness in the original row indices.
    A coefficient-zero/nonzero-RHS row is an exact inconsistency certificate.
    """
    if (type(variables) is not int or variables < 0 or type(width) is not int or width < 1 or
            len(coefficients) != len(right_sides) or
            any(type(c) is not int or c < 0 or c >> variables for c in coefficients) or
            any(type(r) is not int or r < 0 or r >> width for r in right_sides)):
        raise ValueError("invalid packed GF2 system")
    basis, contradictions = {}, []
    for index, (coefficient, rhs) in enumerate(zip(coefficients, right_sides)):
        proof = 1 << index
        while coefficient:
            pivot = (coefficient & -coefficient).bit_length()-1
            if pivot not in basis:
                basis[pivot] = [coefficient, rhs, proof]
                break
            row = basis[pivot]
            coefficient ^= row[0]
            rhs ^= row[1]
            proof ^= row[2]
        else:
            if rhs:
                contradictions.append([0, rhs, proof])
    pivots = sorted(basis)
    rows = [basis[p] for p in pivots]
    for j in reversed(range(len(rows))):
        bit = 1 << pivots[j]
        for i in range(j):
            if rows[i][0] & bit:
                for k in range(3):
                    rows[i][k] ^= rows[j][k]
    # Verify the row witnesses before using preprocessing for any bound.
    for coefficient, rhs, proof in rows+contradictions:
        original_coefficient = original_rhs = 0
        for index in bits(proof):
            original_coefficient ^= coefficients[index]
            original_rhs ^= right_sides[index]
        if (coefficient, rhs) != (original_coefficient, original_rhs):
            raise AssertionError("packed RREF witness failed")
    forced = {c.bit_length()-1: r for c, r, _ in rows if c.bit_count() == 1}
    return dict(rows=rows, contradictions=contradictions, rank=len(rows),
                nullity=variables-len(rows), forced=forced)


def satisfies(system, vectors):
    width, count = system["metadata"]["width"], len(system["pairs"])
    if (len(vectors) != count or any(type(v) is not int or v < 0 or v >> width for v in vectors)):
        return False
    for coefficient, required in zip(system["coefficients"], system["right_sides"]):
        observed = 0
        for g in bits(coefficient):
            observed ^= vectors[g]
        if observed != required:
            return False
    return True


def decode_vectors(system, vectors, metadata=None):
    permutation = ORIENTATIONS[system["metadata"]["orientation"]]
    terms = []
    for pair, vector in zip(system["pairs"], vectors):
        if vector:
            triple = [0, 0, 0]
            for original_axis, value in zip(permutation, (*pair, vector)):
                triple[original_axis] = value
            terms.append(tuple(triple))
    return encode(terms, system["metadata"]["dimension"], metadata)


def build_system(dictionary, dimension, orientation="uv", baseline=None, provenance=None):
    pairs = canonical_pairs(dictionary, dimension, orientation)
    width = dimension*dimension
    coefficients, right_sides = [0]*(width*width), [0]*(width*width)
    for g, (a, b) in enumerate(pairs):
        for i in bits(a):
            for j in bits(b):
                coefficients[i*width+j] |= 1 << g
    permutation = ORIENTATIONS[orientation]
    for i in range(dimension):
        for j in range(dimension):
            for k in range(dimension):
                original = (i*dimension+j, j*dimension+k, k*dimension+i)
                a, b, c = (original[axis] for axis in permutation)
                right_sides[a*width+b] ^= 1 << c
    reduced = packed_rref(coefficients, right_sides, len(pairs), width)
    metadata = dict(encoding="fixed-two-factors-free-third-group-sparsity-native-XOR-v1",
        dimension=dimension, width=width, orientation=orientation, mode_permutation=list(permutation),
        input_dictionary_size=len(dictionary), input_dictionary_sha256=digest(dictionary),
        pair_count=len(pairs), pairs_sha256=digest(pairs), coefficient_rows=width*width,
        scalar_tensor_equations=width**3, linear_rank=reduced["rank"], linear_nullity=reduced["nullity"],
        linear_inconsistent=bool(reduced["contradictions"]),
        forced_active=sum(bool(v) for v in reduced["forced"].values()),
        forced_zero=sum(not v for v in reduced["forced"].values()),
        original_rows_sha256=digest([[hex(c), hex(r)] for c, r in zip(coefficients, right_sides)]),
        rref_rows_sha256=digest([[hex(x) for x in row] for row in reduced["rows"]]),
        code_sha256=code_hash(), provenance=provenance or {}, field=2,
        scope="arbitrary free third-factor vectors on the supplied distinct fixed factor pairs; restricted UNSAT only; no integer lift claim",
        inclusion="includes every whole-triple subset from these pairs after same-pair XOR merging; passing linear/forced bounds is not a solution")
    system = dict(pairs=pairs, coefficients=coefficients, right_sides=right_sides,
                  reduced=reduced, metadata=metadata)
    if baseline is not None:
        terms = canonical_terms(baseline)
        report = verify_candidate(baseline, random_trials=0)
        if not report["valid"] or baseline["dimension"] != dimension:
            raise ValueError("baseline must be independently exact in the requested dimension")
        pair_map = {pair: g for g, pair in enumerate(pairs)}
        vectors = [0]*len(pairs)
        for term in terms:
            a, b, c = (term[axis] for axis in permutation)
            if (a, b) not in pair_map:
                raise ValueError("baseline fixed pair absent from dictionary")
            vectors[pair_map[a, b]] ^= c
        if not satisfies(system, vectors):
            raise AssertionError("independently exact baseline violates packed tensor equations")
        merged = decode_vectors(system, vectors)
        merged_report = verify_candidate(merged, random_trials=16)
        if not merged_report["valid"]:
            raise AssertionError("baseline pair merging failed independent verification")
        system["baseline_vectors"] = vectors
        metadata["baseline"] = dict(supplied_rank=len(baseline["terms"]), canonical_rank=len(terms),
            merged_rank=sum(bool(x) for x in vectors), vectors_hex=[hex(x) for x in vectors],
            source_verification=report, merged_verification=merged_report,
            merged_candidate_sha256=digest(merged))
    return system


def audit(system):
    return dict(metadata=system["metadata"], pairs=[list(p) for p in system["pairs"]],
        row_mapping="r=a*width+b in permuted modes; coefficients bit g selects fixed pair g; RHS bit c is free mode coordinate c",
        variable_mapping="x[g,c]=g*width+c+1; y[g]=pair_count*width+g+1; higher IDs are cardinality auxiliaries",
        original_rows_hex=[[hex(c), hex(r)] for c, r in zip(system["coefficients"], system["right_sides"])],
        rref_rows_hex=[[hex(x) for x in row] for row in system["reduced"]["rows"]],
        contradiction_rows_hex=[[hex(x) for x in row] for row in system["reduced"]["contradictions"]],
        rref_row_layout="[coefficient bitset, packed RHS vector, XOR witness of original coefficient-row indices]",
        forced_group_vectors_hex={str(g): hex(v) for g, v in system["reduced"]["forced"].items()})


class FormulaMemoryLimit(ValueError):
    pass


def estimate_formula(system, rank=92):
    """Conservative CPython formula storage estimate, not solver RSS prediction.

    Native solver allocation is additional. Cardinality allowance uses an
    O(p log^2 p) sorting-network envelope and intentionally overestimates.
    """
    p, width = len(system["pairs"]), system["metadata"]["width"]
    forced = system["reduced"]["forced"]
    active = sum(bool(v) for v in forced.values())
    free = p-len(forced)
    xor_literals = width*sum(row[0].bit_count() for row in system["reduced"]["rows"])
    link_literals = p*(3*width+1)
    link_clauses = p*(width+1)+len(forced)
    remaining = rank-active
    card_bytes = (free*math.ceil(math.log2(max(2, free)))**2*1024
                  if 0 < remaining < free else free*100 if remaining == 0 else 0)
    estimated = (xor_literals*40 + link_literals*40 + link_clauses*96 +
                 len(system["reduced"]["rows"])*width*128 + p*(width+1)*40 + card_bytes)
    return dict(xor_literals=xor_literals, link_literals=link_literals,
        cardinality_estimate_bytes=card_bytes, estimated_python_formula_bytes=estimated,
        estimated_python_formula_mb=math.ceil(estimated/1024**2),
        policy="conservative Python formula estimate; solver and inherited process RSS are additional; hard child RLIMIT_AS remains enforced")


def build_problem(system, rank=92, max_formula_mb=384):
    if type(rank) is not int or rank < 0 or not math.isfinite(max_formula_mb) or max_formula_mb <= 0:
        raise ValueError("invalid rank or formula memory cap")
    estimate = estimate_formula(system, rank)
    if estimate["estimated_python_formula_bytes"] > max_formula_mb*1024**2:
        raise FormulaMemoryLimit(f"estimated formula {estimate['estimated_python_formula_mb']} MiB exceeds cap {max_formula_mb} MiB")
    p, width = len(system["pairs"]), system["metadata"]["width"]
    base_variables = p*(width+1)
    forced = system["reduced"]["forced"]
    clauses, xors = [], []
    for g in range(p):
        y = p*width+g+1
        xs = [g*width+c+1 for c in range(width)]
        clauses.extend([[-x, y] for x in xs])
        clauses.append([-y]+xs)
        if g in forced:
            clauses.append([y if forced[g] else -y])
    for coefficient, rhs, _ in system["reduced"]["rows"]:
        groups = list(bits(coefficient))
        for c in range(width):
            xors.append(([g*width+c+1 for g in groups], bool(rhs >> c & 1)))
    active = sum(bool(v) for v in forced.values())
    remaining = rank-active
    exact_unsat = ("linear inconsistency" if system["reduced"]["contradictions"] else
                   "forced active groups exceed rank bound" if remaining < 0 else None)
    nv = base_variables
    if exact_unsat:
        clauses.append([])
    else:
        indicators = [p*width+g+1 for g in range(p) if g not in forced]
        if remaining < len(indicators):
            from pysat.card import CardEnc, EncType
            card = CardEnc.atmost(lits=indicators, bound=remaining, top_id=base_variables,
                                 encoding=EncType.cardnetwrk)
            clauses.extend(card.clauses)
            nv = max(nv, card.nv)
    metadata = dict(system["metadata"], rank_bound=rank, variables=nv,
        x_variables=p*width, active_variables=p, base_variables=base_variables,
        cardinality_encoding="cardnetwrk with exact forced-indicator substitution",
        cnf_clauses=len(clauses), native_xors=len(xors), solver_threads=1,
        exact_preprocessing_unsat=exact_unsat, formula_memory_estimate=estimate,
        max_formula_mb=max_formula_mb,
        variable_mapping="x[g,c]=g*width+c+1; y[g]=pair_count*width+g+1; larger IDs are cardinality auxiliaries")
    metadata["formula_sha256"] = digest(dict(nv=nv, clauses=clauses, xors=xors))
    return dict(nv=nv, clauses=clauses, xors=xors, metadata=metadata, system=system)


def baseline_assumptions(problem):
    system = problem["system"]
    vectors = system["baseline_vectors"]
    width, p = system["metadata"]["width"], len(vectors)
    fixed = []
    for g, vector in enumerate(vectors):
        fixed.extend(g*width+c+1 if vector >> c & 1 else -(g*width+c+1) for c in range(width))
    fixed.extend(p*width+g+1 if v else -(p*width+g+1) for g, v in enumerate(vectors))
    return fixed


def validate_decode(problem, assignment):
    if (not isinstance(assignment, (list, tuple)) or len(assignment) != problem["nv"]+1 or
            any(type(v) is not bool for v in assignment[1:])):
        raise AssertionError("incomplete or non-Boolean solver model")
    for clause in problem["clauses"]:
        if not any(assignment[abs(lit)] == (lit > 0) for lit in clause):
            raise AssertionError("solver model violates CNF")
    for variables, rhs in problem["xors"]:
        if bool(sum(assignment[v] for v in variables) % 2) != rhs:
            raise AssertionError("solver model violates native XOR")
    system = problem["system"]
    p, width = len(system["pairs"]), system["metadata"]["width"]
    vectors = [sum(int(assignment[g*width+c+1]) << c for c in range(width)) for g in range(p)]
    if any(assignment[p*width+g+1] != bool(v) for g, v in enumerate(vectors)):
        raise AssertionError("active indicator disagrees with free factor")
    if sum(bool(v) for v in vectors) > problem["metadata"]["rank_bound"] or not satisfies(system, vectors):
        raise AssertionError("solver model violates original exact tensor or rank bound")
    candidate = decode_vectors(system, vectors, dict(method="fixed-two-factor-exact-F2-group-sparsity-SAT",
        formula_sha256=problem["metadata"]["formula_sha256"], pairs_sha256=system["metadata"]["pairs_sha256"],
        orientation=system["metadata"]["orientation"], field_claim="F2 only; no integer lift asserted"))
    report = verify_candidate(candidate, random_trials=16)
    if not report["valid"]:
        raise AssertionError("SAT model failed independent full tensor and random verification")
    return candidate, report


def _worker(problem, seconds, conflicts, memory_mb, assumptions, sender):
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (memory_mb*1024**2, memory_mb*1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(seconds)+1, math.ceil(seconds)+2))
        import pycryptosat
        solver = pycryptosat.Solver(threads=1, verbose=0, time_limit=seconds, confl_limit=conflicts)
        if problem["nv"]:
            solver.add_clause([problem["nv"], -problem["nv"]])
        for clause in problem["clauses"]:
            solver.add_clause(clause)
        for variables, rhs in problem["xors"]:
            solver.add_xor_clause(variables, rhs)
        status, assignment = solver.solve(assumptions=assumptions, time_limit=seconds, confl_limit=conflicts)
        sender.send(dict(status="SAT" if status is True else "UNSAT" if status is False else "UNKNOWN",
            assignment=assignment if status is True else None, pycryptosat_version=pycryptosat.__version__))
    except Exception as exc:
        sender.send(dict(status="ERROR", error=f"{type(exc).__name__}: {exc}"))
    finally:
        sender.close()


def _worker_entry(*args):
    # fork inherits CLI stop handlers, which may only set a flag. Reset before
    # entering even a patched worker, so terminate() always stops this child.
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    _worker(*args)


def solve(problem, seconds=10, conflicts=100000, memory_mb=1536, assumptions=None):
    """Hard child wall limit includes loading; cleanup finishes before return.

    Reserve two seconds in the caller's phase budget for process cleanup.
    Exact model verification occurs after the child has been reaped.
    """
    if (not math.isfinite(seconds) or seconds <= 0 or type(conflicts) is not int or conflicts < 1 or
            type(memory_mb) is not int or memory_mb < 128):
        raise ValueError("invalid solver resource bounds")
    assumptions = [] if assumptions is None else list(assumptions)
    if any(type(v) is not int or not 1 <= abs(v) <= problem["nv"] for v in assumptions):
        raise ValueError("invalid assumptions")
    context = mp.get_context("fork")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=_worker_entry, args=(problem, seconds, conflicts, memory_mb, assumptions, sender))
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
            result = dict(status="UNKNOWN", reason="hard wall-clock limit including solver load")
    finally:
        if child.is_alive():
            child.terminate()
        child.join(timeout=0.1)
        if child.is_alive():
            child.kill()
            child.join()
        receiver.close()
    assignment = result.pop("assignment", None)
    result.update(elapsed_seconds=time.monotonic()-started, wall_seconds=seconds,
        conflict_limit=conflicts, memory_mb=memory_mb, threads=1, worker_reaped=not child.is_alive(),
        formula_sha256=problem["metadata"]["formula_sha256"], scope=problem["metadata"]["scope"],
        assumptions=assumptions)
    if result["status"] == "SAT":
        # Solver assumptions are also checked independently; CNF/XOR alone
        # would not detect an incorrect feasibility-control assignment.
        if any(assignment[abs(lit)] != (lit > 0) for lit in assumptions):
            raise AssertionError("solver model violates fixed control assumptions")
        candidate, verification = validate_decode(problem, assignment)
        result.update(candidate=candidate, verification=verification,
                      complete_assignment=list(assignment))
    return result
