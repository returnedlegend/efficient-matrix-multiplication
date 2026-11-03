"""Freeze a direct mutable-five-cube pilot; perform zero native search steps."""
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
from scripts.campaign_mutable_five_cubes42 import (DEFAULT_BINARY,EXPECTED_BINARY_SHA256,
                EXPECTED_SOURCE_SHA256,load_parent,prune_frontier)
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json


def cpu():
    return sum(r.ru_utime+r.ru_stime for r in
               [resource.getrusage(resource.RUSAGE_SELF),resource.getrusage(resource.RUSAGE_CHILDREN)])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,action='append',required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args();start=time.monotonic();start_cpu=cpu()
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    frontier={};provenance=[]
    for path in sorted(set(args.source)):
        parent=load_parent(path,out);frontier[parent['term_set_sha256']]=parent
        provenance.append({k:v for k,v in parent.items() if k not in ('held','residual')})
    prune_frontier(frontier)
    pool=out/'pool';pool.mkdir()
    for key,parent in frontier.items():freeze(pool/(key+'.json'),Path(parent['full_source_snapshot']).read_bytes())
    best=min(frontier,key=lambda key:(len(frontier[key]['held'])+len(frontier[key]['residual']),key))
    source=pool/(best+'.json');rank=len(frontier[best]['held'])+len(frontier[best]['residual'])
    freeze(out/'pool_manifest.json',json_bytes(dict(imported_sources=provenance,retained_count=len(frontier),
           retained_ranks={key:len(v['held'])+len(v['residual']) for key,v in frontier.items()},
           scope='Read-only snapshot of verified local full algorithms; only count5 is constrained by this new search.')))
    runtime=['scripts/campaign_mutable_five_cubes42.py','scripts/freeze_campaign_dictionary.py',
             'mmsearch/__init__.py','mmsearch/native_bridge.py','mmsearch/search.py','mmsearch/verify.py']
    hashes={}
    for name in runtime:
        raw=(ROOT/name).read_bytes();hashes[name]=hashlib.sha256(raw).hexdigest();freeze(out/'runtime'/name,raw)
    extras=['scripts/prepare_mutable_five_cubes42.py','tests/test_mutable_five_cubes42.py',
            'tests/fixtures/held_inventory42_rank113.txt','tests/fixtures/held_inventory42_rank113.provenance.json']
    for name in extras:freeze(out/'provenance'/name,(ROOT/name).read_bytes())
    binary=out/'native/flip_worker_fixed_cubes';raw=DEFAULT_BINARY.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==EXPECTED_BINARY_SHA256
    freeze(binary,raw);binary.chmod(0o555)
    cpp=out/'native/flip_worker_fixed_cubes.cpp';raw=DEFAULT_BINARY.with_suffix('.cpp').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==EXPECTED_SOURCE_SHA256;freeze(cpp,raw)
    wrapper=out/'runtime/scripts/campaign_mutable_five_cubes42.py'
    controls=[]
    for index,headroom in enumerate([6,12]):
        folder=out/f'zero-step-control-{index}'
        command=['python3',str(wrapper),'--binary',str(binary),'--worker-source',str(cpp),
                 '--output-dir',str(folder),'--seconds','4','--phase-seconds','1',
                 '--phase-limit','1','--step-limit','0','--headroom',str(headroom)]
        command+=['--input',str(source),'--pool',str(pool),'--seed','2026110342705'] if index==0 else [
                 '--resume',str(out/'zero-step-control-0/checkpoint.json')]
        result=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=5)
        freeze(out/f'zero-step-control-{index}.log',(result.stdout+result.stderr).encode())
        if result.returncode:raise RuntimeError('standalone full-runtime zero-step control failed')
        stats=read_json((folder/'phase-000/walk.stats.json').read_bytes())
        meta=read_json((folder/'phase-000/manifest.json').read_bytes())
        selected_rank=meta['initial_global_rank']
        assert stats['steps']==0 and stats['best_rank']==selected_rank and not (folder/'WINNER.json').exists()
        assert rank<=selected_rank<=rank+(3 if index else 0)
        assert '--allow-arbitrary' not in meta['command']
        assert meta['command'][meta['command'].index('--fixed-cubes')+1]=='5'
        manifest=read_json((folder/'manifest.json').read_bytes())
        assert manifest['code_sha256']==hashes
        controls.append(dict(path=str(folder),full_rank=selected_rank,steps=0,headroom=headroom,
                             cwd='/tmp',runtime_code_sha256=manifest['code_sha256'],exit_code=0))
    test=subprocess.run(['python3','-m','unittest','tests.test_mutable_five_cubes42'],cwd=ROOT,
                        capture_output=True,text=True,timeout=5)
    freeze(out/'tests.log',(test.stdout+test.stderr).encode())
    if test.returncode:raise RuntimeError('mutable count5 tests failed')
    job=dict(id='mutable-five42-pilot1',cpu=1,memory_mb=768,seconds=1215,enabled=True,
             command=['python3',str(wrapper),'--input',str(source),'--pool',str(pool),'--binary',str(binary),
                      '--worker-source',str(cpp),'--output-dir',str(out.parent/'mutable-five42-pilot1'),
                      '--seconds','1200','--phase-seconds','300','--seed','2026110342705','--headroom','6',
                      '--plus-every','50000','--restart-every','100000000','--archive-size','16'])
    freeze(out/'proposed_job.json',json_bytes(job))
    ready=dict(status='READY',search_launched=False,queue_modified=False,initial_best_full_rank=rank,
               source_pool_count=len(frontier),source_pool=str(pool),fixed_cube_count=5,cube_values_mutable=True,
               global_target=92,native_tensor='full 5x5 F2 multiplication tensor; no arbitrary residual mode',
               binary_sha256=EXPECTED_BINARY_SHA256,worker_source_sha256=EXPECTED_SOURCE_SHA256,
               runtime_root=str(out/'runtime'),runtime_code_sha256=hashes,test_count=4,test_exit_code=0,
               zero_step_controls=controls,proposed_job=str(out/'proposed_job.json'),
               scope='Cube values may change while the total cube count stays5. Distinct from held-five inventory; no improved rank or existence claim.',
               resume='Use --resume CHECKPOINT --output-dir NEW_DIRECTORY; every full source, binary and wrapper hash is checked again.',
               limits='Canonical full rank>=92, rank2mod3, exactly5 arbitrary cubes, native maxrank<=1000, headroom6 or12.',
               preparation_cpu_seconds=cpu()-start_cpu,preparation_wall_seconds=time.monotonic()-start)
    freeze(out/'READY.json',json_bytes(ready))
    freeze(out/'checksums.json',json_bytes({str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest()
           for f in out.rglob('*') if f.is_file()}))
    for f in out.rglob('*'):
        if f.is_file():f.chmod(0o555 if f==binary or f.name.startswith('native-') else 0o444)
    print(json.dumps(ready,indent=2))


if __name__=='__main__':main()
