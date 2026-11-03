"""Checkpointed phases over frozen minimal-W-circuit hyperplanes; v3 oracle reused."""
import argparse
from collections import Counter
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mmsearch import hyperplane_rankone42 as hp
from scripts import campaign_hyperplane_rankone42 as base
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json
from scripts.verify_record42_independent import verify_bytes

GIB=1024**3;MIB=1024**2
TERMINAL={'HYPERPLANE_SPAN_UNSAT','ERROR','WINNER','CONTROL_PASSED'}


def model_identity(source,lam):
    return hp.digest(dict(encoding='rank-one-point-in-coefficient-hyperplane42-v1',width=source['width'],
        R=source['R'],A_columns=source['A_columns'],W_columns=source['W_columns'],free_axis=source['free_axis'],
        lambda_mask=lam,factor_nonzero=True,exclusion='outside span of old coefficient units outside lambda support'))


def allocated(path):
    total=0
    for folder,dirs,files in os.walk(path):
        for name in files:
            try:s=(Path(folder)/name).stat();total+=max(s.st_size,s.st_blocks*512)
            except FileNotFoundError:pass
    return total


def pid_ticks(pid):
    try:return int(Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19])
    except (OSError,ValueError,IndexError):return None


class Resources:
    def __init__(self,guard,output,phase_bytes,deadline,stop):
        self.guard=Path(guard);self.output=Path(output);self.start_bytes=allocated(output)
        self.phase_bytes=phase_bytes;self.deadline=deadline;self.stop=stop;self.reason=None;self.last={}

    def sample(self):
        self.reason=None
        if self.stop():self.reason='STOP_SIGNAL'
        elif time.monotonic()>=self.deadline:self.reason='DEADLINE'
        used=max(0,allocated(self.output)-self.start_bytes)
        if used+16*MIB>=self.phase_bytes:self.reason='PHASE_BYTES_128MIB_HOLD'
        try:
            guard=read_json(self.guard.read_bytes());stamp=dt.datetime.fromisoformat(guard['updated_utc'].replace('Z','+00:00')).timestamp()
            age=time.time()-stamp;working=guard['campaign_allocated_bytes'];pid=guard['pid']
            if age>60 or age< -5:self.reason='GUARD_STALE'
            elif type(pid)is not int or pid_ticks(pid)!=guard.get('process_identity',{}).get('start_ticks'):self.reason='GUARD_IDENTITY'
            elif guard.get('stop_reason'):self.reason='GUARD_STOP'
            elif type(working)is not int or working<0:self.reason='GUARD_INVALID_WORKING_BYTES'
            elif working+16*MIB>=5*GIB:self.reason='WORKING_5GIB_HOLD'
            elif guard.get('rss_bytes',8*GIB)>7*GIB:self.reason='RAM_HOLD'
            elif guard.get('filesystem_free_bytes',0)<8*GIB:self.reason='DISK_HOLD'
            self.last=dict(guard_updated_utc=guard['updated_utc'],guard_age_seconds=age,
                           campaign_allocated_bytes=working,phase_added_bytes=used)
        except (OSError,ValueError,KeyError,TypeError):self.reason='GUARD_UNAVAILABLE'
        return self.reason

    def cancelled(self):return bool(self.reason or self.stop() or time.monotonic()>=self.deadline)


def family_for(bundle,spec,small=False):
    source=(bundle/spec['source_file']).resolve()
    if not source.is_relative_to(bundle):raise ValueError('source escapes frozen bundle')
    raw=source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=spec['source_sha256']:raise ValueError('source hash mismatch')
    prepared=hp.prepare_source(read_json(raw),spec['free_axis']);w=spec['lambda_weight'];lam=spec['lambda_mask']
    if (prepared['dimension']!=(2 if small else 5) or prepared['R']!=(8 if small else 93)
            or w not in (2,3,4) or lam.bit_count()!=w or spec['max_new_points']!=w-1):
        raise ValueError('unreviewed source/weight/point cap')
    if len(hp.linear_basis([prepared['W_rows'][i]for i in hp.bits(lam)]))!=w-1:
        raise ValueError('lambda is not a minimal W circuit')
    family=hp.build_family(prepared,lam)
    if family['physical_H_sha256']!=spec['physical_H_sha256'] or model_identity(prepared,lam)!=spec['model_sha256']:
        raise ValueError('physical-H/model identity mismatch')
    return family


def write_coverage(path,state):
    value=dict(state);value['coverage_sha256']=hp.digest(value);base.atomic(path,value)


def load_coverage(path,catalog_sha,manifest_sha):
    if not path.exists():return dict(format='hyperplane-catalog-coverage42-v1',catalog_sha256=catalog_sha,
                manifest_sha256=manifest_sha,cursor=0,phase_count=0,cases={})
    value=read_json(path.read_bytes());sha=value.pop('coverage_sha256',None)
    if (sha!=hp.digest(value) or value.get('format')!='hyperplane-catalog-coverage42-v1'
            or value.get('catalog_sha256')!=catalog_sha or value.get('manifest_sha256')!=manifest_sha):
        raise ValueError('coverage corruption or bundle mismatch')
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--guard',type=Path,required=True);p.add_argument('--seconds',type=float,default=1800)
    p.add_argument('--oracle-seconds',type=float,default=5);p.add_argument('--max-cases',type=int,default=250)
    p.add_argument('--memory-mb',type=int,default=1536);p.add_argument('--conflicts',type=int,default=10000000)
    p.add_argument('--phase-mb',type=int,default=128);p.add_argument('--seed',type=int,default=2026110343101)
    p.add_argument('--deadline-utc');p.add_argument('--small-controls',action='store_true')
    a=p.parse_args()
    if (not 0<a.seconds<=1800 or not 0<a.oracle_seconds<=5 or not 1<=a.max_cases<=250
            or a.memory_mb!=1536 or not 16<=a.phase_mb<=128 or a.seed<0 or a.conflicts<1):p.error('invalid reviewed phase bounds')
    started=time.monotonic();bundle=a.bundle.resolve();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    lock=(out/'coverage.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    manifest_raw=(bundle/'manifest.json').read_bytes();manifest=read_json(manifest_raw)
    for name,sha in manifest['files'].items():
        path=(bundle/name).resolve()
        if not path.is_relative_to(bundle) or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('frozen bundle checksum mismatch: '+name)
    catalog_raw=(bundle/'catalog.json').read_bytes();catalog=read_json(catalog_raw)
    if bool(catalog.get('small_controls'))!=a.small_controls:raise ValueError('small-control mode mismatch')
    coverage_path=out/'coverage.json';state=load_coverage(coverage_path,hashlib.sha256(catalog_raw).hexdigest(),hashlib.sha256(manifest_raw).hexdigest())
    cases=catalog['cases'];count=len(cases);phase=state['phase_count'];state['phase_count']+=1
    deadline=started+a.seconds
    if a.deadline_utc:
        left=dt.datetime.fromisoformat(a.deadline_utc.replace('Z','+00:00')).timestamp()-time.time()
        deadline=min(deadline,time.monotonic()+max(0,left))
    stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    # A point has <1MiB bounded formula/model artifacts; cap each native log at
    # 8MiB and reserve16MiB before another oracle to stay inside128MiB/phase.
    _,hard=resource.getrlimit(resource.RLIMIT_FSIZE);limit=8*MIB if hard==resource.RLIM_INFINITY else min(8*MIB,hard)
    resource.setrlimit(resource.RLIMIT_FSIZE,(limit,limit))
    resources=Resources(a.guard,out,a.phase_mb*MIB,deadline,lambda:stopped)
    original_cursor=state['cursor'];write_coverage(coverage_path,state)
    rotated=[(original_cursor+i)%count for i in range(count)] if count else []
    new=[];retry=[]
    for index in rotated:
        case=cases[index];old=state['cases'].get(case['id'])
        if old and old['status']in TERMINAL:
            cp=out/'cases'/case['id']/'checkpoint.json'
            if not cp.exists() or hashlib.sha256(cp.read_bytes()).hexdigest()!=old['checkpoint_sha256']:
                raise ValueError('terminal checkpoint changed; no automatic resubmission')
            continue
        (retry if old else new).append(index)
    planned=new+retry;events=[];phase_queries=0;error=None;winner=False;reason=resources.sample()

    def guarded_oracle(problem,**kwargs):
        nonlocal phase_queries
        if resources.sample():return dict(status='UNKNOWN',reason='RESOURCE_PAUSE: '+resources.reason)
        phase_queries+=1
        result=hp.solve_oracle(problem,**kwargs)
        resources.sample()
        return result

    for index in planned:
        if len(events)>=a.max_cases or resources.sample():break
        case=cases[index];folder=out/'cases'/case['id'];old=state['cases'].get(case['id'],{})
        try:
            spec=read_json((bundle/case['file']).read_bytes());family=family_for(bundle,spec,a.small_controls)
            result=base.run_family(family,folder,max_points=spec['max_new_points'],oracle_seconds=a.oracle_seconds,
                    conflicts=a.conflicts,memory_mb=a.memory_mb,deadline=deadline,
                    seed=a.seed+index*1009+old.get('dispatches',0)*1000003,
                    oracle=guarded_oracle,cancelled=resources.cancelled)
            status=result['status']
            if status=='POINT_CAP':raise ValueError('minimal circuit hit full H dimension without target containment')
            if status=='HYPERPLANE_SPAN_UNSAT':base.load_state(folder,family)
            if status=='WINNER':
                candidate=read_json((folder/'WINNER.json').read_bytes())
                if a.small_controls:status='CONTROL_PASSED'
                else:
                    proof=verify_bytes(json_bytes(candidate))
                    if not proof['record_eligible']or proof['exact_entries_checked']!=15625:raise ValueError('independent n5 record gate failed')
                    for name in ['WINNER.json','WINNER.verification.json','WINNER.sha256','WINNER.verify.py']:
                        freeze(out/name,(folder/name).read_bytes())
                    freeze(out/'WINNER.independent.verification.json',json_bytes(proof));winner=True
            cp=folder/'checkpoint.json';record=dict(status=status,dispatches=old.get('dispatches',0)+1,
                    oracle_attempts=result['oracle_attempts'],new_points=len(result['points']),last_phase=phase,
                    checkpoint_sha256=hashlib.sha256(cp.read_bytes()).hexdigest(),
                    model_sha256=spec['model_sha256'],physical_H_sha256=spec['physical_H_sha256'])
            state['cases'][case['id']]=record;state['cursor']=(index+1)%count
            events.append(dict(case=case['id'],**record));write_coverage(coverage_path,state)
            if status=='ERROR':error=result.get('error','terminal case ERROR');break
            if winner:break
        except Exception as exc:
            error=f'{type(exc).__name__}: {exc}';events.append(dict(case=case['id'],status='ERROR',error=error));break
    resources.sample();counts=Counter(row['status']for row in state['cases'].values())
    if error:status='ERROR'
    elif winner:status='WINNER'
    elif resources.reason:status='UNKNOWN_RESOURCE_PAUSE'
    elif all(row['status']=='HYPERPLANE_SPAN_UNSAT'for row in state['cases'].values())and len(state['cases'])==count:status='CATALOG_ONLY_UNSAT'
    elif not planned:status='COVERAGE_TERMINAL'
    else:status='UNKNOWN_PHASE_COMPLETE'
    summary=dict(status=status,winner=winner,error=error,resource_pause=resources.reason,resource_sample=resources.last,
        phase=phase,phase_cases=len(events),phase_queries=phase_queries,production_queries=0 if a.small_controls else phase_queries,
        total_catalog_cases=count,coverage_counts=dict(counts),unvisited=count-len(state['cases']),cursor=state['cursor'],
        max_cases_per_phase=a.max_cases,oracle_seconds=a.oracle_seconds,phase_mib_cap=a.phase_mb,working_hold_gib=5,
        events=events,elapsed_seconds=time.monotonic()-started,
        scope='Only these minimal W-relation physical hyperplanes in the selected old active-pair spans; not global rank92.')
    phases=out/'phases';phases.mkdir(exist_ok=True);freeze(phases/f'phase-{phase:05d}.json',json_bytes(summary))
    base.atomic(out/'summary.json',summary);write_coverage(coverage_path,state)
    print(json.dumps({k:v for k,v in summary.items()if k!='events'},sort_keys=True))
    return 2 if error else 0


if __name__=='__main__':raise SystemExit(main())
