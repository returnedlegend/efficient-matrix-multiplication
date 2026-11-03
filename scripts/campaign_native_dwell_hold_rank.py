"""Bounded separate rank-hold pilot. --preview starts zero native queries.

Matched two-source flag0/flag1 arms use K4/D128/H12, <=30s each, CPU0 or3.
Downward improving flips are deliberately deferred during the dwell window.
Every export has a fresh full tensor check; WINNER requires both verifiers.
"""
from __future__ import annotations
import argparse
import datetime
import json
import math
import os
from pathlib import Path
import resource
import signal
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from scripts import campaign_native_plus_burst42 as base
from scripts import campaign_native_plus_burst42_long as safe

RUNTIME=list(dict.fromkeys([*safe.RUNTIME,'native/flip_worker_dwell_hold_rank.cpp','scripts/campaign_native_dwell_hold_rank.py']))

def runtime_hashes():return {name:base.sha((ROOT/name).read_bytes()) for name in RUNTIME}

def command(binary,input_path,prefix,*,seconds,seed,hold_rank=0):
    if type(hold_rank) is not int or hold_rank not in (0,1):raise ValueError('hold rank arm must be0 or1')
    return base.command(binary,input_path,prefix,seconds=seconds,seed=seed,dwell=128,plus_burst=4)+['--dwell-hold-rank',str(hold_rank)]

def validate_stats(path,*,seed,hold_rank):
    stats,digest=base.validate_stats(path,seed=seed,dwell=128,plus_burst=4)
    if stats.get('dwell_hold_rank')!=hold_rank or stats.get('hold_instrumentation')!='dwell-hold-rank-v1':raise ValueError('hold arm/instrumentation differs')
    names=['active_steps','flip_attempts','rejected_downward_flips','prevented_rank_loss','rank_cap_rejections','steps_at_rank_cap',
           'active_rank_loss_moves','active_rank_loss','windows_started','window_renewals','window_expirations','restart_events','restart_rank_loss_events','restart_rank_loss']
    if any(type(stats.get('hold_'+key)) is not int or stats['hold_'+key]<0 for key in names):raise ValueError('invalid hold counters')
    if not hold_rank:
        if any(stats['hold_'+key] for key in names):raise ValueError('disabled hold counters must be zero')
    elif (stats['hold_active_steps']!=stats['dwell_steps'] or stats['hold_flip_attempts']!=stats['dwell_flip_attempts']
          or stats['hold_rejected_downward_flips']>stats['hold_flip_attempts']
          or stats['hold_prevented_rank_loss']<stats['hold_rejected_downward_flips']
          or stats['hold_windows_started']!=stats['dwell_windows_started']
          or stats['hold_window_renewals']!=stats['dwell_windows_rearmed']
          or stats['hold_restart_events']!=stats['dwell_restart_events']):raise ValueError('hold counters do not reconstruct dwell counters')
    return stats,digest

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['campaign','input','binary','heldout-declaration','output-dir']:p.add_argument('--'+name,type=Path,required=True)
    for name in ['expected-input-sha256','expected-binary-sha256','expected-heldout-sha256','expected-runtime-sha256']:p.add_argument('--'+name,required=True)
    p.add_argument('--seconds',type=float,default=30);p.add_argument('--cpu',type=int,choices=(0,3),default=3)
    p.add_argument('--memory-mb',type=int,choices=(768,),default=768);p.add_argument('--seed',type=int,required=True)
    p.add_argument('--dwell-hold-rank',type=int,choices=(0,1),default=0);p.add_argument('--preview',action='store_true');a=p.parse_args(argv)
    if a.seed<0 or not math.isfinite(a.seconds) or not 0<a.seconds<=30:p.error('nonnegative seed and0<seconds<=30 required')
    campaign=a.campaign.resolve();config,_=base.read(campaign/'campaign.json')
    if config.get('dimension')!=5 or config.get('field')!=2 or config.get('target_rank')!=92:raise ValueError('n5/F2 target92 campaign required')
    deadline=datetime.datetime.fromisoformat(config['deadline_utc'].replace('Z','+00:00')).timestamp()
    stop_policy=safe.StopPolicy(campaign,deadline)
    if stop_policy() or time.time()+a.seconds+15>deadline:raise ValueError('campaign stop/deadline barrier')
    code=runtime_hashes();runtime_sha=base.sha(base.raw_json(code))
    if runtime_sha!=a.expected_runtime_sha256:raise ValueError('frozen runtime hash differs')
    terms,source,source_raw=base.validate_input(a.input,a.expected_input_sha256,a.heldout_declaration,a.expected_heldout_sha256)
    binary_raw=a.binary.read_bytes()
    if base.sha(binary_raw)!=a.expected_binary_sha256:raise ValueError('binary hash differs')
    output=a.output_dir.resolve()
    if not output.is_relative_to(campaign) or output.exists():raise ValueError('output must be a NEW campaign subdirectory')
    prefix=output/'native/walk';frozen_binary=output/'frozen/native-worker';mask_path=output/'native/input.txt'
    child_argv=command(frozen_binary,mask_path,prefix,seconds=a.seconds,seed=a.seed,hold_rank=a.dwell_hold_rank)
    metadata={'format':'bounded-dwell-hold-rank-pilot-v1','source':source,'binary_sha256':a.expected_binary_sha256,
              'seed':a.seed,'reduction_dwell':128,'plus_burst':4,'dwell_hold_rank':a.dwell_hold_rank,
              'seconds':a.seconds,'cpu':a.cpu,'memory_mb':a.memory_mb,'command':child_argv,'runtime_code_sha256':code,'runtime_sha256':runtime_sha,
              'policy':'rank floor applies only to flips while dwelling, including improving flips; restart may lower rank',
              'rank_semantics':'full essential bilinear products; all exports freshly verified','claim':'pilot only; no advantage claim'}
    if a.preview:print(json.dumps({'status':'PREVIEW_ONLY','zero_mutations':True,**metadata},sort_keys=True,indent=2));return
    os.sched_setaffinity(0,{a.cpu});cap=a.memory_mb*1024**2;resource.setrlimit(resource.RLIMIT_AS,(cap,cap));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    output.mkdir(parents=True);base.freeze(output/'input.json',source_raw);base.freeze(output/'input.verification.json',base.raw_json(source))
    for name in code:base.freeze(output/'frozen/runtime'/name,(ROOT/name).read_bytes())
    base.freeze(frozen_binary,binary_raw,True);base.freeze(mask_path,''.join(f'{x} {y} {z}\n' for x,y,z in terms).encode())
    base.freeze(output/'manifest.json',base.raw_json(metadata));stopping=False;seen={};parent_cpu=time.process_time();last_scan=0
    def interrupt(sig,frame):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGINT,interrupt)
    def stopped():return stopping or stop_policy()
    def inspect():
        nonlocal last_scan
        if time.monotonic()-last_scan<.5:return False
        last_scan=time.monotonic();return safe.drain(prefix,output,metadata,seen,stopped)
    if stopped():
        summary={'status':'CAMPAIGN_STOPPED_BEFORE_NATIVE','winner':False,'native_queries_started':0}
        base.atomic(output/'summary.json',summary);print(json.dumps(summary,sort_keys=True));return
    with (output/'worker.log').open('x') as log:result=base.run_child(child_argv,log,stopped,inspect,wall_seconds=a.seconds)
    winner=safe.drain(prefix,output,metadata,seen,stopped) or (output/'WINNER.json').exists()
    if result['exit_code']!=0:raise RuntimeError('native child failed; artifacts retained')
    stats,stats_sha=validate_stats(str(prefix)+'.stats.json',seed=a.seed,hold_rank=a.dwell_hold_rank)
    if len(base._read_terms(str(prefix)+'.best.txt',5))!=stats['best_rank'] or len(base._read_terms(str(prefix)+'.current.txt',5))!=stats['current_rank']:raise ValueError('final exact export rank differs')
    source_terms=set(terms);union=set();by_rank={}
    for item in seen.values():
        current=set(map(tuple,item['terms']));union|=current;by_rank[str(item['rank'])]=by_rank.get(str(item['rank']),0)+1
        item['source_jaccard_distance']=1-len(current&source_terms)/len(current|source_terms);item.pop('terms')
    summary={'status':'VERIFIED_TARGET' if winner else 'UNKNOWN_WITHIN_PILOT','winner':winner,'native_queries_started':1,'execution':result,'stats':stats,
             'stats_sha256':stats_sha,'wrapper_cpu_seconds_after_preparation':time.process_time()-parent_cpu,
             'exported_diversity':{'unique_certificates':len(seen),'unique_certificates_excluding_input':sum(key!=base.term_set_sha256(terms) for key in seen),
                                   'unique_full_terms':len(union),'novel_full_terms_vs_input':len(union-source_terms),'per_rank':by_rank,'certificates':seen},
             'claim':'exact outputs and measured residency/diversity only; no production5x5 advantage established'}
    base.freeze(output/'final_stats.json',base.raw_json(stats));base.atomic(output/'summary.json',summary);print(json.dumps(summary,sort_keys=True))

if __name__=='__main__':main()
