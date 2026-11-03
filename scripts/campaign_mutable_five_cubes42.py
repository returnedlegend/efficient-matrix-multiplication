"""Continue a verified C3 frontier with five mutable fixed-cube factors.

Every native state is a full matrix algorithm. Five cube values may change;
independent verification precedes all certificate and status exports.
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
EXPECTED_SOURCE_SHA256='9df51dc755396bd15fd0571c064b7def74b74550f300fb97fbf024ee4c6747db'


def atomic_json(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.tmp')
    temporary.write_bytes(json_bytes(value));temporary.replace(path)


def inspect_export(prefix,output,metadata,*,n=5,target=92,max_rank=110,
                   fixed_cubes=5,seen=None,counts=None,per_rank=32,final=False):
    """Independently check full native states before exporting global claims."""
    prefix=Path(prefix);output=Path(output)
    seen=seen if seen is not None else set();counts=counts if counts is not None else Counter()
    stats_path=prefix.with_suffix('.stats.json')
    if not stats_path.exists():
        if final:raise ValueError('missing final full native statistics')
        return None
    before=stats_path.read_bytes();raw=read_json(before)
    if (raw.get('dimension')!=n or raw.get('exact') is not True
            or raw.get('tensor_invariant_checked') is not True or raw.get('cyclic') is not True
            or raw.get('required_fixed_cubes')!=fixed_cubes or raw.get('best_fixed_cubes')!=fixed_cubes
            or raw.get('current_fixed_cubes')!=fixed_cubes or raw.get('max_rank')!=max_rank
            or raw.get('target_rank')!=target):
        raise ValueError('native metadata violates full-tensor/cyclic/fixed-count settings')
    if 'native_seed' in metadata and raw.get('seed')!=metadata['native_seed']:
        raise ValueError('native seed mismatch')
    paths=[prefix.with_suffix('.best.txt'),prefix.with_suffix('.current.txt'),
           *sorted(prefix.with_suffix('.archive').glob('*.txt'))]
    snapshots={};reports={}
    for path in paths:
        if not path.exists():
            if final and path in paths[:2]:raise ValueError('missing final full native best/current')
            continue
        terms=set(_read_terms(path,n))
        if (len(terms)>max_rank or not is_cyclic(terms)
                or sum(a==b==c for a,b,c in terms)!=fixed_cubes):
            raise ValueError('native state violates full rank/C3/five-cube count')
        report=verify_candidate(encode_candidate(terms,n),random_trials=0)
        if not report['valid'] or report['exact_entries_checked']!=n**6:
            raise RuntimeError('full native state failed independent matrix tensor verification')
        snapshots[path]=terms;reports[path]=report
    if stats_path.read_bytes()!=before:
        if final:raise ValueError('native statistics changed after exit')
        return None
    if (paths[0] not in snapshots or paths[1] not in snapshots
            or len(snapshots[paths[0]])!=raw.get('best_rank')
            or len(snapshots[paths[1]])!=raw.get('current_rank')):
        if final:raise ValueError('native full ranks disagree with statistics')
        return None
    winner=(output/'WINNER.json').exists();best_record=None
    for path,terms in snapshots.items():
        rank=len(terms);key=term_set_sha256(terms)
        if key in seen or (rank>target and counts[rank]>=per_rank):continue
        candidate=encode_candidate(terms,n,method='mutable-five-cube-count42-native',parent=metadata,
                    fixed_cube_count=fixed_cubes,cube_values_mutable=True,
                    cube_terms=sorted(t for t in terms if t[0]==t[1]==t[2]),
                    essential_rank=rank,status='verified_target' if rank<=target else 'research_checkpoint',
                    target_reached=rank<=target,orbit_profile=orbit_counts(terms))
        payload=json_bytes(candidate);destination=output/'verified'/(key+'.json')
        freeze(destination,payload)
        verification=output/'verification'/(key+'.verification.json');freeze(verification,json_bytes(reports[path]))
        digest=hashlib.sha256(payload).hexdigest()
        freeze(output/'verification'/(key+'.sha256'),(digest+'  '+destination.name+'\n').encode())
        seen.add(key);counts[rank]+=1
        record=dict(path=str(destination),rank=rank,sha256=digest,verification_path=str(verification))
        if path==paths[0]:best_record=record
        if rank<=target and not winner:
            freeze(output/'WINNER.json',payload);freeze(output/'WINNER.verification.json',json_bytes(reports[path]))
            freeze(output/'WINNER.sha256',(digest+'  WINNER.json\n').encode())
            freeze(output/'WINNER.verify.py',(ROOT/'mmsearch/verify.py').read_bytes());winner=True
    adjusted=dict(raw,engine='mutable-five-cubes42-full-verified-v1',
                  rank_semantics='full matrix algorithm; five cube factors may change',
                  cube_values_mutable=True,independent_full_verification=True,exact_entries_checked=n**6,
                  native_stats_path=str(stats_path),native_stats_sha256=hashlib.sha256(before).hexdigest(),
                  global_best_verification=reports[paths[0]],global_current_verification=reports[paths[1]])
    for label,path in [('best',paths[0]),('current',paths[1])]:
        dest=prefix.parent/f'walk.{label}.txt';tmp=dest.with_name(dest.name+'.tmp')
        tmp.write_text(''.join(f'{a} {b} {c}\n' for a,b,c in sorted(snapshots[path])));tmp.replace(dest)
    atomic_json(prefix.parent/'walk.stats.json',adjusted)
    atomic_json(output/'latest_stats.json',dict(phase=metadata.get('phase'),stats=adjusted))
    if best_record:
        pointer=output/'best_verified.json'
        if not pointer.exists() or best_record['rank']<read_json(pointer.read_bytes())['rank']:
            atomic_json(pointer,best_record)
    return dict(winner=winner,adjusted_stats=adjusted,best_record=best_record,
                verified_portfolio_size=len(seen),retained_per_rank={str(k):v for k,v in sorted(counts.items())})


def split_source(candidate,*,strict_n5=True):
    if candidate.get('field') != 2 or type(candidate.get('field')) is not int:
        raise ValueError('mutable five-cube campaign requires declared field2')
    terms=set(canonical_terms(candidate));n=candidate['dimension']
    held={term for term in terms if term[0]==term[1]==term[2]}
    residual=terms-held
    if strict_n5 and (n!=5 or len(terms)<92 or len(terms)%3!=2 or len(held)!=5):
        raise ValueError('mutable-five campaign requires exact5x5 rank>=92, rank2mod3 and exactly five cubes with arbitrary factors')
    if len(terms)>1000:raise ValueError('full rank exceeds native cap1000')
    original=verify_candidate(candidate,random_trials=0)
    canonical=verify_candidate(encode_candidate(terms,n),random_trials=0)
    if not original['valid'] or not canonical['valid'] or not is_cyclic(terms):
        raise ValueError('source must be independently exact F2 matrix multiplication and cyclic')
    if not is_cyclic(residual) or any(a==b==c for a,b,c in residual) or residual&held:
        raise ValueError('cube/noncube partition violates complete C3 orbit structure')
    return held,residual,dict(original=original,canonical=canonical)


def load_parent(path,output):
    """Read a complete certificate, verify original and parity-normalized forms."""
    path=Path(path).resolve();raw=path.read_bytes();candidate=read_json(raw)
    held,residual,report=split_source(candidate)
    digest=hashlib.sha256(raw).hexdigest();snapshot=Path(output)/'sources'/(digest+'.json')
    if snapshot.exists():
        if snapshot.read_bytes()!=raw:raise ValueError('source snapshot hash collision')
    else:
        freeze(snapshot,raw)
        freeze(snapshot.with_suffix('.verification.json'),json_bytes(report))
    return dict(source_path=str(path),source_sha256=digest,full_source_snapshot=str(snapshot),
                held=held,residual=residual,noncube_term_set_sha256=term_set_sha256(residual),
                term_set_sha256=term_set_sha256(held|residual))


def prune_frontier(frontier,cap=32):
    """Retain low ranks and choose distant term sets within each rank level."""
    if not frontier:return
    rank=lambda key:len(frontier[key]['held'])+len(frontier[key]['residual'])
    best=min(map(rank,frontier));remaining={k for k in frontier if rank(k)<=best+6}
    selected=[]
    while remaining and len(selected)<cap:
        level=min(map(rank,remaining));eligible={k for k in remaining if rank(k)==level}
        def distance(key):
            terms=frontier[key]['held']|frontier[key]['residual']
            return min((len(terms^(frontier[k]['held']|frontier[k]['residual'])) for k in selected),default=0)
        choice=min(eligible,key=lambda key:(-distance(key),key))
        selected.append(choice);remaining.remove(choice)
    for key in list(frontier):
        if key not in selected:del frontier[key]


def choose_parent(frontier,uses,phase):
    """Even phases continue a best state; odd phases seek nearby diversity."""
    if not frontier:raise ValueError('empty continuation frontier')
    rank=lambda key:len(frontier[key]['held'])+len(frontier[key]['residual'])
    best=min(map(rank,frontier));best_key=min(frontier,key=lambda key:(rank(key),uses.get(key,0),key))
    eligible=[k for k in frontier if rank(k)<=best+(3 if phase%2 else 0)]
    anchor=frontier[best_key]['held']|frontier[best_key]['residual']
    key=min(eligible,key=lambda k:(uses.get(k,0),
            -len(anchor^(frontier[k]['held']|frontier[k]['residual'])) if phase%2 else 0,rank(k),k))
    return frontier[key]


def save_checkpoint(output,frontier,uses,seed,completed,held):
    atomic_json(Path(output)/'checkpoint.json',dict(format='mutable-five-cubes42-v1',
                binary_sha256=EXPECTED_BINARY_SHA256,fixed_cube_count=5,cube_values_mutable=True,
                wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                base_seed=seed,completed_phase_count=completed,selection_counts=uses,
                frontier=[{k:v for k,v in parent.items() if k not in ('held','residual')}
                          for _,parent in sorted(frontier.items())],
                note='Resume into a fresh output directory; every full source is rehashed and independently reverified.'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path)
    p.add_argument('--resume',type=Path)
    p.add_argument('--pool',type=Path)
    p.add_argument('--binary',type=Path,default=DEFAULT_BINARY)
    p.add_argument('--worker-source',type=Path,default=FROZEN_ROOT/'native/flip_worker_fixed_cubes.cpp')
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=1200)
    p.add_argument('--phase-seconds',type=float,default=300)
    p.add_argument('--seed',type=int)
    p.add_argument('--headroom',type=int,default=6)
    p.add_argument('--plus-every',type=int,default=50000)
    p.add_argument('--restart-every',type=int,default=100000000)
    p.add_argument('--archive-size',type=int,default=16)
    p.add_argument('--step-limit',type=int,default=1000000000000)
    p.add_argument('--phase-limit',type=int,default=0)
    args=p.parse_args()
    if (not math.isfinite(args.seconds) or args.seconds<=2 or not math.isfinite(args.phase_seconds)
            or args.phase_seconds<=0 or args.headroom not in (6,12) or (args.seed is not None and args.seed<0) or args.plus_every<1
            or args.restart_every<1 or not 1<=args.archive_size<=32
            or not 0<=args.step_limit<=1000000000000 or args.phase_limit<0):
        p.error('invalid bounded run settings')
    if not args.input and not args.resume:p.error('--input or --resume is required')
    restored=read_json(args.resume.read_bytes()) if args.resume else None
    if restored and (restored.get('format')!='mutable-five-cubes42-v1'
                     or restored.get('binary_sha256')!=EXPECTED_BINARY_SHA256
                     or restored.get('wrapper_sha256')!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()):
        raise ValueError('checkpoint format/binary/wrapper mismatch')
    if restored and args.seed is not None and args.seed!=restored['base_seed']:
        raise ValueError('resume seed must match checkpoint')
    args.seed=restored['base_seed'] if restored else (args.seed or 0)
    completed_before=restored['completed_phase_count'] if restored else 0
    started=time.monotonic();deadline=started+args.seconds
    output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=False)
    raw_binary=args.binary.read_bytes();binary_sha=hashlib.sha256(raw_binary).hexdigest()
    if binary_sha!=EXPECTED_BINARY_SHA256:
        raise ValueError('worker must match the frozen validated fixed-cube binary')
    binary=output/'frozen'/('native-'+binary_sha);freeze(binary,raw_binary);binary.chmod(0o555)
    frontier={};uses=dict(restored['selection_counts']) if restored else {};seen_sources=set()
    paths=[]
    if restored:
        for source in restored['frontier']:
            path=Path(source['full_source_snapshot'])
            if hashlib.sha256(path.read_bytes()).hexdigest()!=source['source_sha256']:
                raise ValueError('checkpoint source hash mismatch')
            paths.append(path)
    if args.input:paths.append(args.input.resolve())
    if args.pool:
        if not args.pool.is_dir():raise ValueError('pool must be a certificate directory')
        paths.extend(sorted(args.pool.glob('*.json')))
    held_inventory=None
    for path in paths:
        parent=load_parent(path,output)
        if held_inventory is None:held_inventory=parent['held']
        frontier[parent['term_set_sha256']]=parent;seen_sources.add(str(Path(path).resolve()))
    if not frontier:raise ValueError('no verified continuation sources')
    prune_frontier(frontier)
    parents=list(frontier.values())
    freeze(output/'source_cube_profiles.json',json_bytes(dict(fixed_cube_count=5,cube_values_mutable=True,
           initial_profiles=[dict(source_sha256=parent['source_sha256'],cube_terms=sorted(parent['held']))
                             for parent in parents],note='Only the count is fixed; cube factors may change.')))
    names=['scripts/campaign_mutable_five_cubes42.py','mmsearch/native_bridge.py','mmsearch/search.py','mmsearch/verify.py',
           'scripts/freeze_campaign_dictionary.py','mmsearch/__init__.py']
    code={name:(ROOT/name).read_bytes() for name in names}
    for name,raw in code.items():freeze(output/'frozen'/name,raw)
    cpp=args.worker_source.read_bytes()
    if hashlib.sha256(cpp).hexdigest()!=EXPECTED_SOURCE_SHA256:
        raise ValueError('worker source does not match frozen native provenance')
    freeze(output/'frozen/native/flip_worker_fixed_cubes.cpp',cpp)
    manifest=dict(binary_sha256=binary_sha,worker_source_sha256=hashlib.sha256(cpp).hexdigest(),
                  code_sha256={name:hashlib.sha256(raw).hexdigest() for name,raw in code.items()},
                  fixed_cube_count=5,cube_values_mutable=True,global_target=92,
                  sources=[{k:v for k,v in parent.items() if k not in ('held','residual')} for parent in parents],
                  selection='alternate best rank and least-used diverse low-rank state; preserve verified frontier across phases',
                  note='Full tensor native search preserves exactly five cubes while allowing their factors to change; no held residual, no rank92 existence claim.')
    freeze(output/'manifest.json',json_bytes(manifest))
    stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    seen=set();counts=Counter();phases=[]
    save_checkpoint(output,frontier,uses,args.seed,completed_before,held_inventory)
    for parent in frontier.values():
        if len(parent['held'])+len(parent['residual'])<=92:
            payload=json_bytes(encode_candidate(parent['held']|parent['residual'],5,
                     method='verified-parity-normalized-input',source_sha256=parent['source_sha256']))
            freeze(output/'WINNER.json',payload)
            freeze(output/'WINNER.verification.json',json_bytes(verify_candidate(read_json(payload),random_trials=0)))
            freeze(output/'WINNER.sha256',(hashlib.sha256(payload).hexdigest()+'  WINNER.json\n').encode())
            freeze(output/'WINNER.verify.py',(ROOT/'mmsearch/verify.py').read_bytes());stopped=True;break
    while (not stopped and deadline-time.monotonic()>2
           and (not args.phase_limit or len(phases)<args.phase_limit)):
        phase=len(phases);global_phase=completed_before+phase
        parent=choose_parent(frontier,uses,global_phase)
        uses[parent['term_set_sha256']]=uses.get(parent['term_set_sha256'],0)+1
        folder=output/f'phase-{phase:03d}';folder.mkdir();prefix=folder/'native_walk'
        source=folder/'full_input.txt';freeze(source,''.join(f'{a} {b} {c}\n' for a,b,c in sorted(parent['held']|parent['residual'])).encode())
        budget=min(args.phase_seconds,deadline-time.monotonic()-2);maximum=len(parent['held'])+len(parent['residual'])+args.headroom
        native_seed=args.seed+global_phase*1009;res_target=92
        if maximum>1000:raise ValueError('full rank plus headroom exceeds native cap1000')
        command=[str(binary),'--input',str(source),'--output',str(prefix),'--n','5','--target',str(res_target),
                 '--max-rank',str(maximum),'--seed',str(native_seed),'--steps',str(args.step_limit),
                 '--seconds',str(budget),'--checkpoint-seconds','15','--archive-size',str(args.archive_size),
                 '--archive-every','1000','--plus-every',str(args.plus_every),'--restart-every',str(args.restart_every),
                 '--cyclic','--fixed-cubes','5']
        meta=dict(phase=phase,global_phase=global_phase,selection_count=uses[parent['term_set_sha256']],full_source_snapshot=parent['full_source_snapshot'],source_path=parent['source_path'],
                  source_sha256=parent['source_sha256'],source_cube_terms=sorted(parent['held']),cube_values_mutable=True,
                  initial_global_rank=len(parent['residual'])+len(parent['held']),native_seed=native_seed,
                  max_rank=maximum,binary_sha256=binary_sha,wrapper_sha256=manifest['code_sha256'][names[0]],command=command)
        freeze(folder/'manifest.json',json_bytes(meta))
        kwargs=dict(n=5,target=92,max_rank=maximum,seen=seen,counts=counts)
        with (folder/'worker.log').open('x') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT);last_scan=0
            try:
                while process.poll() is None and not stopped:
                    if time.monotonic()-last_scan>=15:
                        last_scan=time.monotonic();result=inspect_export(prefix,output,meta,**kwargs)
                        if result:stopped=stopped or result['winner']
                    time.sleep(.2)
            finally:
                if process.poll() is None:process.terminate()
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        result=inspect_export(prefix,output,meta,final=True,**kwargs)
        if process.returncode!=0:raise RuntimeError(f'full native worker failed({process.returncode}); inspect{folder}')
        stopped=stopped or result['winner'];freeze(folder/'final_global_stats.json',json_bytes(result['adjusted_stats']))
        phases.append(dict(phase=phase,exit_code=process.returncode,global_best_rank=result['adjusted_stats']['best_rank'],
                           fixed_cube_count=5,cube_values_mutable=True))
        for path in sorted((output/'verified').glob('*.json')):
            if result['winner']:break
            if str(path.resolve()) in seen_sources:continue
            new_parent=load_parent(path,output)
            frontier[new_parent['term_set_sha256']]=new_parent;seen_sources.add(str(path.resolve()))
        prune_frontier(frontier)
        save_checkpoint(output,frontier,uses,args.seed,completed_before+len(phases),held_inventory)
        atomic_json(output/'summary.json',dict(phases=phases,winner=(output/'WINNER.json').exists(),
                    retained_per_rank={str(k):v for k,v in sorted(counts.items())},elapsed_seconds=time.monotonic()-started))
    atomic_json(output/'summary.json',dict(phases=phases,winner=(output/'WINNER.json').exists(),stopped=stopped,
                retained_per_rank={str(k):v for k,v in sorted(counts.items())},elapsed_seconds=time.monotonic()-started))
    print(json.dumps(dict(phases=len(phases),winner=(output/'WINNER.json').exists(),stopped=stopped)))


if __name__=='__main__':
    main()
