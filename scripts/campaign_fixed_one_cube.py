"""Long cyclic native phases with exactly one fixed cube in every state.

PLUS and RESET are move intervals, independent of phase wall-clock budgets.
The default profile is PLUS 50,000 / RESET 100,000,000 / rank headroom 6.

Branch progress below the input rank is distinct from a new matrix-multiplication
record: only an independently verified rank <=92 certificate meets the target.
"""
import argparse
from datetime import datetime
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
from mmsearch.cube_polarization import orbit_inventory
from mmsearch.native_bridge import _freeze, _json_bytes, _read_terms, canonical_terms, term_set_sha256
from mmsearch.search import encode_candidate, is_cyclic, orbit_counts
from mmsearch.verify import verify_candidate


def save(path,value):
    path = Path(path)
    tmp = path.with_name(path.name+".tmp")
    tmp.write_bytes(_json_bytes(value))
    tmp.replace(path)


def save_best(output_dir,record):
    if not record:
        return
    path = Path(output_dir)/'best_verified.json'
    if not path.exists() or record['rank'] < json.loads(path.read_text())['rank']:
        save(path,record)


def drain_verified(prefix,output_dir,metadata,*,n=5,target=92,max_rank=109,
                   seen=None,counts=None,per_bucket=64):
    """Drain final or periodic best/current/archive; never miss fast success."""
    prefix,output_dir = Path(prefix),Path(output_dir)
    seen = seen if seen is not None else set()
    counts = counts if counts is not None else Counter()
    paths = [prefix.with_suffix('.best.txt'),prefix.with_suffix('.current.txt'),
             *sorted(prefix.with_suffix('.archive').glob('*.txt'))]
    winner = (output_dir/'WINNER.json').exists()
    best_record = None
    for path in paths:
        if not path.exists():
            continue
        terms = _read_terms(path,n)
        rank = len(terms)
        if rank > max_rank or not is_cyclic(terms) or orbit_counts(terms)['fixed_cubes'] != 1:
            raise ValueError('native checkpoint violates fixed-one-cube/cyclic/rank limits')
        h = term_set_sha256(terms)
        if h in seen:
            continue
        # Keep a bounded portfolio in each branch-progress range, retaining all targets.
        bucket = '<=92' if rank <= target else ('94-97' if rank <= 97 else ('100' if rank <= 100 else '103-109'))
        if rank > target and counts[bucket] >= per_bucket and path != paths[0]:
            continue
        value = encode_candidate(terms,n,method='fixed-one-cube-native-cyclic-checkpoint',parent=metadata,
                                 term_set_sha256=h,orbit_profile=orbit_counts(terms),
                                 orbit_inventory=orbit_inventory(terms),
                                 status='verified_target' if rank <= target else 'branch_progress')
        report = verify_candidate(value,random_trials=0)
        if not report['valid']:
            raise RuntimeError('independent exact verification rejected native checkpoint')
        payload = _json_bytes(value)
        frozen = _freeze(output_dir/'verified'/(h+'.json'),payload)
        verification = _freeze(output_dir/'verification'/(h+'.verification.json'),_json_bytes(report))
        digest = hashlib.sha256(payload).hexdigest()
        _freeze(output_dir/'verification'/(h+'.sha256'),(digest+'  '+frozen.name+'\n').encode())
        seen.add(h);counts[bucket] += 1
        record = dict(path=str(frozen),verification_path=str(verification),sha256=digest,rank=rank,
                      orbit_profile=orbit_counts(terms),bucket=bucket)
        if path == paths[0]:
            best_record = record
        if rank <= target and not winner:
            _freeze(output_dir/'WINNER.json',payload)
            _freeze(output_dir/'WINNER.verification.json',_json_bytes(report))
            _freeze(output_dir/'WINNER.verify.py',Path(__file__).resolve().parents[1].joinpath('mmsearch/verify.py').read_bytes())
            winner = True
            break
    return dict(winner=winner,best_record=best_record,verified=len(seen),buckets=dict(counts))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--pool',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--seconds',type=float,required=True)
    p.add_argument('--deadline-utc',default='2026-11-03T03:07:35Z')
    p.add_argument('--phase-seconds',type=float,default=600)
    p.add_argument('--seed',type=int,default=0)
    p.add_argument('--target',type=int,default=92,choices=(92,))
    p.add_argument('--archive-size',type=int,default=16)
    p.add_argument('--plus-every',type=int,default=50000)
    p.add_argument('--restart-every',type=int,default=100000000)
    p.add_argument('--headroom',type=int,default=6)
    p.add_argument('--cyclic',action='store_true',default=True)
    args = p.parse_args()
    if not all(math.isfinite(x) and x > 0 for x in (args.seconds,args.phase_seconds)):
        p.error('finite positive seconds and phase-seconds required')
    if not 1 <= args.archive_size <= 32:
        p.error('archive-size must be between 1 and 32')
    if not all(1 <= x <= 1000000000000 for x in (args.plus_every,args.restart_every)):
        p.error('plus-every and restart-every must be between 1 and 1000000000000')
    if not 1 <= args.headroom <= 9:
        p.error('headroom must be between 1 and 9 (maximum rank 109)')
    try:
        absolute_deadline = datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00'))
        if absolute_deadline.tzinfo is None:
            raise ValueError('timezone required')
        absolute_deadline = absolute_deadline.timestamp()
    except ValueError:
        p.error('deadline-utc must be an ISO timestamp with a timezone')
    started = time.monotonic()
    deadline = started + min(args.seconds,max(0,absolute_deadline-time.time()))
    args.output_dir.mkdir(parents=True,exist_ok=False)
    sources = sorted(set([args.input.resolve(),*args.pool.resolve().glob('*.json')]))
    rng = random.Random(args.seed);rng.shuffle(sources)
    candidates = []
    for source in sources:
        raw = source.read_bytes();value = json.loads(raw)
        terms = canonical_terms(value);n = value['dimension']
        if n != 5 or len(terms) not in (94,97,100) or orbit_counts(terms)['fixed_cubes'] != 1 or not is_cyclic(terms):
            raise ValueError('campaign requires cyclic rank94, rank97 or rank100 seeds with one fixed cube')
        if not verify_candidate(encode_candidate(terms,n),random_trials=0)['valid']:
            raise ValueError('invalid polarized source')
        candidates.append((source,raw,terms))
    binary_sha = hashlib.sha256(args.binary.read_bytes()).hexdigest()
    wrapper_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    stop = False
    def stopped(signum,frame):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM,stopped);signal.signal(signal.SIGINT,stopped)
    seen,counts,phases = set(),Counter(),[]
    while not stop and time.monotonic() < deadline and time.time() < absolute_deadline:
        phase = len(phases);source,raw,terms = candidates[phase%len(candidates)]
        folder = args.output_dir/f'phase-{phase:03d}';folder.mkdir()
        masks = _freeze(folder/'input.txt',''.join(f'{a} {b} {c}\n' for a,b,c in terms).encode())
        prefix = folder/'walk'
        budget = min(args.phase_seconds,max(0,min(deadline-time.monotonic(),absolute_deadline-time.time())))
        maximum = len(terms)+args.headroom
        command = [str(args.binary.resolve()),'--input',str(masks),'--output',str(prefix),'--n','5',
                   '--target',str(args.target),'--max-rank',str(maximum),'--seed',str(args.seed+phase*1009),
                   '--steps','1000000000000','--seconds',str(budget),'--checkpoint-seconds','15',
                   '--archive-size',str(args.archive_size),'--archive-every','1000',
                   '--plus-every',str(args.plus_every),
                   '--restart-every',str(args.restart_every),'--cyclic','--fixed-cubes','1']
        meta = dict(phase=phase,source=str(source),source_sha256=hashlib.sha256(raw).hexdigest(),
                    binary_sha256=binary_sha,wrapper_sha256=wrapper_sha,command=command,
                    initial_rank=len(terms),initial_profile=orbit_counts(terms),
                    initial_inventory=orbit_inventory(terms),max_rank=maximum,
                    required_fixed_cubes=1,profile='fixed-one-cube-v1',deadline_utc=args.deadline_utc,
                    effective_target_rank=91,
                    plus_every=args.plus_every,restart_every=args.restart_every,headroom=args.headroom,note='C3 closure and exactly one fixed cube enforced; cube factors may change')
        _freeze(folder/'manifest.json',_json_bytes(meta))
        with (folder/'worker.log').open('x') as log:
            process = subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            last_scan = 0
            try:
                while process.poll() is None and not stop and time.monotonic() < deadline and time.time() < absolute_deadline:
                    if time.monotonic()-last_scan >= 15:
                        last_scan = time.monotonic()
                        result = drain_verified(prefix,args.output_dir,meta,max_rank=maximum,seen=seen,counts=counts,target=args.target)
                        save_best(args.output_dir,result['best_record'])
                        if prefix.with_suffix('.stats.json').exists():
                            stats = json.loads(prefix.with_suffix('.stats.json').read_text())
                            save(args.output_dir/'latest_stats.json',dict(phase=phase,stats=stats,verified=result))
                        if result['winner']:
                            stop = True
                    time.sleep(.2)
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait()
        if process.returncode != 0:
            raise RuntimeError(f'native polarized phase failed: {folder}')
        result = drain_verified(prefix,args.output_dir,meta,max_rank=maximum,seen=seen,counts=counts,target=args.target)
        save_best(args.output_dir,result['best_record'])
        stop = stop or result['winner']
        stats = json.loads(prefix.with_suffix('.stats.json').read_text())
        meta.update(exit_code=process.returncode,final_stats=stats,verified=result)
        phases.append(meta)
        save(args.output_dir/'latest_stats.json',dict(phase=phase,stats=stats,verified=result))
        save(args.output_dir/'summary.json',dict(phases=phases,verified=len(seen),buckets=dict(counts),winner=result['winner']))
    print(json.dumps(dict(phases=len(phases),verified=len(seen),buckets=dict(counts),stopped=stop)))


if __name__ == '__main__':
    main()
