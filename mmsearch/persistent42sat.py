"""Cooperative solve slices on one native XOR solver in one bounded child.

Only the solver lifecycle changes. The caller supplies the immutable reviewed
formula. A process relaunch reloads that formula; no solver serialization is
provided or implied.
"""
from __future__ import annotations

import json
import math
import multiprocessing as mp
from pathlib import Path
import signal
import tempfile
import time

from .local_eliminated42sat import validate_decode


def _usage():
    import resource
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return dict(user_seconds=usage.ru_utime,system_seconds=usage.ru_stime,max_rss_kib=usage.ru_maxrss)


def _publish(path,value):
    """Replace checkpoint metadata atomically, never solver-internal state."""
    path = Path(path)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    temporary.replace(path)


def _worker(problem,stages,conflict_limits,memory_mb,assumptions,options,log_path,result_path,sender):
    try:
        import os
        import resource
        def set_bounded_limit(kind,soft,hard):
            _,inherited_hard = resource.getrlimit(kind)
            effective_hard = hard if inherited_hard==resource.RLIM_INFINITY else min(hard,inherited_hard)
            effective_soft = min(soft,effective_hard)
            resource.setrlimit(kind,(effective_soft,effective_hard))
            return dict(soft=effective_soft,hard=effective_hard,inherited_hard=inherited_hard)
        address_limit = set_bounded_limit(resource.RLIMIT_AS,memory_mb*1024**2,memory_mb*1024**2)
        cpu_budget = math.ceil(sum(stages))+30
        cpu_limit = set_bounded_limit(resource.RLIMIT_CPU,cpu_budget,cpu_budget+1)
        if log_path:
            descriptor = os.open(log_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o644)
            os.dup2(descriptor,1)
            os.dup2(descriptor,2)
            os.close(descriptor)
        import pycryptosat
        started = time.monotonic()
        solver = pycryptosat.Solver(threads=1,verbose=1 if log_path else 0,
            options=options,time_limit=sum(stages)+30,confl_limit=max(1,max(conflict_limits)))
        if problem['nv']:
            solver.add_clause([problem['nv'],-problem['nv']])
        for row in problem['clauses']:
            solver.add_clause(row)
        for row,rhs in problem['xors']:
            solver.add_xor_clause(row,rhs)
        identity = dict(worker_pid=os.getpid(),solver_object_id=id(solver),
            solver_variable_count=solver.nb_vars(),pycryptosat_version=pycryptosat.__version__,
            formula_sha256=problem['metadata']['formula_sha256'],formula_load_count=1,
            effective_address_space_limit=address_limit,effective_cpu_limit=cpu_limit)
        sender.send(dict(event='loaded',identity=identity,load_seconds=time.monotonic()-started,
            solver_stats=_usage()))
        result = None
        for index,(seconds,conflicts) in enumerate(zip(stages,conflict_limits)):
            stage_started = time.monotonic()
            # These are documented per-call limits. No clause reload, Solver
            # reconstruction, option mutation or formula mutation occurs here.
            status,assignment = solver.solve(assumptions=assumptions,time_limit=seconds,
                confl_limit=conflicts)
            label = 'SAT' if status is True else 'LOCAL_UNSAT' if status is False else 'UNKNOWN'
            progress = dict(event='slice_complete',index=index,status=label,
                requested_seconds=seconds,conflict_limit=conflicts,
                elapsed_seconds=time.monotonic()-stage_started,
                worker_elapsed_seconds=time.monotonic()-started,identity=identity,
                solver_stats=_usage())
            if status is not None:
                result = dict(status=label,assignment=list(assignment) if status else None,
                    assumption_core=solver.get_conflict() if status is False and assumptions else None,
                    identity=identity,solver_stats=_usage())
                # Persist the complete terminal model before announcing it.
                # A parent deadline must never turn a visible SAT event into
                # an unavailable partial assignment.
                _publish(result_path,result)
            sender.send(progress)
            if status is not None:
                break
        if result is None:
            result = dict(status='UNKNOWN',reason='all cooperative solver slices returned UNKNOWN',
                identity=identity,solver_stats=_usage())
    except Exception as exc:
        result = dict(status='ERROR',error=f'{type(exc).__name__}: {exc}')
    try:
        _publish(result_path,result)
        sender.send(dict(event='worker_result_ready',status=result['status']))
    finally:
        sender.close()


def _entry(*args):
    # Reset inherited campaign stop handlers before even a patched worker.
    signal.signal(signal.SIGTERM,signal.SIG_DFL)
    signal.signal(signal.SIGINT,signal.SIG_DFL)
    _worker(*args)


def solve_staged(problem,stages=(180,720,2700),*,wall_seconds=None,
                 conflict_limits=1000000000,memory_mb=1536,assumptions=(),options=None,
                 checkpoint_path=None,log_path=None,cancelled=None,on_progress=None):
    stages = list(stages)
    wall_seconds = sum(stages)+30 if wall_seconds is None else wall_seconds
    if isinstance(conflict_limits,int):
        conflict_limits = [conflict_limits]*len(stages)
    else:
        conflict_limits = list(conflict_limits)
    if (not stages or any(type(v) not in (float,int) or not math.isfinite(v) or v<=0 for v in stages)
            or not math.isfinite(wall_seconds) or wall_seconds<=0
            or len(conflict_limits)!=len(stages)
            or any(type(v) is not int or v<0 for v in conflict_limits)
            or type(memory_mb) is not int or not 128<=memory_mb<=2048):
        raise ValueError('invalid persistent solve resource bounds')
    assumptions = list(assumptions)
    if any(type(v) is not int or not 1<=abs(v)<=problem['nv'] for v in assumptions):
        raise ValueError('invalid assumptions')
    options = {} if options is None else dict(options)
    if any(not isinstance(k,str) or not isinstance(v,str) for k,v in options.items()):
        raise ValueError('solver options must map strings to strings')
    context = mp.get_context('fork')
    receiver,sender = context.Pipe(duplex=False)
    started = time.monotonic()
    history,events = [],[]
    result = None
    identity = None
    def checkpoint(state):
        if checkpoint_path:
            _publish(checkpoint_path,dict(state=state,formula_sha256=problem['metadata']['formula_sha256'],
                assumptions=assumptions,stages=stages,conflict_limits=conflict_limits,
                elapsed_seconds=time.monotonic()-started,identity=identity,
                slice_history=history,worker_events=events,
                saved_solver_internal_state=False,
                relaunch_policy='Rebuild a fresh solver from immutable formula/assumptions; completed metadata is not a learned-clause checkpoint.'))
    with tempfile.TemporaryDirectory(prefix='mmsearch-persistent42sat-') as directory:
        result_path = Path(directory)/'worker.result.json'
        child = context.Process(target=_entry,args=(problem,stages,conflict_limits,memory_mb,
            assumptions,options,str(log_path) if log_path else None,str(result_path),sender))
        child.start()
        sender.close()
        try:
            checkpoint('running')
            next_heartbeat = time.monotonic()+10
            while result is None:
                left = wall_seconds-(time.monotonic()-started)
                if left<=0 or (cancelled is not None and cancelled()):
                    result = dict(status='UNKNOWN',reason='parent hard wall limit or campaign stop signal')
                    break
                if receiver.poll(min(left,.2)):
                    try:
                        event = receiver.recv()
                    except (EOFError,OSError) as exc:
                        result = dict(status='ERROR',error=f'worker exited before complete result: {exc}')
                        break
                    events.append(event)
                    if event['event']=='loaded':
                        identity = event['identity']
                    elif event['event']=='slice_complete':
                        if event['identity']!=identity:
                            raise AssertionError('solver identity changed between cooperative slices')
                        history.append(event)
                        if event['status'] in ['SAT','LOCAL_UNSAT']:
                            result = json.loads(result_path.read_text())
                    elif event['event']=='worker_result_ready':
                        result = json.loads(result_path.read_text())
                    if on_progress is not None:
                        on_progress(event)
                    checkpoint('running' if result is None else result['status'])
                if time.monotonic()>=next_heartbeat:
                    checkpoint('running')
                    next_heartbeat = time.monotonic()+10
        finally:
            child.join(timeout=.05)
            if child.is_alive():
                child.terminate()
            child.join(timeout=.2)
            if child.is_alive():
                child.kill()
                child.join()
            receiver.close()
    assignment = result.pop('assignment',None)
    result.update(elapsed_seconds=time.monotonic()-started,wall_seconds=wall_seconds,
        stages=stages,conflict_limits=conflict_limits,memory_mb=memory_mb,threads=1,
        assumptions=assumptions,solver_options=options,slice_history=history,
        worker_events=events,worker_pid=child.pid,worker_exitcode=child.exitcode,
        worker_reaped=not child.is_alive(),formula_load_count=1 if identity else 0,
        formula_sha256=problem['metadata']['formula_sha256'],scope=problem['metadata']['scope'],
        persistent_within_worker=True,saved_solver_internal_state=False,
        relaunch_policy='Formula/assumptions replay with a fresh solver, not internal-state resume')
    if result['status']=='SAT':
        candidate,verification = validate_decode(problem,assignment,assumptions)
        result.update(candidate=candidate,verification=verification,complete_assignment=assignment)
    checkpoint(result['status'])
    return result
