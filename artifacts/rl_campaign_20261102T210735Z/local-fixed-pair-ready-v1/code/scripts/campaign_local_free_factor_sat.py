"""Bounded local repairs using assumptions on an unchanged full tensor SAT.

Main campaign: F2 5x5, rank <=92, full WU pair dictionary and exact KM93 baseline.
No SAT formula omits a global tensor equation. Local UNSAT is conditional on
fixing every group outside its explicitly recorded free neighborhood.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import gc
import hashlib
import json
import math
from pathlib import Path
import signal
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from mmsearch.free_factor_sat import (audit, build_problem, build_system, estimate_formula, solve)
from mmsearch.local_free_factor_sat import checked_circuits, local_assumptions, local_bound, neighborhoods
from mmsearch.recombine import digest, save
from mmsearch.verify import verify_candidate
from mmsearch.xor_sat import write_problem


def freeze(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(payload)
    path.chmod(0o444)
    return path


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def freeze_json(path, value):
    return freeze(path, json_bytes(value))


def freeze_code(root):
    files = ['scripts/campaign_local_free_factor_sat.py', 'mmsearch/local_free_factor_sat.py',
        'mmsearch/free_factor_sat.py', 'mmsearch/recombine.py', 'mmsearch/recombine_sat.py',
        'mmsearch/verify.py', 'mmsearch/xor_sat.py', 'mmsearch/sat.py',
        'mmsearch/sat_neighborhoods.py', 'mmsearch/compact_sat.py', 'mmsearch/tensor.py',
        'mmsearch/__init__.py']
    result = {}
    for relative in files:
        payload = (REPO/relative).read_bytes()
        freeze(root/'code'/relative, payload)
        result[relative] = hashlib.sha256(payload).hexdigest()
    return result


def freeze_problem(problem, prefix):
    write_problem(problem, prefix)
    files = {}
    for suffix in ('.cnf','.map.json'):
        path = Path(prefix).with_suffix(suffix)
        files[path.name] = dict(bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        path.chmod(0o444)
    freeze_json(Path(prefix).with_suffix('.files.json'),files)


def save_result(root, stem, result, *, target=False):
    result = dict(result)
    candidate = result.pop('candidate', None)
    assignment = result.pop('complete_assignment', None)
    if candidate is not None:
        report = verify_candidate(candidate, random_trials=0)
        if not report['valid'] or report['exact_entries_checked'] != 15625:
            raise AssertionError('local SAT candidate failed independent full 5x5 verification')
        freeze_json(root/(stem+'.candidate.json'), candidate)
        freeze_json(root/(stem+'.verification.json'), report)
        if target:
            if report['rank'] > 92:
                raise AssertionError('target solver returned rank above 92')
            # Exclusive first certificate; later calls never overwrite this artifact.
            if not (root/'WINNER.json').exists():
                freeze_json(root/'WINNER.json', candidate)
                freeze_json(root/'WINNER.verification.json', report)
                freeze(root/'WINNER.verify.py', (REPO/'mmsearch/verify.py').read_bytes())
    if assignment is not None:
        freeze_json(root/(stem+'.model.json'), dict(assignment=assignment,
            formula_sha256=result['formula_sha256'], assumptions_sha256=digest(result['assumptions']),
            layout='index0 unused; indices1..nv complete Boolean values'))
    freeze_json(root/(stem+'.result.json'), result)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dictionary', type=Path, required=True)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--circuits', type=Path, required=True)
    p.add_argument('--prepared-system', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--seconds', type=float, default=600)
    p.add_argument('--deadline-utc', default='2026-11-03T03:07:35Z')
    p.add_argument('--control-seconds', type=float, default=10)
    p.add_argument('--query-seconds', type=float, nargs='+', default=[5, 10, 15])
    p.add_argument('--memory-mb', type=int, default=1536)
    p.add_argument('--max-formula-mb', type=float, default=384)
    p.add_argument('--conflicts', type=int, default=10000000)
    p.add_argument('--seed', type=int, default=271828)
    p.add_argument('--families', type=int, default=32)
    p.add_argument('--max-groups', type=int, default=128)
    p.add_argument('--prepare-only', action='store_true', help='no formulas or solver queries')
    p.add_argument('--control-only', action='store_true', help='one rank93 control, build target once, no target query')
    args = p.parse_args(argv)
    if (any(not math.isfinite(v) or v <= 0 for v in [args.seconds,args.control_seconds,
            args.max_formula_mb,*args.query_seconds]) or not args.query_seconds
            or any(v > 15 for v in args.query_seconds) or args.memory_mb != 1536
            or not 1 <= args.families <= 256 or not 1 <= args.max_groups <= 128 or args.conflicts < 1
            or (args.prepare_only and args.control_only)):
        p.error('invalid bounds; memory must be 1536MiB, queries <=15s, groups <=128')
    try:
        absolute = datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00'))
        if absolute.tzinfo is None:
            raise ValueError('timezone required')
        absolute = absolute.timestamp()
    except ValueError:
        p.error('deadline requires an ISO timestamp with a timezone')
    started = time.monotonic()
    deadline = started+min(args.seconds, max(0,absolute-time.time()))
    root = args.output_dir
    root.mkdir(parents=True, exist_ok=False)
    stopped = False
    def stop(signum, frame):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    def remaining():
        return max(0,min(deadline-time.monotonic(),absolute-time.time())-2)
    provenance = dict(code_sha256=freeze_code(root), inputs=[], seed=args.seed,
        limits=dict(total_seconds=args.seconds, query_seconds=args.query_seconds,
            memory_mb=args.memory_mb, max_formula_mb=args.max_formula_mb,
            control_seconds=args.control_seconds, conflicts=args.conflicts, threads=1,
            deadline_utc=args.deadline_utc, max_groups=args.max_groups, families=args.families))
    def input_value(path, name):
        payload = path.read_bytes()
        snapshot = freeze(root/'inputs'/name, payload)
        provenance['inputs'].append(dict(path=str(path.resolve()), snapshot=str(snapshot.resolve()),
            bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()))
        return json.loads(payload)
    counts = Counter()
    target_builds = 0
    def finish(status, **extra):
        value = dict(status=status, elapsed_seconds=time.monotonic()-started,
            rank_bound=92, target_problem_builds=target_builds, counts=dict(counts),
            stopped_by_signal=stopped, **extra)
        freeze_json(root/'result.json', value)
        print(json.dumps(value, sort_keys=True), flush=True)
        return 2 if status == 'ERROR' else 0
    try:
        dictionary = input_value(args.dictionary,'dictionary.json')
        baseline = input_value(args.baseline,'baseline.json')
        circuits = input_value(args.circuits,'circuits.json')
        snapshot = input_value(args.prepared_system,'prepared-system.json')
        freeze_json(root/'provenance.json', provenance)
        system = build_system(dictionary,5,'wu',baseline,provenance)
        if (system['metadata']['baseline']['merged_rank'] != 93
                or system['pairs'] != tuple(tuple(pair) for pair in snapshot['pairs'])
                or system['coefficients'] != snapshot['coefficients']
                or system['right_sides'] != snapshot['right_sides']
                or system['baseline_vectors'] != snapshot['baseline_vectors']):
            raise ValueError('prepared system differs from full WU system or baseline is not rank93')
        if len(system['pairs']) != 1536 or len(circuits) != 9262:
            raise ValueError('campaign requires full1536-pair closure and9262 prepared circuits')
        supports = checked_circuits(system,circuits)
        plan = list(neighborhoods(system,supports,seed=args.seed,families=args.families,max_groups=args.max_groups))
        if not plan:
            raise ValueError('empty local repair plan')
        freeze_json(root/'system.audit.json',audit(system))
        freeze_json(root/'neighborhoods.json',plan)
        freeze_json(root/'manifest.json',dict(system=system['metadata'],provenance=provenance,
            circuit_count=len(circuits),neighborhood_count=len(plan),
            target_memory_estimate=estimate_formula(system,92),
            semantics='All full PW=Y equations retained; all25 x bits and y outside free groups fixed to baseline; local UNSAT only for those assumptions.'))
        if args.prepare_only:
            preflight = []
            for index, item in enumerate(plan):
                bound = local_bound(system,item['free_groups'],92)
                freeze_json(root/'bounds'/f'{index:04d}.json',bound)
                counts[bound['status']] += 1
                preflight.append(dict(index=index,lower_bound=bound['lower_bound'],
                    free_group_count=item['free_group_count'],circuit_count=item['circuit_count'],
                    local_nullity=bound['local_nullity'],status=bound['status']))
            freeze_json(root/'preflight.json',preflight)
            return finish('PREPARED',solver_queries=0)
        if remaining() <= 0 or stopped:
            return finish('UNKNOWN',reason='deadline or stop before solver control')
        # Exactly the first target neighborhood's assumptions are used at rank93.
        initial_assumptions = local_assumptions(system,plan[0]['free_groups'])
        control_problem = build_problem(system,93,args.max_formula_mb)
        freeze_problem(control_problem,root/'control.problem')
        if remaining() <= 0 or stopped:
            return finish('UNKNOWN',reason='deadline or stop after control encoding')
        control = solve(control_problem,seconds=min(args.control_seconds,remaining()),
            conflicts=args.conflicts,memory_mb=args.memory_mb,assumptions=initial_assumptions)
        control = save_result(root,'control',control)
        if control['status'] != 'SAT':
            return finish('ERROR',reason='known baseline rank93 local feasibility control failed',
                control_status=control['status'])
        del control_problem
        gc.collect()
        if remaining() <= 0 or stopped:
            return finish('UNKNOWN',reason='control/setup exhausted total budget',control_status='SAT')
        # One target object for every fork; the mathematical encoder is unchanged.
        problem = build_problem(system,92,args.max_formula_mb)
        target_builds += 1
        freeze_problem(problem,root/'target.problem')
        if args.control_only:
            return finish('CONTROL_PASSED',control_status='SAT',target_queries=0,
                formula_sha256=problem['metadata']['formula_sha256'])
        terminal = {}
        queries = 0
        # Broader neighborhoods follow smaller ones. Only UNKNOWN queries retry
        # with the larger time limits; a proved local UNSAT is never retried.
        for pass_index, pass_seconds in enumerate(args.query_seconds):
            for index,item in enumerate(plan):
                if remaining() <= 0 or stopped:
                    return finish('UNKNOWN',reason='total budget, deadline, or signal',
                        control_status='SAT',solver_queries=queries)
                if index in terminal:
                    continue
                bound_path = root/'bounds'/f'{index:04d}.json'
                if pass_index == 0:
                    bound = local_bound(system,item['free_groups'],92)
                    freeze_json(bound_path,bound)
                else:
                    bound = json.loads(bound_path.read_text())
                if bound['status'] == 'LOCAL_UNSAT_BOUND':
                    terminal[index] = 'LOCAL_UNSAT_BOUND'
                    counts['LOCAL_UNSAT_BOUND'] += 1
                    continue
                assumptions = local_assumptions(system,item['free_groups'])
                size_stage = min((item['circuit_count'].bit_length()-1)//2,
                                 len(args.query_seconds)-1)
                # Default initial budgets for 1/2/4/8/16 circuits: 5/5/10/10/15s.
                # Later passes increase budgets only for unresolved neighborhoods.
                query_seconds = max(pass_seconds,args.query_seconds[size_stage])
                seconds = min(query_seconds,remaining())
                stem = f'queries/p{pass_index}-{index:04d}'
                record = dict(neighborhood_index=index,neighborhood=item,pass_index=pass_index,
                    assumptions_sha256=digest(assumptions),assumption_count=len(assumptions),
                    fixed_vector_bits=25*(len(system['pairs'])-len(item['free_groups'])),
                    query_seconds=seconds,bound_path=str(bound_path),formula_sha256=problem['metadata']['formula_sha256'],
                    local_scope=bound['scope'])
                freeze_json(root/(stem+'.manifest.json'),record)
                result = solve(problem,seconds=seconds,conflicts=args.conflicts,
                    memory_mb=args.memory_mb,assumptions=assumptions)
                queries += 1
                if result['status'] == 'UNSAT':
                    result['status'] = 'LOCAL_UNSAT'
                result.update(neighborhood_index=index,local_scope=bound['scope'])
                result = save_result(root,stem,result,target=result['status']=='SAT')
                counts[result['status']] += 1
                save(root/'latest.json',dict(query=record,result=result,counts=dict(counts)))
                if result['status'] == 'SAT':
                    return finish('SAT',control_status='SAT',solver_queries=queries,
                        winner='WINNER.json',verification=result['verification'])
                if result['status'] == 'ERROR':
                    return finish('ERROR',control_status='SAT',solver_queries=queries,error=result.get('error'))
                if result['status'] == 'LOCAL_UNSAT':
                    terminal[index] = 'LOCAL_UNSAT'
        return finish('LOCAL_UNSAT' if len(terminal)==len(plan) else 'UNKNOWN',
            control_status='SAT',solver_queries=queries,
            scope='Only the enumerated neighborhoods under their recorded outside-baseline assumptions; no global UNSAT claim.')
    except Exception as exc:
        return finish('ERROR',error=f'{type(exc).__name__}: {exc}')


if __name__ == '__main__':
    raise SystemExit(main())
