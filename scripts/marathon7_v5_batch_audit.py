#!/usr/bin/env python3
"""Audit the authorized10000case batch; never call a target decoder."""
import argparse
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,read,sha
from mmsearch.marathon7_local import select_plan
from mmsearch.recombine import digest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--batch',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--wait-seconds',type=int,default=0);a=p.parse_args()
    if not 0<=a.wait_seconds<=900:p.error('read-only wait limit must be0..900seconds')
    c=a.campaign.resolve();b=a.bundle.resolve();batch=a.batch.resolve();out=a.output_dir.resolve()
    for name,expected in read(batch/'manifest.json')['files'].items():
        if sha(batch/name)!=expected:raise ValueError('authorized batch changed')
    receipt=read(a.receipt);jobs=read(batch/'PROPOSAL.json')['jobs'];ids=[job['id'] for job in jobs]
    if receipt['status']!='COMMITTED' or receipt['proposal_sha256']!=sha(batch/'PROPOSAL.json') or [job['id'] for job in receipt['effective_jobs']]!=ids or len(set(ids))!=20:raise ValueError('authorized queue receipt differs')
    seen={(case['source_id'],case['mask_lo'],case['mask_hi']) for case in select_plan(b,'000')['cases']};reports=[];launchers=[];polls=callbacks=logical=allocated=0;starts=[];ends=[]
    out.mkdir(parents=True,exist_ok=False)
    wait_deadline=time.monotonic()+a.wait_seconds
    for number,job in enumerate(jobs,1):
        identity=job['id'];output=c/identity;resultfile=c/(identity+'-job.result.json')
        while not (resultfile.exists() and (output/'summary.json').exists()):
            if time.monotonic()>=wait_deadline:raise TimeoutError('authorized job not completed yet: '+identity)
            time.sleep(5)
        summary=read(output/'summary.json');launcher=read(resultfile);chunk=job['command'][job['command'].index('--chunk-id')+1]
        cases=select_plan(b,chunk)['cases'];keys={(case['source_id'],case['mask_lo'],case['mask_hi']) for case in cases}
        if len(keys)!=500 or seen&keys:raise ValueError('repeated source/mask in authorized cases')
        seen|=keys
        if summary['status']!='LOCAL_PORTFOLIO_UNSAT' or not summary['terminal'] or summary['queries_this_invocation']!=500 or launcher['exit_code']!=0 or launcher['timed_out'] or launcher['interrupted']:
            freeze(out/'REPORT.json',dict(status='INCOMPLETE_BATCH_REQUIRES_ROOT_DECISION',failed_job=identity,summary_status=summary['status'],completed_prior_audited_jobs=len(reports),new_decoder_calls=0,no_continuation=True));print(json.dumps(dict(status='INCOMPLETE_BATCH_REQUIRES_ROOT_DECISION',failed_job=identity)));return
        path=out/f'chunk-{chunk}.json'
        run=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/marathon7_local_audit_batch.py'),'--bundle',str(b),'--output',str(output),'--report',str(path)],capture_output=True,text=True)
        if run.returncode:raise RuntimeError('query-free case audit failed '+identity+': '+run.stderr[-1000:])
        checked=read(path)
        if checked['cases']!=500 or not checked['all_exact_negative'] or checked['new_decoder_calls']!=0:raise ValueError('case audit not exact complete')
        reports.append(dict(id=identity,chunk=chunk,cases=500,report=path.name,report_sha256=sha(path),chain_sha256=checked['result_chain_sha256'],summary_sha256=sha(output/'summary.json'),launcher_sha256=sha(c/(identity+'-job.result.json'))))
        logical+=checked['storage']['logical_bytes'];allocated+=checked['storage']['allocated_bytes'];launchers.append(launcher)
        polls+=summary['inner_callback_polling']['filesystem_polls'];callbacks+=summary['inner_callback_polling']['inner_callbacks']
        started=datetime.fromisoformat(launcher['started_utc'].replace('Z','+00:00'));starts.append(started);ends.append(started+timedelta(seconds=launcher['elapsed_seconds']))
        print(json.dumps(dict(audited_job=identity,completed_jobs=len(reports),cases_audited=500*len(reports),new_decoder_calls=0)),flush=True)
    report=dict(status='ALL10000_EXACT_FIXED_RESIDUAL_NEGATIVES_AUDITED',cases=10000,jobs=20,unknowns=0,errors=0,all_exact_negative=True,all_source_masks_unique_and_disjoint_first500=True,new_decoder_calls=0,
        bundle_manifest_sha256=sha(b/'manifest.json'),batch_manifest_sha256=sha(batch/'manifest.json'),queue_receipt_sha256=sha(a.receipt),case_audits=reports,case_audit_set_sha256=digest(reports),
        measured=dict(queue_phase_wall_seconds=(max(ends)-min(starts)).total_seconds(),sum_launcher_wall_seconds=sum(v['elapsed_seconds'] for v in launchers),sum_cpu_seconds=sum(v['cpu_seconds'] for v in launchers),
            max_peak_rss_kib=max(v['max_rss_kib'] for v in launchers),max_launcher_wall_seconds=max(v['elapsed_seconds'] for v in launchers),inner_callbacks=callbacks,inner_filesystem_polls=polls),
        limits=dict(job_cpu=2,jobs=20,outer_wall_seconds_each=330,inner_wall_seconds_each=300,per_case_seconds=2,memory_mb_each=1024,hard_cutoff_utc='2026-11-03T19:24:17Z'),
        storage=dict(outputs_logical_bytes=logical,outputs_allocated_bytes=allocated,audit_logical_bytes=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())),
        no_continuation=True,claim='Experimental exact negatives only for these fixed-source/mask residuals. No new decomposition or global rank lower bound; root decision required for further queries.')
    freeze(out/'REPORT.json',report);freeze(out/'marathon7_v5_batch_audit.py',Path(__file__).read_bytes());freeze(out/'manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    print(json.dumps({key:report[key] for key in ['status','cases','jobs','unknowns','errors','new_decoder_calls','measured','storage','no_continuation']},sort_keys=True))


if __name__=='__main__':main()
