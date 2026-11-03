"""Unrestricted 93..125 continuation adapter using existing verifier/frontier code."""
import argparse
from collections import Counter
import hashlib
import math
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import campaign_variable_rank_native as native
from scripts import campaign_mutable_five_cubes42 as frontier_code
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json
from mmsearch.native_bridge import canonical_terms,term_set_sha256,_read_terms
from mmsearch.search import encode_candidate
from mmsearch.verify import verify_candidate

BINARY_SHA='5f24facddefaeac03436dba1fc85bdfbb4273f676f946bfbe43661fb12a5e7cb'
SOURCE_SHA='3441a0e889084ece9544388394efac9adc40c8f2ae04a24224bc1ec3fedbf844'
DEFAULT_BINARY=ROOT/'artifacts/rl_campaign_20261102T210735Z/new93-continuation-ready-v1/native-worker'
RUNTIME=['scripts/campaign_unrestricted_frontier42.py','scripts/campaign_variable_rank_native.py',
         'scripts/campaign_mutable_five_cubes42.py','scripts/freeze_campaign_dictionary.py',
         'mmsearch/__init__.py','mmsearch/native_bridge.py','mmsearch/search.py','mmsearch/verify.py']


def code_hashes():return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in RUNTIME}


def validate_seed(candidate,strict_n5=True):
    terms,report=native.validate_seed(candidate,strict_n5=False,cyclic=False)
    if strict_n5 and (candidate['dimension']!=5 or not 93<=len(terms)<=125):
        raise ValueError('unrestricted frontier requires exact5x5 F2 essential rank93..125')
    return terms,report


def load_parent(path,output):
    path=Path(path).resolve();raw=path.read_bytes();terms,report=validate_seed(read_json(raw))
    digest=hashlib.sha256(raw).hexdigest();snapshot=Path(output)/'sources'/(digest+'.json')
    if not snapshot.exists():
        freeze(snapshot,raw);freeze(snapshot.with_suffix('.verification.json'),json_bytes(report))
    elif snapshot.read_bytes()!=raw:raise ValueError('source hash collision')
    return dict(source_path=str(path),source_sha256=digest,full_source_snapshot=str(snapshot),
                terms=terms,term_set_sha256=term_set_sha256(terms),rank=len(terms))


def _views(frontier):
    # Adapt only in memory to the existing generic diversity functions.
    return {key:dict(value,held=set(value['terms']),residual=set()) for key,value in frontier.items()}


def prune(frontier):
    views=_views(frontier);frontier_code.prune_frontier(views)
    for key in list(frontier):
        if key not in views:del frontier[key]


def choose(frontier,uses,phase):
    selected=frontier_code.choose_parent(_views(frontier),uses,phase)
    return frontier[selected['term_set_sha256']]


def inspect_export(prefix,output,meta,*,n=5,target=92,seen=None,counts=None,final=False):
    prefix=Path(prefix);stats_file=prefix.with_suffix('.stats.json')
    if not stats_file.exists():
        if final:raise ValueError('missing final unrestricted native statistics')
        return None
    before=stats_file.read_bytes();stats=read_json(before)
    expected=dict(dimension=n,seed=meta['native_seed'],max_rank=meta['max_rank'],target_rank=target)
    if any(type(stats.get(k)) is not int or stats[k]!=v for k,v in expected.items()):
        raise ValueError('unrestricted native metadata mismatch')
    if stats.get('cyclic') is not False or stats.get('exact') is not True or stats.get('tensor_invariant_checked') is not True:
        raise ValueError('unrestricted full-tensor mode mismatch')
    snapshots={};reports={}
    for label in ['best','current']:
        terms=_read_terms(prefix.with_suffix('.'+label+'.txt'),n)
        report=verify_candidate(encode_candidate(terms,n),random_trials=0)
        if not report['valid'] or report['exact_entries_checked']!=n**6:
            raise RuntimeError('unrestricted full matrix tensor verification failed')
        snapshots[label]=terms;reports[label]=report
    if (len(snapshots['best'])!=stats.get('best_rank') or len(snapshots['current'])!=stats.get('current_rank')
            or not 0<len(snapshots['best'])<=meta['source_essential_rank']
            or not len(snapshots['best'])<=len(snapshots['current'])<=meta['max_rank']):
        if final:raise ValueError('unrestricted native ranks disagree with verified snapshots')
        return None
    result=native.drain_verified(prefix,output,meta,n=n,target=target,input_rank=meta['source_essential_rank'],
                                 max_rank=meta['max_rank'],cyclic=False,seen=seen,counts=counts)
    if stats_file.read_bytes()!=before:
        if final:raise ValueError('native statistics changed after exit')
        return None
    adjusted=dict(stats,engine='unrestricted-frontier42-full-verified',rank_semantics='full matrix algorithm',
                  independent_full_verification=True,exact_entries_checked=n**6,
                  global_best_verification=reports['best'],global_current_verification=reports['current'],
                  native_stats_sha256=hashlib.sha256(before).hexdigest())
    for label,terms in snapshots.items():
        path=prefix.parent/f'walk.{label}.txt';tmp=path.with_name(path.name+'.tmp')
        tmp.write_text(''.join(f'{a} {b} {c}\n' for a,b,c in terms));tmp.replace(path)
    native.atomic_json(prefix.parent/'walk.stats.json',adjusted)
    native.atomic_json(Path(output)/'latest_stats.json',dict(phase=meta.get('phase'),stats=adjusted,verification=result))
    return dict(result,adjusted_stats=adjusted)


def checkpoint(output,frontier,uses,seed,completed):
    native.atomic_json(Path(output)/'checkpoint.json',dict(format='unrestricted-frontier42-v1',
          binary_sha256=BINARY_SHA,runtime_code_sha256=code_hashes(),base_seed=seed,
          completed_phase_count=completed,selection_counts=uses,
          frontier=[{k:v for k,v in parent.items() if k!='terms'} for _,parent in sorted(frontier.items())]))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path);p.add_argument('--pool',type=Path);p.add_argument('--resume',type=Path)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--binary',type=Path,default=DEFAULT_BINARY)
    p.add_argument('--worker-source',type=Path,default=ROOT/'native/flip_worker_v2.cpp')
    p.add_argument('--seconds',type=float,default=1200);p.add_argument('--phase-seconds',type=float,default=300)
    p.add_argument('--seed',type=int);p.add_argument('--headroom',type=int,choices=[6],default=6)
    p.add_argument('--archive-size',type=int,default=16);p.add_argument('--plus-every',type=int,default=50000)
    p.add_argument('--restart-every',type=int,default=100000000)
    p.add_argument('--step-limit',type=int,default=1000000000000);p.add_argument('--phase-limit',type=int,default=0)
    a=p.parse_args()
    if (not (a.input or a.resume) or not math.isfinite(a.seconds) or a.seconds<=2
            or not math.isfinite(a.phase_seconds) or a.phase_seconds<=0 or a.plus_every<1 or a.restart_every<1
            or not 1<=a.archive_size<=32 or not 0<=a.step_limit<=1000000000000 or a.phase_limit<0
            or (a.seed is not None and a.seed<0)):p.error('invalid bounded run settings')
    restored=read_json(a.resume.read_bytes()) if a.resume else None
    if restored and (restored.get('format')!='unrestricted-frontier42-v1'
            or restored.get('binary_sha256')!=BINARY_SHA or restored.get('runtime_code_sha256')!=code_hashes()):
        raise ValueError('checkpoint format/binary/runtime mismatch')
    if restored and a.seed is not None and a.seed!=restored['base_seed']:raise ValueError('resume seed mismatch')
    seed=restored['base_seed'] if restored else (a.seed or 0)
    completed=restored['completed_phase_count'] if restored else 0
    started=time.monotonic();deadline=started+a.seconds;output=a.output_dir.resolve();output.mkdir(parents=True,exist_ok=False)
    raw=a.binary.read_bytes();cpp=a.worker_source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=BINARY_SHA or hashlib.sha256(cpp).hexdigest()!=SOURCE_SHA:
        raise ValueError('ordinary native binary/source provenance mismatch')
    binary=output/'frozen/native-worker';freeze(binary,raw);binary.chmod(0o555)
    for name in RUNTIME:freeze(output/'frozen/runtime'/name,(ROOT/name).read_bytes())
    freeze(output/'frozen/flip_worker_v2.cpp',cpp)
    paths=[];frontier={};seen_sources=set();uses=dict(restored['selection_counts']) if restored else {}
    if restored:
        for parent in restored['frontier']:
            path=Path(parent['full_source_snapshot'])
            if hashlib.sha256(path.read_bytes()).hexdigest()!=parent['source_sha256']:raise ValueError('checkpoint source hash mismatch')
            paths.append(path)
    if a.input:paths.append(a.input)
    if a.pool:
        if not a.pool.is_dir():raise ValueError('pool must be a full certificate directory')
        paths.extend(sorted(a.pool.glob('*.json')))
    for path in paths:
        parent=load_parent(path,output);frontier[parent['term_set_sha256']]=parent;seen_sources.add(str(Path(path).resolve()))
    if not frontier:raise ValueError('empty verified frontier')
    prune(frontier)
    freeze(output/'manifest.json',json_bytes(dict(binary_sha256=BINARY_SHA,worker_source_sha256=SOURCE_SHA,
          runtime_code_sha256=code_hashes(),cyclic=False,target_rank=92,headroom=a.headroom,max_native_rank=141,
          sources=[{k:v for k,v in parent.items() if k!='terms'} for parent in frontier.values()],
          note='Unrestricted exact flips may change U,V,W and cube/orbit structure; no improved bound claimed.')))
    stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    phases=[];seen=set();counts=Counter();checkpoint(output,frontier,uses,seed,completed)
    while not stopped and deadline-time.monotonic()>2 and (not a.phase_limit or len(phases)<a.phase_limit):
        phase=len(phases);global_phase=completed+phase;parent=choose(frontier,uses,global_phase)
        uses[parent['term_set_sha256']]=uses.get(parent['term_set_sha256'],0)+1
        folder=output/f'phase-{phase:03d}';folder.mkdir();source=folder/'full_input.txt';prefix=folder/'native_walk'
        freeze(source,''.join(f'{u} {v} {w}\n' for u,v,w in parent['terms']).encode())
        maximum=parent['rank']+a.headroom
        if maximum>141:raise ValueError('native rank exceeds cap141')
        command=[str(binary),'--input',str(source),'--output',str(prefix),'--n','5','--target','92',
                 '--max-rank',str(maximum),'--seed',str(seed+global_phase*1009),'--steps',str(a.step_limit),
                 '--seconds',str(min(a.phase_seconds,deadline-time.monotonic()-2)),'--checkpoint-seconds','15',
                 '--archive-size',str(a.archive_size),'--archive-every','1000','--plus-every',str(a.plus_every),
                 '--restart-every',str(a.restart_every)]
        meta=dict(phase=phase,global_phase=global_phase,source_path=parent['source_path'],
                  source_sha256=parent['source_sha256'],source_essential_rank=parent['rank'],
                  max_rank=maximum,native_seed=seed+global_phase*1009,cyclic=False,command=command)
        freeze(folder/'manifest.json',json_bytes(meta))
        with (folder/'worker.log').open('x') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT);last=0
            try:
                while process.poll() is None and not stopped:
                    if time.monotonic()-last>=15:
                        last=time.monotonic();result=inspect_export(prefix,output,meta,seen=seen,counts=counts)
                        if result:stopped=stopped or result['winner']
                    time.sleep(.2)
            finally:
                if process.poll() is None:process.terminate()
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        if process.returncode:raise RuntimeError('ordinary native phase failed')
        result=inspect_export(prefix,output,meta,seen=seen,counts=counts,final=True);stopped=stopped or result['winner']
        freeze(folder/'final_global_stats.json',json_bytes(result['adjusted_stats']))
        phases.append(dict(phase=phase,global_best_rank=result['adjusted_stats']['best_rank'],exit_code=0))
        if not result['winner']:
            for path in sorted((output/'verified').glob('*.json')):
                if str(path.resolve()) in seen_sources:continue
                new=load_parent(path,output);frontier[new['term_set_sha256']]=new;seen_sources.add(str(path.resolve()))
            prune(frontier)
        checkpoint(output,frontier,uses,seed,completed+len(phases))
        native.atomic_json(output/'summary.json',dict(phases=phases,winner=result['winner'],elapsed_seconds=time.monotonic()-started))
    native.atomic_json(output/'summary.json',dict(phases=phases,winner=(output/'WINNER.json').exists(),stopped=stopped,
                       elapsed_seconds=time.monotonic()-started))


if __name__=='__main__':main()
