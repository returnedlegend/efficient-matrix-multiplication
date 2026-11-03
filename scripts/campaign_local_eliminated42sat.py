"""Prepare or run longer exact repairs for previously unresolved local SAT cases."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import signal
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from mmsearch.free_factor_sat import build_system
from mmsearch.local_eliminated42sat import baseline_assumptions,build_problem,solve,write_problem
from mmsearch.recombine import digest


def frozen_json(path,value):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
    path.chmod(0o444)


def save_result(root,stem,result):
    result = dict(result)
    for key,suffix in [('candidate','candidate'),('complete_assignment','model')]:
        value = result.pop(key,None)
        if value is not None:
            frozen_json(root/(stem+'.'+suffix+'.json'),value)
    frozen_json(root/(stem+'.result.json'),result)
    if result['status']=='SAT' and result['verification']['rank']<=92 and not (root/'WINNER.json').exists():
        candidate = json.loads((root/(stem+'.candidate.json')).read_text())
        frozen_json(root/'WINNER.json',candidate)
        frozen_json(root/'WINNER.verification.json',result['verification'])
    return result


def source_plan(previous,indices):
    plan = json.loads((previous/'neighborhoods.json').read_text())
    latest = {}
    for path in sorted((previous/'queries').glob('p*-*.result.json'),
            key=lambda p:(int(p.name.split('-')[0][1:]),p.name)):
        index = int(path.name.split('-')[1].split('.')[0])
        latest[index] = json.loads(path.read_text())['status']
    selected = sorted(i for i,status in latest.items() if status=='UNKNOWN') if indices is None else indices
    if not selected or len(set(selected)) != len(selected):
        raise ValueError('require distinct unresolved neighborhood indices')
    if any(not 0 <= i < len(plan) or latest.get(i) != 'UNKNOWN' for i in selected):
        raise ValueError('selected neighborhood did not end UNKNOWN in the previous run')
    return [dict(plan[i],previous_index=i,previous_status=latest[i]) for i in selected]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-run',required=True,type=Path)
    parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--indices',type=int,nargs='+')
    parser.add_argument('--query-seconds',type=float,nargs='+',default=[180,900,3600])
    parser.add_argument('--seconds',type=float,default=21600)
    parser.add_argument('--deadline-utc',default='2026-11-04T21:31:16Z')
    parser.add_argument('--memory-mb',type=int,default=1536)
    parser.add_argument('--max-formula-mb',type=float,default=128)
    parser.add_argument('--conflicts',type=int,default=1000000000)
    parser.add_argument('--control-seconds',type=float,default=5)
    parser.add_argument('--solver-options',default='{}',help='JSON dictionary of CMS string options')
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--controls-only',action='store_true')
    parser.add_argument('--resume',action='store_true',help='continue completed query schedule from frozen formula state; rebuild solver without internal state')
    args = parser.parse_args(argv)
    if (not args.query_seconds or any(not math.isfinite(v) or v<=0 for v in
            [args.seconds,args.control_seconds,args.max_formula_mb,*args.query_seconds])
            or not 128<=args.memory_mb<=2048 or args.conflicts<1
            or (args.prepare_only and args.controls_only)):
        parser.error('invalid bounds')
    absolute = datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00'))
    if absolute.tzinfo is None:
        parser.error('deadline must include timezone')
    absolute = absolute.timestamp()
    options = json.loads(args.solver_options)
    if not isinstance(options,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in options.items()):
        parser.error('solver options must map strings to strings')
    root = args.output_dir
    root.mkdir(parents=True,exist_ok=args.resume)
    started = time.monotonic()
    stopped = False
    def stop(signum,frame):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    def remaining():
        return max(0,min(args.seconds-(time.monotonic()-started),absolute-time.time())-2)
    files = ['scripts/campaign_local_eliminated42sat.py','mmsearch/local_eliminated42sat.py',
        'mmsearch/local_free_factor_sat.py','mmsearch/free_factor_sat.py','mmsearch/recombine.py',
        'mmsearch/recombine_sat.py','mmsearch/verify.py','mmsearch/tensor.py','mmsearch/__init__.py']
    hashes = {name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in files}
    config = dict(previous_run=str(args.previous_run.resolve()),indices=args.indices,
        query_seconds=args.query_seconds,memory_mb=args.memory_mb,max_formula_mb=args.max_formula_mb,
        conflicts=args.conflicts,control_seconds=args.control_seconds,solver_options=options,
        deadline_utc=args.deadline_utc,code_sha256=hashes)
    if args.resume:
        if json.loads((root/'config.json').read_text()) != config:
            raise ValueError('resume configuration/code differs from frozen preparation')
    else:
        frozen_json(root/'config.json',config)
        for name in files:
            target = root/'code'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((REPO/name).read_bytes())
            target.chmod(0o444)
    previous = args.previous_run
    inputs = {}
    for name in ['dictionary','baseline','prepared-system']:
        path = previous/'inputs'/f'{name}.json'
        inputs[name] = json.loads(path.read_text())
        if not args.resume:
            frozen_json(root/'inputs'/f'{name}.json',inputs[name])
    prepared = inputs['prepared-system']
    system = build_system(inputs['dictionary'],prepared['metadata']['dimension'],
        prepared['metadata']['orientation'],inputs['baseline'])
    if (system['pairs'] != tuple(tuple(x) for x in prepared['pairs'])
            or system['coefficients'] != prepared['coefficients']
            or system['right_sides'] != prepared['right_sides']
            or system['baseline_vectors'] != prepared['baseline_vectors']):
        raise AssertionError('rebuilt complete system differs from retained input')
    plan = source_plan(previous,args.indices)
    if args.resume:
        if json.loads((root/'plan.json').read_text()) != plan:
            raise ValueError('previous source selection changed since preparation')
    else:
        frozen_json(root/'plan.json',plan)
        frozen_json(root/'input-hashes.json',{k:digest(v) for k,v in inputs.items()})
        frozen_json(root/'selection-provenance.json',dict(
            selection='Only final UNKNOWN cases from previous run; no new random choices',
            previous_provenance=json.loads((previous/'provenance.json').read_text()),
            replay_policy='Original CNF/XOR state and assumptions, no internal solver checkpoint'))
    summaries = []
    terminal = {}
    for item in plan:
        index = item['previous_index']
        case = root/'cases'/f'{index:04d}'
        case.mkdir(parents=True,exist_ok=True)
        for rank,label in [(93,'control'),(92,'target')]:
            problem = build_problem(system,item['free_groups'],rank,
                max_formula_mb=args.max_formula_mb)
            audit = {k:v for k,v in problem.items() if k!='system'}
            audit_path = case/(label+'.formula.json')
            if audit_path.exists():
                if json.loads(audit_path.read_text()) != json.loads(json.dumps(audit)):
                    raise ValueError('rebuilt formula differs from frozen state')
            else:
                write_problem(problem,case/label)
                (case/(label+'.cnf')).chmod(0o444)
                frozen_json(audit_path,audit)
                frozen_json(case/(label+'.cnf.sha256.json'),dict(
                    sha256=hashlib.sha256((case/(label+'.cnf')).read_bytes()).hexdigest()))
            summaries.append(dict(index=index,kind=label,metadata=problem['metadata']))
            if args.prepare_only:
                continue
            if label=='control':
                result_path = case/'control.result.json'
                if result_path.exists():
                    result = json.loads(result_path.read_text())
                else:
                    if stopped or remaining()<=0:
                        return 0
                    result = solve(problem,seconds=min(args.control_seconds,remaining()),
                        conflicts=args.conflicts,memory_mb=args.memory_mb,
                        assumptions=baseline_assumptions(problem),options=options,
                        log_path=case/'control.solver.log',cancelled=lambda:stopped)
                    result = save_result(root,f'cases/{index:04d}/control',result)
                if result['status']!='SAT':
                    print(json.dumps(dict(status='ERROR',reason='positive baseline control failed',index=index,result=result)))
                    return 2
            elif not args.controls_only:
                # Each query is a reproducible fresh solver. Longer stages
                # proceed only when the previous stage remained UNKNOWN.
                for stage,seconds in enumerate(args.query_seconds):
                    stem = f'cases/{index:04d}/p{stage}'
                    result_path = root/(stem+'.result.json')
                    if result_path.exists():
                        result = json.loads(result_path.read_text())
                    else:
                        if stopped or remaining()<=0:
                            return 0
                        actual = min(seconds,remaining())
                        manifest_path = root/(stem+'.manifest.json')
                        if manifest_path.exists():
                            actual = min(actual,json.loads(manifest_path.read_text())['wall_seconds'])
                        else:
                            frozen_json(manifest_path,dict(formula_sha256=problem['metadata']['formula_sha256'],
                                assumptions=[],solver_options=options,wall_seconds=actual,
                                memory_mb=args.memory_mb,conflicts=args.conflicts))
                        log = root/(stem+'.solver.log')
                        # An interrupted solver can leave only its log. Preserve
                        # it and open a new attempt log with exclusive creation.
                        attempt = 0
                        while log.exists():
                            attempt += 1
                            log = root/(stem+f'.retry{attempt}.solver.log')
                        result = solve(problem,seconds=actual,conflicts=args.conflicts,
                            memory_mb=args.memory_mb,options=options,log_path=log,
                            cancelled=lambda:stopped)
                        result = save_result(root,stem,result)
                    print(json.dumps(dict(index=index,stage=stage,status=result['status'])),flush=True)
                    if result['status']!='UNKNOWN':
                        terminal[index] = result['status']
                        break
                if terminal.get(index) in ['SAT','ERROR']:
                    return 0 if terminal[index]=='SAT' else 2
    summary = dict(status='PREPARED' if args.prepare_only else 'CONTROLS_PASSED' if args.controls_only else
        'LOCAL_UNSAT' if len(terminal)==len(plan) else 'UNKNOWN',
        elapsed_seconds=time.monotonic()-started,formula_summaries=summaries,
        terminal=terminal,solver_resume=False,scope='Only the selected local neighborhoods; no unrestricted rank claim.')
    # Preparation/run reports are separate so a prepared directory can resume.
    report = root/('preparation.json' if args.prepare_only else 'controls.json' if args.controls_only else 'result.json')
    if not report.exists():
        frozen_json(report,summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='formula_summaries'}),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
