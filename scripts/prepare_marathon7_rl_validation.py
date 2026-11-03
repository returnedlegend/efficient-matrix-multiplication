"""Audit completed C7 pilots and freeze a disabled validation proposal.

Reads existing results/checkpoints/events and pool metadata only. No task
payloads, native execution, environment episodes, fitting, validation CLI,
queue mutation, or old campaign writes.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.collect_operator44_pilots import read,encoded,freeze,sha
from scripts.append_campaign_jobs42 import proposals
from mmsearch.rl_finetune44 import validate_operator
from mmsearch.rl_search import TinyActorCritic
import numpy as np

ROLES=('learned','frozen','random')

def finite_actor(state):
    actor=TinyActorCritic.from_state(state)
    for group in ('params','m','s'):
        values=getattr(actor,group)
        if set(values)!=set(actor.params):raise ValueError('Adam/policy namespaces differ')
        for name,array in values.items():
            if array.shape!=actor.params[name].shape or not np.isfinite(array).all():raise ValueError('nonfinite/inconsistent actor arrays')
    if actor.params['W'].shape!=(20,32) or state['hidden']!=32:raise ValueError('actor architecture differs')
    return actor

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('campaign','runtime','collection','output-dir'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args(argv);campaign,runtime,collection,out=[Path(x).resolve() for x in (a.campaign,a.runtime,a.collection,a.output_dir)]
    if campaign.name!='marathon7_20261103T122417Z' or not out.is_relative_to(campaign) or out.exists():raise ValueError('new explicit C7 output required')
    report=read(collection/'REPORT.json')
    if not all(report[k] for k in ('all_three_CPU_targets_completed','all_available_checks_pass','quarantine_unchanged')):raise ValueError('pilot result review is not clean/completed')
    initial=read(runtime/'initial/checkpoint.json');initial_schedule=read(runtime/'initial/checkpoint.schedule.json');rows=[];pins={}
    clock=initial['finetune43']['clock'];f=clock['recovery_fraction']
    initial_debt=f*(initial_schedule['record_cpu']-clock['record_origin'])-(1-f)*(initial_schedule['recovery_cpu']-clock['recovery_origin'])
    for role in ROLES:
        directory=campaign/f'marathon7-{role}44-pilot450';cp_path=directory/'checkpoint.json';schedule_path=directory/'checkpoint.schedule.json'
        cp_raw=cp_path.read_bytes();cp=json.loads(cp_raw);schedule=read(schedule_path);result=read(campaign/(directory.name+'-job.result.json'))
        if schedule['checkpoint_sha256']!=sha(cp_raw):raise ValueError('actual final checkpoint/schedule mismatch')
        validate_operator(cp);finite_actor(cp['policy'])
        control=role!='learned';same=cp['policy']==initial['policy']
        if control and not same:raise ValueError('control changed weights/Adam/counters')
        if not control and (cp['policy']['updates']<=initial['policy']['updates'] or any(cp['policy'][key]==initial['policy'][key] for key in ('params','m','s'))):raise ValueError('learned gradient state did not change')
        if cp['finetune43']!=initial['finetune43'] or schedule['finetune43']!=initial_schedule['finetune43']:raise ValueError('phase clock/debt origin changed')
        main_cpu=schedule['record_cpu']-initial_schedule['record_cpu'];recovery_cpu=schedule['recovery_cpu']-initial_schedule['recovery_cpu']
        if main_cpu<450 or not math.isclose(main_cpu,schedule['invocation_main_cpu'],abs_tol=1e-7) or recovery_cpu<0:raise ValueError('actual CPU target/accounting differs')
        if result['exit_code']!=0 or result['timed_out'] or result['interrupted']:raise ValueError('pilot did not cleanly complete')
        r,aux=initial_schedule['record_cpu'],initial_schedule['recovery_cpu'];starts=0
        for line in (directory/'events.jsonl').read_text().splitlines():
            event=json.loads(line)
            if event.get('event')=='recovery_start':
                debt=f*(r-clock['record_origin'])-(1-f)*(aux-clock['recovery_origin'])
                if debt<=0 or event.get('training_split')!='train':raise ValueError('auxiliary launch without inherited training CPU debt')
                starts+=1
            if 'record_cpu' in event and 'recovery_cpu' in event:
                if event['record_cpu']+1e-9<r or event['recovery_cpu']+1e-9<aux:raise ValueError('event CPU decreased')
                r,aux=event['record_cpu'],event['recovery_cpu']
        if not math.isclose(r,schedule['record_cpu'],abs_tol=1e-7) or not math.isclose(aux,schedule['recovery_cpu'],abs_tol=1e-7):raise ValueError('event/final CPU disagreement')
        final_debt=f*(r-clock['record_origin'])-(1-f)*(aux-clock['recovery_origin'])
        saved=next(row for row in report['pilots'] if row['job']==directory.name)
        if saved['checkpoint_sha256']!=sha(cp_raw) or saved['native_stats']['covered']!=saved['native_stats']['referenced']:raise ValueError('collector checkpoint/native coverage differs')
        rows.append(dict(role=role,main_CPU=main_cpu,recovery_CPU=recovery_cpu,updates_before=initial['policy']['updates'],updates_after=cp['policy']['updates'],full_policy_unchanged=same,
            actual_policy_load_finite=True,initial_recovery_debt_CPU=initial_debt,final_recovery_debt_CPU=final_debt,recovery_starts=starts,
            native_runs=saved['native_stats']['covered'],checkpoint_sha256=sha(cp_raw),policy_sha256=sha(encoded(cp['policy'])),best_rank=len(cp['best']),current_rank=len(cp['current'])))
        for path in (cp_path,schedule_path,directory/'events.jsonl',campaign/(directory.name+'-job.result.json')):pins[str(path)]=sha(path.read_bytes())
    learned=collection/'learned-frozen';snapshot=read(learned/'snapshot.json')
    for name,record in snapshot['copies'].items():
        if sha((learned/name).read_bytes())!=record['sha256'] or (learned/name).read_bytes()!=Path(record['source']).read_bytes() or (learned/name).stat().st_mode&0o222:raise ValueError('actual immutable learned snapshot differs')
    cp=read(learned/'checkpoint.json');schedule=read(learned/'checkpoint.schedule.json')
    if schedule['checkpoint_sha256']!=sha((learned/'checkpoint.json').read_bytes()):raise ValueError('snapshot schedule mismatch')
    validate_operator(cp);finite_actor(cp['policy'])
    old_job=read(runtime/'proposed_validation_job.json');job=copy.deepcopy(old_job);job['id']='marathon7-evaluate44-validation-seed4411034407';job['enabled']=False
    cmd=job['command'];new_output=campaign/job['id'];old_output=Path(cmd[cmd.index('--outdir')+1]);old_id=old_job['id']
    cmd[cmd.index('--checkpoint')+1]=str(learned/'checkpoint.json');cmd[cmd.index('--outdir')+1]=str(new_output)
    if new_output.exists() or old_output.exists():raise ValueError('this validation output already exists')
    for directory in (campaign,Path(read(campaign/'campaign.json')['prior_campaign'])):
        for name in ('queue_state.json','queue.json'):
            path=directory/name
            if path.exists():
                value=read(path);jobs=value.get('jobs',{});ids=set(jobs) if isinstance(jobs,dict) else {item['id'] for item in jobs}
                if old_id in ids or job['id'] in ids:raise ValueError('validation id was previously queued; root must review freshness')
    reference=Path(cmd[cmd.index('--reference')+1]);reference_cp=read(reference);validate_operator(reference_cp);finite_actor(reference_cp['policy'])
    if reference_cp['policy']!=initial['policy']:raise ValueError('reference differs from frozen/warm policy')
    pool=Path(cmd[cmd.index('--recovery-pool')+1]);pool_manifest=read(pool/'manifest.json')
    validation_sources=set(pool_manifest['evaluation_sources']['validation']);final_sources=set(pool_manifest['evaluation_sources']['test'])
    tasks=[entry for entry in pool_manifest['entries'] if entry['term_hash'] in pool_manifest['split']['heldout'] and entry['source_term_hash'] in validation_sources]
    if len(tasks)!=14 or len(validation_sources)!=2 or len(final_sources)!=2 or validation_sources&final_sources:raise ValueError('reserved validation/test source split differs')
    if cmd[cmd.index('--heldout-subset')+1]!='validation' or cmd[cmd.index('--seed')+1]!='4411034407' or cmd[cmd.index('--seeds')+1]!='16':raise ValueError('fresh declared validation differs')
    if cmd[cmd.index('--step-limit')+1]!='50000' or cmd[cmd.index('--max-actions')+1]!='4':raise ValueError('matched move/action budgets differ')
    for path in (reference,pool/'manifest.json',Path(cmd[4]),Path(cmd[cmd.index('--native-binary')+1]),runtime/'manifest.json',collection/'REPORT.json',learned/'checkpoint.json',learned/'checkpoint.schedule.json'):pins[str(path)]=sha(path.read_bytes())
    out.mkdir()
    freeze(out/'proposed_job.json',encoded(job));proposals(out/'proposed_job.json',sha((out/'proposed_job.json').read_bytes()))
    freeze(out/'PILOT_INDEPENDENT_QA.json',encoded(dict(status='PASS',pilots=rows,native_runs_covered=sum(row['native_runs'] for row in rows),collector_role_mapping='Explicit C7 learned/frozen/random ids; no prefix inference.',snapshot_checked=True,training_or_validation_calls=0,old42_writes=0)))
    freeze(out/'validation-task-index.json',encoded([{k:entry[k] for k in ('term_hash','source_term_hash','task_bucket','strict_hard')} for entry in tasks]))
    freeze(out/'source-pins.json',encoded(pins))
    freeze(out/'manifest.json',encoded(dict(status='PREPARED_DISABLED_PENDING_ROOT_RESULT_REVIEW',job=job,pilot_report_sha256=sha((collection/'REPORT.json').read_bytes()),independent_pilot_QA_sha256=sha((out/'PILOT_INDEPENDENT_QA.json').read_bytes()),learned_snapshot_sha256=sha((learned/'checkpoint.json').read_bytes()),source_pins_sha256=sha((out/'source-pins.json').read_bytes()),
        validation=dict(tasks=14,repeats=16,triplets=224,max_episodes=672,seed=4411034407,task_payloads_opened=0,validation_source_hashes=sorted(validation_sources),reserved_final_test_source_hashes=sorted(final_sources),heldout_subset='validation',old_output_absent=True,old_and_new_ids_absent_from_queue=True,training=False,weights_frozen=True,matched_step_limit_per_action=50000,max_actions=4,driver_seconds=180,outer_seconds=195,completed_triplets_must_be_reported_not_assumed=True),
        validation_calls=0,validation_launch_authorized=False,promotion_authorized=False,queue_writes=0,old42_writes=0,claim='Pilot parameter updates alone demonstrate no advantage; validation feedback cannot establish unbiased final-test performance. Final two test sources remain reserved.',launch_condition='Root reviews actual pilot report/snapshot/pins and explicitly authorizes;195s outer envelope must fit C7 cutoff and available CPU3/1024MiB.')))
    freeze(out/'prepare_marathon7_rl_validation.py',Path(__file__).read_bytes());freeze(out/'collect_marathon7_operator44_pilots.py',(ROOT/'scripts/collect_marathon7_operator44_pilots.py').read_bytes())
    freeze(out/'checksums.json',encoded({str(path.relative_to(out)):sha(path.read_bytes()) for path in sorted(out.rglob('*')) if path.is_file()}))
    if any(sha(Path(path).read_bytes())!=wanted for path,wanted in pins.items()):raise ValueError('input changed during audit/proposal')
    print(encoded(dict(status='PASS_PREPARED_DISABLED_NO_VALIDATION_CALL',proposal_sha256=sha((out/'proposed_job.json').read_bytes()),manifest_sha256=sha((out/'manifest.json').read_bytes()),pilots=rows,validation_tasks=14,triplets=224)).decode())
    return 0

if __name__=='__main__':raise SystemExit(main())
