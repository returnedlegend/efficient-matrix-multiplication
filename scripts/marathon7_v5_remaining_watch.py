#!/usr/bin/env python3
"""Audit authorized remaining chunks as they finish; scoped holds, no decoder."""
import argparse
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,read,sha
from scripts.append_campaign_jobs42 import atomic
from scripts.marathon7_batch_hold import hold_batch
from mmsearch.marathon7_cached_guard import CampaignGuard,HARD_DEADLINE
from mmsearch.marathon7_local import select_plan
from mmsearch.recombine import digest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--batch',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--resume',action='store_true');a=p.parse_args()
    c=a.campaign.resolve();b=a.bundle.resolve();batch=a.batch.resolve();out=a.output_dir.resolve();jobs=read(batch/'PROPOSAL.json')['jobs'];chunks=read(batch/'CHUNKS.json');receipt=read(a.receipt)
    for root in [b,batch]:
        for name,expected in read(root/'manifest.json')['files'].items():
            if sha(root/name)!=expected:raise ValueError('frozen runtime or authorized batch changed')
    if receipt['status']!='COMMITTED' or receipt['proposal_sha256']!=sha(batch/'PROPOSAL.json') or [j['id'] for j in receipt['effective_jobs']]!=[j['id'] for j in jobs]:raise ValueError('remaining-batch queue receipt differs')
    if len(jobs)!=181 or sum(item['cases'] for item in chunks)!=90387:raise ValueError('remaining-batch scope differs')
    if not a.resume:out.mkdir(parents=True,exist_ok=False)
    prior=read(out/'progress.json') if (out/'progress.json').exists() else dict(audited=[])
    if sha(Path(__file__))!=sha(batch/'marathon7_v5_remaining_watch.py') or sha(ROOT/'scripts/marathon7_batch_hold.py')!=sha(batch/'marathon7_batch_hold.py'):raise ValueError('batch monitor/hold implementation changed')
    specs={job['id']:chunk for job,chunk in zip(jobs,chunks)}
    for item in prior['audited']:
        if item['id'] not in specs or item['cases']!=specs[item['id']]['cases'] or sha(out/item['audit'])!=item['audit_sha256'] or sha(c/item['id']/'summary.json')!=item['summary_sha256'] or sha(c/(item['id']+'-job.result.json'))!=item['launcher_sha256']:raise ValueError('prior query-free audit progress changed')
    completed={item['id']:item for item in prior['audited']};guard=CampaignGuard(max(.001,HARD_DEADLINE-time.time()),'2026-11-03T19:24:17Z',campaign_dir=c,guard_state=c/'operations-v3/state.json')
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    def hold(reason,trigger=None):
        hold_error=None
        try:receipt=hold_batch(c,batch,reason,trigger)
        except Exception as error:receipt=dict(disabled_unstarted_ids=[]);hold_error=type(error).__name__+': '+str(error)
        report=dict(status='HELD_REQUIRES_ROOT_DECISION',reason=reason,trigger=trigger,completed_audited_jobs=len(completed),completed_audited_cases=sum(item['cases'] for item in completed.values()),audited=list(completed.values()),
            batch_hold_receipt_sha256=sha(batch/'HOLD-RECEIPT.json') if (batch/'HOLD-RECEIPT.json').exists() else None,disabled_unstarted_jobs=len(receipt['disabled_unstarted_ids']),hold_error=hold_error,new_decoder_calls=0,no_retries=True,no_global_rank_claim=True)
        atomic(out/'REPORT.json',report);print(json.dumps({key:report[key] for key in ['status','reason','completed_audited_jobs','completed_audited_cases','disabled_unstarted_jobs','new_decoder_calls']},sort_keys=True),flush=True)
    while len(completed)<len(jobs):
        reason=guard.reason(force=True)
        if reason:hold(reason);return
        for job,chunk in zip(jobs,chunks):
            identity=job['id'];output=c/identity;launcherfile=c/(identity+'-job.result.json')
            if identity in completed:continue
            if not launcherfile.exists():continue
            launcher=read(launcherfile);summaryfile=output/'summary.json'
            if launcher['exit_code']!=0 or launcher['timed_out'] or launcher['interrupted'] or not summaryfile.exists():hold('launcher failed or summary missing',dict(id=identity,launcher_sha256=sha(launcherfile)));return
            summary=read(summaryfile)
            if summary['status']!='LOCAL_PORTFOLIO_UNSAT' or not summary['terminal'] or summary['queries_this_invocation']!=chunk['cases']:
                hold('job UNKNOWN/error/record requires root decision',dict(id=identity,status=summary['status'],summary_sha256=sha(summaryfile)));return
            auditfile=out/f'chunk-{chunk["chunk"]}.json'
            if not auditfile.exists():
                run=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/marathon7_local_audit_batch.py'),'--bundle',str(b),'--output',str(output),'--report',str(auditfile)],capture_output=True,text=True)
                if run.returncode:hold('query-free chunk audit failed',dict(id=identity,error=run.stderr[-1000:]));return
            checked=read(auditfile)
            if checked['cases']!=chunk['cases'] or not checked['all_exact_negative'] or checked['new_decoder_calls']!=0 or checked['summary_sha256']!=sha(summaryfile):hold('chunk audit scope/checksum differs',dict(id=identity));return
            completed[identity]=dict(id=identity,chunk=chunk['chunk'],cases=chunk['cases'],audit=auditfile.name,audit_sha256=sha(auditfile),chain_sha256=checked['result_chain_sha256'],summary_sha256=sha(summaryfile),launcher_sha256=sha(launcherfile))
            atomic(out/'progress.json',dict(audited=list(completed.values()),cases=sum(item['cases'] for item in completed.values()),new_decoder_calls=0,updated_utc=datetime.now(timezone.utc).isoformat()))
            print(json.dumps(dict(audited_job=identity,audited_jobs=len(completed),audited_cases=sum(item['cases'] for item in completed.values()),remaining_cases=90387-sum(item['cases'] for item in completed.values()),new_decoder_calls=0)),flush=True)
        if len(completed)<len(jobs):time.sleep(1)
    launchers=[read(c/(job['id']+'-job.result.json')) for job in jobs];audits=[read(out/completed[job['id']]['audit']) for job in jobs];summaries=[read(c/job['id']/'summary.json') for job in jobs]
    starts=[datetime.fromisoformat(v['started_utc'].replace('Z','+00:00')) for v in launchers];ends=[started+timedelta(seconds=value['elapsed_seconds']) for started,value in zip(starts,launchers)]
    report=dict(status='ALL90387_EXACT_FIXED_RESIDUAL_NEGATIVES_AUDITED',cases=90387,jobs=181,unknowns=0,errors=0,new_decoder_calls=0,audited=[completed[job['id']] for job in jobs],audit_set_sha256=digest([completed[job['id']] for job in jobs]),
        bundle_manifest_sha256=sha(b/'manifest.json'),batch_manifest_sha256=sha(batch/'manifest.json'),queue_receipt_sha256=sha(a.receipt),
        measured=dict(queue_phase_wall_seconds=(max(ends)-min(starts)).total_seconds(),sum_launcher_wall_seconds=sum(v['elapsed_seconds'] for v in launchers),sum_cpu_seconds=sum(v['cpu_seconds'] for v in launchers),max_peak_rss_kib=max(v['max_rss_kib'] for v in launchers),max_launcher_wall_seconds=max(v['elapsed_seconds'] for v in launchers),inner_callbacks=sum(v['inner_callback_polling']['inner_callbacks'] for v in summaries),inner_filesystem_polls=sum(v['inner_callback_polling']['filesystem_polls'] for v in summaries)),
        storage=dict(outputs_logical_bytes=sum(v['storage']['logical_bytes'] for v in audits),outputs_allocated_bytes=sum(v['storage']['allocated_bytes'] for v in audits),audit_logical_bytes=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())),
        no_continuation=True,claim='Experimental exact negatives for listed fixed-source/mask residuals only. Finite-family retirement requires union with prior accepted closure ledgers; no unrestricted rank claim.')
    freeze(out/'REPORT.json',report);freeze(out/'marathon7_v5_remaining_watch.py',Path(__file__).read_bytes());freeze(out/'manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    print(json.dumps({key:report[key] for key in ['status','cases','jobs','unknowns','errors','new_decoder_calls','measured','storage','no_continuation']},sort_keys=True))


if __name__=='__main__':main()
