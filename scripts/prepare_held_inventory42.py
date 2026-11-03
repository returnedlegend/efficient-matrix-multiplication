"""Freeze a held-five pilot and zero-step controls without starting a search."""
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
from mmsearch.native_bridge import term_set_sha256
from mmsearch.search import encode_candidate,naive_terms
from mmsearch.verify import verify_candidate
from scripts.campaign_held_inventory42 import (DEFAULT_BINARY,EXPECTED_BINARY_SHA256,
                                               inspect_export,split_source)
from scripts.freeze_campaign_dictionary import freeze,json_bytes


def cpu():
    return sum(r.ru_utime+r.ru_stime for r in
               [resource.getrusage(resource.RUSAGE_SELF),resource.getrusage(resource.RUSAGE_CHILDREN)])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();started=time.monotonic();start_cpu=cpu()
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    source=encode_candidate(naive_terms(5),5,method='classic-naive-reference',novel=False,
                            note='Five singleton diagonal cubes held outside a C3 residual; preparation only.')
    held,residual,verification=split_source(source)
    baseline=out/'standard125_f2.json';freeze(baseline,json_bytes(source))
    freeze(out/'standard125.verification.json',json_bytes(verification))
    freeze(out/'held_inventory.json',json_bytes(dict(cube_terms=sorted(held),
           term_set_sha256=term_set_sha256(held),count=5,immutable=True)))
    residual_file=out/'residual120.txt'
    freeze(residual_file,''.join(f'{a} {b} {c}\n' for a,b,c in sorted(residual)).encode())
    raw_residual_report=verify_candidate(encode_candidate(residual,5),random_trials=0)
    assert not raw_residual_report['valid']
    freeze(out/'raw_residual_not_matrix_algorithm.json',json_bytes(raw_residual_report))
    binary_bytes=DEFAULT_BINARY.read_bytes()
    assert hashlib.sha256(binary_bytes).hexdigest()==EXPECTED_BINARY_SHA256
    binary=out/'native/flip_worker_fixed_cubes';freeze(binary,binary_bytes);binary.chmod(0o555)
    names=['scripts/campaign_held_inventory42.py','scripts/prepare_held_inventory42.py',
           'tests/test_held_inventory42.py','mmsearch/native_bridge.py','mmsearch/search.py',
           'mmsearch/verify.py','scripts/freeze_campaign_dictionary.py']
    code={}
    for name in names:
        raw=(ROOT/name).read_bytes();code[name]=hashlib.sha256(raw).hexdigest()
        freeze(out/'frozen'/name,raw)
    old_cpp=DEFAULT_BINARY.with_suffix('.cpp')
    freeze(out/'native/flip_worker_fixed_cubes.cpp',old_cpp.read_bytes())
    control=out/'zero-step-control';control.mkdir();prefix=control/'residual_walk'
    native_command=[str(binary),'--input',str(residual_file),'--output',str(prefix),
                    '--n','5','--target','87','--max-rank','126','--seed','421205',
                    '--steps','0','--seconds','0','--archive-size','16','--plus-every','50000',
                    '--restart-every','100000000','--cyclic','--fixed-cubes','0','--allow-arbitrary']
    done=subprocess.run(native_command,capture_output=True,text=True,timeout=2,check=True)
    freeze(control/'native.log',(done.stdout+done.stderr).encode())
    exported=inspect_export(prefix,control,dict(native_seed=421205,
                           full_source_snapshot=str(baseline)),held,max_residual_rank=126,final=True)
    assert exported['adjusted_stats']['best_rank']==125 and not exported['winner']
    freeze(control/'control.json',json_bytes(dict(command=native_command,exit_code=done.returncode,
           steps=exported['adjusted_stats']['steps'],raw_rank=120,full_rank=125,
           residual_target=87,full_target=92,independent_entries=15625,winner=False)))
    test=subprocess.run([sys.executable,'-m','unittest','tests.test_held_inventory42'],cwd=ROOT,
                        capture_output=True,text=True,timeout=5)
    freeze(out/'tests.log',(test.stdout+test.stderr).encode())
    if test.returncode:raise RuntimeError('held inventory tests failed; inspect tests.log')
    pilot_out=out.parent/'held-five42-pilot1'
    command=['python3','scripts/campaign_held_inventory42.py','--input',str(baseline),
             '--binary',str(binary),'--output-dir',str(pilot_out),'--seconds','1200',
             '--phase-seconds','300','--seed','2026110342505','--headroom','6',
             '--plus-every','50000','--restart-every','100000000','--archive-size','16']
    freeze(out/'proposed_job.json',json_bytes(dict(id='held-five42-pilot1',cpu=1,memory_mb=768,
           seconds=1215,enabled=True,command=command)))
    ready=dict(status='READY',search_launched=False,queue_modified=False,dimension=5,field=2,
               held_cube_count=5,held_inventory_sha256=term_set_sha256(held),
               residual_term_set_sha256=term_set_sha256(residual),initial_full_rank=125,
               initial_residual_rank=120,global_target=92,residual_target=87,
               max_global_rank=131,max_residual_rank=126,binary_sha256=EXPECTED_BINARY_SHA256,
               worker_source_sha256=hashlib.sha256(old_cpp.read_bytes()).hexdigest(),code_sha256=code,
               test_count=6,test_exit_code=test.returncode,zero_step_control=str(control/'control.json'),
               proposed_job=str(out/'proposed_job.json'),scope='Five exact held cubes; more constrained than fixed-count5. No rank92 existence evidence.',
               measured_preparation_cpu_seconds=cpu()-start_cpu,measured_preparation_wall_seconds=time.monotonic()-started)
    freeze(out/'READY.json',json_bytes(ready))
    checksums={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest()
               for f in out.rglob('*') if f.is_file()}
    freeze(out/'checksums.json',json_bytes(checksums))
    for f in out.rglob('*'):
        if f.is_file():f.chmod(0o555 if f==binary else 0o444)
    print(json.dumps(ready,indent=2))


if __name__=='__main__':main()
