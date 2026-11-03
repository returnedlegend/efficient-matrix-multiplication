"""Keep the source's fixed cube inventory outside a cyclic residual native walk.

Raw residual checkpoints are not full matrix algorithms. Only rejoined and
independently verified full certificates and adjusted global ranks are exported.
"""
import argparse
from collections import Counter
import hashlib
import math
from pathlib import Path
import random
import signal
import subprocess
import sys
import time
import json

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.native_bridge import _read_terms,canonical_terms,term_set_sha256
from mmsearch.search import encode_candidate,is_cyclic,orbit_counts
from mmsearch.verify import verify_candidate
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json

ROOT=Path(__file__).resolve().parents[1]
FROZEN_ROOT=ROOT/'artifacts/rl_campaign_20261102T210735Z/frozen/fixed-cubes-worker-v1'
DEFAULT_BINARY=FROZEN_ROOT/'native/flip_worker_fixed_cubes'
EXPECTED_BINARY_SHA256='d6d136e1b4539de619da2e7a6358a8425927218ecc2cc46b52e44ca4197211ab'


def atomic_json(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.tmp')
    temporary.write_bytes(json_bytes(value));temporary.replace(path)


def split_source(candidate,*,strict_n5=True):
    terms=set(canonical_terms(candidate));n=candidate['dimension']
    held={term for term in terms if term[0]==term[1]==term[2]}
    residual=terms-held
    if strict_n5 and (n!=5 or len(terms)!=93 or len(held)!=3):
        raise ValueError('held-cube campaign requires5x5 rank93 source with exactly3 fixed cubes')
    original=verify_candidate(candidate,random_trials=0)
    canonical=verify_candidate(encode_candidate(terms,n),random_trials=0)
    if not original['valid'] or not canonical['valid'] or not is_cyclic(terms):
        raise ValueError('source must be independently exact F2 matrix multiplication and cyclic')
    if not is_cyclic(residual) or any(a==b==c for a,b,c in residual) or residual&held:
        raise ValueError('held/residual partition violates complete nonfixed orbit inventory')
    return held,residual,dict(original=original,canonical=canonical)


def rejoin_verified(residual,held,*,n=5,max_residual_rank=96):
    residual=set(residual);held=set(held)
    if (len(residual)>max_residual_rank or not is_cyclic(residual)
            or any(a==b==c for a,b,c in residual) or residual&held
            or any(not a==b==c for a,b,c in held)):
        raise ValueError('raw residual violates C3/fixed0/rank/disjoint-inventory constraints')
    full=held^residual
    if len(full)!=len(held)+len(residual):
        raise ValueError('unexpected held/residual cancellation')
    candidate=encode_candidate(full,n)
    report=verify_candidate(candidate,random_trials=0)
    if not report['valid'] or report['exact_entries_checked']!=n**6:
        raise RuntimeError('rejoined residual failed independent full matrix tensor verification')
    return full,report


def inspect_export(prefix,output,metadata,held,*,n=5,target=92,max_residual_rank=96,
                   seen=None,counts=None,per_rank=32,final=False):
    """Raw residual -> verified full exports and separately adjusted global stats."""
    prefix=Path(prefix);output=Path(output);held=set(held)
    seen=seen if seen is not None else set();counts=counts if counts is not None else Counter()
    stats_path=prefix.with_suffix('.stats.json')
    if not stats_path.exists():
        if final:raise ValueError('missing final raw residual statistics')
        return None
    raw_before=stats_path.read_bytes();raw=read_json(raw_before)
    if (raw.get('dimension')!=n or raw.get('exact') is not False
            or raw.get('tensor_invariant_checked') is not True or raw.get('cyclic') is not True
            or raw.get('required_fixed_cubes')!=0 or raw.get('best_fixed_cubes')!=0
            or raw.get('current_fixed_cubes')!=0 or raw.get('max_rank')!=max_residual_rank
            or raw.get('target_rank')!=target-len(held)):
        raise ValueError('raw residual metadata violates arbitrary-tensor/fixed0/cyclic/rank settings')
    if 'native_seed' in metadata and raw.get('seed')!=metadata['native_seed']:
        raise ValueError('raw residual seed mismatch')
    paths=[prefix.with_suffix('.best.txt'),prefix.with_suffix('.current.txt'),
           *sorted(prefix.with_suffix('.archive').glob('*.txt'))]
    ranks={};reports={};full_snapshots={};best_record=None;winner=(output/'WINNER.json').exists()
    for path in paths:
        if not path.exists():
            if final and path in paths[:2]:raise ValueError('missing final residual best/current')
            continue
        residual=_read_terms(path,n)
        full,report=rejoin_verified(residual,held,n=n,max_residual_rank=max_residual_rank)
        rank=len(full);h=term_set_sha256(full);ranks[str(path)]=rank;reports[str(path)]=report
        full_snapshots[str(path)]=full
        if h in seen or (rank>target and counts[rank]>=per_rank):
            continue
        candidate=encode_candidate(full,n,method='held-fixed-cube-inventory-native',parent=metadata,
                    held_cube_terms=sorted(held),held_inventory_sha256=term_set_sha256(held),
                    residual_term_set_sha256=term_set_sha256(residual),raw_residual_path=str(path),
                    essential_rank=rank,status='verified_target' if rank<=target else 'research_checkpoint',
                    target_reached=rank<=target,orbit_profile=orbit_counts(full))
        payload=json_bytes(candidate);destination=output/'verified'/(h+'.json')
        freeze(destination,payload)
        verification=output/'verification'/(h+'.verification.json');freeze(verification,json_bytes(report))
        digest=hashlib.sha256(payload).hexdigest()
        freeze(output/'verification'/(h+'.sha256'),(digest+'  '+destination.name+'\n').encode())
        seen.add(h);counts[rank]+=1
        record=dict(path=str(destination),rank=rank,sha256=digest,verification_path=str(verification))
        if path==paths[0]:best_record=record
        if rank<=target and not winner:
            freeze(output/'WINNER.json',payload);freeze(output/'WINNER.verification.json',json_bytes(report))
            freeze(output/'WINNER.sha256',(digest+'  WINNER.json\n').encode())
            freeze(output/'WINNER.verify.py',(ROOT/'mmsearch/verify.py').read_bytes());winner=True
    if stats_path.read_bytes()!=raw_before:
        if final:raise ValueError('raw statistics changed after native exit')
        return None
    best=ranks.get(str(paths[0]));current=ranks.get(str(paths[1]))
    if (best is None or current is None or best!=raw.get('best_rank',-1)+len(held)
            or current!=raw.get('current_rank',-1)+len(held)):
        if final:raise ValueError('final residual ranks disagree with raw statistics')
        return None
    adjusted=dict(raw)
    adjusted.update(engine='held-cube-inventory-global-adjusted-v1',input=metadata.get('full_source_snapshot'),
                    rank_semantics='full matrix algorithm with held cubes reattached',
                    raw_residual_stats_path=str(stats_path),raw_residual_stats_sha256=hashlib.sha256(raw_before).hexdigest(),
                    raw_residual_best_rank=raw['best_rank'],raw_residual_current_rank=raw['current_rank'],
                    raw_residual_max_rank=raw['max_rank'],raw_residual_target_rank=raw['target_rank'],raw_exact=False,
                    held_cube_count=len(held),held_cube_terms=sorted(held),held_inventory_sha256=term_set_sha256(held),
                    best_rank=best,current_rank=current,max_rank=max_residual_rank+len(held),
                    target_rank=target,target_reached=best<=target,exact=True,
                    required_fixed_cubes=len(held),best_fixed_cubes=len(held),current_fixed_cubes=len(held),
                    independent_full_verification=True,exact_entries_checked=n**6,
                    global_best_verification=reports[str(paths[0])],global_current_verification=reports[str(paths[1])])
    adjusted['raw_residual_history']=raw.get('history',[])
    adjusted['history']=[dict(entry,rank=entry['rank']+len(held)) for entry in raw.get('history',[])]
    # The raw native prefix is NEVER walk. Only these verified adjusted ranks
    # are exposed under the status/supervisor's conventional walk.stats name.
    for index,label in ((0,'best'),(1,'current')):
        destination=prefix.parent/f'walk.{label}.txt';temporary=destination.with_name(destination.name+'.tmp')
        temporary.write_text(''.join(f'{a} {b} {c}\n' for a,b,c in sorted(full_snapshots[str(paths[index])])))
        temporary.replace(destination)
    atomic_json(prefix.parent/'walk.stats.json',adjusted)
    atomic_json(output/'latest_stats.json',dict(phase=metadata.get('phase'),stats=adjusted))
    if best_record:
        pointer=output/'best_verified.json'
        if not pointer.exists() or best_record['rank']<read_json(pointer.read_bytes())['rank']:
            atomic_json(pointer,best_record)
    return dict(winner=winner,adjusted_stats=adjusted,best_record=best_record,
                verified_portfolio_size=len(seen),retained_per_rank={str(k):v for k,v in sorted(counts.items())})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--pool',type=Path)
    p.add_argument('--binary',type=Path,default=DEFAULT_BINARY)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=1800)
    p.add_argument('--phase-seconds',type=float,default=600)
    p.add_argument('--seed',type=int,default=0)
    p.add_argument('--headroom',type=int,default=6)
    p.add_argument('--plus-every',type=int,default=50000)
    p.add_argument('--restart-every',type=int,default=100000000)
    p.add_argument('--archive-size',type=int,default=16)
    args=p.parse_args()
    if (not math.isfinite(args.seconds) or args.seconds<=2 or not math.isfinite(args.phase_seconds)
            or args.phase_seconds<=0 or not 0<=args.headroom<=16 or args.seed<0 or args.plus_every<1
            or args.restart_every<1 or not 1<=args.archive_size<=32):
        p.error('invalid bounded run settings')
    started=time.monotonic();deadline=started+args.seconds
    output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=False)
    raw_binary=args.binary.read_bytes();binary_sha=hashlib.sha256(raw_binary).hexdigest()
    if binary_sha!=EXPECTED_BINARY_SHA256:
        raise ValueError('worker must match the frozen validated fixed-cube binary')
    binary=output/'frozen'/('native-'+binary_sha);freeze(binary,raw_binary);binary.chmod(0o555)
    first=args.input.resolve();others=[]
    if args.pool:
        if not args.pool.is_dir():raise ValueError('pool must be a certificate directory')
        others=sorted({path.resolve() for path in args.pool.glob('*.json') if path.is_file()}-{first})
        random.Random(args.seed).shuffle(others)
    parents=[];held_inventory=None
    for path in [first,*others]:
        raw=path.read_bytes();candidate=read_json(raw);held,residual,report=split_source(candidate)
        if held_inventory is None:held_inventory=held
        if held!=held_inventory:raise ValueError('pool parents must preserve the identical held cube inventory')
        h=hashlib.sha256(raw).hexdigest();snapshot=output/'sources'/(h+'.json')
        if not snapshot.exists():
            freeze(snapshot,raw);freeze(output/'sources'/(h+'.verification.json'),json_bytes(report))
        parents.append(dict(source_path=str(path),source_sha256=h,full_source_snapshot=str(snapshot),
                            held=held,residual=residual))
    freeze(output/'held_inventory.json',json_bytes(dict(cube_terms=sorted(held_inventory),
           inventory_sha256=term_set_sha256(held_inventory),note='These exact cubes remain external and unchanged.')))
    names=['scripts/campaign_held_cubes.py','mmsearch/native_bridge.py','mmsearch/search.py','mmsearch/verify.py',
           'scripts/freeze_campaign_dictionary.py']
    code={name:(ROOT/name).read_bytes() for name in names}
    for name,raw in code.items():freeze(output/'frozen'/name,raw)
    cpp=(FROZEN_ROOT/'native/flip_worker_fixed_cubes.cpp').read_bytes()
    freeze(output/'frozen/native/flip_worker_fixed_cubes.cpp',cpp)
    manifest=dict(binary_sha256=binary_sha,worker_source_sha256=hashlib.sha256(cpp).hexdigest(),
                  code_sha256={name:hashlib.sha256(raw).hexdigest() for name,raw in code.items()},
                  held_cube_terms=sorted(held_inventory),global_target=92,residual_target=92-len(held_inventory),
                  sources=[{k:v for k,v in parent.items() if k not in ('held','residual')} for parent in parents],
                  note='Residual arbitrary-tensor states are not full algorithms. Count3 held inventory permits90, not92; no global impossibility claim.')
    freeze(output/'manifest.json',json_bytes(manifest))
    stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    seen=set();counts=Counter();phases=[]
    while not stopped and deadline-time.monotonic()>2:
        phase=len(phases);parent=parents[phase%len(parents)]
        folder=output/f'phase-{phase:03d}';folder.mkdir();prefix=folder/'residual_walk'
        source=folder/'residual_input.txt';freeze(source,''.join(f'{a} {b} {c}\n' for a,b,c in sorted(parent['residual'])).encode())
        budget=min(args.phase_seconds,deadline-time.monotonic()-2);maximum=len(parent['residual'])+args.headroom
        native_seed=args.seed+phase*1009;res_target=92-len(parent['held'])
        command=[str(binary),'--input',str(source),'--output',str(prefix),'--n','5','--target',str(res_target),
                 '--max-rank',str(maximum),'--seed',str(native_seed),'--steps','1000000000000',
                 '--seconds',str(budget),'--checkpoint-seconds','15','--archive-size',str(args.archive_size),
                 '--archive-every','1000','--plus-every',str(args.plus_every),'--restart-every',str(args.restart_every),
                 '--cyclic','--fixed-cubes','0','--allow-arbitrary']
        meta=dict(phase=phase,full_source_snapshot=parent['full_source_snapshot'],source_path=parent['source_path'],
                  source_sha256=parent['source_sha256'],held_cube_terms=sorted(parent['held']),
                  held_inventory_sha256=term_set_sha256(parent['held']),initial_residual_rank=len(parent['residual']),
                  initial_global_rank=len(parent['residual'])+len(parent['held']),native_seed=native_seed,
                  max_residual_rank=maximum,binary_sha256=binary_sha,wrapper_sha256=manifest['code_sha256'][names[0]],command=command)
        freeze(folder/'manifest.json',json_bytes(meta))
        kwargs=dict(n=5,target=92,max_residual_rank=maximum,seen=seen,counts=counts)
        with (folder/'worker.log').open('x') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT);last_scan=0
            try:
                while process.poll() is None and not stopped:
                    if time.monotonic()-last_scan>=15:
                        last_scan=time.monotonic();result=inspect_export(prefix,output,meta,parent['held'],**kwargs)
                        if result:stopped=stopped or result['winner']
                    time.sleep(.2)
            finally:
                if process.poll() is None:process.terminate()
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        result=inspect_export(prefix,output,meta,parent['held'],final=True,**kwargs)
        if process.returncode!=0:raise RuntimeError(f'residual worker failed({process.returncode}); inspect{folder}')
        stopped=stopped or result['winner'];freeze(folder/'final_global_stats.json',json_bytes(result['adjusted_stats']))
        phases.append(dict(phase=phase,exit_code=process.returncode,global_best_rank=result['adjusted_stats']['best_rank'],
                           residual_best_rank=result['adjusted_stats']['raw_residual_best_rank']))
        atomic_json(output/'summary.json',dict(phases=phases,winner=(output/'WINNER.json').exists(),
                    retained_per_rank={str(k):v for k,v in sorted(counts.items())},elapsed_seconds=time.monotonic()-started))
    atomic_json(output/'summary.json',dict(phases=phases,winner=(output/'WINNER.json').exists(),stopped=stopped,
                retained_per_rank={str(k):v for k,v in sorted(counts.items())},elapsed_seconds=time.monotonic()-started))
    print(json.dumps(dict(phases=len(phases),winner=(output/'WINNER.json').exists(),stopped=stopped)))


if __name__=='__main__':
    main()
