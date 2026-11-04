"""Four new exact XOR3-derived starts; CPU2/1024MiB,180native/210outer,max135."""
import argparse
import json
import os
from pathlib import Path
import resource
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from scripts import campaign_native_portfolio7 as p
from mmsearch import native_xor3_source7 as source

OLD_COMMAND=p.command;OLD_STATS=p.validate_stats;MIB=1024**2
def command(binary,input_path,prefix,profile,*,seconds=180,n=5,target=92,steps=10**12):
    if n!=5:return OLD_COMMAND(binary,input_path,prefix,profile,seconds=seconds,n=n,target=target,steps=steps)
    if seconds!=180 or target!=92 or profile['cyclic']:raise ValueError('new unrestricted180second/target92 plateau only')
    argv=OLD_COMMAND(binary,input_path,prefix,profile,seconds=120,n=5,target=92,steps=steps)
    argv[argv.index('--seconds')+1]='180';argv[argv.index('--max-rank')+1]='135';return argv

def validate_stats(stats,profile,n,target):
    if n!=5:return OLD_STATS(stats,profile,n,target)
    if type(stats.get('max_rank'))is not int or stats['max_rank']!=135 or type(stats.get('max_visited_rank'))is not int or stats['max_visited_rank']>135:
        raise ValueError('actual native plateau cap135 differs')
    original=dict(stats);original['max_rank']=105
    return OLD_STATS(original,profile,n,target)

class Budget:
    def __init__(self,campaign,bundle,output,ids):self.campaign,self.bundle,self.output,self.ids=campaign,bundle,output,ids;self.last=-float('inf')
    def check(self,force=False,pending=0):
        if not force and not pending and time.monotonic()-self.last<.5:return
        self.last=time.monotonic();self.current=p.SpaceBudget.size(self.output)
        self.total=p.SpaceBudget.size(self.bundle)+sum(p.SpaceBudget.size(self.campaign/name)for name in self.ids)
        if self.current>=28*MIB or self.total>=148*MIB or self.current+pending>30*MIB-4096 or self.total+pending>150*MIB-4096:
            raise p.OutputHold('new XOR3 plateau output reserve hold')

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--job-id',required=True);parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--preview',action='store_true')
    args=parser.parse_args(argv);bundle=args.bundle.resolve();raw=(bundle/'manifest.json').read_bytes()
    if source.sha(raw)!=args.manifest_sha256:raise ValueError('externally pinned new runtime manifest differs')
    manifest=json.loads(raw)
    for name,pin in manifest['files'].items():
        path=(bundle/name).resolve(strict=True)
        if not path.is_relative_to(bundle)or source.sha(path.read_bytes())!=pin:raise ValueError('new source/runtime closure differs')
    specification=next(job for job in manifest['profiles']if job['id']==args.job_id)
    profile=specification['profile'];p.validate_profile(profile);campaign=Path(manifest['campaign']);output=args.output_dir.resolve()
    if output!=campaign/args.job_id or output.exists()or args.output_dir.is_symlink():raise ValueError('exclusive new exact output required')
    guard=p.lifecycle.Guard(p.DEADLINE,202,campaign,campaign/'operations-v3/state.json',manifest['campaign_sha256'])
    guard.canonical=p.CampaignGuard(202,guard.hard.isoformat(),(),campaign/'operations-v3/state.json',campaign_dir=campaign)
    guard('pre_xor3_source')
    if time.time()+210>guard.hard.timestamp():raise ValueError('210second envelope cannot fit deadline')
    def input_fresh(barrier):guard(barrier);return True
    terms,receipt=source.load_source(bundle,manifest['source_contract_sha256'],specification['source_index'],input_fresh)
    binary=bundle/'native/plus-burst-worker'
    if source.sha(binary.read_bytes())!=p.BINARY_SHA:raise ValueError('audited original native binary differs')
    metadata=dict(status='PREVIEW_ONLY'if args.preview else'INPUT_AUTHENTICATED',profile=profile,input_rank=len(terms),
        source_receipt=receipt,manifest_sha256=args.manifest_sha256,source_contract_sha256=manifest['source_contract_sha256'],
        native_seconds=180,outer_seconds=210,cpu=2,memory_mib=1024,max_rank=135,archive_cap=16,deadline=p.DEADLINE)
    if args.preview:print(json.dumps(metadata,sort_keys=True));return 0
    if os.sched_getaffinity(0)!={2}:raise ValueError('CPU2 queue affinity required')
    soft,hard=resource.getrlimit(resource.RLIMIT_AS);cap=min([1024*MIB]+[value for value in(soft,hard)if value!=resource.RLIM_INFINITY]);resource.setrlimit(resource.RLIMIT_AS,(cap,hard));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    if os.getpriority(os.PRIO_PROCESS,0)<10:os.nice(10-os.getpriority(os.PRIO_PROCESS,0))
    output.mkdir();p.safe.base.freeze(output/'input-contract.json',source.encoded(metadata));p.safe.base.freeze(output/'input.candidate.raw',(bundle/manifest['source_files'][str(specification['source_index'])]).read_bytes())
    budget=Budget(campaign,bundle,output,[row['id']for row in manifest['profiles']]);reason=None
    def fresh(barrier,pending=0):
        nonlocal reason
        try:guard(barrier);budget.check(force=barrier!='loop',pending=pending);return True
        except(p.lifecycle.Stop,p.OutputHold)as error:reason=str(error);return False
    atomic=p.safe.base.atomic
    def bounded_atomic(path,value):
        if not fresh('pre_native_summary',len(p.safe.base.raw_json(value))):raise p.OutputHold('native summary reserve held')
        return atomic(path,value)
    p.command,p.validate_stats,p.safe.base.atomic=command,validate_stats,bounded_atomic
    try:summary=p.execute(binary,terms,output,fresh,profile,seconds=180)
    finally:p.command,p.validate_stats,p.safe.base.atomic=OLD_COMMAND,OLD_STATS,atomic
    if not(output/'summary.json').exists():p.safe.base.freeze(output/'summary.json',source.encoded(summary))
    execution=summary.get('execution',{});stats=summary.get('stats')or{}
    complete=(execution.get('exit_code')==0 and execution.get('timed_out')is False and execution.get('interrupted')is False
        and stats.get('stopped_by_signal')is False and stats.get('seconds_budget')==180 and stats.get('elapsed_seconds',0)>=179.95
        and summary.get('final_checks_complete')is True and reason is None)
    result=dict(status='TARGET_EMITTED_TO_GLOBAL_GUARD'if summary.get('eligible_target_emitted')else'COMPLETED_EXPLORATION'if complete else'STOPPED_ERROR_OR_UNKNOWN',
        input_rank=len(terms),source_index=specification['source_index'],source_receipt_sha256=source.sha((output/'input-contract.json').read_bytes()),
        native_summary_sha256=source.sha((output/'summary.json').read_bytes()),stop_reason=reason,
        guard_final=guard.observation(),claim='Exact derived source and bounded native exploration; no novelty or global rank-bound claim.')
    payload=source.encoded(result)
    if not fresh('pre_final_evidence',len(payload)):
        result=dict(status='STOPPED_ERROR_OR_UNKNOWN',stop_reason=reason,claim='No completed/withinbudget claim.');payload=source.encoded(result)
        if len(payload)>4096:raise ValueError('compact stop evidence exceeds reserved4096bytes')
    p.safe.base.freeze(output/'outcome.json',payload);print(json.dumps(result,sort_keys=True))
    return 0 if result['status']in('COMPLETED_EXPLORATION','TARGET_EMITTED_TO_GLOBAL_GUARD')else 2

if __name__=='__main__':raise SystemExit(main())
