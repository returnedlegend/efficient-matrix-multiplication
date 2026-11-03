"""Prepare old-span point censuses; only n2 control queries are enabled here."""
import argparse
import hashlib
import math
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mmsearch import hyperplane_rankone42 as hp
from mmsearch import rankone_census42 as rc
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json
from scripts.campaign_hyperplane_rankone42 import atomic


def checkpoint(output,source,state):
    value=dict(state,format='old-span-rankone-census42-v1',source_identity=rc.source_identity(source))
    value['checkpoint_sha256']=hp.digest(value);atomic(Path(output)/'checkpoint.json',value)


def load_state(output,source,cap):
    path=Path(output)/'checkpoint.json'
    if not path.exists():return dict(status='PARTIAL',points=rc.initial_points(source),oracle_attempts=0,history=[],census_complete=False)
    state=read_json(path.read_bytes());sha=state.pop('checkpoint_sha256',None)
    if sha!=hp.digest(state)or state.get('format')!='old-span-rankone-census42-v1'or state.get('source_identity')!=rc.source_identity(source):
        raise ValueError('corrupt census checkpoint or source mismatch')
    rc.validate_points(source,state['points'],cap)
    if state['status']not in {'PARTIAL','UNKNOWN','POINT_CAP','CENSUS_COMPLETE','ERROR'}:raise ValueError('invalid census state')
    if state['census_complete']!=(state['status']=='CENSUS_COMPLETE'):raise ValueError('invalid census completeness flag')
    if state['census_complete']:
        if not state['history']or state['history'][-1]['status']!='CENSUS_COMPLETE_UNSAT':raise ValueError('missing complete-census UNSAT provenance')
        folder=Path(output)/f"oracle-{state['history'][-1]['index']:04d}"
        result=read_json((folder/'result.json').read_bytes());problem=read_json((folder/'problem.json').read_bytes())
        expected=rc.build_oracle(source,state['points'],cap)['metadata']['formula_sha256']
        if (result.get('status')!='CENSUS_COMPLETE_UNSAT'or result.get('formula_sha256')!=expected
                or hp.digest({k:problem[k]for k in ['nv','clauses','xors']})!=expected):
            raise ValueError('complete-census formula/point-block mismatch')
    return {k:v for k,v in state.items()if k not in {'format','source_identity'}}


def run_census(source,output,*,cap=4096,seconds=30,oracle_seconds=2,memory_mb=512,
               seed=2026110343201,max_queries=4096,closure_rounds=0,oracle=rc.solve_oracle):
    if not source['R']<=cap<=4096 or not 0<seconds<=1800 or not 0<oracle_seconds<=5 or memory_mb!=512:
        raise ValueError('unreviewed census prototype bounds')
    out=Path(output);out.mkdir(parents=True,exist_ok=True);state=load_state(out,source,cap)
    if state['status']in {'CENSUS_COMPLETE','ERROR'}:return state
    if state['status']=='POINT_CAP'and len(state['points'])>=cap:return state
    state['run_sequence']=state.get('run_sequence',0)+1
    if closure_rounds:
        state['points'],state['closure']=rc.common_factor_closure(source,state['points'],cap,closure_rounds)
        checkpoint(out,source,state)
    deadline=time.monotonic()+seconds;attempts=0
    while attempts<max_queries:
        if len(state['points'])>=cap:state['status']='POINT_CAP';break
        left=deadline-time.monotonic()
        if left<=.05:state['status']='UNKNOWN';break
        problem=rc.build_oracle(source,state['points'],cap);index=state['oracle_attempts'];folder=out/f'oracle-{index:04d}';folder.mkdir()
        freeze(folder/'problem.json',json_bytes(problem))
        result=oracle(problem,seconds=min(oracle_seconds,left),conflicts=10000000,memory_mb=memory_mb,
                      options={'seed':str(seed+index)},log_path=folder/'solver.log')
        freeze(folder/'result.json',json_bytes(result));state['oracle_attempts']+=1;attempts+=1
        state['history'].append(dict(index=index,status=result['status'],formula_sha256=problem['metadata']['formula_sha256'],
                                     requested_seed=result.get('requested_seed'),solver_seed=result.get('solver_seed')))
        if result['status']=='SAT':
            point=result['point'];rc.validate_point(source,point,{p['c']for p in state['points']})
            state['points'].append(point);state['status']='PARTIAL';checkpoint(out,source,state)
        elif result['status']=='CENSUS_COMPLETE_UNSAT':state['status']='CENSUS_COMPLETE';state['census_complete']=True;break
        elif result['status']=='UNKNOWN':state['status']='UNKNOWN';break
        else:state['status']='ERROR';state['error']=result.get('error','oracle execution failed');break
    checkpoint(out,source,state)
    freeze(out/f"summary-{state['run_sequence']:04d}-after-{state['oracle_attempts']:04d}.json",json_bytes(dict(status=state['status'],known_points=len(state['points']),
          census_complete=state['census_complete'],oracle_attempts=state['oracle_attempts'],scope='Only this old active-pair span S.')))
    return state


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--free-axis',type=int,choices=[0,1,2],default=2)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--prepare-only',action='store_true')
    p.add_argument('--small-control',action='store_true');p.add_argument('--cap',type=int,default=4096)
    p.add_argument('--closure-rounds',type=int,default=0);p.add_argument('--seconds',type=float,default=30)
    p.add_argument('--oracle-seconds',type=float,default=2);p.add_argument('--seed',type=int,default=2026110343201)
    a=p.parse_args();source=hp.prepare_source(read_json(a.source.read_bytes()),a.free_axis)
    if source['dimension']==5 and source['R']!=93:p.error('n5 preparation requires the reviewed rank93 source class')
    if not a.prepare_only and (not a.small_control or source['dimension']!=2):
        p.error('This prototype does not dispatch n5 SAT; use prepare-only pending root review.')
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    if a.prepare_only:
        points=rc.initial_points(source);closure=None
        if a.closure_rounds:points,closure=rc.common_factor_closure(source,points,a.cap,a.closure_rounds)
        problem=rc.build_oracle(source,points,a.cap)
        freeze(out/'prepared.json',json_bytes(problem));freeze(out/'points.json',json_bytes(points))
        freeze(out/'PREPARED.json',json_bytes(dict(status='PREPARED_NO_QUERY',known_points=len(points),closure=closure,
                  census_complete=False,production_queries=0,metadata=problem['metadata'])))
        return 0
    state=run_census(source,out,cap=a.cap,seconds=a.seconds,oracle_seconds=a.oracle_seconds,seed=a.seed,closure_rounds=a.closure_rounds)
    return 2 if state['status']=='ERROR'else 0


if __name__=='__main__':raise SystemExit(main())
