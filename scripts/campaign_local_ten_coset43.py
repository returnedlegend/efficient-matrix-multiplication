#!/usr/bin/env python3
"""Separate exact local10 compact one-coset search; root owns production launch."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time

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
 p.add_argument('--seconds',type=float,default=60);p.add_argument('--memory-mb',type=int,default=1024);p.add_argument('--resume',action='store_true');p.add_argument('--controls-only',action='store_true');p.add_argument('--small-control',action='store_true')
 a=p.parse_args()
 if not 0<a.seconds<=300 or not 128<=a.memory_mb<=1024:p.error('bounded seconds/memory required')
 b=a.bundle.resolve();out=a.output_dir.resolve();manifest=read(b/'launch-manifest.json')
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
 plan=read(b/('small-plan.json' if a.small_control else 'plan.json'));config=dict(launch_manifest_sha256=sha((b/'launch-manifest.json').read_bytes()),small_control=a.small_control,controls_only=a.controls_only)
 config_sha=sha(json.dumps(config,sort_keys=True).encode());started=time.monotonic();stop=False
 def stopped(sig,frame):
  nonlocal stop
  stop=True
 signal.signal(signal.SIGTERM,stopped);signal.signal(signal.SIGINT,stopped)
 def cancelled():return stop or time.monotonic()-started>=a.seconds
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
 if (out/'WINNER.json').exists():
  checked=verify_bytes((out/'WINNER.json').read_bytes())
  if not checked['record_eligible']:raise ValueError('corrupt prior winner')
  print(json.dumps(dict(status='VERIFIED_TARGET',terminal_resume_guard=True)));return 0
 if state.get('terminal'):
  print(json.dumps(dict(status=state['status'],terminal_resume_guard=True)));return 2 if state['status']=='ERROR' else 0
 query_count=0
 for i in range(state['next_case'],len(plan['cases'])):
  if cancelled():break
  case=plan['cases'][i]
  try:
   source=read(b/case['source']);data=read(b/case['core']);verified=verify_candidate(source,random_trials=0)
   if not verified['valid'] or verified['rank']!=case['source_products'] or verified['exact_entries_checked']!=source['dimension']**6:raise ValueError('source full tensor control failed')
   terms=factor_masks(source);ambient=0
   for j in data['source_indices']:ambient^=packed_tensor(terms[j],source['dimension']**2)
   if expand_core(data['core'],data['shape'],data['image_bases'],source['dimension']**2)!=ambient:raise ValueError('core/source exact expansion failed')
   if a.controls_only:result=dict(status='CONTROL_PASSED',full_entries_checked=verified['exact_entries_checked'])
   else:
    result=solve_core(data['core'],data['shape'],case['target_local_products'],axis=case['free_axis'],max_points=65025,cancelled=cancelled);query_count+=1
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
     if a.small_control:
      if source['dimension']!=2 or full['rank']!=case['source_products']-case['source_local_products']+case['target_local_products'] or full['exact_entries_checked']!=64:raise ValueError('small constructive repair failed')
      write(out/'SMALL_CONTROL.verification.json',full);write(out/'SMALL_CONTROL.json',candidate);result['status']='SMALL_CONTROL_PASSED'
     else:
      independent=verify_bytes(json.dumps(candidate,sort_keys=True).encode())
      if not independent['record_eligible'] or full['rank']>92 or full['exact_entries_checked']!=15625:raise ValueError('n5 winner failed full independent verification')
      write(out/'WINNER.verification.json',full);write(out/'WINNER.independent.verification.json',independent)
      write(out/'WINNER.core-certificate.json',dict(result,case=case['id'],config_sha256=config_sha))
      write(out/'WINNER.proof.json',dict(candidate_sha256=sha(raw(candidate)),files={name:sha((out/name).read_bytes()) for name in ['WINNER.verification.json','WINNER.independent.verification.json','WINNER.core-certificate.json']}))
      # Durable full proof precedes the externally observed winner marker.
      write(out/'WINNER.json',candidate);result['status']='VERIFIED_TARGET'
   result.update(case=case['id'],config_sha256=config_sha,scope='Exact specified fixed-outside residual only.',effective_AS_limit_bytes=effective)
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
  elapsed_seconds=time.monotonic()-started,terminal=state['terminal'],scope='Only these exact residuals; no global rank lower bound.')
 atomic(out/'summary.json',summary);print(json.dumps(summary,sort_keys=True));return 2 if summary['status']=='ERROR' else 0

if __name__=='__main__':raise SystemExit(main())
