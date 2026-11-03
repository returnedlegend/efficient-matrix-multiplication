"""One restartable, bounded lossless recovery archive phase for root queue CPU3.

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
from scripts.archive_recovery_runs_v2 import archive_runs, runs_root, sha256_file
from scripts.rl_campaign_queue import atomic_json, load_json, parse_time, utc

GIB=1024**3


def phase(campaign,config,*,archiver=archive_runs,now=time.time,free_bytes=None):
    campaign=Path(campaign).resolve()
    policy,_=load_json(campaign/'campaign.json')
    if now()>=parse_time(policy['deadline_utc']): return {'status':'deadline','runs':0}
    if (campaign/'guard_stopped.json').exists(): return {'status':'guard_stopped','runs':0}
    roots=config.get('runs_directories',[])
    if not roots or not isinstance(roots,list): raise ValueError('runs_directories must be a nonempty explicit list')
    max_runs=config.get('max_runs',1000)
    if type(max_runs) is not int or not 1<=max_runs<=1000: raise ValueError('max_runs must be1..1000')
    age=config.get('minimum_age',60)
    if type(age) not in (int,float) or not math.isfinite(age) or age<30: raise ValueError('minimum_age must be finite and>=30')
    root=campaign/'recovery-maintenance-v3'; root.mkdir(exist_ok=True)
    state_path=root/'state.json'
    state,_=load_json(state_path) if state_path.exists() else ({'format':'recovery-maintenance-v3','next_source':0,'phases':0,'total_runs_removed':0},None)
    # Reserve scratch beyond the8GiB minimum; never archive onto a full disk.
    if free_bytes is None:
        disk=os.statvfs(campaign); free_bytes=disk.f_bavail*disk.f_frsize
    if free_bytes<9*GIB: return {'status':'insufficient_archive_scratch','free_bytes':free_bytes,'runs':0}
    index=state['next_source']%len(roots); source=runs_root(roots[index])
    # Explicit runs roots from this campaign or declared prior campaign only.
    allowed=[campaign]
    if policy.get('prior_campaign'): allowed.append(Path(policy['prior_campaign']).resolve())
    if not any(source.is_relative_to(p) for p in allowed): raise ValueError('recovery source outside authorized campaigns')
    output=source.parent.parent.parent/'recovery-archives'
    before=now()
    result=archiver(source,output,minimum_age=age,max_runs=max_runs,remove_after_verify=True,record_rank=92)
    result.update(status='ok',source=str(source),elapsed_seconds=now()-before,utc=utc(now()),
                  utility_sha256=sha256_file(Path(__file__)),archive_helper_sha256=sha256_file(REPO/'scripts/archive_recovery_runs_v2.py'))
    state.update(next_source=(index+1)%len(roots),phases=state['phases']+1,last_result=result,
                 total_runs_removed=state['total_runs_removed']+result.get('removed_runs',0))
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
    lock=(args.campaign/'recovery-maintenance-v3.lock').open('a'); fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    config,_=load_json(args.config)
    def terminate(sig,frame):
        # Unwind the archive helper so its temporary bundle cleanup runs.
        raise SystemExit(128+sig)
    signal.signal(signal.SIGTERM,terminate); signal.signal(signal.SIGINT,terminate)
    print(json.dumps(phase(args.campaign,config),sort_keys=True),flush=True)


if __name__=='__main__': main()
