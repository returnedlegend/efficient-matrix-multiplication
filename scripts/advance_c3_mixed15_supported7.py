"""Enable one authorized batch only after every predecessor is audited negative."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.marathon7_cached_guard import CampaignGuard
from scripts.append_campaign_jobs42 import append_jobs

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def budget_ok(cpu,reserve=530,cap=1800):return cpu+reserve<=cap

def audit(campaign,jobid,ids,pin):
    out=campaign/jobid;resource=campaign/(jobid+'-job.result.json')
    if not resource.exists():return None
    usage=read(resource)
    if usage['exit_code']!=0 or usage['timed_out'] or usage['interrupted']:raise ValueError('failed predecessor; no retry')
    s=read(out/'summary.json');m=read(out/'result-manifest.json')
    if s['config_sha256']!=pin or m['config_sha256']!=pin or m['summary_sha256']!=sha(out/'summary.json'):raise ValueError('result binding differs')
    if s['status']!='SUPPORTED_BATCH_LOCAL_UNSAT' or s['stop_reason'] is not None or s['decoder_calls']!=len(ids) or [r['case'] for r in s['results']]!=ids:raise ValueError('incomplete/UNKNOWN/error/positive predecessor; pause')
    for r in s['results']:
        if r['status']!='LOCAL_UNSAT' or not r['complete'] or r['raw_decoder'].get('complete') is not True:raise ValueError('nonnegative/incomplete predecessor; pause')
        name=r['case']+'.result.json'
        if sha(out/name)!=m['result_files'][name] or read(out/name)!=r:raise ValueError('percase evidence differs')
    return usage

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--expected-manifest-sha256',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    if sha(a.manifest)!=a.expected_manifest_sha256:raise ValueError('plan pin differs')
    plan=read(a.manifest);C=Path(plan['campaign']);ready=a.manifest.parent
    if sha(plan['catalog'])!=plan['catalog_sha256'] or sha(C/'campaign.json')!=plan['campaign_sha256']:raise ValueError('catalog/campaign differs')
    catalog=json.loads(gzip.decompress(Path(plan['catalog']).read_bytes()));supported={r['id'] for r in catalog['packets'] if r['branch_metadata']['d'] in (13,14)}
    pc=C/'c3-mixed15-exact7-pilot-ready-v1/config.json';pilot=read(pc);ids=[c['id'] for c in pilot['cases']]
    allids=ids+[i for b in plan['batches'] for i in b['case_ids']]
    if sha(pc)!=plan['pilot_config_sha256'] or len(allids)!=len(set(allids)) or set(allids)!=supported or len(allids)!=5181:raise ValueError('scope not exact supported partition')
    usage=audit(C,plan['pilot_job_id'],ids,plan['pilot_config_sha256'])
    if usage is None:print(json.dumps({'status':'WAIT_PILOT'}));return
    usages=[usage];done=len(ids);nextb=None
    for b in plan['batches']:
        if sha(b['config'])!=b['config_sha256'] or sha(b['job'])!=b['job_sha256'] or [c['id'] for c in read(b['config'])['cases']]!=b['case_ids']:raise ValueError('batch pins/order differ')
        usage=audit(C,b['id'],b['case_ids'],b['config_sha256'])
        if usage is None:nextb=b;break
        usages.append(usage);done+=b['count']
    cpu=sum(u['cpu_seconds'] for u in usages)
    if nextb is None:print(json.dumps({'status':'ALL5181_SUPPORTED_COMPLETE_LOCAL_UNSAT','cpu_seconds':cpu,'done_cases':done}));return
    entry=read(C/'queue_state.json').get('jobs',{}).get(nextb['id'])
    if entry:
        if entry['status'] in ('running','launching'):print(json.dumps({'status':'WAIT_RUNNING','id':nextb['id']}));return
        raise ValueError('already attempted without audited result; no retry')
    if not budget_ok(cpu,plan['conservative_next_outer_reserve'],plan['measured_cpu_cap']):raise ValueError('CPU cap reserve prevents next batch')
    names=[plan['pilot_job_id']]+[b['id'] for b in plan['batches']]
    used=sum(f.stat().st_size for name in names for f in (C/name).rglob('*') if f.is_file());fixed=sum(f.stat().st_size for f in ready.rglob('*') if f.is_file());remaining=5181-done
    forecast_bytes=fixed+used+remaining*max(8192,used/done)*2;forecast_seconds=remaining*(cpu/done)*2+len(plan['batches'])*5
    if forecast_bytes>plan['storage_cap_bytes'] or forecast_seconds>plan['eta_cap_seconds']:raise ValueError('storage/ETA exceeds condition')
    g=CampaignGuard(500,'2026-11-03T19:24:17Z',guard_state=C/'operations-v3/state.json',campaign_dir=C);g.check('pre_advance')
    r=append_jobs(C/'queue.json',nextb['job'],nextb['job_sha256'],C/'root-queue-receipts'/(nextb['id']+'.json'),apply=a.apply,enable=True)
    print(json.dumps({'status':r['status'],'id':nextb['id'],'done_cases':done,'cpu_seconds':cpu,'forecast_seconds':forecast_seconds,'forecast_bytes':forecast_bytes},sort_keys=True))

if __name__=='__main__':main()
