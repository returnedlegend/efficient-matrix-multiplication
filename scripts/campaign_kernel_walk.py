"""Bounded exact fixed-pair kernel walk; no global or restricted UNSAT claim."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.free_factor_kernel import (decode_checked,native_input,pair_column,prepare_system,validate_circuit)
from mmsearch.free_factor_sat import ORIENTATIONS,audit
from mmsearch.search import decode_candidate
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json

ROOT=Path(__file__).resolve().parents[1]


def atomic_json(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.tmp');tmp.write_bytes(json_bytes(value));tmp.replace(path)


def read_vectors(path,p,width):
    lines=Path(path).read_text().splitlines()
    if len(lines)!=p or any(len(line.split())!=1 or not line.strip().isdecimal() for line in lines):
        raise ValueError('malformed or incomplete raw W-vector model')
    vectors=[int(line) for line in lines]
    if any(not 0<=value<1<<width for value in vectors):
        raise ValueError('raw W vector outside strict binary mask width')
    return vectors


def export_checkpoints(prefix,output,system,metadata,*,target=92,seen=None,counts=None,final=False):
    prefix=Path(prefix);output=Path(output);seen=seen if seen is not None else set()
    counts=counts if counts is not None else Counter();n=system['metadata']['dimension'];p=len(system['pairs'])
    stats_path=prefix.with_suffix('.stats.json')
    if not stats_path.exists():
        if final:raise ValueError('missing final native W-model statistics')
        return None
    raw_bytes=stats_path.read_bytes();stats=read_json(raw_bytes)
    if (stats.get('dimension')!=n or stats.get('pair_count')!=p or stats.get('linear_exact') is not True
            or stats.get('tensor_invariant_checked') is not True or stats.get('target_rank')!=target
            or stats.get('full_matrix_verified') is not False):
        raise ValueError('native model statistics violate full PW=Y contract')
    if 'native_seed' in metadata and stats.get('seed')!=metadata['native_seed']:
        raise ValueError('native model seed mismatch')
    paths=[Path(str(prefix)+'.best.w.txt'),Path(str(prefix)+'.current.w.txt'),
           *sorted(prefix.with_suffix('.archive').glob('*.w.txt'))]
    ranks={};reports={};full={};best_record=None;winner=(output/'WINNER.json').exists()
    for path in paths:
        if not path.exists():
            if final and path in paths[:2]:raise ValueError('missing final W-model best/current')
            continue
        vectors=read_vectors(path,p,n*n)
        raw_model=''.join(str(value)+'\n' for value in vectors).encode();h=hashlib.sha256(raw_model).hexdigest()
        candidate,report=decode_checked(system,vectors,dict(metadata,method='exact-fixed-pair-kernel-circuit-walk',
                         orientation=system['metadata']['orientation'],model_sha256=h,
                         finite_family='supplied fixed pairs; arbitrary integer-bit free vector per group'))
        rank=report['rank'];ranks[str(path)]=rank;reports[str(path)]=report;full[str(path)]=candidate
        if h in seen or (rank>target and counts[rank]>=32):continue
        payload=json_bytes(candidate);destination=output/'verified'/(h+'.json')
        freeze(destination,payload);freeze(output/'models'/(h+'.w.txt'),raw_model)
        verification=output/'verification'/(h+'.verification.json');freeze(verification,json_bytes(report))
        digest=hashlib.sha256(payload).hexdigest()
        freeze(output/'verification'/(h+'.sha256'),(digest+'  '+destination.name+'\n').encode())
        seen.add(h);counts[rank]+=1
        record=dict(path=str(destination),sha256=digest,rank=rank,model_sha256=h,verification_path=str(verification))
        if path==paths[0]:best_record=record
        if rank<=target and not winner:
            freeze(output/'WINNER.json',payload);freeze(output/'WINNER.verification.json',json_bytes(report))
            freeze(output/'WINNER.sha256',(digest+'  WINNER.json\n').encode())
            freeze(output/'WINNER.verify.py',(ROOT/'mmsearch/verify.py').read_bytes());winner=True
    if stats_path.read_bytes()!=raw_bytes:
        if final:raise ValueError('raw W-model statistics changed after exit')
        return None
    best=ranks.get(str(paths[0]));current=ranks.get(str(paths[1]))
    if best!=stats.get('best_rank') or current!=stats.get('current_rank'):
        if final:raise ValueError('native active-group counts disagree with decoded essential ranks')
        return None
    adjusted=dict(stats,engine='kernel-walk-full-matrix-verified-v1',exact=True,full_matrix_verified=True,
                  independent_full_verification=True,exact_entries_checked=n**6,
                  orientation=system['metadata']['orientation'],rank_semantics='verified full matrix algorithm active-group count',
                  raw_model_stats_path=str(stats_path),raw_model_stats_sha256=hashlib.sha256(raw_bytes).hexdigest(),
                  global_best_verification=reports[str(paths[0])],global_current_verification=reports[str(paths[1])])
    for index,label in ((0,'best'),(1,'current')):
        destination=prefix.parent/f'walk.{label}.txt';tmp=destination.with_name(destination.name+'.tmp')
        tmp.write_text(''.join(f'{a} {b} {c}\n' for a,b,c in decode_candidate(full[str(paths[index])],n)));tmp.replace(destination)
    atomic_json(prefix.parent/'walk.stats.json',adjusted);atomic_json(output/'latest_stats.json',adjusted)
    if best_record:
        pointer=output/'best_verified.json'
        if not pointer.exists() or best_record['rank']<read_json(pointer.read_bytes())['rank']:
            atomic_json(pointer,best_record)
    return dict(winner=winner,stats=adjusted,verified=len(seen),retained_per_rank={str(k):v for k,v in sorted(counts.items())})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dictionary',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--orientation',choices=ORIENTATIONS,default='wu')
    parser.add_argument('--outdir','--output-dir',dest='outdir',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=1800)
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--headroom',type=int,default=6)
    parser.add_argument('--plus-every',type=int,default=500)
    parser.add_argument('--restart-every',type=int,default=100000000)
    parser.add_argument('--archive-size',type=int,default=16)
    parser.add_argument('--profile',choices=('mixed','short','wide'),default='mixed')
    parser.add_argument('--max-circuits',type=int,default=50000)
    parser.add_argument('--no-combos',action='store_true')
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--prepared',type=Path)
    parser.add_argument('--binary',type=Path,default=ROOT/'native/free_factor_kernel_worker')
    args=parser.parse_args()
    if (not math.isfinite(args.seconds) or args.seconds<=2 or args.seed<0 or not 0<=args.headroom<=32
            or args.plus_every<1 or args.restart_every<1 or not 1<=args.archive_size<=16):
        parser.error('invalid finite wall budget or bounded native settings')
    started=time.monotonic();output=args.outdir.resolve();output.mkdir(parents=True,exist_ok=False)
    dictionary_raw=args.dictionary.read_bytes();baseline_raw=args.baseline.read_bytes()
    dictionary=read_json(dictionary_raw);baseline=read_json(baseline_raw)
    provenance=dict(dictionary_path=str(args.dictionary.resolve()),dictionary_sha256=hashlib.sha256(dictionary_raw).hexdigest(),
                    baseline_path=str(args.baseline.resolve()),baseline_sha256=hashlib.sha256(baseline_raw).hexdigest(),
                    orientation=args.orientation,seed=args.seed)
    freeze(output/'inputs/dictionary.json',dictionary_raw);freeze(output/'inputs/baseline.json',baseline_raw)
    if args.prepared:
        prepared=args.prepared.resolve();previous=read_json((prepared/'preparation.json').read_bytes())
        for key in ('dictionary_sha256','baseline_sha256','orientation'):
            if previous['provenance'][key]!=provenance[key]:raise ValueError('prepared inputs/orientation mismatch')
        for name,expected in previous['artifacts_sha256'].items():
            if hashlib.sha256((prepared/name).read_bytes()).hexdigest()!=expected:
                raise ValueError('prepared artifact checksum mismatch: '+name)
        system=read_json((prepared/'system.json').read_bytes());circuits=read_json((prepared/'circuits.json').read_bytes())
        columns=[pair_column(pair,25) for pair in system['pairs']]
        for circuit in circuits:validate_circuit(columns,circuit['support'])
        summary=previous['circuits']
        decode_checked(system,system['baseline_vectors'])
        if hashlib.sha256(native_input(system,circuits)).hexdigest()!=previous['input_sha256']:
            raise ValueError('prepared native input does not match reconstructed system/circuits')
    else:
        system,circuits,summary=prepare_system(dictionary,baseline,dimension=5,orientation=args.orientation,
                                              max_circuits=args.max_circuits,seed=args.seed,combos=not args.no_combos)
    if (system['metadata']['dimension']!=5 or system['metadata']['baseline']['canonical_rank']!=93
            or system['metadata']['orientation']!=args.orientation):
        raise ValueError('main kernel campaign requires verified5x5 rank93 baseline')
    input_raw=native_input(system,circuits)
    prepared_artifacts={'system.json':json_bytes(system),'system.audit.json':json_bytes(audit(system)),
                        'circuits.json':json_bytes(circuits),'kernel_input.txt':input_raw}
    for name,data in prepared_artifacts.items():freeze(output/name,data)
    names=['scripts/campaign_kernel_walk.py','mmsearch/free_factor_kernel.py','mmsearch/free_factor_sat.py',
           'mmsearch/recombine.py','mmsearch/recombine_sat.py','mmsearch/verify.py','mmsearch/search.py',
           'scripts/freeze_campaign_dictionary.py','native/free_factor_kernel_worker.cpp']
    code={name:(ROOT/name).read_bytes() for name in names}
    for name,raw in code.items():freeze(output/'code'/name,raw)
    preparation=dict(provenance=provenance,circuits=summary,
                     baseline_active_groups=[g for g,w in enumerate(system['baseline_vectors']) if w],
                     code_sha256={name:hashlib.sha256(raw).hexdigest() for name,raw in code.items()},
                     artifacts_sha256={name:hashlib.sha256(data).hexdigest() for name,data in prepared_artifacts.items()},
                     input_sha256=hashlib.sha256(input_raw).hexdigest(),
                     preparation_seconds=time.monotonic()-started,
                     scope='Known kernel moves in a finite fixed-pair family. Failure is not global or restricted UNSAT.')
    freeze(output/'preparation.json',json_bytes(preparation))
    if args.prepare_only:
        print(json.dumps(dict(status='PREPARED',**summary,preparation_seconds=time.monotonic()-started)));return 0
    binary=args.binary.resolve()
    if not binary.exists():
        subprocess.run(['g++','-std=c++17','-O3','-DNDEBUG',str(ROOT/'native/free_factor_kernel_worker.cpp'),'-o',str(binary)],check=True,timeout=20)
    binary_raw=binary.read_bytes();binary_sha=hashlib.sha256(binary_raw).hexdigest();frozen=output/'native-worker'
    freeze(frozen,binary_raw);frozen.chmod(0o555)
    remaining=args.seconds-(time.monotonic()-started)-2
    if remaining<=0:
        atomic_json(output/'summary.json',dict(status='BUDGET_EXHAUSTED',reason='preparation consumed wall budget'));return 0
    prefix=output/'phase-000/kernel_walk';prefix.parent.mkdir()
    command=[str(frozen),'--input',str(output/'kernel_input.txt'),'--output',str(prefix),'--seconds',str(remaining),
             '--seed',str(args.seed),'--target','92','--headroom',str(args.headroom),'--plus-every',str(args.plus_every),
             '--restart-every',str(args.restart_every),'--archive-size',str(args.archive_size),'--profile',args.profile,
             '--memory-mb','512']
    meta=dict(native_seed=args.seed,binary_sha256=binary_sha,source_sha256=preparation['code_sha256']['native/free_factor_kernel_worker.cpp'],
              provenance=provenance,preparation_sha256=hashlib.sha256(json_bytes(preparation)).hexdigest(),command=command)
    freeze(output/'manifest.json',json_bytes(meta));stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    seen=set();counts=Counter()
    with (output/'worker.log').open('x') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT);last_scan=0
        try:
            while process.poll() is None and not stopped:
                if time.monotonic()-last_scan>=15:
                    last_scan=time.monotonic();result=export_checkpoints(prefix,output,system,meta,seen=seen,counts=counts)
                    if result:stopped=stopped or result['winner']
                time.sleep(.2)
        finally:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:process.kill();process.wait()
    result=export_checkpoints(prefix,output,system,meta,seen=seen,counts=counts,final=True)
    atomic_json(output/'summary.json',dict(exit_code=process.returncode,winner=result['winner'],
                best_rank=result['stats']['best_rank'],current_rank=result['stats']['current_rank'],
                attempted_moves=result['stats']['steps'],verified=result['verified'],retained_per_rank=result['retained_per_rank'],
                elapsed_seconds=time.monotonic()-started,
                scope='Finite known kernel-circuit walk only; no global or restricted UNSAT claim.'))
    if process.returncode!=0:raise RuntimeError('kernel worker failed; inspect worker.log')
    print(json.dumps(dict(best_rank=result['stats']['best_rank'],verified=result['verified'],winner=result['winner'])))


if __name__=='__main__':
    main()
