"""Bounded single-source dwell pilot arm; preview never starts a target query.

Only root-approved exact n5/F2 essential93 inputs, CPU1/768MiB, <=30s native.
WINNER.json is the existing dispatch-stop marker, published after proof files.
The campaign guard retains ownership of global verification/freeze/termination.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from mmsearch.native_bridge import canonical_terms,_read_terms,term_set_sha256
from mmsearch.search import encode_candidate
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import verify_bytes


def sha(raw):return hashlib.sha256(raw).hexdigest()
def raw_json(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('duplicate JSON key: '+key)
        value[key]=item
    return value


def read(path):
    raw=Path(path).read_bytes();value=json.loads(raw,object_pairs_hook=unique)
    if not isinstance(value,dict):raise ValueError('expected JSON object')
    return value,raw


def freeze(path,raw,executable=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    except FileExistsError:
        if path.read_bytes()!=raw:raise ValueError('immutable artifact collision: '+str(path))
    path.chmod(0o555 if executable else 0o444)


def atomic(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.tmp');tmp.write_bytes(raw_json(value));tmp.replace(path)


def source_identity(terms):return sha(json.dumps(sorted(terms),separators=(',',':')).encode())


RUNTIME=['scripts/campaign_native_dwell42.py','scripts/verify_record42_independent.py','mmsearch/__init__.py',
         'mmsearch/native_bridge.py','mmsearch/search.py','mmsearch/verify.py','native/flip_worker_dwell42.cpp']


def runtime_hashes():return {name:sha((ROOT/name).read_bytes()) for name in RUNTIME}


def validate_input(path,expected_sha,declaration_path,declaration_sha):
    candidate,raw=read(path)
    if sha(raw)!=expected_sha:raise ValueError('input raw hash differs')
    terms=canonical_terms(candidate)
    if candidate['dimension']!=5 or len(terms)!=93:raise ValueError('pilot input must be exact n5/F2 essential93')
    report=verify_candidate(candidate,random_trials=0)
    canonical=encode_candidate(terms,5);canonical_report=verify_candidate(canonical,random_trials=0)
    if not report['valid'] or not canonical_report['valid'] or canonical_report['exact_entries_checked']!=15625:
        raise ValueError('input failed full15625-entry exact tensor check')
    declaration,declaration_raw=read(declaration_path)
    if sha(declaration_raw)!=declaration_sha:raise ValueError('heldout declaration hash differs')
    held=declaration.get('heldout_source_term_hashes')
    if (not isinstance(held,list) or len(held)!=4
        or any(not isinstance(x,str) or len(x)!=64 or any(c not in '0123456789abcdef' for c in x) for x in held)
        or len(set(held))!=4):
        raise ValueError('expected frozen four-source heldout identity declaration')
    identity=source_identity(terms)
    if identity in held:raise ValueError('heldout source is forbidden for this pilot')
    return terms,{'raw_sha256':expected_sha,'source_term_hash':identity,'term_set_sha256':term_set_sha256(terms),
                  'heldout_declaration_sha256':declaration_sha,'heldout_excluded':True,'original_verification':report,
                  'canonical_verification':canonical_report},raw


def command(binary,input_path,prefix,*,seconds,seed,dwell,max_rank=105,archive_size=16):
    if type(dwell) is not int or dwell not in (0,64,32768):raise ValueError('pilot arms are D0/D64/D32768')
    if not math.isfinite(seconds) or not 0<seconds<=30:raise ValueError('native pilot budget must be positive and<=30s')
    return [str(binary),'--input',str(input_path),'--output',str(prefix),'--n','5','--target','92','--max-rank',str(max_rank),
            '--seed',str(seed),'--steps','1000000000000','--seconds',str(seconds),'--checkpoint-seconds','3',
            '--archive-size',str(archive_size),'--archive-every','1000','--plus-every','20000','--restart-every','50000000',
            '--reduction-dwell',str(dwell)]


def freeze_winner(output,candidate,source,source_raw,*,n=5,target=92):
    """Small n2 controls are supported only through this testable helper API."""
    if candidate.get('dimension')!=n or candidate.get('field')!=2 or not 0<len(candidate['terms'])<=target:
        raise ValueError('winner eligibility differs')
    report=verify_candidate(candidate,random_trials=16)
    if not report['valid'] or report['exact_entries_checked']!=n**6:raise ValueError('winner failed full tensor verification')
    raw=raw_json(candidate);output=Path(output)
    proofs={'WINNER.verification.json':raw_json(report),'WINNER.verify.py':(ROOT/'mmsearch/verify.py').read_bytes(),
            'WINNER.source.raw':source_raw,'WINNER.source.json':raw_json({'source':str(source),'sha256':sha(source_raw)})}
    if n==5:
        if target!=92:raise ValueError('production n5 target must be92')
        independent=verify_bytes(raw)
        if independent.get('record_eligible') is not True or independent.get('exact_entries_checked')!=15625:
            raise ValueError('winner failed second independent verifier')
        proofs['WINNER.independent.verification.json']=raw_json(independent)
        proofs['WINNER.independent.verify.py']=(ROOT/'scripts/verify_record42_independent.py').read_bytes()
    hashes={name:sha(value) for name,value in proofs.items()};hashes['WINNER.json']=sha(raw)
    for name,value in proofs.items():freeze(output/name,value)
    freeze(output/'WINNER.sha256',(sha(raw)+'  WINNER.json\n').encode())
    freeze(output/'WINNER.checksums.json',raw_json(hashes))
    # Publish the legacy dispatch-stop marker LAST, after proof bytes/checksums.
    freeze(output/'WINNER.json',raw)
    descriptor=os.open(output,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)
    return hashes


def snapshot(path,n):
    raw=Path(path).read_bytes();terms=[]
    for line in raw.decode('ascii').splitlines():
        fields=line.split()
        if len(fields)!=3 or any(not value.isdecimal() for value in fields):raise ValueError('malformed native snapshot')
        term=tuple(map(int,fields))
        if any(not 0<value<1<<(n*n) for value in term):raise ValueError('native factor outside nonzero bit width')
        terms.append(term)
    if not terms or len(set(terms))!=len(terms):raise ValueError('empty/noncanonical native snapshot')
    return tuple(sorted(terms)),raw


def drain(prefix,output,metadata,seen,*,n=5,target=92,max_rank=105):
    paths=[Path(str(prefix)+'.best.txt'),Path(str(prefix)+'.current.txt'),*sorted(Path(str(prefix)+'.archive').glob('*.txt'))]
    winner=False
    for path in paths:
        if not path.exists():continue
        terms,source_raw=snapshot(path,n)
        if len(terms)>max_rank:raise ValueError('export exceeds rank cap')
        digest=term_set_sha256(terms)
        if digest in seen:continue
        candidate=encode_candidate(terms,n,method='bounded-dwell42-native',parent=metadata,term_set_sha256=digest)
        report=verify_candidate(candidate,random_trials=0)
        if not report['valid'] or report['exact_entries_checked']!=n**6:raise ValueError('export failed independent full tensor verification')
        payload=raw_json(candidate);destination=Path(output)/'verified'/(digest+'.json')
        freeze(destination,payload);freeze(destination.with_suffix('.verification.json'),raw_json(report))
        seen[digest]={'path':str(destination),'rank':len(terms),'sha256':sha(payload),'terms':[list(t) for t in terms]}
        if len(terms)<=target:
            freeze_winner(output,candidate,path,source_raw,n=n,target=target);winner=True;break
    return winner


def validate_stats(path,*,seed,dwell,max_rank=105):
    stats,raw=read(path)
    for key,value in {'dimension':5,'target_rank':92,'max_rank':max_rank,'seed':seed,'reduction_dwell':dwell,
                      'plus_every':20000,'restart_every':50000000}.items():
        if type(stats.get(key)) is not int or stats[key]!=value:raise ValueError('native parameter mismatch: '+key)
    if stats.get('exact') is not True or stats.get('tensor_invariant_checked') is not True or stats.get('cyclic') is not False:
        raise ValueError('native tensor/cyclic claims differ')
    steps=stats['steps']
    if type(steps) is not int or steps<0:raise ValueError('invalid step count')
    if any(type(stats.get(key)) is not int or stats[key]<0 for key in ['best_rank','current_rank','max_visited_rank','max_rank_excess','accepted_moves','rejected_moves']):
        raise ValueError('invalid native integer counters')
    for name in ['rank_residency_steps','rank_after_move_steps','rank_excess_residency_steps']:
        hist=stats.get(name,{})
        if (not isinstance(hist,dict) or any(not k.isdecimal() or int(k)>max_rank or type(v) is not int or v<0 for k,v in hist.items())
            or sum(hist.values())!=steps):raise ValueError('invalid complete residency histogram: '+name)
    if (not 0<stats['best_rank']<=93 or not stats['best_rank']<=stats['current_rank']<=max_rank
        or not max(93,stats['current_rank'])<=stats['max_visited_rank']<=max_rank
        or not max(map(int,stats['rank_excess_residency_steps']),default=0)<=stats['max_rank_excess']<=max_rank-93):
        raise ValueError('native rank/excess limits differ')
    observed=max([93,*map(int,stats['rank_residency_steps']),*map(int,stats['rank_after_move_steps'])])
    if stats['max_visited_rank']!=observed:raise ValueError('native maximum rank disagrees with complete histograms')
    if (set(stats['accepted_by_kind'])!={'flip','plus','reduction'}
        or any(type(value) is not int or value<0 for value in stats['accepted_by_kind'].values())
        or sum(stats['accepted_by_kind'].values())!=stats['accepted_moves'] or stats['accepted_moves']+stats['rejected_moves']!=steps):
        raise ValueError('native move counts differ')
    if sum(stats[key] for key in ['flip_attempts','plus_attempts','reduction_attempts'])!=steps:
        raise ValueError('native attempt counts differ')
    for kind in ['flip','plus','reduction']:
        changes=stats['rank_changes_by_kind'][kind]
        if sum(changes[key] for key in ['up','equal','down'])!=stats['accepted_by_kind'][kind]:raise ValueError('native accepted-kind rank counts differ')
    return stats,sha(raw)


def run_child(argv,log,stop,inspect,*,wall_seconds,interval=.1):
    """Reap exactly this child with wait4; never signal a process group."""
    process=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT);start=time.monotonic();term_at=None;winner=False;timed_out=False;interrupted=False
    try:
        while True:
            pid,status,usage=os.wait4(process.pid,os.WNOHANG)
            if pid:
                process.returncode=os.waitstatus_to_exitcode(status)
                return {'exit_code':process.returncode,'child_user_seconds':usage.ru_utime,'child_system_seconds':usage.ru_stime,
                        'child_cpu_seconds':usage.ru_utime+usage.ru_stime,'child_max_rss_kib':usage.ru_maxrss,
                        'elapsed_seconds':time.monotonic()-start,'winner':winner,'timed_out':timed_out,'interrupted':interrupted}
            winner=winner or inspect()
            now=time.monotonic();requested=stop()
            if (requested or winner or now-start>wall_seconds+2) and term_at is None:
                interrupted=bool(requested);timed_out=now-start>wall_seconds+2
                try:os.kill(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                term_at=now
            if term_at is not None and now-term_at>2:
                try:os.kill(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            time.sleep(interval)
    except BaseException:
        if process.returncode is None:
            try:os.kill(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            end=time.monotonic()+2
            while time.monotonic()<end:
                pid,status,usage=os.wait4(process.pid,os.WNOHANG)
                if pid:process.returncode=os.waitstatus_to_exitcode(status);break
                time.sleep(.02)
            if process.returncode is None:
                try:os.kill(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                _,status,_=os.wait4(process.pid,0);process.returncode=os.waitstatus_to_exitcode(status)
        raise


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['campaign','input','binary','heldout-declaration','output-dir']:p.add_argument('--'+name,type=Path,required=True)
    for name in ['expected-input-sha256','expected-binary-sha256','expected-heldout-sha256','expected-runtime-sha256']:p.add_argument('--'+name,required=True)
    p.add_argument('--seconds',type=float,default=30);p.add_argument('--cpu',type=int,default=1);p.add_argument('--memory-mb',type=int,default=768)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--reduction-dwell',type=int,choices=(0,64,32768),required=True)
    p.add_argument('--preview',action='store_true');a=p.parse_args(argv)
    if a.cpu!=1 or a.memory_mb!=768 or a.seed<0 or not math.isfinite(a.seconds) or not 0<a.seconds<=30:p.error('CPU1/768MiB,nonnegative seed,0<seconds<=30 required')
    campaign=a.campaign.resolve();config,_=read(campaign/'campaign.json')
    if config.get('dimension')!=5 or config.get('field')!=2 or config.get('target_rank')!=92:raise ValueError('n5/F2 target92 campaign required')
    deadline=__import__('datetime').datetime.fromisoformat(config['deadline_utc'].replace('Z','+00:00')).timestamp()
    if (campaign/'guard_stopped.json').exists() or time.time()+a.seconds+2>deadline:raise ValueError('campaign stop/deadline barrier')
    if any(path.exists() for path in [campaign/'WINNER.json',*campaign.glob('*/WINNER.json')]):raise ValueError('existing campaign WINNER barrier')
    code=runtime_hashes();runtime_sha=sha(raw_json(code))
    if runtime_sha!=a.expected_runtime_sha256:raise ValueError('frozen runtime hash differs')
    terms,source,source_raw=validate_input(a.input,a.expected_input_sha256,a.heldout_declaration,a.expected_heldout_sha256)
    binary_raw=a.binary.read_bytes()
    if sha(binary_raw)!=a.expected_binary_sha256:raise ValueError('binary hash differs')
    output=a.output_dir.resolve()
    if not output.is_relative_to(campaign) or output.exists():raise ValueError('output must be a NEW campaign subdirectory')
    prefix=output/'native/walk';frozen_binary=output/'frozen/native-worker';mask_path=output/'native/input.txt'
    argv=command(frozen_binary,mask_path,prefix,seconds=a.seconds,seed=a.seed,dwell=a.reduction_dwell)
    metadata={'format':'bounded-native-dwell42-v1','source':source,'binary_sha256':a.expected_binary_sha256,
              'seed':a.seed,'reduction_dwell':a.reduction_dwell,'seconds':a.seconds,'cpu':1,'memory_mb':768,'command':argv,
              'runtime_code_sha256':code,'runtime_sha256':runtime_sha,
              'rank_semantics':'full essential bilinear products; all exports freshly verified','claim':'pilot only; no advantage claim'}
    if a.preview:print(json.dumps({'status':'PREVIEW_ONLY','zero_mutations':True,**metadata},sort_keys=True,indent=2));return
    os.sched_setaffinity(0,{1});cap=768*1024**2;resource.setrlimit(resource.RLIMIT_AS,(cap,cap));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    output.mkdir(parents=True);freeze(output/'input.json',source_raw);freeze(output/'input.verification.json',raw_json(source))
    for name in code:freeze(output/'frozen/runtime'/name,(ROOT/name).read_bytes())
    freeze(frozen_binary,binary_raw,True);freeze(mask_path,''.join(f'{x} {y} {z}\n' for x,y,z in terms).encode())
    freeze(output/'manifest.json',raw_json(metadata));stopping=False;seen={};parent_cpu=time.process_time();last_scan=0
    def interrupt(sig,frame):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGINT,interrupt)
    def stopped():return stopping or (campaign/'guard_stopped.json').exists() or time.time()>=deadline
    def inspect():
        nonlocal last_scan
        if time.monotonic()-last_scan<.5:return False
        last_scan=time.monotonic();return drain(prefix,output,metadata,seen)
    if stopped():
        summary={'status':'CAMPAIGN_STOPPED_BEFORE_NATIVE','winner':False,'native_queries_started':0,'claim':'no native target query started'}
        atomic(output/'summary.json',summary);print(json.dumps(summary,sort_keys=True));return
    with (output/'worker.log').open('x') as log:result=run_child(argv,log,stopped,inspect,wall_seconds=a.seconds)
    winner=drain(prefix,output,metadata,seen) or (output/'WINNER.json').exists()
    if result['exit_code']!=0:raise RuntimeError('native child failed; artifacts retained')
    stats,stats_sha=validate_stats(str(prefix)+'.stats.json',seed=a.seed,dwell=a.reduction_dwell)
    raw_best=_read_terms(str(prefix)+'.best.txt',5);raw_current=_read_terms(str(prefix)+'.current.txt',5)
    if len(raw_best)!=stats['best_rank'] or len(raw_current)!=stats['current_rank']:raise ValueError('final native ranks disagree with exact exports')
    source_terms=set(terms);union=set();by_rank={}
    for item in seen.values():
        current=set(map(tuple,item['terms']));union|=current;by_rank[str(item['rank'])]=by_rank.get(str(item['rank']),0)+1
        item['source_jaccard_distance']=1-len(current&source_terms)/len(current|source_terms)
        item.pop('terms')
    summary={'status':'VERIFIED_TARGET' if winner else 'UNKNOWN_WITHIN_PILOT','winner':winner,'native_queries_started':1,'execution':result,'stats':stats,
             'stats_sha256':stats_sha,'wrapper_cpu_seconds_after_preparation':time.process_time()-parent_cpu,
             'exported_diversity':{'unique_certificates':len(seen),'unique_certificates_excluding_input':sum(key!=term_set_sha256(terms) for key in seen),
                                   'unique_full_terms':len(union),'novel_full_terms_vs_input':len(union-source_terms),'per_rank':by_rank,'certificates':seen},
             'claim':'exact outputs and measured residency/diversity only; no learning or5x5 advantage established'}
    freeze(output/'final_stats.json',raw_json(stats));atomic(output/'summary.json',summary);print(json.dumps(summary,sort_keys=True))


if __name__=='__main__':main()
