"""Exact Boolean encoding of one Fano quotient cover branch, never full CP UNSAT.

B0 consists of original rank-one matrices. Four Fano sums must form a basis
of S/B0. SAT constructs a cover of every raw S slice by B0 plus seven points.
"""
from datetime import datetime, timezone
import copy
import math
import multiprocessing as mp
import time

from .compact_eight43 import exact_coordinates
from .compact_sat import BinaryBasis, bits
from .compact_coset43 import digest, expand_products, mode_slices, pair_column
from .fano_quotient_worker7 import worker

DEADLINE = '2026-11-03T19:24:17Z'
HARD_DEADLINE = datetime.fromisoformat(DEADLINE.replace('Z', '+00:00')).timestamp()
RELATIONS = ((3, 0, 1), (4, 0, 2), (5, 1, 2), (6, 0, 1, 2))
SCOPE = ('Exact Fano branch for the supplied S and original B0 points only. '
         'FANO_BRANCH_UNSAT alone is not a complete CP-rank negative.')


def xor_values(values):
    result = 0
    for value in values:
        result ^= value
    return result


def and_clauses(a, b, out):
    return [[-out, a], [-out, b], [out, -a, -b]]


def build_problem(targets, rows, columns, backbone_points, space_basis=None):
    """Encode q=4, at most 11x11; do not replace original factor points by GE rows.

    The generic encoder is also useful for tiny constraints tests. Completeness
    as the remaining CP(d+3) branch requires B0 to be the full rank-one backbone,
    certified separately by the pinned production-input adapter.
    """
    if any(type(v) is not int or not 1 <= v <= 11 for v in (rows, columns)):
        raise ValueError('positive matrix dimensions at most 11 required')
    targets = list(targets)
    if any(type(v) is not int or v < 0 or v >> (rows*columns) for v in targets):
        raise ValueError('raw matrix outside declared shape')
    basis = list(BinaryBasis(targets).vectors) if space_basis is None else list(space_basis)
    if (not 4 <= len(basis) <= 11 or len(BinaryBasis(basis).vectors) != len(basis)
            or any(type(v) is not int or v <= 0 or v >> (rows*columns) for v in basis)):
        raise ValueError('independent S basis of dimension 4..11 required')
    for value in targets:
        exact_coordinates(value, basis)
    if len(BinaryBasis(targets).vectors) != len(basis):
        raise ValueError('raw targets must span the complete S basis')
    points = []
    for point in backbone_points:
        left, right, column = point['left'], point['right'], point['column']
        if (type(left) is not int or type(right) is not int or type(column) is not int or not 0 < left < 1 << rows
                or not 0 < right < 1 << columns or column != pair_column(left, right, columns)):
            raise ValueError('original nonzero rank-one B0 factor point required')
        points.append(dict(left=left, right=right, column=column))
    bcoords = [exact_coordinates(p['column'], basis) for p in points]
    if len(points) != len(basis)-4 or len(BinaryBasis(bcoords).vectors) != len(points):
        raise ValueError('B0 points must be independent with quotient dimension four')
    # GE is only a membership test. Retain each original B0 coordinate vector.
    combined = list(bcoords)
    complement = []
    for t in range(len(basis)):
        candidate = 1 << t
        if len(BinaryBasis(combined+[candidate]).vectors) > len(combined):
            combined.append(candidate)
            complement.append(candidate)
    if len(complement) != 4:
        raise AssertionError('quotient complement dimension differs')
    quotient = [exact_coordinates(1 << t, combined) >> len(points) for t in range(len(basis))]
    clauses, xors = [], []
    nv = 0
    def fresh(count):
        nonlocal nv
        result = list(range(nv+1, nv+count+1)); nv += count
        return result
    us = [fresh(rows) for _ in range(7)]
    vs = [fresh(columns) for _ in range(7)]
    zs = [fresh(len(basis)) for _ in range(4)]
    products = [fresh(rows*columns) for _ in range(7)]
    for p in range(7):
        for i in range(rows):
            for j in range(columns):
                clauses.extend(and_clauses(us[p][i], vs[p][j], products[p][i*columns+j]))
    for ell, relation in enumerate(RELATIONS):
        for cell in range(rows*columns):
            xors.append(([products[p][cell] for p in relation]+
                         [zs[ell][t] for t, value in enumerate(basis) if value >> cell & 1], False))
    a = [fresh(4) for _ in range(4)]
    inverse = [fresh(4) for _ in range(4)]
    for r in range(4):
        for ell in range(4):
            xors.append(([a[r][ell]]+[zs[ell][t] for t, value in enumerate(quotient) if value >> r & 1], False))
    inverse_products = [[fresh(4) for _ in range(4)] for _ in range(4)]
    for r in range(4):
        for c in range(4):
            for k in range(4):
                clauses.extend(and_clauses(a[r][k], inverse[k][c], inverse_products[r][c][k]))
            xors.append((inverse_products[r][c], r == c))
    problem = dict(nv=nv, clauses=clauses, xors=xors, u_variables=us, v_variables=vs,
                   z_variables=zs, product_variables=products, a_variables=a,
                   inverse_variables=inverse, inverse_product_variables=inverse_products,
                   rows=rows, columns=columns, targets=targets, space_basis=basis,
                   backbone_points=points, quotient_columns=quotient,
                   quotient_complement_coordinates=complement)
    problem['metadata'] = dict(algorithm='fano_quotient_sat7', scope=SCOPE,
        target_rank=len(basis), backbone_rank=len(points), quotient_dimension=4,
        cover_budget=len(points)+7, variables=nv, cnf_clauses=len(clauses), native_xors=len(xors),
        relation_xors=4*rows*columns, matrix_and_auxiliaries=7*rows*columns,
        inverse_and_auxiliaries=64, formula_sha256=digest(problem),
        zero_factor_policy='Allowed; zero products are omitted from the decoded cover.')
    return problem


def validate_decode(problem, assignment, assumptions=()):
    if (not isinstance(assignment, (list, tuple)) or len(assignment) != problem['nv']+1
            or any(type(value) is not bool for value in assignment[1:])):
        raise AssertionError('complete Boolean model required')
    if any(assignment[abs(lit)] != (lit > 0) for lit in assumptions):
        raise AssertionError('model violates explicit assumptions')
    for clause in problem['clauses']:
        if not any(assignment[abs(lit)] == (lit > 0) for lit in clause):
            raise AssertionError('model violates AND CNF')
    for row, rhs in problem['xors']:
        if bool(sum(assignment[v] for v in row) % 2) != rhs:
            raise AssertionError('model violates native XOR')
    def value(variables):
        return sum(int(assignment[v]) << k for k, v in enumerate(variables))
    factors = [(value(u), value(v)) for u, v in zip(problem['u_variables'], problem['v_variables'])]
    columns = [pair_column(u, v, problem['columns']) for u, v in factors]
    relations = [xor_values(columns[p] for p in relation) for relation in RELATIONS]
    relation_coords = [value(z) for z in problem['z_variables']]
    for raw, coordinates in zip(relations, relation_coords):
        if raw != xor_values(problem['space_basis'][t] for t in bits(coordinates)):
            raise AssertionError('literal Fano relation differs')
    quotients = [xor_values(problem['quotient_columns'][t] for t in bits(coordinates)) for coordinates in relation_coords]
    if len(BinaryBasis(quotients).vectors) != 4:
        raise AssertionError('Fano sums do not span S/B0')
    pool = [dict(p) for p in problem['backbone_points']]+[
        dict(left=u, right=v, column=column) for (u, v), column in zip(factors, columns) if column]
    support = []
    for point in pool:
        if len(BinaryBasis([p['column'] for p in support]+[point['column']]).vectors) > len(support):
            support.append(point)  # Original factors, never GE residues.
    basis = [p['column'] for p in support]
    coordinates = [exact_coordinates(raw, basis) for raw in problem['targets']]
    for raw, mask in zip(problem['targets'], coordinates):
        if xor_values(basis[j] for j in bits(mask)) != raw:
            raise AssertionError('every original raw slice must reconstruct')
    if len(support) > problem['metadata']['cover_budget']:
        raise AssertionError('cover exceeds B0+7 budget')
    return dict(support=support, target_coordinates=coordinates,
                factor_point_pool=pool, seven_factors=[list(p) for p in factors],
                fano_sums=relations, fano_sum_coordinates=relation_coords,
                quotient_sum_coordinates=quotients, all_raw_slices_verified=True)


class _Guard:
    def __init__(self, seconds, deadline_utc, cancelled):
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('positive finite seconds required')
        stamp = datetime.fromisoformat(deadline_utc.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('deadline requires timezone')
        self.until = time.monotonic()+seconds
        self.deadline = min(HARD_DEADLINE, stamp.timestamp())
        self.cancelled = cancelled
    def reason(self):
        if time.time() >= self.deadline:
            return 'deadline'
        if time.monotonic() >= self.until:
            return 'timeout'
        if self.cancelled and self.cancelled():
            return 'cancelled'
        # Callback IO may itself cross either clock boundary.
        if time.time() >= self.deadline:
            return 'deadline'
        if time.monotonic() >= self.until:
            return 'timeout'
        return None


def solve(problem, seconds=20, memory_mb=1024, cancelled=None, deadline_utc=DEADLINE, assumptions=()):
    if type(memory_mb) is not int or not 128 <= memory_mb <= 1024:
        raise ValueError('worker memory must be 128..1024 MiB')
    assumptions = list(assumptions)
    if any(type(v) is not int or not 1 <= abs(v) <= problem['nv'] for v in assumptions):
        raise ValueError('invalid Boolean assumptions')
    guard = _Guard(seconds, deadline_utc, cancelled)
    caller_problem = problem
    problem = copy.deepcopy(caller_problem)
    expected_hash = problem['metadata']['formula_sha256']
    def formula_hash(value):
        return digest({k:v for k,v in value.items() if k != 'metadata'})
    if formula_hash(problem) != expected_hash:
        raise ValueError('formula bytes differ from their construction hash')
    def checked_reason():
        reason = guard.reason()
        if reason:
            return reason
        try:
            if (caller_problem['metadata']['formula_sha256'] != expected_hash
                    or problem['metadata']['formula_sha256'] != expected_hash
                    or formula_hash(caller_problem) != expected_hash
                    or formula_hash(problem) != expected_hash):
                return 'formula_changed'
        except (KeyError, TypeError, ValueError):
            return 'formula_changed'
        # Hashing is work too; never cache clocks across the binding barrier.
        if time.time() >= guard.deadline:
            return 'deadline'
        if time.monotonic() >= guard.until:
            return 'timeout'
        return None
    started = time.monotonic()
    base = dict(algorithm='fano_quotient_sat7', scope=SCOPE, complete=False,
                formula_sha256=problem['metadata']['formula_sha256'], memory_mb=memory_mb,
                effective_deadline_utc=datetime.fromtimestamp(guard.deadline, timezone.utc).isoformat(),
                assumptions=assumptions)
    reason = checked_reason()
    if reason:
        return dict(base, status='UNKNOWN', reason=reason, worker_started=False)
    context = mp.get_context('spawn');receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=worker, args=(problem, max(.001, guard.until-time.monotonic()), memory_mb, sender, assumptions))
    try:
        child.start()
    except Exception as exc:
        receiver.close();sender.close()
        return dict(base, status='ERROR', error=type(exc).__name__+': '+str(exc), worker_started=False)
    sender.close();raw = None
    try:
        while raw is None:
            reason = checked_reason()
            if reason:
                raw = dict(status='UNKNOWN', reason=reason)
            elif receiver.poll(min(.05, max(0, guard.until-time.monotonic()))):
                try:
                    raw = receiver.recv()
                except EOFError:
                    raw = dict(status='ERROR', error='worker exited without a result')
    finally:
        child.join(timeout=.03)
        if child.is_alive():child.terminate()
        child.join(timeout=.2)
        if child.is_alive():child.kill();child.join()
        receiver.close()
    result = dict(base, worker_started=True, worker_pid=child.pid, worker_exitcode=child.exitcode,
                  worker_reaped=not child.is_alive(), elapsed_seconds=time.monotonic()-started)
    reason = checked_reason()
    if reason:
        return dict(result, status='UNKNOWN', reason=reason, raw_worker_result=raw,
                    after_cutoff=True, publication_eligible=False)
    assignment = raw.pop('assignment', None)
    result.update(raw)
    if result['status'] == 'SAT':
        witness = validate_decode(problem, assignment, assumptions)
        reason = checked_reason()
        if reason:
            return dict(result, status='UNKNOWN', reason=reason, raw_compact=witness,
                        after_cutoff=True, publication_eligible=False)
        result.update(witness, complete=True, complete_assignment=assignment,
                      publication_eligible=False)  # Ambient/global verification is a caller gate.
    elif result['status'] == 'FANO_BRANCH_UNSAT':
        if assumptions:result['status'] = 'FANO_ASSUMPTIONS_UNSAT'
        result['complete'] = True
        result['fano_branch_complete'] = not assumptions
    reason = checked_reason()
    if reason:
        return dict(status='UNKNOWN', complete=False, reason=reason, raw_compact=result,
                    after_cutoff=True, publication_eligible=False, scope=SCOPE)
    return result


def solve_core(core, shape, backbone_points, *, axis=0, space_basis=None,
               seconds=20, memory_mb=1024, cancelled=None, deadline_utc=DEADLINE, assumptions=()):
    if (len(shape) != 3 or any(type(v) is not int or not 1 <= v <= 11 for v in shape)
            or len(core) != math.prod(shape) or any(type(v) is not int or v not in (0, 1) for v in core)
            or type(axis) is not int or axis not in (0, 1, 2)):
        raise ValueError('invalid binary core or axis')
    core, shape = list(core), list(shape)
    backbone_points = copy.deepcopy(backbone_points)
    space_basis = None if space_basis is None else list(space_basis)
    guard = _Guard(seconds, deadline_utc, cancelled)
    slices, other = mode_slices(core, shape, axis)
    problem = build_problem(slices, shape[other[0]], shape[other[1]], backbone_points, space_basis)
    reason = guard.reason()
    if reason:return dict(status='UNKNOWN', complete=False, reason=reason, scope=SCOPE)
    result = solve(problem, seconds=max(.000001, guard.until-time.monotonic()), memory_mb=memory_mb,
                   cancelled=guard.reason, deadline_utc=deadline_utc, assumptions=assumptions)
    result.update(shape=list(shape), axis=axis, core_sha256=digest(dict(core=core, shape=list(shape))))
    if result['status'] == 'SAT':
        free = [0]*len(result['support'])
        for index, mask in enumerate(result['target_coordinates']):
            for j in bits(mask):free[j] |= 1 << index
        products = []
        for j, point in enumerate(result['support']):
            term = [0, 0, 0];term[axis]=free[j];term[other[0]]=point['left'];term[other[1]]=point['right']
            if all(term):products.append(term)
        if expand_products(products, shape) != list(core):
            raise AssertionError('complete compact tensor reconstruction failed')
        result['products'] = products
        result['all_compact_coefficients_verified'] = True
    reason = guard.reason()
    if reason:
        return dict(status='UNKNOWN', complete=False, reason=reason, raw_compact=result,
                    after_cutoff=True, publication_eligible=False, scope=SCOPE)
    return result
