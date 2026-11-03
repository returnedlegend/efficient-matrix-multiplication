"""Bounded, checkpointed census and exact dictionary support inside twelve old spans."""
import argparse
from collections import Counter
import datetime as dt
import fcntl
import gzip
import hashlib
import json
from pathlib import Path
import resource
import signal
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mmsearch import hyperplane_rankone42 as hp,rankone_census42 as rc,old_span_support42 as support
from mmsearch.free_factor_sat import FormulaMemoryLimit
from scripts import campaign_hyperplane_rankone42 as base
from scripts.prototype_rankone_census42 import load_state,checkpoint
from scripts.campaign_hyperplane_catalog42 import Resources,MIB,load_coverage,write_coverage
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json
from scripts.verify_record42_independent import verify_bytes,_check_all_basis_outputs

TERMINAL={'OLD_S_ONLY_UNSAT','WINNER','CONTROL_PASSED','ERROR'}


def source_for(bundle,spec,small=False):
    path=(bundle/spec['source_file']).resolve()
    if not path.is_relative_to(bundle):raise ValueError('source escapes bundle')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=spec['source_sha256']:raise ValueError('source checksum mismatch')
    candidate=read_json(raw);source=hp.prepare_source(candidate,spec['free_axis'])
    if source['dimension']!=(2 if small else 5)or source['R']!=(8 if small else 93):raise ValueError('wrong source class')
    if source['A_rank']!=source['R']or rc.source_identity(source)!=spec['source_identity']:raise ValueError('source A/W identity mismatch')
    return candidate,source


def immutable(path,raw):
    if Path(path).exists():
        if Path(path).read_bytes()!=raw:raise ValueError('immutable export changed: '+str(path))
    else:freeze(path,raw)


class ArtifactHold(Exception):pass


def save_problem(path,problem,max_bytes=7*MIB):
    # Streaming compressed audit copy avoids a second large JSON allocation.
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise FileExistsError(path)
    with gzip.open(path,'wt',encoding='utf8')as stream:
        for index,piece in enumerate(json.JSONEncoder(sort_keys=True,separators=(',',':')).iterencode(problem)):
            stream.write(piece)
            if index%65536==0:
                stream.flush()
                if path.stat().st_size>=max_bytes:raise ArtifactHold('support formula artifact exceeds7MiB bounded file allowance')
    if path.stat().st_size>=max_bytes:raise ArtifactHold('support formula artifact exceeds7MiB bounded file allowance')


def verify_export(candidate,dimension,target):
    if dimension==5:
        proof=verify_bytes(json_bytes(candidate))
        if not proof['record_eligible']or proof['exact_entries_checked']!=15625:raise AssertionError('independent full record gate failed')
    else:
        terms=[[tuple(t[k])for k in ['u','v','w']]for t in candidate['terms']]
        proof=_check_all_basis_outputs(2,terms)
        if proof['mismatch_count']or len(candidate['terms'])>target:raise AssertionError('independent n2 control gate failed')
    return proof


def census(source,folder,resources,*,seconds,oracle_seconds,seed,cap,memory_mb,closure_rounds=4,oracle=rc.solve_oracle):
    folder.mkdir(parents=True,exist_ok=True);state=load_state(folder,source,cap)
    if state['status']in {'CENSUS_COMPLETE','ERROR'}:return state,0
    if closure_rounds and not state.get('closure'):
        state['points'],state['closure']=rc.common_factor_closure(source,state['points'],cap,closure_rounds)
        checkpoint(folder,source,state)
    deadline=min(resources.deadline,time.monotonic()+seconds);queries=0
    while not resources.sample()and time.monotonic()<deadline:
        if len(state['points'])>=cap:state['status']='POINT_CAP';break
        left=deadline-time.monotonic()
        if left<.05:break
        problem=rc.build_oracle(source,state['points'],cap);index=state['oracle_attempts'];out=folder/f'oracle-{index:04d}';out.mkdir(exist_ok=True)
        # Keep the exact uncompressed prototype schema for terminal validation.
        problemraw=json_bytes(problem)
        if (out/'problem.json').exists():
            if (out/'problem.json').read_bytes()!=problemraw:raise ValueError('orphan census formula changed')
        else:freeze(out/'problem.json',problemraw)
        if resources.sample():state['status']='UNKNOWN';break
        if (out/'result.json').exists():
            result=read_json((out/'result.json').read_bytes())
            if result.get('formula_sha256')!=problem['metadata']['formula_sha256']:raise ValueError('orphan result formula mismatch')
            if result['status']=='SAT':
                point,_=rc.validate_decode(problem,result['complete_assignment'])
                if point!=result['point']:raise ValueError('orphan point mismatch')
        else:
            result=oracle(problem,seconds=min(oracle_seconds,left),conflicts=10000000,memory_mb=memory_mb,
                          options={'seed':str(seed+index)},log_path=out/'solver.log',cancelled=resources.cancelled)
            freeze(out/'result.json',json_bytes(result));queries+=1
        state['oracle_attempts']+=1
        state['history'].append(dict(index=index,status=result['status'],formula_sha256=problem['metadata']['formula_sha256'],
                                     requested_seed=result.get('requested_seed'),solver_seed=result.get('solver_seed')))
        if result['status']=='SAT':
            point=result['point'];rc.validate_point(source,point,{p['c']for p in state['points']})
            state['points'].append(point);state['status']='PARTIAL'
        elif result['status']=='CENSUS_COMPLETE_UNSAT':state['status']='CENSUS_COMPLETE';state['census_complete']=True
        elif result['status']=='UNKNOWN':state['status']='UNKNOWN'
        else:state['status']='ERROR';state['error']=result.get('error','census oracle ERROR')
        checkpoint(folder,source,state);resources.sample()
        if result['status']!='SAT':break
    if not state['census_complete']and state['status']not in {'POINT_CAP','ERROR'}:state['status']='UNKNOWN'
    checkpoint(folder,source,state)
    return state,queries


def run_case(candidate,source,folder,resources,*,target=92,census_seconds=60,support_seconds=60,
             oracle_seconds=5,seed=2026110343301,cap=4096,memory_mb=1536,closure_rounds=4,skip_census=False):
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'WINNER.json').exists():
        raw=(folder/'WINNER.json').read_bytes()
        if (folder/'WINNER.sha256').read_text().strip()!=hashlib.sha256(raw).hexdigest():raise ValueError('winner checkpoint hash mismatch')
        recovered=read_json(raw);verify_export(recovered,source['dimension'],target)
        state=load_state(folder/'census',source,cap)
        return dict(status='WINNER',census_status=state['status'],census_complete=state['census_complete'],
            known_points=len(state['points']),point_catalog_sha256=hp.digest(state['points']),
            census_oracle_queries=0,support_queries=0,source_identity=rc.source_identity(source),verified_products=len(recovered['terms']))
    if skip_census:
        (folder/'census').mkdir(exist_ok=True)
        state=load_state(folder/'census',source,cap);queries=0
        checkpoint(folder/'census',source,state)
    else:
        state,queries=census(source,folder/'census',resources,seconds=census_seconds,oracle_seconds=oracle_seconds,
                            seed=seed,cap=cap,memory_mb=memory_mb,closure_rounds=closure_rounds)
    pointsha=hp.digest(state['points']);result=dict(status='UNKNOWN',census_status=state['status'],
        census_complete=state['census_complete'],known_points=len(state['points']),point_catalog_sha256=pointsha,
        census_oracle_queries=queries,support_queries=0,source_identity=rc.source_identity(source))
    if state['status']=='ERROR':return dict(result,status='ERROR',error=state.get('error'))
    path=folder/'support-checkpoint.json';old=None
    if path.exists():
        old=read_json(path.read_bytes());sha=old.pop('checkpoint_sha256',None)
        if sha!=hp.digest(old)or old['source_identity']!=rc.source_identity(source):raise ValueError('support checkpoint corrupted')
    if resources.sample():return dict(result,resource_pause=resources.reason)
    try:problem=support.build_problem(candidate,source,state['points'],target,max_formula_mb=640)
    except FormulaMemoryLimit as exc:return dict(result,support_status='UNKNOWN_FORMULA_MEMORY_HOLD',reason=str(exc))
    if old and old['point_catalog_sha256']==pointsha and old['status']in {'SUPPORT_CATALOG_UNSAT','SAT'}:
        stored=folder/old['result_file']
        if hashlib.sha256(stored.read_bytes()).hexdigest()!=old['result_sha256']:raise ValueError('support UNSAT evidence changed')
        answer=read_json(stored.read_bytes());result['support_reused']=True
        if old['formula_sha256']!=problem['metadata']['formula_sha256']or answer['formula_sha256']!=old['formula_sha256']:raise ValueError('support checkpoint formula mismatch')
        if answer['status']=='SAT':
            recovered,_=support.validate_decode(problem,answer['complete_assignment'])
            if recovered!=answer['candidate']:raise ValueError('support checkpoint candidate mismatch')
    else:
        attempt=0 if not old else old['attempts'];out=folder/f'support-{attempt:04d}'
        while out.exists():attempt+=1;out=folder/f'support-{attempt:04d}'
        out.mkdir()
        try:save_problem(out/'problem.json.gz',problem)
        except ArtifactHold as exc:return dict(result,support_status='UNKNOWN_FORMULA_ARTIFACT_HOLD',reason=str(exc))
        if resources.sample():return dict(result,resource_pause=resources.reason)
        left=min(support_seconds,resources.deadline-time.monotonic())
        if left<=.05:return result
        answer=support.solve(problem,seconds=left,conflicts=10000000,memory_mb=memory_mb,
                    options={'seed':str(seed+100000+attempt)},log_path=out/'solver.log',cancelled=resources.cancelled)
        freeze(out/'result.json',json_bytes(answer));result['support_queries']=1
        record=dict(source_identity=rc.source_identity(source),point_catalog_sha256=pointsha,status=answer['status'],
            attempts=attempt+1,result_file=str((out/'result.json').relative_to(folder)),
            result_sha256=hashlib.sha256((out/'result.json').read_bytes()).hexdigest(),formula_sha256=problem['metadata']['formula_sha256'])
        record['checkpoint_sha256']=hp.digest(record);base.atomic(path,record);resources.sample()
    result['support_status']=answer['status']
    if answer['status']=='SUPPORT_CATALOG_UNSAT':
        result['status']='OLD_S_ONLY_UNSAT'if state['census_complete']else'PARTIAL_CATALOG_UNSAT'
    elif answer['status']=='SAT':
        recovered=answer['candidate'];raw=json_bytes(recovered);proof=verify_export(recovered,source['dimension'],target)
        immutable(folder/'WINNER.verification.json',json_bytes(answer['verification']))
        immutable(folder/'WINNER.independent.verification.json',json_bytes(proof))
        immutable(folder/'WINNER.sha256',(hashlib.sha256(raw).hexdigest()+'\n').encode())
        immutable(folder/'WINNER.json',raw)
        result.update(status='WINNER',verified_products=len(recovered['terms']))
    elif answer['status']=='ERROR':result.update(status='ERROR',error=answer.get('error','support oracle ERROR'))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--guard',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=1800);p.add_argument('--census-seconds',type=float,default=60)
    p.add_argument('--support-seconds',type=float,default=60);p.add_argument('--oracle-seconds',type=float,default=5)
    p.add_argument('--memory-mb',type=int,default=1536);p.add_argument('--phase-mb',type=int,default=128);p.add_argument('--cap',type=int,default=4096)
    p.add_argument('--seed',type=int,default=2026110343301);p.add_argument('--deadline-utc');p.add_argument('--stop-file',type=Path)
    p.add_argument('--small-controls',action='store_true');a=p.parse_args()
    if (not 0<a.seconds<=1800 or not 0<a.census_seconds<=60 or not 0<a.support_seconds<=60 or not 0<a.oracle_seconds<=5
            or a.memory_mb!=1536 or not 16<=a.phase_mb<=128 or a.cap!=4096 or a.seed<0):p.error('unreviewed resource bounds')
    bundle=a.bundle.resolve();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    if out.is_relative_to(bundle):raise ValueError('output must be outside immutable bundle')
    lock=(out/'coverage.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    raw=(bundle/'manifest.json').read_bytes();manifest=read_json(raw)
    for name,sha in manifest['files'].items():
        path=(bundle/name).resolve()
        if not path.is_relative_to(bundle)or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('frozen input changed: '+name)
    catalograw=(bundle/'catalog.json').read_bytes();catalog=read_json(catalograw)
    if bool(catalog['small_controls'])!=a.small_controls:raise ValueError('control mode mismatch')
    if not a.small_controls and(len(catalog['cases'])!=12 or catalog['target']!=92):raise ValueError('wrong production catalog')
    if (out/'WINNER.json').exists():
        raw=(out/'WINNER.json').read_bytes()
        if (out/'WINNER.sha256').read_text().strip()!=hashlib.sha256(raw).hexdigest():raise ValueError('global winner hash changed')
        verify_export(read_json(raw),2 if a.small_controls else 5,catalog['target'])
        print(json.dumps(dict(status='WINNER',phase_queries=0,production_queries=0,resumed_terminal_winner=True)));return 0
    statepath=out/'coverage.json';state=load_coverage(statepath,hashlib.sha256(catalograw).hexdigest(),hashlib.sha256(raw).hexdigest())
    phase=state['phase_count'];state['phase_count']+=1;write_coverage(statepath,state)
    deadline=time.monotonic()+a.seconds;stopped=False
    if a.deadline_utc:deadline=min(deadline,time.monotonic()+max(0,dt.datetime.fromisoformat(a.deadline_utc.replace('Z','+00:00')).timestamp()-time.time()))
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    _,hard=resource.getrlimit(resource.RLIMIT_FSIZE);limit=8*MIB if hard==resource.RLIM_INFINITY else min(8*MIB,hard)
    resource.setrlimit(resource.RLIMIT_FSIZE,(limit,limit))
    resources=Resources(a.guard,out,a.phase_mb*MIB,deadline,lambda:stopped or bool(a.stop_file and a.stop_file.exists()))
    events=[];error=None;winner=False;cases=catalog['cases'];start=state['cursor'];queries=0
    for offset in range(len(cases)):
        index=(start+offset)%len(cases);spec=cases[index];folder=out/'cases'/spec['id'];old=state['cases'].get(spec['id'])
        if old and old['status']in TERMINAL:
            if hashlib.sha256((folder/'case-result.json').read_bytes()).hexdigest()!=old['result_sha256']:raise ValueError('terminal result changed')
            continue
        if resources.sample():break
        try:
            candidate,source=source_for(bundle,spec,a.small_controls)
            result=run_case(candidate,source,folder,resources,target=catalog['target'],census_seconds=a.census_seconds,
                support_seconds=a.support_seconds,oracle_seconds=a.oracle_seconds,seed=a.seed+index*1009,
                cap=a.cap,memory_mb=a.memory_mb,closure_rounds=spec.get('closure_rounds',4),
                skip_census=a.small_controls and spec.get('skip_census',False))
            queries+=result['census_oracle_queries']+result['support_queries']
            if result['status']=='WINNER':
                if a.small_controls:result['status']='CONTROL_PASSED'
                else:
                    for name in ['WINNER.verification.json','WINNER.independent.verification.json','WINNER.sha256']:
                        immutable(out/name,(folder/name).read_bytes())
                    immutable(out/'WINNER.verify.py',(ROOT/'scripts/verify_record42_independent.py').read_bytes())
                    immutable(out/'WINNER.json',(folder/'WINNER.json').read_bytes());winner=True
            base.atomic(folder/'case-result.json',result)
            state['cases'][spec['id']]=dict(status=result['status'],result_sha256=hashlib.sha256((folder/'case-result.json').read_bytes()).hexdigest(),
                  census_complete=result['census_complete'],known_points=result['known_points'],point_catalog_sha256=result['point_catalog_sha256'])
            events.append(dict(id=spec['id'],**result))
            state['cursor']=index if result.get('resource_pause')else(index+1)%len(cases);write_coverage(statepath,state)
            if result['status']=='ERROR':error=result.get('error')or'case ERROR';break
            if winner:break
        except Exception as exc:error=f'{type(exc).__name__}: {exc}';events.append(dict(id=spec['id'],status='ERROR',error=error));break
    resources.sample();summary=dict(status='ERROR'if error else'WINNER'if winner else'UNKNOWN_RESOURCE_PAUSE'if resources.reason else'PHASE_COMPLETE',
        error=error,phase=phase,phase_queries=queries,production_queries=0 if a.small_controls else queries,
        coverage_counts=dict(Counter(x['status']for x in state['cases'].values())),cursor=state['cursor'],events=events,
        resource_pause=resources.reason,resource_sample=resources.last,working_hold_GiB=5,phase_artifact_cap_MiB=a.phase_mb,
        scope='Only the chosen old active-pair span S. Complete census + support UNSAT excludes that S; partial census UNSAT excludes only the recorded point catalog.')
    freeze(out/f'phase-{phase:04d}.json',json_bytes(summary));base.atomic(out/'summary.json',summary);write_coverage(statepath,state)
    print(json.dumps({k:v for k,v in summary.items()if k!='events'},sort_keys=True));return 2 if error else 0


if __name__=='__main__':raise SystemExit(main())
