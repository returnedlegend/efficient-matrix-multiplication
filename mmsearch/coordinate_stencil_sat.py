"""Exact coordinatewise recombination of independently verified F2 algorithms.

Each column stencil represents the same tensor column, so choosing one source
per coordinate preserves every coefficient. UNSAT concerns only this finite
stencil family, which is a subset of the arbitrary-free-factor family.
"""
from __future__ import annotations

import hashlib
import json
import math
import multiprocessing as mp
from pathlib import Path
import tempfile
import time

from .free_factor_sat import ORIENTATIONS, canonical_pairs
from .recombine import canonical_terms, digest, encode
from .recombine_sat import bits
from .verify import verify_candidate


SCOPE = "finite independently exact source-column stencil family only; F2 only; no integer lift or global rank lower bound"


def code_hash():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
        Path(__file__), Path(__file__).with_name("free_factor_sat.py"),
        Path(__file__).with_name("recombine.py"), Path(__file__).with_name("recombine_sat.py"),
        Path(__file__).with_name("verify.py"))}


class VerifiedSources:
    """Verify every supplied source before canonical deduplication."""
    def __init__(self, candidates, dimension=5, provenance=None):
        if type(dimension) is not int or dimension < 1 or not candidates:
            raise ValueError("nonempty sources and positive dimension required")
        if provenance is not None and len(provenance) != len(candidates):
            raise ValueError("source provenance count differs")
        self.dimension, self.terms, self.sources = dimension, [], []
        self.input_sources = []
        seen = {}
        for i, candidate in enumerate(candidates):
            terms = canonical_terms(candidate)
            if candidate["dimension"] != dimension:
                raise ValueError("source dimension differs")
            report = verify_candidate(candidate, random_trials=0)
            if not report["valid"] or report["exact_entries_checked"] != dimension**6:
                raise ValueError("source failed independent full tensor verification")
            sha = digest(encode(terms, dimension))
            entry = dict(canonical_sha256=sha, supplied_rank=len(candidate["terms"]),
                canonical_rank=len(terms), verification=report,
                provenance=provenance[i] if provenance is not None else {})
            if sha not in seen:
                seen[sha] = len(self.sources)
                self.terms.append(terms)
                self.sources.append(entry)
            entry = dict(entry, source_index=seen[sha])
            self.input_sources.append(entry)
        self.sha256 = digest(dict(dimension=dimension, inputs=self.input_sources))


def prune_stencils(stencils):
    """Dedupe, remove strict supersets, and map every original to a subset.

    The returned retained provenance includes all equal original stencils.
    Dominated stencils keep their own provenance in the audit's original map.
    """
    grouped = {}
    for source, stencil in enumerate(stencils):
        if type(stencil) is not int or stencil < 0:
            raise ValueError("stencils must be nonnegative integer bitsets")
        grouped.setdefault(stencil, []).append(source)
    retained, replacement = [], {}
    for stencil in sorted(grouped, key=lambda x: (x.bit_count(), x)):
        parent = next((i for i, item in enumerate(retained) if item["mask"] & stencil == item["mask"]), None)
        if parent is None:
            parent = len(retained)
            retained.append(dict(mask=stencil, sources=grouped[stencil]))
        replacement[stencil] = parent
    return retained, [replacement[s] for s in stencils], [
        dict(mask_hex=hex(s), sources=grouped[s], retained_index=replacement[s],
             dominated=(retained[replacement[s]]["mask"] != s))
        for s in sorted(grouped)]


def build_family(sources, orientation="uv"):
    if not isinstance(sources, VerifiedSources) or orientation not in ORIENTATIONS:
        raise ValueError("verified sources and valid orientation required")
    dimension, width = sources.dimension, sources.dimension**2
    permutation = ORIENTATIONS[orientation]
    dictionary = [term for terms in sources.terms for term in terms]
    pairs = canonical_pairs(dictionary, dimension, orientation)
    pair_index = {pair: i for i, pair in enumerate(pairs)}
    originals = []
    merged_ranks = []
    for terms in sources.terms:
        vectors = {}
        for term in terms:
            a, b, c = (term[axis] for axis in permutation)
            g = pair_index[a, b]
            vectors[g] = vectors.get(g, 0) ^ c
        stencils = [0]*width
        for g, vector in vectors.items():
            for c in bits(vector):
                stencils[c] |= 1 << g
        originals.append(stencils)
        merged_ranks.append(sum(bool(v) for v in vectors.values()))
    choices, mappings, pruning = [], [], []
    for c in range(width):
        kept, mapped, original_map = prune_stencils([s[c] for s in originals])
        choices.append(kept)
        mappings.append(mapped)
        pruning.append(original_map)
    source_choices = [[mappings[c][s] for c in range(width)] for s in range(len(sources.sources))]
    family = dict(pairs=pairs, choices=choices, source_choices=source_choices,
        original_stencils=originals, pruning=pruning,
        metadata=dict(encoding="exact-coordinatewise-source-stencil-choice-CNF-v1", dimension=dimension,
            width=width, field=2, orientation=orientation, mode_permutation=list(permutation),
            source_pool_sha256=sources.sha256, source_count=len(sources.sources),
            supplied_source_count=len(sources.input_sources), sources=sources.sources,
            pair_count=len(pairs), pairs_sha256=digest(pairs),
            raw_stencils_per_coordinate=[len(p) for p in pruning],
            retained_stencils_per_coordinate=[len(c) for c in choices],
            merged_source_ranks=merged_ranks, code_sha256=code_hash(), scope=SCOPE))
    ranks = [selected_union(family, s).bit_count() for s in source_choices]
    if any(r > m for r, m in zip(ranks, merged_ranks)):
        raise AssertionError("dominance substitution increased a source rank")
    family["metadata"].update(dominance_source_ranks=ranks,
        baseline_source=min(range(len(ranks)), key=lambda i: (ranks[i], i)))
    family["metadata"]["choices_sha256"] = digest(audit(family)["coordinates"])
    return family


def selected_union(family, selection):
    if (not isinstance(selection, (list, tuple)) or len(selection) != len(family["choices"]) or
            any(type(j) is not int or not 0 <= j < len(family["choices"][c]) for c, j in enumerate(selection))):
        raise ValueError("one valid stencil index per coordinate required")
    union = 0
    for c, j in enumerate(selection):
        union |= family["choices"][c][j]["mask"]
    return union


def decode_selection(family, selection, metadata=None):
    active = selected_union(family, selection)
    vectors = {g: 0 for g in bits(active)}
    for c, j in enumerate(selection):
        for g in bits(family["choices"][c][j]["mask"]):
            vectors[g] |= 1 << c
    permutation = ORIENTATIONS[family["metadata"]["orientation"]]
    terms = []
    for g, vector in vectors.items():
        triple = [0, 0, 0]
        for axis, value in zip(permutation, (*family["pairs"][g], vector)):
            triple[axis] = value
        terms.append(tuple(triple))
    return encode(terms, family["metadata"]["dimension"], dict(metadata or {},
        method="exact-coordinatewise-source-stencil-recombination", orientation=family["metadata"]["orientation"],
        source_pool_sha256=family["metadata"]["source_pool_sha256"],
        pairs_sha256=family["metadata"]["pairs_sha256"],
        choices_sha256=family["metadata"].get("choices_sha256"),
        selection=list(selection), field_claim="F2 only; no integer lift asserted"))


def verify_selection(family, selection, metadata=None):
    candidate = decode_selection(family, selection, metadata)
    report = verify_candidate(candidate, random_trials=16)
    if (not report["valid"] or report["rank"] != selected_union(family, selection).bit_count() or
            report["exact_entries_checked"] != family["metadata"]["dimension"]**6):
        raise AssertionError("coordinatewise assembly failed independent full tensor/random verification")
    return candidate, report


def audit(family):
    return dict(metadata=family["metadata"], pairs=[list(p) for p in family["pairs"]],
        source_choices=family["source_choices"], coordinates=[dict(
            coordinate=c, retained=[dict(mask_hex=hex(x["mask"]), sources=x["sources"]) for x in row],
            originals=family["pruning"][c]) for c, row in enumerate(family["choices"])],
        proof="each original stencil is an independently exact flattened tensor column; every retained stencil is original; independently choose one per column; strict supersets may be removed for union minimization")


def single_coordinate_scan(family, seconds=120, max_sources=512, on_improvement=None):
    """Exhaustive single-coordinate swaps from bounded dominance-mapped sources.

    tested_swaps counts scored unions, never independently verified certificates.
    Every retained record is independently verified before its callback/export.
    """
    if not math.isfinite(seconds) or seconds <= 0 or type(max_sources) is not int or not 1 <= max_sources <= 512:
        raise ValueError("positive seconds and max_sources in 1..512 required")
    started, tested, completed = time.monotonic(), 0, 0
    baseline = family["metadata"]["baseline_source"]
    best = list(family["source_choices"][baseline])
    best_rank = selected_union(family, best).bit_count()
    candidate, verification = verify_selection(family, best, dict(phase="dominance baseline"))
    if on_improvement:
        on_improvement(candidate, verification, list(best))
    order = sorted(range(len(family["source_choices"])), key=lambda s: (
        family["metadata"]["dominance_source_ranks"][s], s))[:max_sources]
    for s in order:
        if time.monotonic()-started >= seconds:
            break
        selection = family["source_choices"][s]
        active = selected_union(family, selection)
        seen_once = repeated = 0
        for c, j in enumerate(selection):
            mask = family["choices"][c][j]["mask"]
            repeated |= seen_once & mask
            seen_once |= mask
        exclusive = [family["choices"][c][j]["mask"] & ~repeated for c, j in enumerate(selection)]
        done = True
        for c, row in enumerate(family["choices"]):
            without = active & ~exclusive[c]
            for j, item in enumerate(row):
                if tested % 256 == 0 and time.monotonic()-started >= seconds:
                    done = False
                    break
                tested += 1
                rank = (without | item["mask"]).bit_count()
                if rank < best_rank:
                    chosen = list(selection)
                    chosen[c] = j
                    candidate, verification = verify_selection(family, chosen,
                        dict(phase="single-coordinate scan", source=s, coordinate=c, tested_swaps=tested))
                    best, best_rank = chosen, rank
                    if on_improvement:
                        on_improvement(candidate, verification, list(best))
            if not done:
                break
        completed += int(done)
        if not done:
            break
    return dict(status="SCAN_COMPLETE" if completed == len(order) else "UNKNOWN", selection=best,
        rank=best_rank, tested_swaps=tested, sources_completed=completed, sources_selected=len(order),
        elapsed_seconds=time.monotonic()-started, max_seconds=seconds, max_sources=max_sources,
        candidate=candidate, verification=verification,
        scope="single-coordinate swaps from the selected source baselines only; counts are scored unions")


class FormulaMemoryLimit(ValueError):
    pass


def estimate_formula(family, rank=92, reverse_links=True):
    p = len(family["pairs"])
    sizes = [len(row) for row in family["choices"]]
    links = sum(x["mask"].bit_count() for row in family["choices"] for x in row)
    # Seqcounter upper bound: <= 2*n*k vars and <= 4*n*k clauses.
    # Python CNF storage is intentionally charged generously; native RSS extra.
    card_nk = p*min(max(rank, 0), max(0, p-1)) if rank < p else 0
    clauses = links + (p if reverse_links else 0) + 6*sum(sizes) + (p if rank == 0 else 4*card_nk)
    literals = 2*links + (links+p if reverse_links else 0) + 18*sum(sizes) + (p if rank == 0 else 12*card_nk)
    estimated = clauses*96+literals*40+(sum(sizes)+p+2*card_nk)*40
    return dict(pair_count=p, choice_count=sum(sizes), link_count=links,
        estimated_cnf_clauses=clauses, estimated_cnf_literals=literals,
        estimated_python_formula_bytes=estimated, estimated_python_formula_mb=math.ceil(estimated/1024**2),
        policy="conservative Python seqcounter CNF estimate; native solver/inherited RSS additional; hard child memory limit")


def build_problem(family, rank=92, max_formula_mb=384, reverse_links=True):
    if type(rank) is not int or rank < 0 or not math.isfinite(max_formula_mb) or max_formula_mb <= 0:
        raise ValueError("invalid rank or memory limit")
    estimate = estimate_formula(family, rank, reverse_links)
    if estimate["estimated_python_formula_bytes"] > max_formula_mb*1024**2:
        raise FormulaMemoryLimit(f"estimated formula {estimate['estimated_python_formula_mb']} MiB exceeds {max_formula_mb} MiB cap")
    from pysat.card import CardEnc, EncType
    xs, nv = [], 0
    for row in family["choices"]:
        xs.append(list(range(nv+1, nv+len(row)+1)))
        nv += len(row)
    ys = list(range(nv+1, nv+len(family["pairs"])+1))
    nv += len(ys)
    clauses, reverse = [], [[] for _ in ys]
    for c, row in enumerate(family["choices"]):
        card = CardEnc.equals(lits=xs[c], bound=1, top_id=nv, encoding=EncType.seqcounter)
        clauses.extend(card.clauses)
        nv = max(nv, card.nv)
        for j, item in enumerate(row):
            for g in bits(item["mask"]):
                clauses.append([-xs[c][j], ys[g]])
                reverse[g].append(xs[c][j])
    if reverse_links:
        clauses.extend([[-y]+reverse[g] for g, y in enumerate(ys)])
    if rank < len(ys):
        card = CardEnc.atmost(lits=ys, bound=rank, top_id=nv, encoding=EncType.seqcounter)
        clauses.extend(card.clauses)
        nv = max(nv, card.nv)
    metadata = dict(family["metadata"], rank_bound=rank, variables=nv, cnf_clauses=len(clauses),
        native_xors=0, cardinality_encoding="seqcounter (choice exactly-one and group at-most)",
        reverse_links=reverse_links, formula_memory_estimate=estimate, max_formula_mb=max_formula_mb)
    metadata["formula_sha256"] = digest(dict(nv=nv, clauses=clauses, x_variables=xs, y_variables=ys))
    return dict(family=family, clauses=clauses, nv=nv, xs=xs, ys=ys, metadata=metadata)


def source_assumptions(problem, source=None):
    family = problem["family"]
    if source is None:
        source = family["metadata"]["baseline_source"]
    selection = family["source_choices"][source]
    return [x if j == selection[c] else -x for c, row in enumerate(problem["xs"]) for j, x in enumerate(row)]


def validate_decode(problem, assignment):
    if (not isinstance(assignment, (list, tuple)) or len(assignment) != problem["nv"]+1 or
            any(type(v) is not bool for v in assignment[1:])):
        raise AssertionError("incomplete or non-Boolean solver model")
    for clause in problem["clauses"]:
        if not any(assignment[abs(lit)] == (lit > 0) for lit in clause):
            raise AssertionError("solver model violates CNF")
    selection = []
    for row in problem["xs"]:
        chosen = [j for j, x in enumerate(row) if assignment[x]]
        if len(chosen) != 1:
            raise AssertionError("solver model violates exactly-one choice")
        selection.append(chosen[0])
    union = selected_union(problem["family"], selection)
    if union.bit_count() > problem["metadata"]["rank_bound"]:
        raise AssertionError("solver model violates union rank bound")
    for g, y in enumerate(problem["ys"]):
        if union >> g & 1 and not assignment[y]:
            raise AssertionError("active stencil group lacks indicator")
        if problem["metadata"]["reverse_links"] and assignment[y] != bool(union >> g & 1):
            raise AssertionError("indicator disagrees with selected stencil union")
    candidate, report = verify_selection(problem["family"], selection,
        dict(formula_sha256=problem["metadata"]["formula_sha256"]))
    return candidate, report, selection


def _worker(problem, seconds, memory_mb, assumptions, result_path):
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (memory_mb*1024**2, memory_mb*1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(seconds)+1, math.ceil(seconds)+2))
        from pysat.solvers import Solver
        import pysat
        with Solver(name="cadical195", bootstrap_with=problem["clauses"]) as solver:
            if problem["nv"]:
                solver.add_clause([problem["nv"], -problem["nv"]])
            sat = solver.solve(assumptions=assumptions)
            assignment = None
            if sat:
                model = solver.get_model()
                mapped = {abs(x): x > 0 for x in model}
                if set(mapped) != set(range(1, problem["nv"]+1)):
                    raise AssertionError("solver returned incomplete assignment")
                assignment = [None]+[mapped[i] for i in range(1, problem["nv"]+1)]
            result = dict(status="SAT" if sat else "UNSAT", assignment=assignment,
                solver="cadical195", pysat_version=pysat.__version__)
    except Exception as exc:
        result = dict(status="ERROR", error=f"{type(exc).__name__}: {exc}")
    # Parent waits for process completion before reading: no partial IPC recv
    # can hang beyond the deadline when a large model exceeds the pipe buffer.
    with open(result_path, "w") as stream:
        json.dump(result, stream)


def solve(problem, seconds=10, memory_mb=1536, assumptions=None):
    """Hard wall limit includes load; child is reaped, reserve 2s in caller."""
    if not math.isfinite(seconds) or seconds <= 0 or type(memory_mb) is not int or memory_mb < 128:
        raise ValueError("invalid solver resource bounds")
    assumptions = [] if assumptions is None else list(assumptions)
    if any(type(x) is not int or not 1 <= abs(x) <= problem["nv"] for x in assumptions):
        raise ValueError("invalid assumptions")
    context = mp.get_context("fork")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="mmsearch-stencil-solver-") as directory:
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
        formula_sha256=problem["metadata"]["formula_sha256"], scope=SCOPE)
    if result["status"] == "SAT":
        if (assignment is None or len(assignment) != problem["nv"]+1 or
                any(assignment[abs(x)] != (x > 0) for x in assumptions)):
            raise AssertionError("solver model violates control assumptions or is incomplete")
        candidate, verification, selection = validate_decode(problem, assignment)
        result.update(candidate=candidate, verification=verification, selection=selection,
            complete_assignment=assignment)
    return result
