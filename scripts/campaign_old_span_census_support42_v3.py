"""Selection-only v3 layer for immutable old-span census/support v2 math."""
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
if not(ROOT/'mmsearch').is_dir():
    ROOT=Path(json.loads((ROOT.parent/'REUSE.json').read_text())['runtime_root']).resolve()
sys.path.insert(0,str(ROOT))
from mmsearch import hyperplane_rankone42 as hp,rankone_census42 as rc,old_span_support42 as support
from mmsearch.free_factor_sat import FormulaMemoryLimit
from scripts import campaign_hyperplane_rankone42 as base
from scripts.prototype_rankone_census42 import load_state,checkpoint
from scripts.campaign_hyperplane_catalog42 import Resources,MIB,load_coverage,write_coverage
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json
from scripts.verify_record42_independent import verify_bytes,_check_all_basis_outputs

from scripts.campaign_old_span_census_support42 import source_for,run_case,verify_export,immutable,TERMINAL


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--guard',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=1800);p.add_argument('--census-seconds',type=float,default=60)
    p.add_argument('--support-seconds',type=float,default=60);p.add_argument('--oracle-seconds',type=float,default=5)
    p.add_argument('--memory-mb',type=int,default=1536);p.add_argument('--phase-mb',type=int,default=128);p.add_argument('--cap',type=int,default=4096)
    p.add_argument('--seed',type=int,default=2026110343301);p.add_argument('--deadline-utc');p.add_argument('--stop-file',type=Path)
    p.add_argument('--small-controls',action='store_true');p.add_argument('--case-id',action='append',dest='case_ids');a=p.parse_args()
    if (not 0<a.seconds<=1800 or not 0<a.census_seconds<=60 or not 0<a.support_seconds<=60 or not 0<a.oracle_seconds<=5
            or a.memory_mb!=1536 or not 16<=a.phase_mb<=128 or a.cap!=4096 or a.seed<0):p.error('unreviewed resource bounds')
    overlay=a.bundle.resolve();overlayraw=(overlay/'manifest.json').read_bytes();overlaymanifest=read_json(overlayraw)
    for name,sha in overlaymanifest['files'].items():
        path=(overlay/name).resolve()
        if not path.is_relative_to(overlay)or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('selection overlay changed: '+name)
    reuse=read_json((overlay/'REUSE.json').read_bytes());bundle=Path(reuse['upstream_bundle']).resolve()
    if hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest()!=reuse['upstream_manifest_sha256']:raise ValueError('upstream manifest changed')
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    if out.is_relative_to(bundle):raise ValueError('output must be outside immutable bundle')
    lock=(out/'coverage.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    raw=(bundle/'manifest.json').read_bytes();manifest=read_json(raw)
    for name,sha in manifest['files'].items():
        path=(bundle/name).resolve()
        if not path.is_relative_to(bundle)or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('frozen input changed: '+name)
    catalograw=(bundle/'catalog.json').read_bytes();catalog=read_json(catalograw)
    if bool(catalog['small_controls'])!=a.small_controls:raise ValueError('control mode mismatch')
    if not a.small_controls and(len(catalog['cases'])!=12 or catalog['target']!=92):raise ValueError('wrong production catalog')
    allowed=read_json((overlay/'selection.json').read_bytes())['representative_ids']
    selected_ids=list(allowed)if a.case_ids is None else a.case_ids
    if not selected_ids or len(set(selected_ids))!=len(selected_ids)or not set(selected_ids)<=set(allowed):raise ValueError('invalid or duplicate case selection')
    all_cases=catalog['cases'];catalog['cases']=[case for case in all_cases if case['id']in set(selected_ids)]
    if len(catalog['cases'])!=len(selected_ids):raise ValueError('selected case absent from upstream catalog')
    selected_ids=[case['id']for case in catalog['cases']]
    selection_identity=hp.digest(dict(upstream_catalog_sha256=hashlib.sha256(catalograw).hexdigest(),selected_ids=selected_ids))
    statepath=out/'coverage.json';state=load_coverage(statepath,selection_identity,hp.digest(dict(upstream_manifest_sha256=hashlib.sha256(raw).hexdigest(),overlay_manifest_sha256=hashlib.sha256(overlayraw).hexdigest())))
    if (out/'WINNER.json').exists():
        rawwinner=(out/'WINNER.json').read_bytes()
        if (out/'WINNER.sha256').read_text().strip()!=hashlib.sha256(rawwinner).hexdigest():raise ValueError('global winner hash changed')
        verify_export(read_json(rawwinner),2 if a.small_controls else 5,catalog['target'])
        print(json.dumps(dict(status='WINNER',phase_queries=0,production_queries=0,resumed_terminal_winner=True)));return 0
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
        selected_case_ids=selected_ids,selection_identity=selection_identity,
        resource_pause=resources.reason,resource_sample=resources.last,working_hold_GiB=5,phase_artifact_cap_MiB=a.phase_mb,
        scope='Only the chosen old active-pair span S. Complete census + support UNSAT excludes that S; partial census UNSAT excludes only the recorded point catalog.')
    freeze(out/f'phase-{phase:04d}.json',json_bytes(summary));base.atomic(out/'summary.json',summary);write_coverage(statepath,state)
    print(json.dumps({k:v for k,v in summary.items()if k!='events'},sort_keys=True));return 2 if error else 0


if __name__=='__main__':raise SystemExit(main())
