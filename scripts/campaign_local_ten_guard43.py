#!/usr/bin/env python3
"""Separate guarded local10 compact one-coset search; root owns production launch."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.local_guard43 import CampaignGuard,CampaignHold

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
 p.add_argument('--deadline-utc',default='2026-11-04T21:31:16Z');p.add_argument('--stop-marker',type=Path,action='append',default=[]);p.add_argument('--guard-state',type=Path)
 p.add_argument('--seconds',type=float,default=60);p.add_argument('--memory-mb',type=int,default=1024);p.add_argument('--resume',action='store_true');p.add_argument('--controls-only',action='store_true');p.add_argument('--small-control',action='store_true')
 a=p.parse_args()
 if not 0<a.seconds<=300 or not 128<=a.memory_mb<=1024:p.error('bounded seconds/memory required')
 b=a.bundle.resolve();out=a.output_dir.resolve()
 markers=a.stop_marker
 guard=CampaignGuard(a.seconds,a.deadline_utc,markers,a.guard_state,campaign_dir=b.parent)
 manifest=read(b/'launch-manifest.json')
 for name,expected in manifest['files'].items():
  path=(b/name).resolve()
  if not path.is_relative_to(b) or sha(path.read_bytes())!=expected:raise ValueError('frozen checksum mismatch: '+name)
 sys.path.insert(0,str(b/'runtime'))
 from mmsearch.compact_coset43 import solve_core
 from mmsearch.compact_eight43 import bits,expand_core,packed_tensor,replace_and_verify
 from mmsearch.sat_neighborhoods import factor_masks
 from mmsearch.verify import verify_candidate
 from scripts.verify_record42_independent import verify_bytes
 requested=a.memory_mb*1024**2;_,hard=resource.getrlimit(resource.RLIMIT_AS);effective=requested if hard==resource.RLIM_INFINITY else min(requested,hard)
 resource.setrlimit(resource.RLIMIT_AS,(effective,effective))
 plan=read(b/('small-plan.json' if a.small_control else 'plan.json'));config=dict(launch_manifest_sha256=sha((b/'launch-manifest.json').read_bytes()),small_control=a.small_control,controls_only=a.controls_only,deadline_utc=guard.deadline_utc,stop_markers=[str(p) for p in guard.stop_markers],guard_state=str(a.guard_state.resolve()) if a.guard_state else None,campaign_dir=str(b.parent))
 config_sha=sha(json.dumps(config,sort_keys=True).encode());started=guard.started
 def stopped(sig,frame):
  guard.stop()
 signal.signal(signal.SIGTERM,stopped);signal.signal(signal.SIGINT,stopped)
 def cancelled():return guard.reason() is not None
 if a.resume:
  if read(out/'config.json')!=config:raise ValueError('resume configuration/source/runtime changed')
  state=read(out/'cursor.json')
  if state['config_sha256']!=config_sha:raise ValueError('resume cursor hash mismatch')
 else:
  out.mkdir(parents=True,exist_ok=False);write(out/'config.json',config);state=dict(config_sha256=config_sha,next_case=0,results=[],attempts={},terminal=False,status='UNKNOWN');atomic(out/'cursor.json',state)
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
  checked=verify_bytes((out/'WINNER.json').read_bytes())
  if not checked['record_eligible']:raise ValueError('corrupt prior winner')
  print(json.dumps(dict(status='VERIFIED_TARGET',terminal_resume_guard=True)));return 0
 if state.get('terminal'):
  print(json.dumps(dict(status=state['status'],terminal_resume_guard=True)));return 2 if state['status']=='ERROR' else 0
 query_count=0
 for i in range(state['next_case'],len(plan['cases'])):
  if cancelled():break
  case=plan['cases'][i];attempt=state['attempts'].get(str(i),0);raw_decoder=None;candidate=None;full=None;independent=None
  try:
   guard.check('pre_source_control')
   source=read(b/case['source']);data=read(b/case['core']);verified=verify_candidate(source,random_trials=0)
   if not verified['valid'] or verified['rank']!=case['source_products'] or verified['exact_entries_checked']!=source['dimension']**6:raise ValueError('source full tensor control failed')
   terms=factor_masks(source);ambient=0
   for j in data['source_indices']:ambient^=packed_tensor(terms[j],source['dimension']**2)
   if expand_core(data['core'],data['shape'],data['image_bases'],source['dimension']**2)!=ambient:raise ValueError('core/source exact expansion failed')
   guard.check('pre_dispatch')
   if source['dimension']==5 and not a.controls_only and guard.resources is None:raise CampaignHold('n5 production resource guard required','pre_dispatch')
   if a.controls_only:result=dict(status='CONTROL_PASSED',full_entries_checked=verified['exact_entries_checked'])
   else:
    query_count+=1
    result=solve_core(data['core'],data['shape'],case['target_local_products'],axis=case['free_axis'],max_points=65025,cancelled=cancelled)
    raw_decoder=json.loads(json.dumps(result));guard.check('post_solve')
    if result['status']=='SAT':
     products=[]
     for term in result['products']:
      expanded=[]
      for coefficient,basis in zip(term,data['image_bases']):
       value=0
       for j in bits(coefficient):value^=basis[j]
       expanded.append(value)
      products.append(expanded)
     candidate,full=replace_and_verify(source,data['source_indices'],products,dict(method='exact exhaustive opposite-pair one-coset decoder'))
     guard.check('post_full_verification')
     if a.small_control:
      if source['dimension']!=2 or full['rank']!=case['source_products']-case['source_local_products']+case['target_local_products'] or full['exact_entries_checked']!=64:raise ValueError('small constructive repair failed')
      guard.check('pre_small_publication')
      write(out/'SMALL_CONTROL.verification.json',full);write(out/'SMALL_CONTROL.json',candidate);result['status']='SMALL_CONTROL_PASSED'
     else:
      independent=verify_bytes(json.dumps(candidate,sort_keys=True).encode())
      guard.check('post_independent_verification')
      if not independent['record_eligible'] or full['rank']>92 or full['exact_entries_checked']!=15625:raise ValueError('n5 winner failed full independent verification')
      proofdir=out/'proofs'/f'case-{i:02d}-attempt-{attempt:03d}';proofdir.mkdir(parents=True,exist_ok=False)
      certificate=dict(result,case=case['id'],config_sha256=config_sha)
      for name,value in [('candidate.json',candidate),('verification.json',full),('independent.json',independent),('core-certificate.json',certificate)]:write(proofdir/name,value)
      guard.check('pre_publication_views')
      # Orphan top-level proof views may be replaced before a marker exists;
      # immutable attempt proofs remain the authoritative full record.
      for name,value in [('WINNER.verification.json',full),('WINNER.independent.verification.json',independent),('WINNER.core-certificate.json',certificate)]:atomic(out/name,value)
      atomic(out/'WINNER.proof.json',dict(candidate_sha256=sha(raw(candidate)),proof_directory=str(proofdir.relative_to(out)),files={name:sha((out/name).read_bytes()) for name in ['WINNER.verification.json','WINNER.independent.verification.json','WINNER.core-certificate.json']}))
      guard.check('pre_winner_marker')
      # Durable full proof and the final cutoff barrier precede the marker.
      write(out/'WINNER.json',candidate);result['status']='VERIFIED_TARGET'
   if result['status'] not in ('VERIFIED_TARGET','SMALL_CONTROL_PASSED'):guard.check('pre_result_commit')
   result.update(case=case['id'],config_sha256=config_sha,scope='Exact specified fixed-outside residual only.',effective_AS_limit_bytes=effective)
  except CampaignHold as hold:
   result=dict(status='UNKNOWN',case=case['id'],config_sha256=config_sha,reason=hold.reason,barrier=hold.barrier,complete=False,after_cutoff=True,guard=guard.observation())
   if raw_decoder is not None:
    late=out/f'case-{i:02d}.attempt-{attempt:03d}.after-cutoff.raw.json'
    write(late,dict(after_cutoff=True,no_within_budget_claim=True,case=case['id'],config_sha256=config_sha,reason=hold.reason,barrier=hold.barrier,guard=guard.observation(),raw_decoder_result=raw_decoder,candidate=candidate,full_verification=full,independent_verification=independent,source_sha256=sha((b/case['source']).read_bytes()),core_sha256=sha((b/case['core']).read_bytes())))
    result.update(after_cutoff_artifact=late.name,after_cutoff_artifact_sha256=sha(late.read_bytes()))
  except Exception as error:result=dict(status='ERROR',case=case['id'],error_type=type(error).__name__,error=str(error),config_sha256=config_sha)
  attempt=state['attempts'].get(str(i),0);path=out/f'case-{i:02d}.attempt-{attempt:03d}.result.json';write(path,result)
  record=dict(case=case['id'],status=result['status'],result_file=path.name,result_sha256=sha(path.read_bytes()))
  state['attempts'][str(i)]=attempt+1
  if result['status']=='UNKNOWN':
   state['pending_unknown']=record;state['status']='UNKNOWN';atomic(out/'cursor.json',state);break
  state.pop('pending_unknown',None);state['results'].append(record);state['next_case']=i+1
  state['status']=result['status'];state['terminal']=result['status'] in ('ERROR','VERIFIED_TARGET','SMALL_CONTROL_PASSED')
  atomic(out/'cursor.json',state)
  if state['terminal']:break
 if not state['terminal'] and state['next_case']==len(plan['cases']):
  state.update(terminal=True,status='CONTROLS_PASSED' if a.controls_only else 'LOCAL_PORTFOLIO_UNSAT');atomic(out/'cursor.json',state)
 summary=dict(status=state['status'] if state['terminal'] else 'UNKNOWN',results=state['results'],planned_cases=len(plan['cases']),queries_this_invocation=query_count,
  elapsed_seconds=time.monotonic()-started,stop_reason=guard.reason(),deadline_utc=guard.deadline_utc,terminal=state['terminal'],scope='Only these exact residuals; no global rank lower bound.')
 atomic(out/'summary.json',summary);print(json.dumps(summary,sort_keys=True));return 2 if summary['status']=='ERROR' else 0

if __name__=='__main__':raise SystemExit(main())
