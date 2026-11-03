#!/usr/bin/env python3
"""Read-only result/certificate-chain audit, without any tensor decoder call."""
from collections import Counter
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

def read(p):return json.loads(p.read_bytes())
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(v):return sha(json.dumps(v,sort_keys=True,separators=(',',':')).encode())
def write(p,v):
 with p.open('x') as f:json.dump(v,f,sort_keys=True,indent=2);f.write('\n')

def main():
 resource.setrlimit(resource.RLIMIT_CPU,(25,30));started=time.process_time();c=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();out.mkdir(exist_ok=False,parents=True)
 b=c/'fullpassing-cp7-43-ready-v2';r=c/'fullpassing-cp7-43-run2';plan=read(b/'plan.json');config=read(r/'config.json');cs=digest(config);summary=read(r/'summary.json')
 assert config['launch_manifest_sha256']==sha((b/'launch-manifest.json').read_bytes()) and not config['small_control'] and not config['controls_only']
 assert config['plan_sha256']==digest(plan) and summary['status']=='LOCAL_PORTFOLIO_UNSAT'
 counts=Counter();methods=Counter();cases=Counter();scatter=Counter();chunkreports=[];archives=0;bytes_total=0;allmasks=set()
 for chunk in plan['chunks']:
  items=json.loads(gzip.decompress((b/chunk['plan']).read_bytes()));assert digest(items)==chunk['plan_sha256'];cd=r/'chunks'/chunk['id'];cursor=read(cd/'cursor.json');data=(cd/'results.jsonl').read_bytes();events=data.splitlines();chain=digest([cs,chunk])
  assert cursor['config_sha256']==cs and cursor['chunk_sha256']==chunk['plan_sha256'] and cursor['next_index']==len(items)==len(events) and cursor['journal_bytes']==len(data)
  for i,line in enumerate(events):
   event=json.loads(line);v=event['value'];assert event['previous_sha256']==chain and event['sha256']==digest({k:x for k,x in event.items() if k!='sha256'});chain=event['sha256']
   assert v['index']==i and v['mask_sha256']==digest(items[i]) and v['config_sha256']==cs and v['source_id']==chunk['source_id'] and v['source_sha256']==plan['sources'][chunk['source_id']]['sha256']
   compressed=(cd/v['archive']).read_bytes();assert sha(compressed)==v['archive_sha256'];proof=json.loads(gzip.decompress(compressed));result=proof['result']
   assert proof['case']==items[i] and proof['source_sha256']==v['source_sha256'] and proof['mask_sha256']==v['mask_sha256'] and proof['config_sha256']==cs
   assert proof['core_sha256']==v['core_sha256']==result['core_sha256'] and proof['basis_sha256']==v['basis_sha256']
   assert v['status']==result['status']=='LOCAL_UNSAT' and v['complete'] is True and result['complete'] is True and v['after_cutoff'] is False and proof['after_cutoff'] is False
   assert result['target']==7 and result['shape']==items[i]['shape'] and result['axis']==items[i]['free_axis'] and result['mode_rank']==max(items[i]['shape'])
   d=result['mode_rank'];assert result['inside_rank']<d
   if d==7:assert result['tested_span_vectors']==127 and result['algorithm']=='enumerate_mode_subspace_rankone_test'
   else:assert d==6 and result['algorithm']=='complete_one_coset' and all(row[2]<d for row in result['bucket_span_ranks'])
   key=(v['source_sha256'],items[i]['mask_lo'],items[i]['mask_hi']);assert key not in allmasks;allmasks.add(key)
   counts[result['status']]+=1;methods[result['algorithm']]+=1;cases[result['case']]+=1;scatter[(chunk['source_id'],d)]+=1;archives+=1;bytes_total+=len(compressed)
  assert chain==cursor['chain_sha256'];assert not list((cd/'attempts').glob('*after-cutoff*')) and not (cd/'last-unknown.json').exists()
  chunkreports.append(dict(id=chunk['id'],cases=len(items),journal_sha256=sha(data),chain_sha256=chain))
 excluded=read(b/'excluded449.json');prior=Counter()
 for p in excluded:
  assert sha(Path(p['proof_path']).read_bytes())==p['proof_sha256'];key=(p['source_sha256'],p['mask_lo'],p['mask_hi']);assert key not in allmasks;allmasks.add(key);prior[p['kind']]+=1
 assert archives==summary['queries']==plan['case_count']==21380 and len(excluded)==449 and len(allmasks)==21829
 assert len(chunkreports)==87 and all(x['complete'] for x in summary['chunks']) and sum(x['closed'] for x in summary['chunks'])==21380
 assert not (r/'WINNER.json').exists()
 scan=c/'compact-eight43-fullscan-v1';sc=read(scan/'cursor.json');binary=(scan/'all-bounds.bin').read_bytes();hist=Counter(binary[6::7]);assert len(binary)==7*981476 and sc['next_sample']==981476 and hist==Counter({6:11,7:21818,8:959647})
 output=dict(status='COMPLETED_FINITE_FAMILY_CHAIN_AUDIT_PASS',new_CP7_negatives=archives,methods=dict(methods),decision_cases=dict(cases),prior_negative_proof_counts=dict(prior),prior_exact_masks=449,p1_rank8_exclusions=959647,p1_passing=21829,total_supplied_eight_union_residuals=981476,
  source_mode_scatter={f'{s}-d{d}':n for (s,d),n in scatter.items()},chunks=chunkreports,compressed_decision_archive_bytes=bytes_total,resume_needed=False,unknown=0,error=0,winner=False,after_cutoff_closed=0,late_raw_attempts=0,
  launcher=read(c/'fullpassing-cp7-43-v2-run1-job.result.json'),runtime_summary=summary,config_sha256=sha((r/'config.json').read_bytes()),prepared_manifest_sha256=sha((b/'manifest.json').read_bytes()),launch_manifest_sha256=sha((b/'launch-manifest.json').read_bytes()),
  scope='All supplied981476 eight-term circuit-union residuals on these four frozen rank93 sources have no at-most7-product replacement while their85 outside products stay fixed. No conclusion for other subsets, changed outside terms, arbitrary local families or global tensor rank.',audit_work='Verified every committed result/archive hash, source/mask/core/basis chain, complete flag and recorded certificate bounds. Did not regenerate a tensor quotient or call any decoder.')
 write(out/'CP7-FINITE-FAMILY.json',output)
 # Rank3: independently replay completed result/archive chains, then snapshot007.
 prepared=c/'observed-rank3-lazy-ready-v2';rp=read(prepared/'plan.json');bychunk={x['id']:x for x in rp['chunks']};jobs=c/'observed-rank3-remaining-jobs-v1';ledger=read(jobs/'coverage-ledger.json');completed=[];rank3counts=Counter();rank3sources=Counter();totalbranches=0
 for number in range(1,7):
  d=c/f'observed-rank3-remaining-{number:03d}';cfg=read(d/'config.json');cfgsha=digest(cfg);report=read(d/'report-launch000.json');assert report['status']=='SELECTED_CHUNKS_COMPLETE' and report['reason'] is None and cfg['plan_sha256']==digest(rp)
  count=0;sub=[]
  for name in cfg['chunk_ids']:
   ch=bychunk[name];items=json.loads(gzip.decompress((prepared/ch['plan']).read_bytes()));assert digest(items)==ch['plan_sha256'];cd=d/'chunks'/name;events=(cd/'results.jsonl').read_bytes().splitlines();cursor=read(cd/'cursor.json');chain=digest([cfgsha,ch])
   assert len(events)==cursor['next_index']==ch['count']==len(items) and cursor['config_sha256']==cfgsha
   for i,line in enumerate(events):
    event=json.loads(line);v=event['value'];assert event['previous_sha256']==chain and event['sha256']==digest({k:x for k,x in event.items() if k!='sha256'});chain=event['sha256']
    result=v['result'];assert v['index']==i and v['case']==items[i] and v['source_id']==ch['source_id'] and v['source_system_sha256']==rp['sources'][ch['source_id']]['system_sha256']
    assert result['status']=='NO_ONE_SUBSPACE_GAIN' and result['complete_for_requested_bound'] is True and result['worker_reaped'] is True and result['requested_bound']==items[i]['weight_bound']
    archive=(cd/v['branch_ledger']).read_bytes();assert sha(archive)==v['branch_ledger_sha256'];rawledger=gzip.decompress(archive);assert sha(rawledger)==v['branch_ledger_uncompressed_sha256'] and len(rawledger.splitlines())==v['branch_records']
    rank3counts[result['status']]+=1;rank3sources[ch['source_id']]+=1;totalbranches+=v['branch_records']
   assert chain==cursor['result_chain_sha256'];count+=len(events);sub.append(dict(id=name,cases=len(events),chain_sha256=chain))
  assert count==report['target_queries_this_launch']==ledger['jobs'][number-1]['cases'];completed.append(dict(sequence=number,cases=count,chunks=sub,report_sha256=sha((d/'report-launch000.json').read_bytes())))
 assert sum(x['cases'] for x in completed)==32354
 live=c/'observed-rank3-remaining-007';livecounts={};queue=read(c/'queue_state.json');qstate=queue['jobs'].get('observed-rank3-remaining-007',{})
 if (live/'config.json').exists():
  cfg=read(live/'config.json');cfgsha=digest(cfg)
  for name in cfg['chunk_ids']:
   cd=live/'chunks'/name
   if not (cd/'cursor.json').exists():continue
   cursor=read(cd/'cursor.json');lines=(cd/'results.jsonl').read_bytes().splitlines();chain=digest([cfgsha,bychunk[name]])
   for line in lines[:cursor['next_index']]:
    event=json.loads(line);assert event['previous_sha256']==chain and event['sha256']==digest({k:x for k,x in event.items() if k!='sha256'});assert event['value']['result']['status']=='NO_ONE_SUBSPACE_GAIN';chain=event['sha256']
   assert chain==cursor['result_chain_sha256'];livecounts[name]=cursor['next_index']
 nextjobs=[]
 for item in ledger['jobs'][6:]:
  path=jobs/item['template'];h=sha(path.read_bytes());assert h==item['template_sha256'];nextjobs.append(dict(sequence=item['sequence'],cases=item['cases'],chunks=[dict(id=x['id'],count=x['count']) for x in item['chunks']],template_path=str(path),template_sha256=h,identity_sha256=item['identity_sha256'],output_exists=(c/f'observed-rank3-remaining-{item["sequence"]:03d}').exists()))
 result=dict(status='READ_ONLY_PROGRESS_RECONCILIATION',asof_utc=datetime.now(timezone.utc).isoformat(),completed_jobs=completed,completed_remaining_cases=32354,completed_sources=dict(rank3sources),terminal_counts=dict(rank3counts),branch_records=totalbranches,remaining_after006=9368,remaining_sources_after006=dict(ae93=7084,current_new=2284,current_diverse=0),job006_resume_needed=False,
  job007_queue_status=qstate.get('status'),job007_started_utc=qstate.get('launched_utc'),job007_committed_snapshot=livecounts,job007_snapshot_closed=sum(livecounts.values()),unlaunched008_010_cases=5368,next_job_templates=nextjobs,
  original_catalogued=310788,cheap_k3_rank_bounds=263002,earlier_exact_pilot18_budget646_first6000=6064,closed_after006_including_cheap=301420,pending_after006=9368,scope='Explicit observed3D palettes in this immutable fixedP/source catalog only; no unrestricted rank/all-image-rank3 claim.',decoder_calls_during_audit=0)
 write(out/'RANK3-PROGRESS.json',result)
 (out/'REPORT.md').write_text(f'''CP7 is complete: all21380 newcases are LOCAL_UNSAT in87complete chunks. All archive/result chains, completeness flags and recorded certificate bounds passed this read-only audit; no decoder was called. Together with449 exact prior masks and959647 p1 exclusions, this closes exactly the supplied981476 eight-term circuit-union residuals on four frozen93-product sources, with85outside products fixed. It is not a global rank lower bound. No resume is needed. Limited worker:255.123wall seconds/210.272CPU/maxRSS29176KiB.

Observed-rank3 jobs001–006 closed32354 explicit palettes, all NO_ONE_SUBSPACE_GAIN. Job006 closed4000(AE2000,new2000), so it needs no resume. After006 the frozen ledger had9368cases left: AE7084,new2284,diverse0. Job007 is {qstate.get('status')} and has a committed snapshot of{sum(livecounts.values())}/4000 at{result['asof_utc']}; this is live progress, not a completion claim. Jobs008–010 remain5368cases. Their exact template hashes and source/chunk counts are in RANK3-PROGRESS.json. Do not launch a duplicate007 or advance any unfinished case as negative. The explicit observed-space catalog remains narrower than all image-rank3 or unrestricted decompositions.
''')
 write(out/'manifest.json',dict(files={p.name:sha(p.read_bytes()) for p in out.iterdir() if p.is_file()}))
 for p in out.iterdir():
  if p.is_file():p.chmod(0o444)
 print(json.dumps(dict(CP7='PASS_FINITE_FAMILY_COMPLETE',CP7_cases=archives,rank3_done32354=True,rank3_007=qstate.get('status'),rank3_007_snapshot=livecounts,unlaunched008_010=5368,audit_CPU=time.process_time()-started,decoder_calls=0)))

if __name__=='__main__':main()
