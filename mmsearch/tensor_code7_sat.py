"""Exact finite whole-atom dictionary SAT: native XOR plus support cardinality.

UNSAT concerns only the supplied, pinned dictionary. It is never a tensor-rank
lower bound. Production input reads and solving are disabled by default in CLI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import resource
import signal
import time
from types import SimpleNamespace

from mmsearch.verify import verify_candidate

SCHEMA = "tensor_code7_sat.v1"
MAX_ATOMS = 5000
MAX_ENTRIES = 15625
SCOPE = "Only this exact whole-atom F2 dictionary and support bound; no global tensor-rank claim."


def raw_json(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value):
    return hashlib.sha256(raw_json(value)).hexdigest()


class Stopped(Exception):
    """A bounded computation cannot publish a terminal mathematical outcome."""


def unknown_with_raw(previous, reason, document=None):
    """Retain diagnostic bytes without accepting a late SAT or UNSAT outcome."""
    previous = previous or {}
    native = previous.get("raw_native_result", previous)
    result = {key: value for key, value in previous.items()
              if key not in ("candidate", "checks", "state_hex", "essential_rank")}
    raw_native = {key: value for key, value in native.items()
                  if key not in ("candidate", "checks", "raw_native_result", "raw_witness")}
    result.update(status="UNKNOWN", reason=reason, scope=SCOPE, complete=False,
                  raw_native_result=raw_native)
    state = previous.get("state_hex", native.get("state_hex"))
    if state is not None or previous.get("candidate") is not None:
        result["raw_witness"] = dict(state_hex=state, within_budget=False,
            verified_before_stop="checks" in previous,
            claim="Diagnostic witness only; no accepted within-budget SAT result or publication.")
        if document is not None:
            result["raw_witness"]["document_digest"] = digest(document)
        if previous.get("candidate") is not None:
            result["raw_witness"]["candidate"] = previous["candidate"]
    return result


def bits(value):
    while value:
        bit = value & -value
        yield bit.bit_length() - 1
        value ^= bit


def full_rows(columns, target, entries):
    """Transpose literal complete tensor columns, retaining every target bit."""
    if type(entries) is not int or not 1 <= entries <= MAX_ENTRIES:
        raise ValueError("entries must be a literal integer in 1..15625")
    if not isinstance(columns, (list, tuple)) or len(columns) > MAX_ATOMS:
        raise ValueError("dictionary exceeds 5000 atoms")
    if type(target) is not int or target < 0 or target.bit_length() > entries:
        raise ValueError("invalid target column")
    rows = [0] * entries
    for index, column in enumerate(columns):
        if type(column) is not int or column < 0 or column.bit_length() > entries:
            raise ValueError("invalid literal full column")
        for row in bits(column):
            rows[row] |= 1 << index
    return [(mask, (target >> row) & 1) for row, mask in enumerate(rows)]


def reduce_rows(rows):
    """Independent row elimination, with exact original-row XOR witnesses.

The RHS is the least significant augmented bit, so a contradiction has pivot0.
The retained row space equals the complete original row space, including RHS.
"""
    pivots = {}
    for index, (mask, rhs) in enumerate(rows):
        value, witness = (mask << 1) | rhs, 1 << index
        while value:
            pivot = value.bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = (value, witness)
                break
            previous, proof = pivots[pivot]
            value ^= previous
            witness ^= proof
    reduced = [(value >> 1, value & 1, witness)
               for _, (value, witness) in sorted(pivots.items(), reverse=True)]
    # Check both row-space inclusions, independently of the construction loop.
    for mask, rhs, witness in reduced:
        rebuilt = 0
        for index in bits(witness):
            rebuilt ^= (rows[index][0] << 1) | rows[index][1]
        if rebuilt != (mask << 1) | rhs:
            raise AssertionError("row elimination witness failed")
    for mask, rhs in rows:
        value = (mask << 1) | rhs
        for pivot, (row, _) in sorted(pivots.items(), reverse=True):
            if value >> pivot & 1:
                value ^= row
        if value:
            raise AssertionError("row reduction lost an original equation")
    return reduced


def build_problem(columns, target, entries, bound, *, compress=True, guard=None):
    """One atom-selection variable per column; no factor or nonlinear variables."""
    if type(bound) is not int or bound < 0 or type(compress) is not bool:
        raise ValueError("literal nonnegative support bound and Boolean compression required")
    if guard:
        guard("pre_formula")
    rows = full_rows(columns, target, entries)
    encoded = reduce_rows(rows) if compress else [(a, b, 1 << i) for i, (a, b) in enumerate(rows) if a or b]
    clauses, xors = [], []
    for mask, rhs, _ in encoded:
        if mask:
            xors.append(([index + 1 for index in bits(mask)], bool(rhs)))
        elif rhs:
            clauses.append([])
    count, nv = len(columns), len(columns)
    if bound < count:
        from pysat.card import CardEnc, EncType
        cardinality = CardEnc.atmost(lits=list(range(1, count + 1)), bound=bound,
                                    top_id=count, encoding=EncType.seqcounter)
        clauses.extend(cardinality.clauses)
        nv = max(nv, cardinality.nv)
    problem = dict(columns=list(columns), target=target, entries=entries, bound=bound,
                   nv=nv, selection_variables=count, clauses=clauses, xors=xors,
                   reduced_rows=[(hex(a), b, hex(w)) for a, b, w in encoded])
    # Full n5 tensor integers can exceed Python's decimal JSON digit ceiling.
    # Hash their exact hexadecimal representation, never decimal big integers.
    formula_payload = {key: value for key, value in problem.items() if key not in ("columns", "target")}
    formula_payload.update(columns_hex=[hex(c) for c in columns], target_hex=hex(target))
    problem["metadata"] = dict(schema=SCHEMA, scope=SCOPE, full_equations=entries,
        full_rows_sha256=digest([(hex(a), b) for a, b in rows]),
        columns_sha256=digest([hex(c) for c in columns]), target_hex=hex(target),
        atom_count=count, support_bound=bound, row_compression=compress,
        encoded_linear_rows=len(encoded), native_xors=len(xors), cnf_clauses=len(clauses),
        cardinality_encoding="PySAT sequential counter", solver_threads=1,
        formula_sha256=digest(formula_payload))
    if guard:
        guard("post_formula")
    return problem


def validate_state(problem, state):
    if type(state) is not int or state < 0 or state.bit_length() > problem["selection_variables"]:
        raise ValueError("incomplete or invalid atom selection")
    value = 0
    for index in bits(state):
        value ^= problem["columns"][index]
    if value != problem["target"] or state.bit_count() > problem["bound"]:
        raise ValueError("model violates complete original tensor rows or cardinality")
    return True


def kernel_diagnostics(columns, seed, cycles, *, bound=92, max_component_nullity=20,
                       max_combinations=1 << 20, guard=None):
    """Exact code parity and separable coset certificates, never global rank.

Completeness and independence of the supplied kernel basis are checked afresh.
DSU components have no crossing kernel basis vector, so each feasible state is
the seed plus independent component kernel combinations. Enumeration is an
optional bounded Gray traversal; unfinished components retain lower bound0/1.
"""
    if (not isinstance(columns, (list, tuple)) or len(columns) > MAX_ATOMS
            or not isinstance(cycles, (list, tuple)) or len(cycles) > MAX_ATOMS
            or type(seed) is not int or seed < 0 or seed.bit_length() > len(columns)
            or type(bound) is not int or bound < 0
            or type(max_component_nullity) is not int or not 0 <= max_component_nullity <= 20
            or type(max_combinations) is not int or max_combinations < 0):
        raise ValueError("invalid exact component diagnostic bounds")
    # Independent column elimination checks rank, rather than trusting metadata.
    pivots = {}
    for column in columns:
        if type(column) is not int or column < 0 or column.bit_length() > MAX_ENTRIES:
            raise ValueError("invalid literal column")
        value = column
        while value:
            pivot = value.bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = value
                break
            value ^= pivots[pivot]
    cycle_pivots = {}
    for cycle in cycles:
        if type(cycle) is not int or not 0 < cycle < 1 << len(columns):
            raise ValueError("invalid kernel cycle")
        value = 0
        for index in bits(cycle):
            value ^= columns[index]
        if value:
            raise ValueError("cycle is not a complete-column relation")
        value = cycle
        while value:
            pivot = value.bit_length() - 1
            if pivot not in cycle_pivots:
                cycle_pivots[pivot] = value
                break
            value ^= cycle_pivots[pivot]
        if not value:
            raise ValueError("dependent kernel cycle basis")
    if len(cycles) != len(columns) - len(pivots):
        raise ValueError("incomplete kernel basis")
    parents = list(range(len(columns)))
    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index
    for cycle in cycles:
        indices = list(bits(cycle))
        for index in indices[1:]:
            parents[find(index)] = find(indices[0])
    masks = {}
    for index in range(len(columns)):
        root = find(index)
        masks[root] = masks.get(root, 0) | 1 << index
    grouped = {root: [] for root in masks}
    for cycle in cycles:
        root = find(next(bits(cycle)))
        if cycle & ~masks[root]:
            raise AssertionError("kernel vector crosses declared components")
        grouped[root].append(cycle)
    records, spent, best_state = [], 0, 0
    for root, mask in sorted(masks.items()):
        if guard:
            guard("component_diagnostics")
        local = grouped[root]
        count = 1 << len(local)
        state = best = seed & mask
        exact = len(local) <= max_component_nullity and count <= max_combinations - spent
        if not local:
            exact = True
        if exact:
            for index in range(1, count):
                if guard and index % 1024 == 0:
                    guard("component_gray_enumeration")
                state ^= local[(index & -index).bit_length() - 1]
                if state.bit_count() < best.bit_count():
                    best = state
            spent += count if local else 0
        even = all(cycle.bit_count() % 2 == 0 for cycle in local)
        lower = best.bit_count() if exact else (seed & mask).bit_count() % 2 if even else 0
        best_state |= best
        records.append(dict(atom_mask_hex=hex(mask), atoms=mask.bit_count(), nullity=len(local),
            seed_state_hex=hex(seed & mask), kernel_hex=[hex(cycle) for cycle in local],
            all_kernel_cycles_even=even, exact_minimum=exact, lower_bound=lower,
            minimum_weight=best.bit_count() if exact else None, best_state_hex=hex(best),
            combinations_enumerated=count if exact and local else 0))
    original = rebuilt = 0
    for index in bits(seed):
        original ^= columns[index]
    for index in bits(best_state):
        rebuilt ^= columns[index]
    if original != rebuilt:
        raise AssertionError("component witness left the exact seed coset")
    all_even = all(cycle.bit_count() % 2 == 0 for cycle in cycles)
    parity = seed.bit_count() % 2 if all_even else None
    effective = bound - ((bound - parity) % 2) if all_even else bound
    return dict(scope=SCOPE, dictionary_rank=len(pivots), dictionary_nullity=len(cycles),
        complete_kernel_basis_checked=True, all_kernel_cycles_even=all_even,
        feasible_weight_parity=parity, requested_bound=bound, parity_adjusted_bound=effective,
        components=records, combinations_enumerated=spent,
        global_lower_bound=sum(record["lower_bound"] for record in records),
        exact_dictionary_coset_minimum=all(record["exact_minimum"] for record in records),
        best_state_hex=hex(best_state), best_weight=best_state.bit_count(),
        explanation="Complete code-kernel coset only; fixed components are exact. Unknown large components have only the stated safe lower bound.")


def _clamp_limit(which, requested):
    soft, hard = resource.getrlimit(which)
    # Preserve both inherited ceilings; no child can raise a parent policy.
    finite = [v for v in (soft, hard, requested) if v != resource.RLIM_INFINITY]
    effective = min(finite)
    resource.setrlimit(which, (effective, hard))
    return effective


def _worker(problem, deadline, conflicts, memory_mib, sender):
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    try:
        os.sched_setaffinity(0, {1})
        nice = os.getpriority(os.PRIO_PROCESS, 0)
        if nice < 10:
            os.nice(10 - nice)
        memory_limit = _clamp_limit(resource.RLIMIT_AS, memory_mib * 1024**2)
        _clamp_limit(resource.RLIMIT_CPU, math.ceil(max(0, deadline - time.monotonic())) + 1)
        import pycryptosat
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Stopped("budget elapsed during backend import")
        solver = pycryptosat.Solver(threads=1, verbose=0, time_limit=remaining, confl_limit=conflicts)
        if problem["nv"]:
            solver.add_clause([problem["nv"], -problem["nv"]])
        for index, clause in enumerate(problem["clauses"]):
            if index % 256 == 0 and time.monotonic() >= deadline:
                raise Stopped("budget elapsed during CNF loading")
            solver.add_clause(clause)
        for variables, rhs in problem["xors"]:
            if time.monotonic() >= deadline:
                raise Stopped("budget elapsed during XOR loading")
            solver.add_xor_clause(variables, rhs)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Stopped("budget elapsed before solve")
        status, assignment = solver.solve(time_limit=remaining, confl_limit=conflicts)
        result = dict(status="SAT" if status is True else "DICTIONARY_UNSAT" if status is False else "UNKNOWN",
                      solver="CryptoMiniSat", pycryptosat_version=pycryptosat.__version__)
        if status is True:
            if len(assignment) < problem["nv"] + 1 or any(type(v) is not bool for v in assignment[1:]):
                raise ValueError("incomplete native solver assignment")
            if any(not any(assignment[abs(lit)] == (lit > 0) for lit in clause) for clause in problem["clauses"]):
                raise ValueError("native assignment violates CNF")
            if any(bool(sum(assignment[v] for v in variables) % 2) != rhs for variables, rhs in problem["xors"]):
                raise ValueError("native assignment violates XOR")
            state = sum(int(assignment[index + 1]) << index for index in range(problem["selection_variables"]))
            validate_state(problem, state)
            result["state_hex"] = hex(state)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        result.update(cpu_seconds=usage.ru_utime + usage.ru_stime, max_rss_kib=usage.ru_maxrss,
                      effective_memory_limit_bytes=memory_limit, cpu_affinity=sorted(os.sched_getaffinity(0)),
                      nice=os.getpriority(os.PRIO_PROCESS, 0))
    except Stopped as exc:
        result = dict(status="UNKNOWN", reason=str(exc))
    except Exception as exc:
        result = dict(status="ERROR", error=f"{type(exc).__name__}: {exc}")
    try:
        sender.send(result)
    finally:
        sender.close()


def solve_linear(problem, *, seconds=30, conflicts=1000000, memory_mib=1024, cancelled=None):
    """Hard wall bound covers native import, loading and solving, with child reap."""
    if (not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not math.isfinite(seconds)
            or not 0 < seconds <= 30 or type(conflicts) is not int or conflicts < 1
            or type(memory_mib) is not int or not 128 <= memory_mib <= 1024):
        raise ValueError("seconds 0..30, positive conflicts, memory 128..1024 MiB required")
    started = time.monotonic()
    if cancelled and cancelled():
        return dict(status="UNKNOWN", reason="cancelled before native launch", worker_reaped=True,
                    solver_called=False, scope=SCOPE)
    context = mp.get_context("fork")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=_worker, args=(problem, started + seconds, conflicts, memory_mib, sender))
    child.start()
    sender.close()
    result = None
    try:
        while result is None:
            remaining = started + seconds - time.monotonic()
            if remaining <= 0 or (cancelled and cancelled()):
                result = dict(status="UNKNOWN", reason="hard wall limit or cancellation")
            elif receiver.poll(min(remaining, .05)):
                try:
                    result = receiver.recv()
                except EOFError:
                    result = dict(status="ERROR", error="native child exited without a result")
                if time.monotonic() >= started + seconds or (cancelled and cancelled()):
                    result = unknown_with_raw(result, "native result arrived after stop barrier")
    finally:
        child.join(timeout=.02)
        if child.is_alive():
            child.terminate()
        child.join(timeout=.1)
        if child.is_alive():
            child.kill()
            child.join()
        receiver.close()
    result.update(elapsed_seconds=time.monotonic() - started, wall_seconds=seconds,
                  solver_threads=1, cpu=1, memory_mib=memory_mib, worker_pid=child.pid,
                  worker_exitcode=child.exitcode, worker_reaped=not child.is_alive(),
                  solver_called=True, formula_sha256=problem["metadata"]["formula_sha256"], scope=SCOPE)
    if result["status"] == "SAT":
        validate_state(problem, int(result["state_hex"], 16))
    return result


def independent_tensor_data(atoms, n):
    """Reconstruct columns and target independently of the owner column kernel."""
    if type(n) is not int or not 1 <= n <= 5:
        raise ValueError("literal matrix dimension in 1..5 required")
    width = n*n
    columns = []
    for atom in atoms:
        if len(atom) != 3 or any(type(v) is not int or not 0 < v < 1 << width for v in atom):
            raise ValueError("literal nonzero whole rank-one factors required")
        column = 0
        for a in range(width):
            for b in range(width):
                if not ((atom[0] >> a & 1) and (atom[1] >> b & 1)):
                    continue
                for c in range(width):
                    if atom[2] >> c & 1:
                        column ^= 1 << ((a*width + b)*width + c)
        columns.append(column)
    target = 0
    for a in range(width):
        i, j = divmod(a, n)
        for b in range(width):
            jj, k = divmod(b, n)
            for c in range(width):
                kk, ii = divmod(c, n)
                if i == ii and j == jj and k == kk:
                    target |= 1 << ((a*width + b)*width + c)
    return columns, target


def verify_solution(candidate, bound, guard=None):
    if type(bound) is not int or bound < 0:
        raise ValueError("literal nonnegative support bound required")
    from mmsearch.tensor_code7 import atom_from_term
    n = candidate["dimension"]
    atoms = [atom_from_term(term, n) for term in candidate["terms"]]
    if type(candidate.get("field")) is not int or candidate["field"] != 2 or len(set(atoms)) != len(atoms):
        raise ValueError("F2 distinct whole atoms required")
    if not 0 < len(atoms) <= bound:
        raise ValueError("candidate exceeds exact support bound")
    primary = verify_candidate(candidate, random_trials=0)
    if guard:
        guard("post_primary_verification")
    columns, target = independent_tensor_data(atoms, n)
    observed = 0
    for column in columns:
        observed ^= column
    independent = dict(valid=observed == target, exact_entries_checked=n**6,
                       mismatch_count=(observed ^ target).bit_count(),
                       checker="independent literal whole-atom complete tensor reconstruction")
    if not primary["valid"] or primary["exact_entries_checked"] != n**6 or not independent["valid"]:
        raise ValueError("SAT witness failed complete independent tensor checks")
    checks = dict(primary=primary, independent=independent)
    if n == 5:
        from scripts.verify_record42_independent import verify_bytes
        report = verify_bytes(raw_json(candidate))
        if report.get("record_eligible") is not True or report.get("exact_entries_checked") != 15625:
            raise ValueError("SAT witness failed strict independent record checker")
        checks["record_independent"] = report
    if guard:
        guard("post_independent_verification")
    return checks


def solve_prepared(document, *, bound=92, seconds=30, conflicts=1000000,
                   memory_mib=1024, guard=None, production_receipt=None):
    """Tiny controls are available directly; n5 requires root-pinned provenance."""
    n = document.get("dimension")
    if n == 5 and (not production_receipt or production_receipt.get("qa_approval") != "root-reviewed"
                   or production_receipt.get("document_digest") != digest(document)):
        raise PermissionError("n5 SAT requires root-reviewed pinned prepared/source receipt")
    if n == 5 and bound != 92:
        raise ValueError("production n5 support bound must be92")
    if (not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not math.isfinite(seconds)
            or not 0 < seconds <= 30 or type(conflicts) is not int or conflicts < 1
            or type(memory_mib) is not int or not 128 <= memory_mib <= 1024):
        raise ValueError("invalid bounded solve resources")
    started = time.monotonic()
    result = None
    def checkpoint(phase):
        if time.monotonic() - started >= seconds:
            raise Stopped("total formula/solve/verification budget elapsed: " + phase)
        if guard:
            try:
                guard(phase)
            except Stopped:
                raise
            except Exception as exc:
                from scripts.tensor_code7 import Stop as OwnerStop
                if isinstance(exc, OwnerStop):
                    raise Stopped(str(exc)) from exc
                raise
    try:
        checkpoint("pre_prepared_validation")
        from mmsearch.tensor_code7 import validate_prepared
        atoms, columns, _seeds, _cycles = validate_prepared(document, lambda: checkpoint("prepared_validation"))
        rebuilt, target = independent_tensor_data(atoms, n)
        if rebuilt != columns or document["target_hex"] != hex(target):
            raise ValueError("prepared columns/target disagree with independent full reconstruction")
        problem = build_problem(rebuilt, target, n**6, bound, guard=checkpoint)
        remaining = seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise Stopped("formula construction exhausted total budget")
        def cancelled():
            try:
                checkpoint("native_solver")
                return False
            except Exception as exc:
                # A failed guard cannot authorize a terminal mathematical result.
                return True
        result = solve_linear(problem, seconds=remaining, conflicts=conflicts,
                              memory_mib=memory_mib, cancelled=cancelled)
        checkpoint("post_native_result")
        result.update(metadata=problem["metadata"], dictionary_sha256=document["dictionary_sha256"],
                      dimension=n, support_bound=bound, document_digest=digest(document))
        if result["status"] == "SAT":
            state = int(result["state_hex"], 16)
            selected = [atoms[index] for index in bits(state)]
            width = n*n
            candidate = dict(dimension=n, field=2, terms=[
                {axis: [(value >> index) & 1 for index in range(width)]
                 for axis, value in zip(("u", "v", "w"), atom)} for atom in selected],
                metadata=dict(method=SCHEMA, scope=SCOPE, novelty_claim=False,
                              dictionary_sha256=document["dictionary_sha256"]))
            result.update(candidate=candidate, checks=verify_solution(candidate, bound, checkpoint),
                          essential_rank=len(selected))
        return result
    except Stopped as exc:
        return unknown_with_raw(result, str(exc), document)


def load_root_pinned_prepared(path, prepared_sha256, manifest, manifest_sha256,
                              approved_root, scratch, guard):
    """Reuse the owner's reviewed source-closure validator; never trust self hashes."""
    from mmsearch.tensor_code7 import strict_load
    path, manifest, approved_root = Path(path), Path(manifest), Path(approved_root)
    if path.is_symlink() or manifest.is_symlink():
        raise ValueError("pinned artifacts must not be symlinks")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != prepared_sha256:
        raise ValueError("prepared raw hash differs from root-reviewed pin")
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != manifest_sha256:
        raise ValueError("source manifest raw hash differs from root-reviewed pin")
    document = strict_load(raw)
    if type(document.get("dimension")) is not int or document["dimension"] != 5:
        raise ValueError("production prepared artifact must be dimension5")
    if document.get("dictionary_size", MAX_ATOMS + 1) > MAX_ATOMS:
        raise ValueError("root-approved dictionary exceeds5000atom cap")
    # The shared provenance checker must itself match the prepared review pins.
    owner_code = document.get("code_sha256")
    if not isinstance(owner_code, dict) or not owner_code:
        raise ValueError("prepared owner code review pins missing")
    repo = Path(__file__).resolve().parents[1]
    for name, expected in owner_code.items():
        source = (repo/name).resolve(strict=True)
        if not source.is_relative_to(repo) or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError("prepared owner code differs from reviewed pin: " + name)
    from scripts.tensor_code7 import verify_source_binding
    args = SimpleNamespace(prepared=path, manifest=manifest, manifest_sha256=manifest_sha256,
                           approved_root=approved_root, outdir=Path(scratch))
    verify_source_binding(args, document, guard)
    return document, dict(qa_approval="root-reviewed", prepared_sha256=prepared_sha256,
                          source_manifest_sha256=manifest_sha256, document_digest=digest(document))


def freeze_solution(destination, result, guard=None):
    """Atomic immutable certificate directory; no campaign stop marker is written."""
    if result.get("status") != "SAT":
        raise ValueError("only a fully checked SAT witness can be frozen")
    destination = Path(destination)
    if destination.exists():
        raise ValueError("immutable certificate destination already exists")
    candidate = result["candidate"]
    checks = verify_solution(candidate, result["support_bound"], guard)
    if guard:
        guard("pre_freeze")
    stage = destination.with_name("." + destination.name + f".pending-{os.getpid()}-{time.monotonic_ns()}")
    stage.mkdir(parents=True, exist_ok=False)
    values = {"candidate.json": raw_json(candidate), "verification.json": raw_json(checks),
              "provenance.json": raw_json({key: value for key, value in result.items() if key not in ("candidate", "checks")}),
              "tensor_code7_sat.py": Path(__file__).read_bytes()}
    repo = Path(__file__).resolve().parents[1]
    values["verify.py"] = (repo/"mmsearch/verify.py").read_bytes()
    if candidate["dimension"] == 5:
        values["verify_record42_independent.py"] = (repo/"scripts/verify_record42_independent.py").read_bytes()
    for name, raw in values.items():
        with (stage/name).open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        (stage/name).chmod(0o444)
    persisted = json.loads((stage/"candidate.json").read_bytes())
    verify_solution(persisted, result["support_bound"], guard)
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in values.items()}
    if any(hashlib.sha256((stage/name).read_bytes()).hexdigest() != h for name, h in hashes.items()):
        raise ValueError("persisted certificate hash mismatch")
    marker = "WINNER.json" if candidate["dimension"] == 5 else "CONTROL.json"
    hashes[marker] = hashes["candidate.json"]
    (stage/"checksums.json").write_bytes(raw_json(hashes))
    (stage/"checksums.json").chmod(0o444)
    if guard:
        guard("premarker")
    with (stage/marker).open("xb") as stream:
        stream.write(values["candidate.json"])
        stream.flush()
        os.fsync(stream.fileno())
    (stage/marker).chmod(0o444)
    fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    stage.rename(destination)
    try:
        if guard:
            guard("postmarker")
    except Exception:
        destination.rename(stage)
        raise
    fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return str(destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-search", action="store_true")
    parser.add_argument("--qa-approval", choices=("root-reviewed",))
    for name in ("prepared", "manifest", "approved-root", "outdir", "campaign-dir", "guard-state"):
        parser.add_argument("--" + name, type=Path)
    for name in ("prepared-sha256", "manifest-sha256", "campaign-sha256", "hard-utc"):
        parser.add_argument("--" + name)
    parser.add_argument("--stop-marker", type=Path, action="append", default=[])
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--memory-mib", type=int, choices=(1024,), default=1024)
    parser.add_argument("--cpu", type=int, choices=(1,), default=1)
    parser.add_argument("--conflicts", type=int, default=1000000)
    args = parser.parse_args(argv)
    if not args.authorize_search or args.qa_approval != "root-reviewed":
        print(json.dumps(dict(status="DISABLED_PENDING_ROOT_QA", production_inputs_read=False, solver_called=False)))
        return 0
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 30 or args.conflicts < 1:
        parser.error("initial solve budget must be finite0..30seconds with positiveconflicts")
    for name in ("prepared", "prepared_sha256", "manifest", "manifest_sha256", "approved_root", "outdir",
                 "campaign_dir", "campaign_sha256", "guard_state", "hard_utc"):
        if getattr(args, name) is None:
            parser.error("root-reviewed production requires --" + name.replace("_", "-"))
    from scripts.tensor_code7 import Guard, Stop
    guard = Guard(args.hard_utc, args.seconds, args.campaign_dir, args.guard_state,
                  args.campaign_sha256, args.stop_marker)
    result = None
    document = None
    try:
        guard("pre_input")
        os.sched_setaffinity(0, {1})
        nice = os.getpriority(os.PRIO_PROCESS, 0)
        if nice < 10:
            os.nice(10 - nice)
        _clamp_limit(resource.RLIMIT_AS, args.memory_mib*1024**2)
        args.outdir.mkdir(parents=True, exist_ok=False)
        document, receipt = load_root_pinned_prepared(args.prepared, args.prepared_sha256,
            args.manifest, args.manifest_sha256, args.approved_root, args.outdir, guard)
        result = solve_prepared(document, seconds=args.seconds, conflicts=args.conflicts,
                                memory_mib=args.memory_mib, guard=guard, production_receipt=receipt)
        if result["status"] == "SAT":
            freeze_solution(args.outdir/"verified-record", result, guard)
        if result["status"] != "UNKNOWN":
            guard("pre_result_publication")
        (args.outdir/"result.json").write_bytes(raw_json(result))
    except (Stop, Stopped) as exc:
        result = unknown_with_raw(result, str(exc), document)
        if args.outdir.exists():
            (args.outdir/"result.json").write_bytes(raw_json(result))
    print(json.dumps({key: value for key, value in result.items() if key not in ("candidate", "checks")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
