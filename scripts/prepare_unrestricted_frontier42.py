"""Prepare the unrestricted frontier adapter with zero target-search steps."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.campaign_unrestricted_frontier42 import (RUNTIME,BINARY_SHA,SOURCE_SHA,DEFAULT_BINARY,
                 load_parent,prune)
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json


def cpu():
    return sum(r.ru_utime+r.ru_stime for r in
               [resource.getrusage(resource.RUSAGE_SELF),resource.getrusage(resource.RUSAGE_CHILDREN)])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input101',type=Path,required=True);p.add_argument('--source',type=Path,action='append',default=[])
    p.add_argument('--completed-pool',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();start=time.monotonic();start_cpu=cpu();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    first=load_parent(a.input101,out)
    if first['rank']!=101:raise ValueError('preparation requires the frozen101 reference')
    frozen101=out/'input101.json';freeze(frozen101,Path(first['full_source_snapshot']).read_bytes())
    frontier={first['term_set_sha256']:first};sources=[]
    for path in a.source:
        parent=load_parent(path,out);frontier[parent['term_set_sha256']]=parent
        sources.append({k:v for k,v in parent.items() if k!='terms'})
    prune(frontier);pool=out/'pool';pool.mkdir()
    for key,parent in frontier.items():freeze(pool/(key+'.json'),Path(parent['full_source_snapshot']).read_bytes())
    freeze(out/'pool_manifest.json',json_bytes(dict(source101=first['source_sha256'],
           snapshot_sources=sources,retained_ranks={k:v['rank'] for k,v in frontier.items()},
           completed_pool_to_read_at_launch=str(a.completed_pool.resolve()),
           note='Runtime reads the completed mutable pool and freezes/reverifies each complete source before frontier selection.')))
    hashes={}
    for name in RUNTIME:
        raw=(ROOT/name).read_bytes();hashes[name]=hashlib.sha256(raw).hexdigest();freeze(out/'runtime'/name,raw)
    for name in ['scripts/prepare_unrestricted_frontier42.py','tests/test_unrestricted_frontier42.py']:
        freeze(out/'provenance'/name,(ROOT/name).read_bytes())
    binary=out/'native/native-worker';raw=DEFAULT_BINARY.read_bytes();assert hashlib.sha256(raw).hexdigest()==BINARY_SHA
    freeze(binary,raw);binary.chmod(0o555)
    cpp=out/'native/flip_worker_v2.cpp';raw=(ROOT/'native/flip_worker_v2.cpp').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==SOURCE_SHA;freeze(cpp,raw)
    wrapper=out/'runtime/scripts/campaign_unrestricted_frontier42.py';controls=[]
    for index in range(2):
        folder=out/f'zero-step-control-{index}'
        command=['python3',str(wrapper),'--binary',str(binary),'--worker-source',str(cpp),'--output-dir',str(folder),
                 '--seconds','5','--phase-seconds','1','--phase-limit','1','--step-limit','0']
        command+=['--input',str(frozen101),'--pool',str(pool),'--seed','2026110342805'] if index==0 else [
                 '--resume',str(out/'zero-step-control-0/checkpoint.json')]
        done=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=6)
        freeze(out/f'zero-step-control-{index}.log',(done.stdout+done.stderr).encode())
        if done.returncode:raise RuntimeError('frozen unrestricted launch control failed')
        stats=read_json((folder/'phase-000/walk.stats.json').read_bytes())
        meta=read_json((folder/'phase-000/manifest.json').read_bytes())
        manifest=read_json((folder/'manifest.json').read_bytes())
        assert stats['steps']==0 and stats['cyclic'] is False and stats['independent_full_verification']
        assert stats['best_rank']==meta['source_essential_rank']
        assert manifest['runtime_code_sha256']==hashes and meta['max_rank']<=141
        assert all(flag not in meta['command'] for flag in ['--cyclic','--fixed-cubes','--allow-arbitrary'])
        controls.append(dict(path=str(folder),steps=0,full_rank=stats['best_rank'],
                             max_rank=meta['max_rank'],global_phase=meta['global_phase'],cwd='/tmp',exit_code=0))
    test=subprocess.run(['python3','-m','unittest','tests.test_unrestricted_frontier42'],cwd=ROOT,
                        capture_output=True,text=True,timeout=5)
    freeze(out/'tests.log',(test.stdout+test.stderr).encode())
    if test.returncode:raise RuntimeError('unrestricted tests failed')
    job=dict(id='unrestricted-frontier42-pilot1',cpu=1,memory_mb=768,seconds=1215,enabled=True,
             command=['python3',str(wrapper),'--input',str(frozen101),'--pool',str(a.completed_pool.resolve()),
                      '--binary',str(binary),'--worker-source',str(cpp),'--output-dir',str(out.parent/'unrestricted-frontier42-pilot1'),
                      '--seconds','1200','--phase-seconds','300','--seed','2026110342805','--headroom','6',
                      '--plus-every','50000','--restart-every','100000000','--archive-size','16'])
    freeze(out/'proposed_job.json',json_bytes(job))
    ready=dict(status='READY',search_launched=False,queue_modified=False,input101=str(frozen101),
               source_pool_snapshot_count=len(frontier),completed_pool_to_read_at_launch=str(a.completed_pool.resolve()),
               accepted_source_ranks=[93,125],global_target=92,headroom=6,max_native_rank=141,
               actual_max_for_rank125=131,cyclic=False,fixed_cube_constraint=False,
               binary_sha256=BINARY_SHA,worker_source_sha256=SOURCE_SHA,runtime_root=str(out/'runtime'),
               runtime_code_sha256=hashes,test_count=3,test_exit_code=0,zero_step_controls=controls,
               proposed_job=str(out/'proposed_job.json'),
               reuse='Existing variable-rank verifier/exporter and frontier selection functions are imported unchanged.',
               scope='Full exact tensor continuation; all U,V,W and cube/orbit profiles may change. No improved bound claimed.',
               preparation_cpu_seconds=cpu()-start_cpu,preparation_wall_seconds=time.monotonic()-start)
    freeze(out/'READY.json',json_bytes(ready))
    freeze(out/'checksums.json',json_bytes({str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest()
                                         for f in out.rglob('*') if f.is_file()}))
    for f in out.rglob('*'):
        if f.is_file():f.chmod(0o555 if f.name=='native-worker' else 0o444)
    print(json.dumps(ready,indent=2))


if __name__=='__main__':main()
