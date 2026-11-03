"""Bounded frozen affine-slice portfolio with fixed-source positive controls."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import signal
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.two_color_affine_sat42 import solve,quotient_certificate
from mmsearch.recombine import digest
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=480);p.add_argument('--query-seconds',type=float,default=20)
    p.add_argument('--control-seconds',type=float,default=3);p.add_argument('--memory-mb',type=int,default=1536)
    p.add_argument('--conflicts',type=int,default=100000000);p.add_argument('--seed',type=int,default=424601)
    p.add_argument('--deadline-utc');p.add_argument('--controls-only',action='store_true');p.add_argument('--prepare-only',action='store_true')
    p.add_argument('--case-id',action='append')
    args=p.parse_args();b=args.bundle.resolve();out=args.output_dir.resolve()
    if not 0<args.control_seconds<=args.seconds or not 0<args.query_seconds<=args.seconds or not 128<=args.memory_mb<=2048 or args.conflicts<1:
        p.error('invalid resource limits')
    sys.path.insert(0,str(b/'deps'))
    out.mkdir(parents=True,exist_ok=False);started=time.monotonic();stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    cutoff=datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00')).timestamp() if args.deadline_utc else float('inf')
    def remaining():return max(0,min(args.seconds-(time.monotonic()-started),cutoff-time.time())-1)
    plan=read_json((b/'portfolio.json').read_bytes())
    for name,expected in plan['files'].items():
        if hashlib.sha256((b/name).read_bytes()).hexdigest()!=expected:raise ValueError('frozen formula/runtime binding mismatch: '+name)
    cases=[case for case in plan['cases'] if args.case_id is None or case['id'] in args.case_id]
    if not cases or (args.case_id and set(args.case_id)!={case['id'] for case in cases}):raise ValueError('invalid portfolio subset')
    config=dict(bundle=str(b),case_ids=[case['id'] for case in cases],seconds=args.seconds,query_seconds=args.query_seconds,
        control_seconds=args.control_seconds,memory_mb=args.memory_mb,conflicts=args.conflicts,seed=args.seed,
        deadline_utc=args.deadline_utc,controls_only=args.controls_only,prepare_only=args.prepare_only,
        portfolio_sha256=hashlib.sha256((b/'portfolio.json').read_bytes()).hexdigest(),threads=1,
        checkpoint_policy='Frozen formulas and assumptions only; solver rebuilt for every attempt, no internal learned-clause resume.')
    freeze(out/'config.json',json_bytes(config));results=[];winner=False;target_queries=0;control_cache={}
    def record(prefix,result):
        result=dict(result)
        for key,suffix in (('candidate','candidate'),('complete_assignment','model')):
            value=result.pop(key,None)
            if value is not None:freeze(prefix.with_name(prefix.name+'.'+suffix+'.json'),json_bytes(value))
        freeze(prefix.with_name(prefix.name+'.result.json'),json_bytes(result));return result
    for number,case in enumerate(cases):
        directory=out/case['id'];directory.mkdir()
        problems={kind:read_json((b/case[kind]).read_bytes()) for kind in ('control','target')}
        for kind,problem in problems.items():
            expected=digest(dict(nv=problem['nv'],clauses=problem['clauses'],xors=problem['xors']))
            if expected!=problem['metadata']['formula_sha256']:raise ValueError('formula canonical checksum mismatch')
            certificate=quotient_certificate(problem['matrices'],problem['neutral_columns'])
            if certificate!=problem['quotient_certificate'] or certificate['quotient_syndrome_rank']!=2:
                raise ValueError('monochrome omission lacks an exact rank2 quotient certificate')
        if args.prepare_only:continue
        if stopped or remaining()<=.05:break
        assumptions=read_json((b/case['control_assumptions']).read_bytes())
        options={'seed':str(args.seed+number)}
        if case['space_id'] not in control_cache:
            control=solve(problems['control'],seconds=min(args.control_seconds,remaining()),conflicts=args.conflicts,
                memory_mb=args.memory_mb,assumptions=assumptions,options=options,log_path=directory/'control.solver.log',cancelled=lambda:stopped)
            control=record(directory/'control',control)
            control_cache[case['space_id']]=control
        else:
            control=control_cache[case['space_id']]
            freeze(directory/'control-reused.json',json_bytes(dict(space_id=case['space_id'],
                formula_sha256=problems['control']['metadata']['formula_sha256'],status=control['status'])))
        if control['status']!='SAT' or control['verification']['rank']!=93 or control['verification']['exact_entries_checked']!=15625:
            results.append(dict(case_id=case['id'],status='ERROR',reason='fixed original-factor positive control failed',control=control));break
        if args.controls_only:
            results.append(dict(case_id=case['id'],status='CONTROL_SAT',target_dispatched=False,control=control));continue
        if stopped or remaining()<=.05:break
        target_queries+=1;problem=problems['target']
        result=solve(problem,seconds=min(args.query_seconds,remaining()),conflicts=args.conflicts,memory_mb=args.memory_mb,
                  options=options,log_path=directory/'target.solver.log',cancelled=lambda:stopped)
        candidate=result.get('candidate');checked=result.get('verification')
        result=record(directory/'target',result)
        results.append(dict(case_id=case['id'],status=result['status'],formula_sha256=problem['metadata']['formula_sha256'],
            family_sha256=problem['metadata']['family_sha256'],free_axis=problem['free_axis'],palette=problem['palette'],profile=problem['profile'],
            source_sha256=case['source_sha256'],scope=problem['metadata']['scope'],target=result,control=control))
        if result['status']=='SAT':
            if not checked['valid'] or checked['rank']>92 or checked['exact_entries_checked']!=15625:raise ValueError('target failed independent full5x5 verification')
            freeze(out/'WINNER.json',json_bytes(candidate));freeze(out/'WINNER.verification.json',json_bytes(checked));winner=True;break
        if result['status']=='ERROR':break
    if winner:status='VERIFIED_TARGET'
    elif args.prepare_only:status='PREPARED'
    elif any(result['status']=='ERROR' for result in results):status='ERROR'
    elif args.controls_only and len(results)==len(cases):status='CONTROLS_PASSED'
    elif len(results)==len(cases) and all(result['status']=='TWO_COLOR_PROFILE_UNSAT' for result in results):status='TWO_COLOR_PORTFOLIO_UNSAT'
    else:status='UNKNOWN'
    summary=dict(status=status,winner=winner,cases=results,planned_cases=len(cases),target_queries_dispatched=target_queries,positive_control_spaces=len(control_cache),
        elapsed_seconds=time.monotonic()-started,scope='Only the recorded source/free-axis/two-color spaces and fixed color profiles; no global rank92 nonexistence claim.',
        solver_threads=1,memory_mb=args.memory_mb)
    freeze(out/'summary.json',json_bytes(summary));print(json.dumps(summary,sort_keys=True));return 2 if status=='ERROR' else 0


if __name__=='__main__':raise SystemExit(main())
