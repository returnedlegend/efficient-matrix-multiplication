"""Root-authorized one-at-a-time queue chain, at most eight native epochs."""
import argparse
import datetime as dt
import fcntl
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from scripts import campaign_native_bandit7 as b
from scripts.append_campaign_jobs42 import append_jobs

def global_check(campaign,manifest):
    guard=b.p.lifecycle.Guard(b.p.DEADLINE,5,campaign,campaign/'operations-v3/state.json',manifest['campaign_sha256'])
    guard.canonical=b.p.CampaignGuard(5,guard.hard.isoformat(),(),campaign/'operations-v3/state.json',campaign_dir=campaign)
    guard('bandit_controller_fresh_global')
    return guard

def run(bundle,pin,checkpoint,checkpoint_pin,output):
    manifest=b.load_bundle(bundle,pin);campaign=Path(manifest['campaign']);output.mkdir(exist_ok=True)
    while True:
        state=b.validate_state(b.read_pin(checkpoint,checkpoint_pin),pin,manifest['baseline_sha256'])
        if state['completed_epochs']>=8:return dict(status='COMPLETE_EIGHT_EPOCHS',checkpoint_sha256=checkpoint_pin)
        choice=b.choose(state,manifest['sources']);name=choice['profile']['id'];directory=campaign/name
        guard=global_check(campaign,manifest)
        if time.time()+210>guard.hard.timestamp():raise ValueError('next full epoch cannot fit deadline')
        queue=json.loads((campaign/'queue.json').read_text());existing=next((job for job in queue['jobs'] if job['id']==name),None)
        if existing is None:
            if directory.exists():raise ValueError('orphan epoch output; no reset/relaunch')
            qstate=json.loads((campaign/'queue_state.json').read_text())
            if any(job.get('status')=='running' and job['spec']['cpu']==2 for job in qstate['jobs'].values()):
                time.sleep(1);continue
            proposal=output/(name+'.proposal.json')
            prepared=b.prepare_job(bundle,pin,checkpoint,checkpoint_pin,proposal)
            global_check(campaign,manifest)
            receipt=append_jobs(campaign/'queue.json',proposal,prepared['proposal_sha256'],output/(name+'.receipt.json'),apply=True,enable=True)
            print(json.dumps(dict(event='APPENDED',epoch=state['completed_epochs']+1,id=name,utc=receipt['utc'],profile=choice['profile'])),flush=True)
        else:
            expected=dict(id=name,cpu=2,memory_mb=768,seconds=210,enabled=True,command=[sys.executable,'-B',
                str(bundle/'code/scripts/campaign_native_bandit7.py'),'--bundle',str(bundle),'--manifest-sha256',pin,
                '--checkpoint',str(checkpoint),'--checkpoint-sha256',checkpoint_pin,'--output-dir',str(directory),'--execute'])
            if existing!=expected:
                raise ValueError('existing job does not match exact expected checkpoint/runtime')
        wait_deadline=time.monotonic()+240
        while True:
            global_check(campaign,manifest)
            qstate=json.loads((campaign/'queue_state.json').read_text());job=qstate['jobs'].get(name,{})
            if job.get('status')in('completed','failed_to_launch'):
                if not(directory/'outcome.json').exists():raise ValueError('terminal job without verified outcome; no continuation')
                break
            if time.monotonic()>wait_deadline:raise ValueError('queue/epoch supervision elapsed; no continuation')
            time.sleep(1)
        outcome=json.loads((directory/'outcome.json').read_text())
        if outcome['status']=='TARGET_EMITTED_TO_GLOBAL_GUARD':return dict(status='STOP_TARGET_GLOBAL_GUARD',id=name)
        if outcome['status']!='COMPLETED_EXPLORATION' or outcome.get('previous_checkpoint_sha256')!=checkpoint_pin:
            raise ValueError('UNKNOWN/error/malformed outcome; no continuation')
        if b.sha((directory/'summary.json').read_bytes())!=outcome['native_summary_sha256']:raise ValueError('native summary drift')
        next_path=directory/'checkpoint.json';next_pin=outcome['checkpoint_sha256']
        next_state=b.validate_state(b.read_pin(next_path,next_pin),pin,manifest['baseline_sha256'])
        if next_state['completed_epochs']!=state['completed_epochs']+1 or next_state['previous_checkpoint_sha256']!=checkpoint_pin:
            raise ValueError('policy chain skipped or repeated epoch')
        print(json.dumps(dict(event='VERIFIED_EPOCH_COMPLETE',id=name,reward=outcome['reward_evidence']['reward'],
            doubleverified_samples=outcome['reward_evidence']['doubleverified_samples'],new_atoms=outcome['reward_evidence']['new_atom_count'],checkpoint_sha256=next_pin)),flush=True)
        checkpoint,checkpoint_pin=next_path,next_pin

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['bundle','checkpoint','output-dir']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--manifest-sha256',required=True);parser.add_argument('--checkpoint-sha256',required=True);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not args.execute:raise ValueError('disabled without root-authorized explicit execute')
    output=args.output_dir.resolve()
    output.mkdir(parents=True,exist_ok=True)
    lock=(output/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    b.p.safe.base.freeze(output/'request.json',b.encoded(dict(bundle=str(args.bundle.resolve()),manifest_sha256=args.manifest_sha256,
        checkpoint=str(args.checkpoint.resolve()),checkpoint_sha256=args.checkpoint_sha256,max_epochs=8)))
    try:result=run(args.bundle.resolve(),args.manifest_sha256,args.checkpoint.resolve(),args.checkpoint_sha256,output)
    except Exception as error:result=dict(status='STOP_ERROR_OR_UNKNOWN',reason=str(error))
    result['utc']=dt.datetime.now(dt.timezone.utc).isoformat();b.p.safe.base.freeze(output/'FINAL.json',b.encoded(result));print(json.dumps(result),flush=True)
    return 0 if result['status']=='COMPLETE_EIGHT_EPOCHS' else 2

if __name__=='__main__':raise SystemExit(main())
