#!/usr/bin/env python3
"""Prepare the root-authorized exact remaining local10 partition, same v5 argv."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,read,sha
from scripts.phase_coordinator42_v2 import validate_job
from scripts.append_campaign_jobs42 import append_jobs
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.marathon7_local import select_plan
from mmsearch.recombine import digest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    c=a.campaign.resolve();b=a.bundle.resolve();out=a.output_dir.resolve();prior=c/'local10-v5-next10000-audit-v1';audit=read(prior/'REPORT.json');first=read(c/'local10-v5-first500-binding-audit-v1.json')
    if audit['status']!='ALL10000_EXACT_FIXED_RESIDUAL_NEGATIVES_AUDITED' or audit['cases']!=10000 or audit['unknowns'] or audit['errors'] or audit['new_decoder_calls']!=0 or first['cases']!=500 or not first['all_exact_negative']:raise ValueError('prior10500 exact audit gate failed')
    if audit['bundle_manifest_sha256']!=sha(b/'manifest.json') or first['bundle_manifest_sha256']!=sha(b/'manifest.json'):raise ValueError('prior audits differ from frozen v5')
    for root in [b,prior]:
        for name,expected in read(root/'manifest.json')['files'].items():
            path=(root/name).resolve()
            if not path.is_relative_to(root) or sha(path)!=expected:raise ValueError('frozen runtime or prior audit changed')
    guard=CampaignGuard(60,'2026-11-03T19:24:17Z',campaign_dir=c,guard_state=c/'operations-v3/state.json');guard.check('pre_remaining_prepare')
    plan=read(b/'plan.json');template=read(b/'PROPOSED-JOB.json');closed=set();remaining=set();jobs=[];chunks=[]
    for number,chunk in enumerate(plan['chunks']):
        if chunk['id']!=f'{number:03d}':raise ValueError('unexpected frozen chunk order')
        cases=select_plan(b,chunk['id'])['cases'];keys={(case['source_id'],case['mask_lo'],case['mask_hi']) for case in cases}
        if len(keys)!=len(cases) or (closed|remaining)&keys:raise ValueError('frozen family source/mask duplicate')
        if number<=20:
            output=c/f'marathon7-local-local10-v5-{number:03d}';summary=read(output/'summary.json')
            if summary['status']!='LOCAL_PORTFOLIO_UNSAT' or not summary['terminal'] or summary['planned_cases']!=len(cases):raise ValueError('previously closed chunk no longer exact')
            closed|=keys;continue
        remaining|=keys;job=json.loads(json.dumps(template));identity=f'marathon7-local-local10-v5-{number:03d}';job['id']=identity
        for flag,value in [('--output-dir',str(c/identity)),('--chunk-id',chunk['id'])]:job['command'][job['command'].index(flag)+1]=value
        # Existing runtime handles this scoped marker; no runtime or math changes.
        job['command']+=['--stop-marker',str(out/'BATCH-HOLD.json')]
        validate_job(job)
        if job['enabled'] or job['cpu']!=2 or job['seconds']!=330 or job['memory_mb']!=1024:raise ValueError('authorized job parameters changed')
        if (c/identity).exists() or (c/(identity+'-job.result.json')).exists():raise ValueError('remaining job already has artifacts; never blind retry')
        jobs.append(job);chunks.append(dict(id=identity,chunk=chunk['id'],cases=len(cases),selected_plan_sha256=digest(cases),source_mask_sha256=digest(sorted(keys))))
    if len(closed)!=10500 or len(remaining)!=90387 or len(jobs)!=181 or sum(chunk['cases'] for chunk in chunks)!=90387 or len(closed|remaining)!=plan['pending_cases']:raise ValueError('remaining partition is not exact complete90387')
    live=read(c/'operations-v3/state.json');ratio=len(remaining)/10000;allocated=int(audit['storage']['outputs_allocated_bytes']*ratio+1);audit_bytes=int(audit['storage']['audit_logical_bytes']*ratio+1)
    if live['campaign_allocated_bytes']+allocated+audit_bytes>=5*1024**3:raise ValueError('forecast plus audits reaches5GiB')
    forecast_wall=audit['measured']['queue_phase_wall_seconds']*ratio
    if datetime.now(timezone.utc).timestamp()+forecast_wall>=guard.deadline:raise ValueError('measured remaining ETA exceeds absolute cutoff')
    out.mkdir(parents=True,exist_ok=False);freeze(out/'PROPOSAL.json',dict(jobs=jobs));freeze(out/'CHUNKS.json',chunks)
    forecast=dict(authorization='Root authorizes all remaining90387 distinct local10 masks on unchanged v5; stop on guard/record/deadline/resource hold/errors, preserve UNKNOWN, no retries/new sources.',
        original_frozen_v5_cases=plan['pending_cases'],already_closed=10500,remaining_cases=90387,jobs=181,source_mask_partition_sha256=digest(sorted(remaining)),closed_source_mask_sha256=digest(sorted(closed)),
        prior10000_audit_sha256=sha(prior/'REPORT.json'),prior500_audit_sha256=sha(c/'local10-v5-first500-binding-audit-v1.json'),bundle_manifest_sha256=sha(b/'manifest.json'),
        forecast_queue_wall_seconds=forecast_wall,forecast_cpu_seconds=audit['measured']['sum_cpu_seconds']*ratio,forecast_outputs_logical_bytes=int(audit['storage']['outputs_logical_bytes']*ratio+1),forecast_outputs_allocated_bytes=allocated,forecast_audit_logical_bytes=audit_bytes,
        observed_guard_allocated_bytes=live['campaign_allocated_bytes'],job_cpu=2,memory_mb_each=1024,outer_wall_seconds_each=330,inner_wall_seconds_each=300,per_case_seconds=2,hard_cutoff_utc='2026-11-03T19:24:17Z',
        scoped_batch_hold_marker=str(out/'BATCH-HOLD.json'),runtime_changes=False,decoder_calls_in_preparation=0,claim='Finite fixed-source/mask experimental family closure only; no global rank claim.')
    freeze(out/'AUTHORIZATION-AND-FORECAST.json',forecast);freeze(out/'marathon7_v5_remaining_batch.py',Path(__file__).read_bytes())
    for name in ['marathon7_v5_remaining_watch.py','marathon7_batch_hold.py']:freeze(out/name,(ROOT/'scripts'/name).read_bytes())
    preview=append_jobs(c/'queue.json',out/'PROPOSAL.json',sha(out/'PROPOSAL.json'),a.receipt,apply=False,enable=True);freeze(out/'PREVIEW.json',preview)
    freeze(out/'manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}));guard.check('pre_remaining_append')
    result=append_jobs(c/'queue.json',out/'PROPOSAL.json',sha(out/'PROPOSAL.json'),a.receipt,apply=a.apply,enable=True)
    print(json.dumps(dict(status=result['status'],apply=a.apply,jobs=181,cases=90387,manifest_sha256=sha(out/'manifest.json'),proposal_sha256=sha(out/'PROPOSAL.json'),forecast_queue_wall_seconds=forecast_wall,forecast_cpu_seconds=forecast['forecast_cpu_seconds'],forecast_allocated_bytes=allocated,receipt=str(a.receipt.resolve())),sort_keys=True))


if __name__=='__main__':main()
