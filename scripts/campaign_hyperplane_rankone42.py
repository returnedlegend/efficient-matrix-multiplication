"""Bounded fresh-oracle portfolio for fixed-pair hyperplane rank-one spans."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import signal
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mmsearch import hyperplane_rankone42 as hp
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json

TERMINAL={'WINNER','ERROR','HYPERPLANE_SPAN_UNSAT','SPANNED_CONTROL'}


def atomic(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.tmp');tmp.write_bytes(json_bytes(value));tmp.replace(path)


def checkpoint(output,family,state):
    value=dict(state,format='hyperplane-rankone42-v1',family_sha256=family['family_sha256'])
    value['checkpoint_sha256']=hp.digest(value);atomic(Path(output)/'checkpoint.json',value)


def load_state(output,family):
    path=Path(output)/'checkpoint.json'
    if not path.exists():return dict(status='ACTIVE',points=[],oracle_attempts=0,history=[])
    state=read_json(path.read_bytes());claimed=state.pop('checkpoint_sha256',None)
    if claimed!=hp.digest(state) or state.get('format')!='hyperplane-rankone42-v1' or state.get('family_sha256')!=family['family_sha256']:
        raise ValueError('corrupt checkpoint digest/format/family')
    hp.state_vectors(family,state['points'])
    if state['status']not in TERMINAL|{'ACTIVE','UNKNOWN','POINT_CAP'}:raise ValueError('invalid checkpoint status')
    coefficients,_=hp.state_vectors(family,state['points'])
    if state['status']in {'WINNER','SPANNED_CONTROL'}:
        candidate,report=hp.decode_containment(family,state['points'])
        if state['status']=='WINNER':
            winner=Path(output)/'WINNER.json'
            if not winner.exists() or read_json(winner.read_bytes())!=candidate:raise ValueError('terminal winner certificate mismatch')
            if read_json((Path(output)/'WINNER.verification.json').read_bytes())!=report:raise ValueError('terminal winner report mismatch')
    if state['status']=='HYPERPLANE_SPAN_UNSAT' and hp.contained(family,coefficients):
        raise ValueError('UNSAT checkpoint incorrectly excludes a contained target')
    if state['status']=='HYPERPLANE_SPAN_UNSAT':
        if not state['history'] or state['history'][-1]['status']!='HYPERPLANE_SPAN_UNSAT':
            raise ValueError('terminal UNSAT lacks oracle provenance')
        result=read_json((Path(output)/f"oracle-{state['history'][-1]['index']:03d}/result.json").read_bytes())
        if result.get('status')!='HYPERPLANE_SPAN_UNSAT':raise ValueError('terminal UNSAT result mismatch')
        expected=hp.build_oracle(family,state['points'])['metadata']['formula_sha256']
        problem=read_json((Path(output)/f"oracle-{state['history'][-1]['index']:03d}/problem.json").read_bytes())
        actual=hp.digest({key:problem[key]for key in ['nv','clauses','xors']})
        if (state['history'][-1]['formula_sha256']!=expected or result.get('formula_sha256')!=expected
                or problem['metadata']['formula_sha256']!=expected or actual!=expected):
            raise ValueError('terminal UNSAT formula/U provenance mismatch')
    return {k:v for k,v in state.items()if k not in {'format','family_sha256'}}


def run_family(family,output,*,max_points=3,oracle_seconds=20,conflicts=10000000,memory_mb=1536,
               deadline=None,seed=0,oracle=hp.solve_oracle,cancelled=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if not (output/'family.json').exists():freeze(output/'family.json',json_bytes(family))
    elif read_json((output/'family.json').read_bytes())!=family:raise ValueError('immutable family mismatch')
    state=load_state(output,family)
    if state['status']in TERMINAL:return state
    def save():checkpoint(output,family,state)
    try:
        while True:
            coefficients,_=hp.state_vectors(family,state['points'])
            if hp.contained(family,coefficients):
                candidate,report=hp.decode_containment(family,state['points'])
                if family['source']['kind']=='full-matrix-multiplication':
                    freeze(output/'WINNER.json',json_bytes(candidate));freeze(output/'WINNER.verification.json',json_bytes(report))
                    freeze(output/'WINNER.sha256',(hashlib.sha256(json_bytes(candidate)).hexdigest()+'  WINNER.json\n').encode())
                    freeze(output/'WINNER.verify.py',(ROOT/'mmsearch/verify.py').read_bytes());state['status']='WINNER'
                else:
                    freeze(output/'SPANNED_CONTROL.json',json_bytes(dict(witness=candidate,verification=report)));state['status']='SPANNED_CONTROL'
                save();return state
            if len(state['points'])>=max_points:
                state['status']='POINT_CAP';save();return state
            left=math.inf if deadline is None else deadline-time.monotonic()
            if left<=.1 or (cancelled and cancelled()):
                state['status']='UNKNOWN';state['reason']='campaign stop/deadline before oracle';save();return state
            problem=hp.build_oracle(family,state['points']);index=state['oracle_attempts']
            folder=output/f'oracle-{index:03d}';folder.mkdir(exist_ok=False)
            freeze(folder/'problem.json',json_bytes(problem))
            result=oracle(problem,seconds=min(oracle_seconds,left),conflicts=conflicts,memory_mb=memory_mb,
                          options={'seed':str(seed+index)},log_path=folder/'solver.log',cancelled=cancelled)
            freeze(folder/'result.json',json_bytes(result));state['oracle_attempts']+=1
            state['history'].append(dict(index=index,status=result['status'],formula_sha256=problem['metadata']['formula_sha256'],
                   requested_seed=result.get('requested_seed'),solver_seed=result.get('solver_seed')))
            if result['status']=='SAT':
                point=result['point'];hp.validate_point(family,coefficients,point)
                state['points'].append(point);state['status']='ACTIVE';save()
            elif result['status']=='HYPERPLANE_SPAN_UNSAT':
                state['status']='HYPERPLANE_SPAN_UNSAT';state['scope']=family['scope'];save();return state
            elif result['status']=='UNKNOWN':
                state['status']='UNKNOWN';state['reason']=result.get('reason','bounded oracle UNKNOWN');save();return state
            else:
                state['status']='ERROR';state['error']=result.get('error',str(result));save();return state
    except Exception as exc:
        state['status']='ERROR';state['error']=f'{type(exc).__name__}: {exc}';save();raise


def family_from_spec(spec):
    source=Path(spec['source_path']);raw=source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=spec['source_sha256']:raise ValueError('frozen source checksum mismatch')
    family=hp.build_family(hp.prepare_source(read_json(raw),spec['free_axis']),spec['lambda_mask'])
    if family['physical_H_sha256']!=spec['physical_H_sha256']:raise ValueError('physical hyperplane checksum mismatch')
    return family


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=1200);p.add_argument('--oracle-seconds',type=float,default=20)
    p.add_argument('--max-points',type=int,default=3);p.add_argument('--conflicts',type=int,default=10000000)
    p.add_argument('--memory-mb',type=int,default=1536);p.add_argument('--seed',type=int,default=2026110342905)
    p.add_argument('--prepare-only',action='store_true');args=p.parse_args()
    if (not math.isfinite(args.seconds)or args.seconds<=0 or not math.isfinite(args.oracle_seconds)or args.oracle_seconds<=0
            or not 1<=args.max_points<=3 or not 128<=args.memory_mb<=1536 or args.seed<0):p.error('invalid bounded portfolio settings')
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True);deadline=time.monotonic()+args.seconds
    stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);results=[]
    for index,path in enumerate(sorted(args.cases_dir.glob('case-*.json'))):
        if stopped or time.monotonic()>=deadline:break
        spec=read_json(path.read_bytes());family=family_from_spec(spec);folder=out/path.stem
        if args.prepare_only:
            folder.mkdir(parents=True,exist_ok=False);freeze(folder/'first_problem.json',json_bytes(hp.build_oracle(family)))
            results.append(dict(case=path.name,status='PREPARED_NO_QUERY'));continue
        state=run_family(family,folder,max_points=args.max_points,oracle_seconds=args.oracle_seconds,
                 conflicts=args.conflicts,memory_mb=args.memory_mb,deadline=deadline,seed=args.seed+index*1009,
                 cancelled=lambda:stopped)
        results.append(dict(case=path.name,status=state['status'],new_points=len(state['points']),
                   oracle_attempts=state['oracle_attempts'],requested_case_seed=args.seed+index*1009,
                   solver_seeds=[row.get('solver_seed')for row in state['history']],
                   error=state.get('error'),scope=family['scope']))
        atomic(out/'summary.json',portfolio_summary(results,state['status']=='WINNER',stopped,args.prepare_only))
        if state['status']=='WINNER':
            for name in ['WINNER.json','WINNER.verification.json','WINNER.sha256','WINNER.verify.py']:
                freeze(out/name,(folder/name).read_bytes())
            break
    summary=portfolio_summary(results,(out/'WINNER.json').exists(),stopped,args.prepare_only)
    atomic(out/'summary.json',summary)
    return summary['exit_code']


def portfolio_summary(results,winner,stopped=False,prepare_only=False):
    counts={status:sum(row['status']==status for row in results)for status in sorted({row['status']for row in results})}
    errors=counts.get('ERROR',0)
    return dict(results=results,counts_by_status=counts,error_count=errors,
                hyperplane_only_unsat_count=counts.get('HYPERPLANE_SPAN_UNSAT',0),
                status='ERROR'if errors else 'WINNER'if winner else 'PREPARED_NO_QUERY'if prepare_only else 'STOPPED'if stopped else 'COMPLETE',
                winner=winner,stopped=stopped,exit_code=2 if errors else 0,
                no_learned_clause_serialization=True,
                seed_policy='requested nonnegative seed modulo2147483647; requested and solver seeds retained per oracle',
                error_scope='ERROR is execution failure, never a hyperplane or tensor-rank negative result.')


if __name__=='__main__':raise SystemExit(main())
