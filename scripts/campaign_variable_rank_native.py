"""Bounded native diversification from exact 5x5 F2 rank93..100 baselines.

Rank95 or rank93 reached from AlphaTensor96 is branch progress, not a new
record. Only an independently verified rank<=92 certificate meets the target.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import signal
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.native_bridge import _read_terms,canonical_terms,term_set_sha256
from mmsearch.search import encode_candidate,is_cyclic,orbit_counts
from mmsearch.verify import verify_candidate
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json

ROOT=Path(__file__).resolve().parents[1]


def atomic_json(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.tmp')
    tmp.write_bytes(json_bytes(value));tmp.replace(path)


def validate_seed(candidate,*,strict_n5=True,cyclic=False):
    terms=canonical_terms(candidate);n=candidate['dimension']
    if strict_n5 and (n!=5 or not 93<=len(terms)<=100):
        raise ValueError('main campaign requires dimension5 and essential rank93..100')
    report=verify_candidate(candidate,random_trials=0)
    canonical_report=verify_candidate(encode_candidate(terms,n),random_trials=0)
    if not report['valid'] or not canonical_report['valid'] or report['exact_entries_checked']!=n**6:
        raise ValueError('source failed independent exhaustive F2 verification')
    if cyclic and not is_cyclic(terms):
        raise ValueError('cyclic mode requires complete source orbits')
    return terms,dict(original=report,canonical=canonical_report)


def drain_verified(prefix,output,metadata,*,n=5,target=92,input_rank=96,max_rank=102,
                   cyclic=False,seen=None,counts=None,per_rank=32):
    """Drain final best/current/all archives; exactness precedes rank retention."""
    prefix=Path(prefix);output=Path(output)
    seen=seen if seen is not None else set();counts=counts if counts is not None else Counter()
    paths=[prefix.with_suffix('.best.txt'),prefix.with_suffix('.current.txt'),
           *sorted(prefix.with_suffix('.archive').glob('*.txt'))]
    winner=(output/'WINNER.json').exists();best_record=None;checked=0
    for path in paths:
        if not path.exists():
            continue
        terms=_read_terms(path,n);rank=len(terms);h=term_set_sha256(terms)
        if rank>max_rank or (cyclic and not is_cyclic(terms)):
            raise ValueError('native candidate violates rank or cyclic limits')
        if h in seen:
            continue
        value=encode_candidate(terms,n,method='variable-rank-native-checkpoint',parent=metadata,
                               source_essential_rank=input_rank,term_set_sha256=h,
                               status='verified_target' if rank<=target else
                                      ('branch_progress' if rank<input_rank else 'verified_seed_rank_state'),
                               meets_campaign_target=rank<=target,
                               orbit_profile=orbit_counts(terms) if is_cyclic(terms) else None)
        report=verify_candidate(value,random_trials=0);checked+=1
        if not report['valid'] or report['exact_entries_checked']!=n**6:
            raise RuntimeError('native checkpoint failed independent exhaustive verification')
        if rank>input_rank or (rank>target and counts[rank]>=per_rank):
            continue
        raw=json_bytes(value);name=h+'.json';frozen=output/'verified'/name
        freeze(frozen,raw)
        verification=output/'verification'/(h+'.verification.json')
        freeze(verification,json_bytes(report))
        digest=hashlib.sha256(raw).hexdigest()
        freeze(output/'verification'/(h+'.sha256'),(digest+'  '+name+'\n').encode())
        seen.add(h);counts[rank]+=1
        record=dict(path=str(frozen),rank=rank,sha256=digest,verification_path=str(verification),
                    source_essential_rank=input_rank,meets_campaign_target=rank<=target)
        if path==paths[0]:
            best_record=record
        if rank<=target and not winner:
            freeze(output/'WINNER.json',raw);freeze(output/'WINNER.verification.json',json_bytes(report))
            freeze(output/'WINNER.sha256',(digest+'  WINNER.json\n').encode())
            freeze(output/'WINNER.verify.py',(ROOT/'mmsearch/verify.py').read_bytes())
            winner=True;break
    if best_record:
        pointer=output/'best_verified.json'
        if not pointer.exists() or best_record['rank']<read_json(pointer.read_bytes())['rank']:
            atomic_json(pointer,best_record)
    return dict(winner=winner,best_record=best_record,independent_checks=checked,
                verified_portfolio_size=len(seen),retained_per_rank={str(k):v for k,v in sorted(counts.items())})


def validate_final_stats(prefix,metadata,*,n=5):
    prefix=Path(prefix);stats=read_json(prefix.with_suffix('.stats.json').read_bytes())
    expected=dict(dimension=n,seed=metadata['native_seed'],max_rank=metadata['max_rank'],target_rank=92)
    for key,value in expected.items():
        if type(stats.get(key)) is not int or stats[key]!=value:
            raise ValueError('native final metadata mismatch: '+key)
    if (stats.get('exact') is not True or stats.get('tensor_invariant_checked') is not True
            or stats.get('cyclic') is not metadata['cyclic']):
        raise ValueError('native final exactness/cyclic metadata mismatch')
    best=len(_read_terms(prefix.with_suffix('.best.txt'),n));current=len(_read_terms(prefix.with_suffix('.current.txt'),n))
    if (stats.get('best_rank')!=best or stats.get('current_rank')!=current
            or not 0<best<=metadata['source_essential_rank'] or not best<=current<=metadata['max_rank']):
        raise ValueError('native final essential ranks disagree with metadata/limits')
    return stats


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,default=ROOT/'native/flip_worker_cyclic')
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--pool',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=1800)
    p.add_argument('--phase-seconds',type=float,default=600)
    p.add_argument('--seed',type=int,default=0)
    p.add_argument('--headroom',type=int,default=6)
    p.add_argument('--plus-every',type=int,default=50000)
    p.add_argument('--restart-every',type=int,default=100000000)
    p.add_argument('--archive-size',type=int,default=16)
    p.add_argument('--cyclic',action='store_true')
    args=p.parse_args()
    if (not math.isfinite(args.seconds) or args.seconds<=2 or not math.isfinite(args.phase_seconds)
            or args.phase_seconds<=0 or args.headroom<0 or args.plus_every<1 or args.restart_every<1
            or not 1<=args.archive_size<=32 or args.seed<0):
        p.error('invalid positive budgets/frequencies or bounded archive settings')
    started=time.monotonic();deadline=started+args.seconds
    output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=False)
    pool=args.pool.resolve()
    if not pool.is_dir():
        raise ValueError('pool must be a directory of certificates')
    first=args.input.resolve();others=sorted({path.resolve() for path in pool.glob('*.json') if path.is_file()}-{first})
    random.Random(args.seed).shuffle(others)
    parents=[]
    for path in [first,*others]:
        raw=path.read_bytes();candidate=read_json(raw)
        terms,report=validate_seed(candidate,cyclic=args.cyclic)
        if len(terms)+args.headroom>109:
            raise ValueError('source essential rank plus headroom must not exceed109')
        h=hashlib.sha256(raw).hexdigest()
        snapshot=output/'sources'/(h+'.json')
        if not snapshot.exists():
            freeze(snapshot,raw)
            freeze(output/'sources'/(h+'.verification.json'),json_bytes(report))
        elif snapshot.read_bytes()!=raw:
            raise RuntimeError('source checksum collision')
        parents.append(dict(path=str(path),raw_sha256=h,terms=terms,rank=len(terms)))
    binary_raw=args.binary.resolve().read_bytes();binary_sha=hashlib.sha256(binary_raw).hexdigest()
    binary=output/'frozen'/('native-'+binary_sha);freeze(binary,binary_raw);binary.chmod(0o555)
    code_names=['scripts/campaign_variable_rank_native.py','mmsearch/native_bridge.py','mmsearch/search.py',
                'mmsearch/verify.py','scripts/freeze_campaign_dictionary.py','native/flip_worker_v2.cpp']
    code={name:(ROOT/name).read_bytes() for name in code_names}
    for name,raw in code.items():
        freeze(output/'frozen'/name,raw)
    notes=ROOT/'research/ALPHATENSOR_SOURCE.md'
    freeze(output/'frozen/ALPHATENSOR_SOURCE.md',notes.read_bytes())
    manifest=dict(binary_source_path=str(args.binary.resolve()),binary_sha256=binary_sha,
                  code_sha256={name:hashlib.sha256(raw).hexdigest() for name,raw in code.items()},
                  source_notes_sha256=hashlib.sha256(notes.read_bytes()).hexdigest(),
                  sources=[{k:v for k,v in item.items() if k!='terms'} for item in parents],
                  target_rank=92,cyclic=args.cyclic,headroom=args.headroom,
                  note='Published96 baseline and rank95/93 descendants are not new records; target is <=92.')
    freeze(output/'manifest.json',json_bytes(manifest))
    stop=False
    def stopped(signum,frame):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGTERM,stopped);signal.signal(signal.SIGINT,stopped)
    phases=[];seen=set();counts=Counter()
    while not stop and deadline-time.monotonic()>2:
        index=len(phases);parent=parents[index%len(parents)]
        folder=output/f'phase-{index:03d}';folder.mkdir()
        masks=folder/'input.txt';freeze(masks,''.join(f'{a} {b} {c}\n' for a,b,c in parent['terms']).encode())
        prefix=folder/'walk';budget=min(args.phase_seconds,deadline-time.monotonic()-2)
        maximum=parent['rank']+args.headroom;native_seed=args.seed+index*1009
        command=[str(binary),'--input',str(masks),'--output',str(prefix),'--n','5','--target','92',
                 '--max-rank',str(maximum),'--seed',str(native_seed),'--steps','1000000000000',
                 '--seconds',str(budget),'--checkpoint-seconds','15','--archive-size',str(args.archive_size),
                 '--archive-every','1000','--plus-every',str(args.plus_every),'--restart-every',str(args.restart_every)]
        if args.cyclic:
            command.append('--cyclic')
        meta=dict(phase=index,source_path=parent['path'],source_raw_sha256=parent['raw_sha256'],
                  source_essential_rank=parent['rank'],max_rank=maximum,native_seed=native_seed,
                  binary_sha256=binary_sha,wrapper_sha256=manifest['code_sha256'][code_names[0]],
                  cyclic=args.cyclic,command=command)
        freeze(folder/'manifest.json',json_bytes(meta))
        kwargs=dict(n=5,target=92,input_rank=parent['rank'],max_rank=maximum,cyclic=args.cyclic,seen=seen,counts=counts)
        with (folder/'worker.log').open('x') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            last_scan=time.monotonic()
            try:
                while process.poll() is None and not stop:
                    if time.monotonic()-last_scan>=15:
                        last_scan=time.monotonic();result=drain_verified(prefix,output,meta,**kwargs)
                        if prefix.with_suffix('.stats.json').exists():
                            atomic_json(output/'latest_stats.json',dict(phase=index,stats=read_json(prefix.with_suffix('.stats.json').read_bytes()),verification=result))
                        stop=stop or result['winner']
                    time.sleep(.2)
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait()
        if process.returncode!=0:
            raise RuntimeError(f'native phase failed ({process.returncode}); inspect {folder}')
        stats=validate_final_stats(prefix,meta)
        result=drain_verified(prefix,output,meta,**kwargs)
        freeze(folder/'final_stats.json',json_bytes(stats));stop=stop or result['winner']
        meta.update(exit_code=process.returncode,final_stats=stats,verification=result)
        phases.append(meta)
        atomic_json(output/'latest_stats.json',dict(phase=index,stats=stats,verification=result))
        atomic_json(output/'summary.json',dict(phases=phases,winner=(output/'WINNER.json').exists(),
                    verified_portfolio_size=len(seen),retained_per_rank={str(k):v for k,v in sorted(counts.items())},
                    elapsed_seconds=time.monotonic()-started))
    atomic_json(output/'summary.json',dict(phases=phases,winner=(output/'WINNER.json').exists(),
                verified_portfolio_size=len(seen),retained_per_rank={str(k):v for k,v in sorted(counts.items())},
                elapsed_seconds=time.monotonic()-started,stopped=stop))
    print(json.dumps(dict(phases=len(phases),verified=len(seen),winner=(output/'WINNER.json').exists(),stopped=stop)))


if __name__=='__main__':
    main()
