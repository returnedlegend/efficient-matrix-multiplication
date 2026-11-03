"""Freeze case-only low-weight relation catalog and small native CLI controls."""
from collections import defaultdict,deque,Counter
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mmsearch import hyperplane_rankone42 as hp
from scripts.campaign_hyperplane_catalog42 import model_identity,pid_ticks
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json


def cpu():
    return sum(r.ru_utime+r.ru_stime for r in
        [resource.getrusage(resource.RUSAGE_SELF),resource.getrusage(resource.RUSAGE_CHILDREN)])


def ordered(terms):
    from mmsearch.search import encode_candidate
    return dict(dimension=2,field=2,terms=[encode_candidate([t],2)['terms'][0]for t in terms])


def manifest(bundle):
    files={str(p.relative_to(bundle)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in bundle.rglob('*')if p.is_file() and p.name!='manifest.json'and '__pycache__'not in p.parts}
    freeze(bundle/'manifest.json',json_bytes(dict(format='hyperplane-catalog-bundle42-v1',files=files)))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preparation',type=Path,required=True);p.add_argument('--v3-runtime',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();start=time.monotonic();start_cpu=cpu()
    prep=a.preparation.resolve();out=a.output_dir.resolve();camp=out.parent;out.mkdir(parents=True,exist_ok=False)
    raw=read_json((prep/'deduplicated_cases.json').read_bytes());source_info=read_json((prep/'CATALOG_SIZE.json').read_bytes())['sources']
    sources={}
    for item in source_info:
        data=Path(item['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==item['sha256']
        rel=f"sources/source-{item['source_id']}.json";freeze(out/rel,data);sources[item['source_id']]=(rel,item['sha256'])
    strata=defaultdict(deque)
    for case in raw:strata[case['source_id'],case['free_axis'],case['lambda_weight']].append(case)
    ordered_cases=[]
    while any(strata.values()):
        for key in sorted(strata):
            if strata[key]:ordered_cases.append(strata[key].popleft())
    entries=[];aliases={}
    for index,case in enumerate(ordered_cases):
        source_file,source_sha=sources[case['source_id']]
        case_id=f"case-{index:04d}-w{case['lambda_weight']}-s{case['source_id']}-a{case['free_axis']}"
        spec={k:v for k,v in case.items()if k!='aliases'}
        spec.update(source_file=source_file,source_sha256=source_sha,id=case_id)
        file=f'cases/{case_id}.json';freeze(out/file,json_bytes(spec));aliases[case_id]=case['aliases']
        entries.append(dict(id=case_id,file=file,source_id=case['source_id'],free_axis=case['free_axis'],
                            lambda_weight=case['lambda_weight'],model_sha256=case['model_sha256'],
                            physical_H_sha256=case['physical_H_sha256']))
    catalog=dict(format='complete-minimal-W-circuit-catalog42-v1',small_controls=False,cases=entries,
                 raw_relations=3231,physical_H_cases=len(entries),weights=dict(Counter(c['lambda_weight']for c in entries)),
                 max_new_points='lambda_weight−1',excluded_prior_exact_model_H=0,
                 scope='All minimal relations of weights2..4 for these four fresh sources/all axes; not all hyperplanes or global rank92.')
    freeze(out/'catalog.json',json_bytes(catalog));freeze(out/'aliases.json',json_bytes(aliases))
    for name in ['CATALOG_SIZE.json','DEDUPLICATED_SIZE.json','excluded_prior.json','enumerate_relations.py','deduplicate_catalog.py']:
        freeze(out/'provenance'/name,(prep/name).read_bytes())
    # The complete v3 oracle/decoder/lifecycle and native solver remain byte-identical.
    for path in a.v3_runtime.rglob('*'):
        if path.is_file()and '__pycache__'not in path.parts:
            freeze(out/'runtime'/path.relative_to(a.v3_runtime),path.read_bytes())
    for name in ['scripts/campaign_hyperplane_catalog42.py','scripts/verify_record42_independent.py']:
        freeze(out/'runtime'/name,(ROOT/name).read_bytes())
    freeze(out/'provenance/prepare_hyperplane_catalog42.py',Path(__file__).read_bytes())
    # Small n2 circuits of weight3 and4 both admit Strassen7 in H. A third
    # schoolbook circuit is a chosen-H negative; it never becomes a global claim.
    positive3=[(13,1,10),(1,11,12),(1,1,6),(9,9,9),(8,5,3),(3,8,5),(5,3,8),(10,12,1)]
    positive4=[(1,1,7),(1,11,12),(2,4,1),(13,1,10),(3,8,4),(5,3,8),(8,5,2),(9,9,8)]
    from mmsearch.search import naive_terms
    controls=out/'controls/small-bundle';control_entries=[]
    for index,(terms,lam)in enumerate([(positive3,7),(positive4,15),(naive_terms(2),None)]):
        candidate=ordered(terms);data=json_bytes(candidate);rel=f'sources/n2-{index}.json';freeze(controls/rel,data)
        source=hp.prepare_source(candidate,2)
        if lam is None:lam=sum(1<<i for i,w in enumerate(source['W_rows'])if w==1)
        family=hp.build_family(source,lam);weight=lam.bit_count();case_id=f'control-{index}-w{weight}'
        spec=dict(id=case_id,source_file=rel,source_sha256=hashlib.sha256(data).hexdigest(),free_axis=2,
                  lambda_mask=lam,lambda_weight=weight,max_new_points=weight-1,
                  model_sha256=model_identity(source,lam),physical_H_sha256=family['physical_H_sha256'])
        file=f'cases/{case_id}.json';freeze(controls/file,json_bytes(spec));control_entries.append(dict(id=case_id,file=file))
    freeze(controls/'catalog.json',json_bytes(dict(small_controls=True,cases=control_entries)));manifest(controls)
    metric=out/'controls/guard.json'
    def guard(working):
        value=dict(updated_utc=dt.datetime.now(dt.timezone.utc).isoformat(),pid=os.getpid(),
            process_identity=dict(start_ticks=pid_ticks(os.getpid())),campaign_allocated_bytes=working,
            rss_bytes=64*1024**2,filesystem_free_bytes=16*1024**3,stop_reason=None)
        metric.write_bytes(json_bytes(value))
    wrapper=out/'runtime/scripts/campaign_hyperplane_catalog42.py';control_output=out/'controls/actual-native-cli'
    base=['python3','-B',str(wrapper),'--bundle',str(controls),'--output-dir',str(control_output),
          '--guard',str(metric),'--small-controls','--seconds','1800','--oracle-seconds','5','--max-cases','250',
          '--memory-mb','1536','--phase-mb','128','--seed','2026110343101']
    guard(int(4.25*1024**3))
    first=subprocess.run(base,cwd='/tmp',capture_output=True,text=True,timeout=30)
    freeze(out/'controls/first-launch.log',(first.stdout+first.stderr).encode())
    if first.returncode:raise RuntimeError('frozen small CLI control failed')
    first_summary=read_json((control_output/'summary.json').read_bytes())
    assert first_summary['coverage_counts']=={'CONTROL_PASSED':2,'HYPERPLANE_SPAN_UNSAT':1}
    assert first_summary['phase_queries']==6 and first_summary['production_queries']==0
    coverage=read_json((control_output/'coverage.json').read_bytes())
    assert coverage['cases']['control-0-w3']['new_points']==2 and coverage['cases']['control-1-w4']['new_points']==3
    again=subprocess.run(base,cwd='/tmp',capture_output=True,text=True,timeout=10)
    freeze(out/'controls/resume-launch.log',(again.stdout+again.stderr).encode())
    resumed=read_json((control_output/'summary.json').read_bytes());assert again.returncode==0 and resumed['phase_queries']==0
    # A working hold must exit cleanly UNKNOWN, retain cursor, and issue no oracle.
    guard(5*1024**3);held=out/'controls/working-hold-cli'
    held_command=[str(held)if v==str(control_output)else v for v in base]
    hold=subprocess.run(held_command,cwd='/tmp',capture_output=True,text=True,timeout=10)
    held_summary=read_json((held/'summary.json').read_bytes())
    assert hold.returncode==0 and held_summary['status']=='UNKNOWN_RESOURCE_PAUSE'
    assert held_summary['phase_queries']==0 and held_summary['cursor']==0
    freeze(out/'controls/working-hold-launch.log',(hold.stdout+hold.stderr).encode())
    control_report=dict(status='PASS',small_native_control_dimensions=2,weight3_new_points=2,weight4_new_points=3,
        both_verified_rank=7,negative_chosen_H='UNSAT',initial_queries=6,resume_queries=0,production_queries=0,
        fresh_working_metric_above4GiB_accepted=True,working5GiB_hold_exits_UNKNOWN=True,hold_cursor_preserved=True)
    freeze(out/'controls/CONTROL_REPORT.json',json_bytes(control_report))
    # Data/code manifest is the immutable identity used by persistent coverage.
    manifest(out)
    job=dict(id='hyperplane-catalog42-phase000',cpu=1,memory_mb=1536,seconds=1815,enabled=False,
        command=['python3','-B',str(wrapper),'--bundle',str(out),'--output-dir',str(camp/'hyperplane-catalog42-state'),
          '--guard',str(camp/'operations-v3/state.json'),'--seconds','1800','--oracle-seconds','5','--max-cases','250',
          '--memory-mb','1536','--phase-mb','128','--seed','2026110343101','--deadline-utc','2026-11-04T21:31:16Z'])
    freeze(out/'PROPOSED-JOB.json',json_bytes(job))
    sizes=[p.stat().st_size for p in out.rglob('*')if p.is_file()]
    ready=dict(status='READY',unlaunched=True,catalog_cases=len(entries),raw_relations=3231,
        counts_by_weight=dict(Counter(c['lambda_weight']for c in entries)),distinct_physical_H=len(entries),
        prior_exact_model_H_exclusions=0,production_queries=0,production_formulas_built_during_prep=0,
        small_native_CLI_controls=control_report,oracle_implementation='Byte-identical frozen v3; fresh solver per point.',
        max_cases_per_phase=250,max_oracle_seconds=5,max_inner_seconds=1800,max_outer_seconds=1815,
        point_cap='weight−1≤3',phase_artifact_cap_MiB=128,working_hold_GiB=5,
        resource_policy='Fresh operations-v3 metric before/after each oracle; reserve16MiB; stale/hold pauses UNKNOWN with points/cursor intact.',
        coverage_policy='New families before UNKNOWN retries; immutable completed-UNSAT checkpoints are skipped, never resubmitted.',
        artifact_logical_bytes=sum(sizes),artifact_max_file_bytes=max(sizes),
        proposed_job=str(out/'PROPOSED-JOB.json'),manifest_sha256=hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest(),
        preparation_CPU_seconds=cpu()-start_cpu,preparation_wall_seconds=time.monotonic()-start,
        scope='Only low-weight minimal W-relation hyperplanes in these four fresh old-active-pair spans; no global rank92 nonexistence.')
    freeze(out/'READY.json',json_bytes(ready))
    for path in out.rglob('*'):
        if path.is_file():path.chmod(0o555 if '.so'in path.name else 0o444)
    print(json.dumps(ready,indent=2))


if __name__=='__main__':main()
