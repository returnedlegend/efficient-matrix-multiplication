#!/usr/bin/env python3
"""Marathon7 local12/image9/target11 exact surplus-two pilot; root owns launch."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.marathon7_local import CampaignGuard,CampaignHold
from mmsearch.marathon7_local12_runtime import select_plan,SourceCache,compact_negative,ensure_room,restore_journal,commit_journal,verify_winner_resume

def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(path.read_bytes())
def raw(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
def syncdir(path):
 descriptor=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(descriptor)
 finally:os.close(descriptor)
def write(path,value):
 with path.open('xb') as f:f.write(raw(value));f.flush();os.fsync(f.fileno())
 path.chmod(0o444)
 syncdir(path.parent)
def atomic(path,value):
 temporary=Path(str(path)+'.tmp')
 with temporary.open('wb') as f:f.write(raw(value));f.flush();os.fsync(f.fileno())
 temporary.replace(path);syncdir(path.parent)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
 p.add_argument('--chunk-id');p.add_argument('--max-cases',type=int,default=0);p.add_argument('--backend',choices=['python'],default='python');p.add_argument('--per-case-seconds',type=float)
 p.add_argument('--deadline-utc',default='2026-11-03T19:24:17Z');p.add_argument('--stop-marker',type=Path,action='append',default=[]);p.add_argument('--guard-state',type=Path)
 p.add_argument('--seconds',type=float,default=60);p.add_argument('--memory-mb',type=int,default=1024);p.add_argument('--resume',action='store_true');p.add_argument('--controls-only',action='store_true');p.add_argument('--small-control',action='store_true')
 a=p.parse_args()
 if not 0<a.seconds<=500 or not 128<=a.memory_mb<=1024 or a.max_cases<0:p.error('bounded seconds/memory/prefix required')
 if a.per_case_seconds is None:a.per_case_seconds=a.seconds
 if not 0<a.per_case_seconds<=a.seconds:p.error('per-case budget must be positive and within launch budget')
 b=a.bundle.resolve();out=a.output_dir.resolve()
 markers=a.stop_marker
 guard=CampaignGuard(a.seconds,a.deadline_utc,markers,a.guard_state,campaign_dir=b.parent)
 manifest=read(b/'launch-manifest.json')
 for name,expected in manifest['files'].items():
  path=(b/name).resolve()
  if not path.is_relative_to(b) or sha(path.read_bytes())!=expected:raise ValueError('frozen checksum mismatch: '+name)
 sys.path.insert(0,str(b/'runtime'))
 from mmsearch.surplus_two7 import solve_core
 from mmsearch.compact_eight43 import bits,expand_core,packed_tensor,replace_and_verify
 from mmsearch.sat_neighborhoods import factor_masks
 from mmsearch.verify import verify_candidate
 from scripts.verify_record42_independent import verify_bytes
 requested=a.memory_mb*1024**2;_,hard=resource.getrlimit(resource.RLIMIT_AS);effective=requested if hard==resource.RLIM_INFINITY else min(requested,hard)
 resource.setrlimit(resource.RLIMIT_AS,(effective,effective))
 selection=select_plan(b,a.chunk_id,a.max_cases,a.small_control);plan=dict(cases=selection['cases']);config=dict(launch_manifest_sha256=sha((b/'launch-manifest.json').read_bytes()),selected_plan_sha256=selection['selected_sha256'],catalog_plan_sha256=selection['catalog_plan_sha256'],chunk_id=selection['identity'],backend=a.backend,small_control=a.small_control,controls_only=a.controls_only,deadline_utc=guard.deadline_utc,stop_markers=[str(p) for p in guard.stop_markers],guard_state=str(a.guard_state.resolve()) if a.guard_state else None,campaign_dir=str(b.parent))
 config_sha=sha(json.dumps(config,sort_keys=True).encode());started=guard.started
 def stopped(sig,frame):
  guard.stop()
 signal.signal(signal.SIGTERM,stopped);signal.signal(signal.SIGINT,stopped)
 case_deadline=None
 def cancelled():return guard.reason() is not None or (case_deadline is not None and time.monotonic()>=case_deadline)
 def check_case(barrier):
  guard.check(barrier)
  if case_deadline is not None and time.monotonic()>=case_deadline:raise CampaignHold('per-case wall cutoff',barrier)
 if a.resume:
  if read(out/'config.json')!=config:raise ValueError('resume configuration/source/runtime changed')
  state=read(out/'cursor.json')
  if state['config_sha256']!=config_sha:raise ValueError('resume cursor hash mismatch')
 else:
  out.mkdir(parents=True,exist_ok=False);write(out/'config.json',config);state=dict(config_sha256=config_sha,next_case=0,results=[],attempts={},terminal=False,status='UNKNOWN');atomic(out/'cursor.json',state)
 if state.get('terminal') and state.get('status')=='ERROR':
  print(json.dumps(dict(status='ERROR',terminal_resume_guard=True,reason='prior error requires review')));return 2
 completed,chain=restore_journal(out,plan['cases'],config_sha)
 if state['next_case']>len(completed):raise ValueError('cursor ahead of committed completion journal')
 if len(completed)>state['next_case']:state.pop('pending_unknown',None)
 state['results']=completed;state['next_case']=len(completed);state['result_chain_sha256']=chain
 if completed and completed[-1]['status'] in ('VERIFIED_TARGET','SMALL_CONTROL_PASSED'):state.update(terminal=True,status=completed[-1]['status'])
 # Every committed result is bound to this exact input/runtime and cursor.
 for i,prior in enumerate(state['results']):
  path=out/prior['result_file']
  if sha(path.read_bytes())!=prior['result_sha256'] or read(path)['case']!=plan['cases'][i]['id']:raise ValueError('corrupt prior case/cursor')
 if state['next_case']!=len(state['results']):raise ValueError('resume cursor count mismatch')
 if state.get('pending_unknown'):
  pending=state['pending_unknown'];path=out/pending['result_file']
  if sha(path.read_bytes())!=pending['result_sha256'] or read(path)['status']!='UNKNOWN':raise ValueError('corrupt prior UNKNOWN attempt')
  pending_result=read(path)
  if pending_result.get('after_cutoff_artifact') and sha((out/pending_result['after_cutoff_artifact']).read_bytes())!=pending_result['after_cutoff_artifact_sha256']:raise ValueError('corrupt after-cutoff raw witness')
 if (out/'WINNER.json').exists():
  verify_winner_resume(out,config_sha,plan['cases'],verify_bytes)
  print(json.dumps(dict(status='VERIFIED_TARGET',terminal_resume_guard=True)));return 0
 if state.get('terminal'):
  print(json.dumps(dict(status=state['status'],terminal_resume_guard=True)));return 2 if state['status']=='ERROR' else 0
 query_count=0;cache=SourceCache(b)
 current=out/'current'
 if current.exists() and not (current/'case.json').exists():shutil.rmtree(current)
 if current.exists():
  current_meta=read(current/'case.json')
  if current_meta['index']<state['next_case']:shutil.rmtree(current)
 for i in range(state['next_case'],len(plan['cases'])):
  if guard.reason() is not None:break
  case=plan['cases'][i];attempt=state['attempts'].get(str(i),0);raw_decoder=None;candidate=None;full=None;independent=None;data=None;source_sha=None;core_math_sha=None;core_input_sha=None
  case_deadline=time.monotonic()+a.per_case_seconds
  try:
   ensure_room(out)
   state['attempts'][str(i)]=attempt+1;atomic(out/'cursor.json',state)
   check_case('pre_source_control')
   source,data,verified,source_sha,core_math_sha,core_input_sha=cache.core(case)
   if current.exists():
    prior=read(current/'case.json')
    if prior!=dict(index=i,case=case['id'],config_sha256=config_sha,source_sha256=source_sha,core_input_sha256=core_input_sha):raise ValueError('partial lazy core/model changed')
    if (current/'core.json').exists():
     if sha(raw(read(current/'core.json')))!=core_input_sha:raise ValueError('retained partial core bytes changed')
    else:atomic(current/'core.json',data)
   check_case('pre_dispatch')
   if source['dimension']==5 and not a.controls_only and guard.resources is None:raise CampaignHold('n5 production resource guard required','pre_dispatch')
   if a.controls_only:result=dict(status='CONTROL_PASSED',full_entries_checked=verified['exact_entries_checked'])
   else:
    query_count+=1
    result=solve_core(data['core'],data['shape'],case['target_local_products'],axis=case['free_axis'],max_vectors=selection['family']['max_vectors'],max_extensions=selection['family']['max_extensions'],cancelled=cancelled)
    raw_decoder=json.loads(json.dumps(result));check_case('post_solve')
    if result['status']=='LOCAL_UNSAT':result=compact_negative(result)
    if result['status']=='SAT':
     products=[]
     for term in result['products']:
      expanded=[]
      for coefficient,basis in zip(term,data['image_bases']):
       value=0
       for j in bits(coefficient):value^=basis[j]
       expanded.append(value)
      products.append(expanded)
     candidate,full=replace_and_verify(source,data['source_indices'],products,dict(method='exact exhaustive repeated-pair CP(d+2) decoder'))
     check_case('post_full_verification')
     if a.small_control:
      if source['dimension'] not in (2,3) or full['rank']!=case['source_products']-case['source_local_products']+case['target_local_products'] or full['exact_entries_checked']!=source['dimension']**6:raise ValueError('small constructive repair failed')
      check_case('pre_small_publication')
      write(out/'SMALL_CONTROL.verification.json',full);write(out/'SMALL_CONTROL.json',candidate);result['status']='SMALL_CONTROL_PASSED'
     else:
      independent=verify_bytes(json.dumps(candidate,sort_keys=True).encode())
      check_case('post_independent_verification')
      if source['dimension']!=5 or source.get('field')!=2 or not independent['record_eligible'] or full['rank']>92 or full['exact_entries_checked']!=15625:raise ValueError('n5 winner failed full independent verification')
      proofdir=out/'proofs'/f'case-{i:02d}-attempt-{attempt:03d}';proofdir.mkdir(parents=True,exist_ok=False)
      certificate=dict(result,case=case['id'],config_sha256=config_sha,source_sha256=source_sha,core_input_sha256=core_input_sha,core_math_sha256=core_math_sha)
      for name,value in [('candidate.json',candidate),('input-core.json',data),('verification.json',full),('independent.json',independent),('core-certificate.json',certificate)]:write(proofdir/name,value)
      check_case('pre_publication_views')
      # Orphan top-level proof views may be replaced before a marker exists;
      # immutable attempt proofs remain the authoritative full record.
      for name,value in [('WINNER.verification.json',full),('WINNER.independent.verification.json',independent),('WINNER.core-certificate.json',certificate)]:atomic(out/name,value)
      atomic(out/'WINNER.proof.json',dict(candidate_sha256=sha(raw(candidate)),proof_directory=str(proofdir.relative_to(out)),files={name:sha((out/name).read_bytes()) for name in ['WINNER.verification.json','WINNER.independent.verification.json','WINNER.core-certificate.json']}))
      check_case('pre_winner_marker')
      # Durable full proof and the final cutoff barrier precede the marker.
      write(out/'WINNER.json',candidate);result['status']='VERIFIED_TARGET'
   if result['status'] not in ('VERIFIED_TARGET','SMALL_CONTROL_PASSED'):check_case('pre_result_commit')
   result.update(case=case['id'],config_sha256=config_sha,source_sha256=source_sha,core_input_sha256=core_input_sha,core_math_sha256=core_math_sha,scope='Exact specified fixed-outside residual only.',effective_AS_limit_bytes=effective)
  except CampaignHold as hold:
   result=dict(status='UNKNOWN',case=case['id'],config_sha256=config_sha,reason=hold.reason,barrier=hold.barrier,complete=False,after_cutoff=True,guard=guard.observation())
   if raw_decoder is not None:
    late=out/f'case-{i:02d}.attempt-{attempt:03d}.after-cutoff.raw.json'
    write(late,dict(after_cutoff=True,no_within_budget_claim=True,case=case['id'],config_sha256=config_sha,reason=hold.reason,barrier=hold.barrier,guard=guard.observation(),raw_decoder_result=raw_decoder,candidate=candidate,full_verification=full,independent_verification=independent,source_sha256=source_sha,core_input_sha256=core_input_sha,core_math_sha256=core_math_sha,core_input=data))
    result.update(after_cutoff_artifact=late.name,after_cutoff_artifact_sha256=sha(late.read_bytes()))
  except Exception as error:result=dict(status='ERROR',case=case['id'],error_type=type(error).__name__,error=str(error),config_sha256=config_sha)
  path=out/f'case-{i:02d}.attempt-{attempt:03d}.result.json';write(path,result)
  record=dict(case=case['id'],status=result['status'],result_file=path.name,result_sha256=sha(path.read_bytes()))
  state['attempts'][str(i)]=attempt+1
  if result['status']=='UNKNOWN':
   if data is not None:
    current.mkdir(exist_ok=True);atomic(current/'case.json',dict(index=i,case=case['id'],config_sha256=config_sha,source_sha256=source_sha,core_input_sha256=core_input_sha));atomic(current/'core.json',data)
   state['pending_unknown']=record;state['status']='UNKNOWN';atomic(out/'cursor.json',state);break
  state.pop('pending_unknown',None)
  if result['status'] in ('LOCAL_UNSAT','CONTROL_PASSED','VERIFIED_TARGET','SMALL_CONTROL_PASSED'):
   chain=commit_journal(out,i,record,chain);state['result_chain_sha256']=chain
  state['results'].append(dict(record,index=i));state['next_case']=i+1
  if current.exists():shutil.rmtree(current)
  state['status']=result['status'];state['terminal']=result['status'] in ('ERROR','VERIFIED_TARGET','SMALL_CONTROL_PASSED')
  atomic(out/'cursor.json',state)
  if state['terminal']:break
 if not state['terminal'] and state['next_case']==len(plan['cases']):
  state.update(terminal=True,status='CONTROLS_PASSED' if a.controls_only else 'LOCAL_PORTFOLIO_UNSAT');atomic(out/'cursor.json',state)
 summary=dict(status=state['status'] if state['terminal'] else 'UNKNOWN',results=state['results'],planned_cases=len(plan['cases']),chunk_id=selection['identity'],backend=a.backend,per_case_seconds=a.per_case_seconds,result_chain_sha256=chain,queries_this_invocation=query_count,
  elapsed_seconds=time.monotonic()-started,stop_reason=guard.reason(),deadline_utc=guard.deadline_utc,terminal=state['terminal'],scope='Only these exact residuals; no global rank lower bound.')
 atomic(out/'summary.json',summary);print(json.dumps(summary,sort_keys=True));return 2 if summary['status']=='ERROR' else 0

if __name__=='__main__':raise SystemExit(main())
