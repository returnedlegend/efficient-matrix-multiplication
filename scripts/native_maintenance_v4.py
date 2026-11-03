"""One root-queued CPU3 phase: bounded, exact-audited lossless all-native archival.

All original removal is delegated to the bytewise verified V2 archive helper.
This does not touch certificates, proofs, final models, or queue policy. A single
phase handles at most1000 completed known-recovery runs and rotates sources.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import resource
import signal
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from scripts.archive_native_runs_v4 import archive_runs, runs_root, sha256_file
from scripts.rl_campaign_queue import atomic_json, load_json, parse_time, utc

GIB=1024**3


def phase(campaign,config,*,archiver=archive_runs,now=time.time,free_bytes=None):
    campaign=Path(campaign).resolve()
    policy,_=load_json(campaign/'campaign.json')
    if now()>=parse_time(policy['deadline_utc']): return {'status':'deadline','runs':0}
    if (campaign/'guard_stopped.json').exists(): return {'status':'guard_stopped','runs':0}
    roots=config.get('runs_directories',[])
    if not isinstance(roots,list): raise ValueError('runs_directories must be an explicit list')
    allowed_campaigns=[campaign]
    if policy.get('prior_campaign'): allowed_campaigns.append(Path(policy['prior_campaign']).resolve())
    if config.get('discover_all_native',False):
        discovered=[]
        for allowed in allowed_campaigns:
            for pattern in ('*/native/record/runs','*/native/runs','*/native/known-recovery/runs'):
                discovered.extend(allowed.glob(pattern))
        roots=sorted(set([str(Path(x).resolve()) for x in roots]+[str(x.resolve()) for x in discovered]))
    if not roots: return {'status':'no_sources','runs':0}
    max_runs=config.get('max_runs',100)
    if type(max_runs) is not int or not 1<=max_runs<=1000: raise ValueError('max_runs must be1..1000')
    age=config.get('minimum_age',60)
    if type(age) not in (int,float) or not math.isfinite(age) or age<30: raise ValueError('minimum_age must be finite and>=30')
    root=campaign/'native-maintenance-v4'; root.mkdir(exist_ok=True)
    state_path=root/'state.json'
    state,_=load_json(state_path) if state_path.exists() else ({'format':'native-maintenance-v4','next_source':0,'phases':0,'total_runs_removed':0},None)
    # Reserve scratch beyond the8GiB minimum; never archive onto a full disk.
    if free_bytes is None:
        disk=os.statvfs(campaign); free_bytes=disk.f_bavail*disk.f_frsize
    if free_bytes<9*GIB: return {'status':'insufficient_archive_scratch','free_bytes':free_bytes,'runs':0}
    current=[x for x in roots if Path(x).is_relative_to(campaign)]
    historical=[x for x in roots if not Path(x).is_relative_to(campaign)]
    # Alternate current and historical trees to bound new campaign growth.
    choose_current=bool(current and (state['phases']%2==0 or not historical))
    pool=current if choose_current else historical
    cursor='next_current' if choose_current else 'next_historical'
    index=state.get(cursor,0)%len(pool); source=runs_root(pool[index])
    # Explicit runs roots from this campaign or declared prior campaign only.
    allowed=[campaign]
    if policy.get('prior_campaign'): allowed.append(Path(policy['prior_campaign']).resolve())
    if not any(source.is_relative_to(p) for p in allowed): raise ValueError('recovery source outside authorized campaigns')
    native=source.parent if source.parent.name=='native' else source.parent.parent
    output=native.parent/'native-run-archives'
    if config.get('archive_output_root'):
        import hashlib
        central=Path(config['archive_output_root']).resolve()
        if not any(central.is_relative_to(p) for p in allowed):
            raise ValueError('central archive output outside authorized campaigns')
        source_key=hashlib.sha256(str(source).encode()).hexdigest()[:16]
        output=central/(native.parent.name+'-'+source.parent.name+'-'+source_key)
    max_raw_bytes=config.get('max_raw_bytes',512*1024**2)
    if type(max_raw_bytes) is not int or not 1024**2<=max_raw_bytes<=512*1024**2:
        raise ValueError('max_raw_bytes must be1MiB..512MiB')
    before=now()
    result=archiver(source,output,minimum_age=age,max_runs=max_runs,remove_after_verify=True,record_rank=92,max_raw_bytes=max_raw_bytes)
    if result.get('status')=='record_preserved':
        # The live guard prioritizes immediate experiment/records/*.json paths.
        raw=(json.dumps(result['record']['candidate'],sort_keys=True)+'\n').encode()
        import hashlib
        record_directory=campaign/'maintenance-records/records'; record_directory.mkdir(parents=True,exist_ok=True)
        destination=record_directory/(hashlib.sha256(raw).hexdigest()+'.json')
        if not destination.exists():
            with destination.open('xb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            destination.chmod(0o444)
    result.update(status=result.get('status','ok'),source=str(source),elapsed_seconds=now()-before,utc=utc(now()),
                  utility_sha256=sha256_file(Path(__file__)),archive_helper_sha256=sha256_file(REPO/'scripts/archive_native_runs_v4.py'))
    state.update(next_source=state['next_source']+1,phases=state['phases']+1,last_result=result,
                 total_runs_removed=state['total_runs_removed']+result.get('removed_runs',0))
    state[cursor]=state.get(cursor,0)+1
    atomic_json(state_path,state)
    # Per-phase manifests and all archive manifests are preserved; bounded
    # summaries need no ever-growing JSONL or repeated scans of old artifacts.
    atomic_json(root/'latest.json',result)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True); p.add_argument('--config',type=Path,required=True)
    args=p.parse_args(argv)
    os.sched_setaffinity(0,{3}); resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    lock=(args.campaign/'native-maintenance-v4.lock').open('a'); fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    config,_=load_json(args.config)
    def terminate(sig,frame):
        # Unwind the archive helper so its temporary bundle cleanup runs.
        raise SystemExit(128+sig)
    signal.signal(signal.SIGTERM,terminate); signal.signal(signal.SIGINT,terminate)
    print(json.dumps(phase(args.campaign,config),sort_keys=True),flush=True)


if __name__=='__main__': main()
