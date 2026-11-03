#!/usr/bin/env python3
"""Prepare and optionally append the explicitly authorized20-job v5 batch."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,read,sha
from scripts.phase_coordinator42_v2 import validate_job
from scripts.append_campaign_jobs42 import append_jobs
from mmsearch.marathon7_local import select_plan
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.recombine import digest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    c=a.campaign.resolve();b=a.bundle.resolve();out=a.output_dir.resolve();first=c/'marathon7-local-local10-v5-000';audit=read(a.audit);summary=read(first/'summary.json');launcher=read(c/'marathon7-local-local10-v5-000-job.result.json')
    if audit['status']!='AUDITED_EXACT_FIXED_SOURCE_MASK_NEGATIVES' or audit['cases']!=500 or not audit['all_exact_negative'] or audit['new_decoder_calls']!=0 or audit['bundle_manifest_sha256']!=sha(b/'manifest.json') or audit['summary_sha256']!=sha(first/'summary.json'):raise ValueError('first500 exact audit gate failed')
    if summary['status']!='LOCAL_PORTFOLIO_UNSAT' or summary['queries_this_invocation']!=500 or not summary['terminal'] or summary['elapsed_seconds']>60 or launcher['exit_code']!=0 or launcher['timed_out'] or launcher['interrupted']:raise ValueError('first500 completion/throughput gate failed')
    for name,expected in read(b/'manifest.json')['files'].items():
        path=(b/name).resolve()
        if not path.is_relative_to(b) or sha(path)!=expected:raise ValueError('frozen v5 runtime/data changed')
    guard=CampaignGuard(30,'2026-11-03T19:24:17Z',campaign_dir=c,guard_state=c/'operations-v3/state.json');guard.check('pre_batch_prepare')
    live=read(c/'operations-v3/state.json');forecast=audit['storage']['forecast_additional_10000_allocated_bytes']
    if live['campaign_allocated_bytes']+forecast>=5*1024**3:raise ValueError('forecast storage reaches5GiB guard threshold')
    template=read(b/'PROPOSED-JOB.json');jobs=[];plans=[];seen={(case['source_id'],case['mask_lo'],case['mask_hi']) for case in select_plan(b,'000')['cases']}
    for number in range(1,21):
        chunk=f'{number:03d}';selection=select_plan(b,chunk);cases=selection['cases']
        if len(cases)!=500:raise ValueError('every authorized chunk must contain500cases')
        keys={(case['source_id'],case['mask_lo'],case['mask_hi']) for case in cases}
        if len(keys)!=500 or seen&keys:raise ValueError('source/mask overlaps prior or batch chunk')
        seen|=keys;job=json.loads(json.dumps(template));identity=f'marathon7-local-local10-v5-{chunk}';job['id']=identity
        for flag,value in [('--output-dir',str(c/identity)),('--chunk-id',chunk)]:job['command'][job['command'].index(flag)+1]=value
        if job['enabled'] is not False or job['cpu']!=2 or job['seconds']!=330 or job['memory_mb']!=1024:raise ValueError('authorized job limits differ')
        validate_job(job);jobs.append(job);plans.append(dict(chunk=chunk,cases=500,selected_plan_sha256=selection['selected_sha256'],source_mask_sha256=digest(sorted(keys)),first_case=cases[0]['id'],last_case=cases[-1]['id']))
    out.mkdir(parents=True,exist_ok=False);freeze(out/'PROPOSAL.json',dict(jobs=jobs));freeze(out/'CHUNKS.json',plans)
    evidence=dict(authorization='Root explicitly authorizes automatic20ids/chunks001..020 after first500 exact audit and<=60second throughput gate; stop after this10000 pending root decision.',
        first_audit_sha256=sha(a.audit),first_summary_sha256=sha(first/'summary.json'),first_launcher_sha256=sha(c/'marathon7-local-local10-v5-000-job.result.json'),bundle_manifest_sha256=sha(b/'manifest.json'),
        first500_wall_seconds=summary['elapsed_seconds'],first500_launcher_wall_seconds=launcher['elapsed_seconds'],first500_cpu_seconds=launcher['cpu_seconds'],first500_max_rss_kib=launcher['max_rss_kib'],
        additional_cases=10000,jobs=20,job_cpu=2,inner_wall_seconds=300,per_case_seconds=2,outer_wall_seconds=330,memory_mb=1024,
        forecast_wall_seconds=launcher['elapsed_seconds']*20,forecast_cpu_seconds=launcher['cpu_seconds']*20,forecast_logical_bytes=audit['storage']['forecast_additional_10000_logical_bytes'],forecast_allocated_bytes=forecast,
        observed_campaign_allocated_bytes=live['campaign_allocated_bytes'],hard_cutoff_utc='2026-11-03T19:24:17Z',new_decoder_calls_in_preparation=0,claim='Experimental fixed-residual search only; no new construction or global rank conclusion.')
    freeze(out/'AUTHORIZATION-AND-BUDGET.json',evidence);freeze(out/'marathon7_v5_authorized_batch.py',Path(__file__).read_bytes())
    preview=append_jobs(c/'queue.json',out/'PROPOSAL.json',sha(out/'PROPOSAL.json'),a.receipt,apply=False,enable=True);freeze(out/'PREVIEW.json',preview)
    freeze(out/'manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    guard.check('pre_authorized_queue_append')
    result=append_jobs(c/'queue.json',out/'PROPOSAL.json',sha(out/'PROPOSAL.json'),a.receipt,apply=a.apply,enable=True)
    print(json.dumps(dict(status=result['status'],apply=a.apply,jobs=20,cases=10000,proposal_sha256=sha(out/'PROPOSAL.json'),manifest_sha256=sha(out/'manifest.json'),receipt=str(a.receipt.resolve()),forecast_wall_seconds=evidence['forecast_wall_seconds'],forecast_cpu_seconds=evidence['forecast_cpu_seconds'],forecast_allocated_bytes=forecast),sort_keys=True))


if __name__=='__main__':main()
