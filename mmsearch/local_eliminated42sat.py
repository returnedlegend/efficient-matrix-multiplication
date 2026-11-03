"""Exact conditional local SAT after witnessed elimination of fixed vectors.

The outside-baseline substitutions are made in every original tensor row.
Only nonforced local groups receive SAT variables. UNSAT is local to this
recorded substitution; it does not concern unrestricted tensor rank.
"""
from __future__ import annotations

import math
import multiprocessing as mp
from pathlib import Path
import signal
import time

from .free_factor_sat import FormulaMemoryLimit, decode_vectors, satisfies
from .local_free_factor_sat import local_bound
from .recombine import digest
from .recombine_sat import bits
from .verify import verify_candidate


def build_problem(system, free_groups, rank=92, *, implied_cuts=True, max_formula_mb=128):
    if type(rank) is not int or rank < 0 or type(implied_cuts) is not bool:
        raise ValueError('invalid rank or implied-cut setting')
    if not math.isfinite(max_formula_mb) or max_formula_mb <= 0:
        raise ValueError('positive finite formula cap required')
    bound = local_bound(system, free_groups, rank)
    groups = bound['free_groups']
    width = system['metadata']['width']
    forced = {int(g): int(v, 16) for g,v in bound['forced_vectors_hex'].items()}
    live = [g for g in groups if g not in forced]
    positions = {g:i for i,g in enumerate(live)}
    remaining = rank-bound['fixed_active']-bound['forced_nonzero']
    # Same conservative storage envelope as the reviewed global encoder,
    # applied to the reduced local problem before constructing cardinality.
    estimate = (len(live)*(width+1)*2048 +
        width*sum(int(row[0],16).bit_count() for row in bound['rref_rows_hex'])*80 +
        len(live)*math.ceil(math.log2(max(2,len(live))))**2*1024)
    if estimate > max_formula_mb*1024**2:
        raise FormulaMemoryLimit('local formula estimate exceeds configured cap')
    xs = {str(g): [i*width+c+1 for c in range(width)] for g,i in positions.items()}
    ys = {str(g): len(live)*width+i+1 for g,i in positions.items()}
    nv = len(live)*(width+1)
    clauses, xors, cuts = [], [], []
    for g in live:
        clauses.extend([[-x,ys[str(g)]] for x in xs[str(g)]])
        clauses.append([-ys[str(g)]]+xs[str(g)])
    for coefficient_hex, rhs_hex, _ in bound['rref_rows_hex']:
        coefficient, rhs = int(coefficient_hex,16), int(rhs_hex,16)
        row_groups = []
        for local in bits(coefficient):
            g = groups[local]
            if g in forced:
                rhs ^= forced[g]
            else:
                row_groups.append(g)
        if not row_groups:
            if rhs:
                clauses.append([])
            continue
        for c in range(width):
            xors.append(([xs[str(g)][c] for g in row_groups],bool(rhs >> c & 1)))
        # XOR of all-zero group vectors is zero. This clause is implied by
        # the vector equation, but exposes that consequence to CNF propagation.
        if implied_cuts and rhs:
            cuts.append([ys[str(g)] for g in row_groups])
    clauses.extend(cuts)
    if remaining < 0:
        clauses.append([])
    elif remaining < len(live):
        from pysat.card import CardEnc, EncType
        card = CardEnc.atmost(list(ys.values()),remaining,top_id=nv,encoding=EncType.cardnetwrk)
        clauses.extend(card.clauses)
        nv = max(nv,card.nv)
    metadata = dict(encoding='conditional-eliminated-local-native-xor-42-v1',
        rank_bound=rank, width=width, variables=nv, x_variables=len(live)*width,
        active_variables=len(live), cnf_clauses=len(clauses), native_xors=len(xors),
        implied_support_clauses=len(cuts), local_rank_budget=remaining,
        free_group_count=len(groups), nonforced_local_groups=len(live),
        local_linear_rank=bound['local_linear_rank'],local_nullity=bound['local_nullity'],
        estimated_python_formula_mb=math.ceil(estimate/1024**2),
        max_formula_mb=max_formula_mb, source_pairs_sha256=system['metadata']['pairs_sha256'],
        baseline_vectors_sha256=digest(system['baseline_vectors']),
        scope=bound['scope'], checkpoint_policy='Reproducible formula and assumptions only; no solver-internal checkpoint or learned-clause resume is supported by this Python API.')
    formula = dict(nv=nv,clauses=clauses,xors=xors,x_variables=xs,y_variables=ys,
        forced_vectors=forced,free_groups=groups,bound=bound,metadata=metadata)
    metadata['formula_sha256'] = digest({k:v for k,v in formula.items() if k != 'metadata'})
    return dict(formula,system=system)


def baseline_assumptions(problem):
    vectors = problem['system']['baseline_vectors']
    result = []
    for key,xs in problem['x_variables'].items():
        value = vectors[int(key)]
        result.extend(x if value >> c & 1 else -x for c,x in enumerate(xs))
        y = problem['y_variables'][key]
        result.append(y if value else -y)
    return result


def validate_decode(problem, assignment, assumptions=()):
    if (not isinstance(assignment,(list,tuple)) or len(assignment) != problem['nv']+1
            or any(type(v) is not bool for v in assignment[1:])):
        raise AssertionError('incomplete or non-Boolean solver model')
    if any(assignment[abs(lit)] != (lit > 0) for lit in assumptions):
        raise AssertionError('model violates assumptions')
    if any(not any(assignment[abs(lit)] == (lit > 0) for lit in row) for row in problem['clauses']):
        raise AssertionError('model violates CNF')
    if any(bool(sum(assignment[v] for v in row)%2) != rhs for row,rhs in problem['xors']):
        raise AssertionError('model violates native XOR')
    vectors = list(problem['system']['baseline_vectors'])
    for g,value in problem['forced_vectors'].items():
        vectors[int(g)] = value
    for key,xs in problem['x_variables'].items():
        value = sum(int(assignment[x]) << c for c,x in enumerate(xs))
        if assignment[problem['y_variables'][key]] != bool(value):
            raise AssertionError('active indicator disagrees with vector')
        vectors[int(key)] = value
    if sum(bool(v) for v in vectors) > problem['metadata']['rank_bound']:
        raise AssertionError('decoded full vector rank exceeds bound')
    if not satisfies(problem['system'],vectors):
        raise AssertionError('decoded model violates original complete tensor rows')
    candidate = decode_vectors(problem['system'],vectors,dict(
        method='conditional-eliminated-local-native-xor-42',
        formula_sha256=problem['metadata']['formula_sha256'],field_claim='F2 only'))
    report = verify_candidate(candidate,random_trials=0)
    if not report['valid'] or report['exact_entries_checked'] != problem['metadata']['width']**3:
        raise AssertionError('independent full tensor verification failed')
    return candidate,report


def _worker(problem, seconds, conflicts, memory_mb, assumptions, options, log_path, sender):
    signal.signal(signal.SIGTERM,signal.SIG_DFL)
    signal.signal(signal.SIGINT,signal.SIG_DFL)
    try:
        import os
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(memory_mb*1024**2,memory_mb*1024**2))
        resource.setrlimit(resource.RLIMIT_CPU,(math.ceil(seconds)+1,math.ceil(seconds)+2))
        if log_path:
            fd = os.open(log_path,os.O_CREAT|os.O_WRONLY|os.O_EXCL,0o644)
            os.dup2(fd,1)
            os.dup2(fd,2)
            os.close(fd)
        import pycryptosat
        solver = pycryptosat.Solver(threads=1,verbose=1 if log_path else 0,
            time_limit=seconds,confl_limit=conflicts,options=options)
        if problem['nv']:
            solver.add_clause([problem['nv'],-problem['nv']])
        for row in problem['clauses']:
            solver.add_clause(row)
        for row,rhs in problem['xors']:
            solver.add_xor_clause(row,rhs)
        status,assignment = solver.solve(assumptions=assumptions,time_limit=seconds,confl_limit=conflicts)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        result = dict(status='SAT' if status is True else 'LOCAL_UNSAT' if status is False else 'UNKNOWN',
            assignment=assignment if status is True else None,
            assumption_core=solver.get_conflict() if status is False and assumptions else None,
            pycryptosat_version=pycryptosat.__version__, solver_variable_count=solver.nb_vars(),
            solver_stats=dict(user_seconds=usage.ru_utime,system_seconds=usage.ru_stime,max_rss_kib=usage.ru_maxrss),
            solver_stats_limit='Python API exposes no conflict/restart counters; native verbosity log retained when configured.')
    except Exception as exc:
        result = dict(status='ERROR',error=f'{type(exc).__name__}: {exc}')
    try:
        sender.send(result)
    finally:
        sender.close()


def solve(problem, seconds=180, conflicts=100000000, memory_mb=1536,
          assumptions=(), options=None, log_path=None, cancelled=None):
    if (not math.isfinite(seconds) or seconds <= 0 or type(conflicts) is not int or conflicts < 1
            or type(memory_mb) is not int or not 128 <= memory_mb <= 2048):
        raise ValueError('invalid solve resource bounds')
    assumptions = list(assumptions)
    if any(type(lit) is not int or not 1 <= abs(lit) <= problem['nv'] for lit in assumptions):
        raise ValueError('invalid assumptions')
    options = {} if options is None else dict(options)
    if any(not isinstance(k,str) or not isinstance(v,str) for k,v in options.items()):
        raise ValueError('solver options must be string pairs')
    # A fork inherits the parent's full address space before the worker applies
    # RLIMIT_AS. A large caller can otherwise make even a tiny native formula
    # abort under a valid256MiB child budget. Spawn keeps that budget meaningful.
    context = mp.get_context('spawn')
    receiver,sender = context.Pipe(duplex=False)
    child = context.Process(target=_worker,args=(problem,seconds,conflicts,memory_mb,
        assumptions,options,str(log_path) if log_path else None,sender))
    started = time.monotonic()
    child.start()
    sender.close()
    result = None
    try:
        while result is None:
            left = seconds-(time.monotonic()-started)
            if left <= 0 or (cancelled is not None and cancelled()):
                result = dict(status='UNKNOWN',reason='hard wall limit or campaign stop signal')
            elif receiver.poll(min(left,.2)):
                try:
                    result = receiver.recv()
                except EOFError:
                    result = dict(status='ERROR',error='worker exited without result')
    finally:
        # Allow normal exit and native log flushing, then enforce termination.
        child.join(timeout=.05)
        if child.is_alive():
            child.terminate()
        child.join(timeout=.2)
        if child.is_alive():
            child.kill()
            child.join()
        receiver.close()
    assignment = result.pop('assignment',None)
    result.update(elapsed_seconds=time.monotonic()-started,wall_seconds=seconds,
        memory_mb=memory_mb,conflict_limit=conflicts,threads=1,worker_pid=child.pid,
        worker_exitcode=child.exitcode,worker_reaped=not child.is_alive(),
        assumptions=assumptions,solver_options=options,
        formula_sha256=problem['metadata']['formula_sha256'],scope=problem['metadata']['scope'])
    if result['status'] == 'SAT':
        candidate,report = validate_decode(problem,assignment,assumptions)
        result.update(candidate=candidate,verification=report,complete_assignment=list(assignment))
    return result


def write_problem(problem,prefix):
    prefix = Path(prefix)
    with prefix.with_suffix('.cnf').open('x') as stream:
        stream.write(f"p cnf {problem['nv']} {len(problem['clauses'])+len(problem['xors'])}\n")
        for row in problem['clauses']:
            stream.write(' '.join(map(str,row))+' 0\n')
        for row,rhs in problem['xors']:
            values = list(row)
            if not rhs:
                values[0] *= -1
            stream.write('x'+' '.join(map(str,values))+' 0\n')
