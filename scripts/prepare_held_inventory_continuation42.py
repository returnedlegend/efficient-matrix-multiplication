"""Freeze continuation readiness using verified input and zero-step controls only."""
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
from scripts.campaign_held_inventory_continuation42 import split_source,DEFAULT_BINARY,EXPECTED_BINARY_SHA256
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json
from mmsearch.native_bridge import term_set_sha256


def cpu():
    return sum(r.ru_utime+r.ru_stime for r in
               [resource.getrusage(resource.RUSAGE_SELF),resource.getrusage(resource.RUSAGE_CHILDREN)])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args();start=time.monotonic();start_cpu=cpu()
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    raw=args.input.read_bytes();held,residual,report=split_source(read_json(raw))
    source=out/'input_full.json';freeze(source,raw);freeze(out/'input_full.verification.json',json_bytes(report))
    names=['scripts/campaign_held_inventory_continuation42.py','scripts/prepare_held_inventory_continuation42.py',
           'tests/test_held_inventory_continuation42.py','tests/fixtures/held_inventory42_rank113.txt',
           'tests/fixtures/held_inventory42_rank113.provenance.json','mmsearch/native_bridge.py',
           'mmsearch/search.py','mmsearch/verify.py','scripts/freeze_campaign_dictionary.py']
    hashes={}
    for name in names:
        data=(ROOT/name).read_bytes();hashes[name]=hashlib.sha256(data).hexdigest();freeze(out/'frozen'/name,data)
    binary=out/'native/flip_worker_fixed_cubes';data=DEFAULT_BINARY.read_bytes()
    assert hashlib.sha256(data).hexdigest()==EXPECTED_BINARY_SHA256
    freeze(binary,data);binary.chmod(0o555)
    freeze(out/'native/flip_worker_fixed_cubes.cpp',DEFAULT_BINARY.with_suffix('.cpp').read_bytes())
    controls=[]
    for index,headroom in enumerate([6,12]):
        folder=out/f'zero-step-control-{index}'
        command=['python3','scripts/campaign_held_inventory_continuation42.py','--output-dir',str(folder),
                 '--binary',str(binary),'--seconds','4','--phase-seconds','1','--phase-limit','1',
                 '--step-limit','0','--headroom',str(headroom)]
        command+=['--input',str(source),'--seed','2026110342605'] if index==0 else [
                 '--resume',str(out/'zero-step-control-0/checkpoint.json')]
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=4)
        freeze(out/f'zero-step-control-{index}.log',(result.stdout+result.stderr).encode())
        if result.returncode:raise RuntimeError('zero-step continuation control failed')
        stats=read_json((folder/'phase-000/walk.stats.json').read_bytes())
        checkpoint=read_json((folder/'checkpoint.json').read_bytes())
        assert stats['steps']==0 and stats['best_rank']==len(held)+len(residual)
        assert stats['raw_residual_best_rank']==len(residual) and not (folder/'WINNER.json').exists()
        assert checkpoint['completed_phase_count']==index+1
        controls.append(dict(path=str(folder),full_rank=stats['best_rank'],raw_rank=stats['raw_residual_best_rank'],
                             headroom=headroom,steps=0,completed_phase_count=index+1,exit_code=0))
    test=subprocess.run(['python3','-m','unittest','tests.test_held_inventory_continuation42'],cwd=ROOT,
                        capture_output=True,text=True,timeout=5)
    freeze(out/'tests.log',(test.stdout+test.stderr).encode())
    if test.returncode:raise RuntimeError('continuation tests failed')
    pilot=out.parent/'held-five42-pilot1'
    job=dict(id='held-five42-continuation1',cpu=1,memory_mb=768,seconds=1215,enabled=True,
             command=['python3','scripts/campaign_held_inventory_continuation42.py','--input',str(source),
                      '--pool',str(pilot/'verified'),'--binary',str(binary),'--output-dir',str(out.parent/'held-five42-continuation1'),
                      '--seconds','1200','--phase-seconds','300','--seed','2026110342605','--headroom','6',
                      '--plus-every','50000','--restart-every','100000000','--archive-size','16'])
    freeze(out/'proposed_job.json',json_bytes(job))
    old=ROOT/'scripts/campaign_held_inventory42.py'
    ready=dict(status='READY',search_launched=False,queue_modified=False,input_original_path=str(args.input.resolve()),
               input_sha256=hashlib.sha256(raw).hexdigest(),initial_full_rank=len(held)+len(residual),
               initial_residual_rank=len(residual),held_inventory_sha256=term_set_sha256(held),
               binary_sha256=EXPECTED_BINARY_SHA256,code_sha256=hashes,old_wrapper_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),
               test_count=9,test_exit_code=0,zero_step_controls=controls,proposed_job=str(out/'proposed_job.json'),
               selection='Even phases use best rank; odd phases choose a least-used diverse state within3 products of best. Frontier keeps up to32 states within6 products.',
               resume='--resume CHECKPOINT --output-dir NEW_DIRECTORY; source/binary/wrapper hashes and full15k checks are required again.',
               limits='Only exactF2 C3 sources with the same five singleton cubes and canonical rank>=92 congruent2mod3. Residual cap1000; headroom6 or12.',
               preparation_cpu_seconds=cpu()-start_cpu,preparation_wall_seconds=time.monotonic()-start)
    freeze(out/'READY.json',json_bytes(ready))
    checksums={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file()}
    freeze(out/'checksums.json',json_bytes(checksums))
    for f in out.rglob('*'):
        if f.is_file():f.chmod(0o555 if f==binary or f.name.startswith('native-') else 0o444)
    print(json.dumps(ready,indent=2))


if __name__=='__main__':main()
