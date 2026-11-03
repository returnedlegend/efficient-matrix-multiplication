#!/usr/bin/env python3
"""Guarded lazy CP7 portfolio; no prepared SAT models or per-case quotients."""
import argparse
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time

def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(v):return sha(json.dumps(v,sort_keys=True,separators=(',',':')).encode())
def read(p):return json.loads(p.read_bytes())
def raw(v):return (json.dumps(v,sort_keys=True)+'\n').encode()
def syncdir(p):
 fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def atomic(p,v):
 q=Path(str(p)+'.tmp')
 with q.open('wb') as f:f.write(raw(v));f.flush();os.fsync(f.fileno())
 q.replace(p);syncdir(p.parent)
def immutable(p,data):
 with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 p.chmod(0o444);syncdir(p.parent)
def allocated(p):return sum(x.stat().st_blocks*512 for x in p.rglob('*') if x.is_file())

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--guard-state',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
 p.add_argument('--chunk-id',action='append');p.add_argument('--seconds',type=float,default=570);p.add_argument('--memory-mb',type=int,default=512);p.add_argument('--deadline-utc',default='2026-11-04T21:31:16Z');p.add_argument('--restart',action='store_true');p.add_argument('--small-control',action='store_true');p.add_argument('--controls-only',action='store_true');a=p.parse_args()
 if not 0<a.seconds<=600 or not 128<=a.memory_mb<=1024:p.error('bounded seconds/memory required')
 b=a.bundle.resolve();out=a.output_dir.resolve();manifest=read(b/'launch-manifest.json')
 for name,h in manifest['files'].items():
  f=(b/name).resolve()
  if not f.is_relative_to(b) or sha(f.read_bytes())!=h:raise ValueError('frozen source/input checksum mismatch: '+name)
 sys.path.insert(0,str(b/'runtime'))
 from mmsearch.fullpassing_guardv2_43 import CampaignBarrier,SourceRuntime,guarded_call,solve_cp_core,CAP
 from mmsearch.compact_eight43 import bits,replace_and_verify
 from mmsearch.verify import verify_candidate
 from scripts.verify_record42_independent import verify_bytes
 plan=read(b/('small-plan.json' if a.small_control else 'plan.json'));chunks=[c for c in plan['chunks'] if not a.chunk_id or c['id'] in a.chunk_id]
 if a.chunk_id and set(a.chunk_id)!={c['id'] for c in chunks}:raise ValueError('unknown chunk ID')
 if not a.small_control:
  for proof in read(b/'excluded449.json'):
   path=Path(proof['proof_path'])
   if sha(path.read_bytes())!=proof['proof_sha256']:raise ValueError('prior449 exact proof changed')
 requested=a.memory_mb*1024**2;_,hard=resource.getrlimit(resource.RLIMIT_AS);effective=requested if hard==resource.RLIM_INFINITY else min(requested,hard);resource.setrlimit(resource.RLIMIT_AS,(effective,effective))
 out.mkdir(parents=True,exist_ok=a.restart);lock=(out/'.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 config=dict(launch_manifest_sha256=sha((b/'launch-manifest.json').read_bytes()),plan_sha256=digest(plan),chunk_ids=[c['id'] for c in chunks],campaign=str(a.campaign.resolve()),guard_state=str(a.guard_state.resolve()),deadline_utc=a.deadline_utc,small_control=a.small_control,controls_only=a.controls_only,chunk_cap_bytes=CAP)
 config_sha=digest(config)
 if a.restart:
  if read(out/'config.json')!=config:raise ValueError('restart plan/source/runtime/stop binding changed')
 else:immutable(out/'config.json',raw(config))
 if (out/'WINNER.json').exists():
  checked=verify_bytes((out/'WINNER.json').read_bytes())
  if not checked['record_eligible']:raise ValueError('prior winner invalid')
  print(json.dumps(dict(status='VERIFIED_TARGET',queries=0,terminal_resume_guard=True)));return 0
 if a.small_control and (out/'SMALL_CONTROL.json').exists():
  checked=verify_candidate(read(out/'SMALL_CONTROL.json'),random_trials=0)
  if not checked['valid'] or checked['rank']!=7 or checked['exact_entries_checked']!=64:raise ValueError('prior small control invalid')
  print(json.dumps(dict(status='SMALL_CONTROL_PASSED',queries=0,terminal_resume_guard=True)));return 0
 guard=CampaignBarrier(a.campaign,a.guard_state,a.seconds,a.deadline_utc);signal.signal(signal.SIGTERM,lambda *_:setattr(guard,'stopped',True));signal.signal(signal.SIGINT,lambda *_:setattr(guard,'stopped',True))
 launches=out/'launches';launches.mkdir(exist_ok=True);immutable(launches/f'{len(list(launches.iterdir())):04d}.json',raw(dict(seconds=a.seconds,memory_mb=a.memory_mb,effective_AS_bytes=effective,started_utc=time.time(),config_sha256=config_sha)))
 runtimes={};queries=0;reports=[];status='UNKNOWN';reason=None
 for chunk in chunks:
  cd=out/'chunks'/chunk['id'];cd.mkdir(parents=True,exist_ok=True);attempts=cd/'attempts';attempts.mkdir(exist_ok=True);journal=cd/'results.jsonl';journal.touch(exist_ok=True)
  items=json.loads(gzip.decompress((b/chunk['plan']).read_bytes()))
  if digest(items)!=chunk['plan_sha256']:raise ValueError('chunk mask metadata changed')
  initial=digest([config_sha,chunk]);statepath=cd/'cursor.json'
  state=read(statepath) if statepath.exists() else dict(config_sha256=config_sha,chunk_sha256=chunk['plan_sha256'],next_index=0,journal_bytes=0,chain_sha256=initial,status='OPEN')
  if state['config_sha256']!=config_sha or state['chunk_sha256']!=chunk['plan_sha256']:raise ValueError('chunk continuation binding changed')
  data=journal.read_bytes()
  if len(data)<state['journal_bytes']:raise ValueError('committed journal truncated')
  with journal.open('r+b') as f:f.truncate(state['journal_bytes']);f.flush();os.fsync(f.fileno())
  chain=initial;events=[]
  for line in data[:state['journal_bytes']].splitlines():
   event=json.loads(line);value=event['value']
   if event['previous_sha256']!=chain or event['sha256']!=digest({k:v for k,v in event.items() if k!='sha256'}):raise ValueError('result chain corrupt')
   if value['index']!=len(events) or value['mask_sha256']!=digest(items[len(events)]) or value['config_sha256']!=config_sha:raise ValueError('result source/mask chain changed')
   if sha((cd/value['archive']).read_bytes())!=value['archive_sha256']:raise ValueError('result proof archive changed')
   if value['status']=='LOCAL_UNSAT' and (not value['complete'] or value['after_cutoff']):raise ValueError('incomplete/late negative in closed journal')
   chain=event['sha256'];events.append(value)
  if len(events)!=state['next_index'] or chain!=state['chain_sha256']:raise ValueError('cursor/result chain mismatch')
  if events and events[-1]['status'] in ('ERROR','SMALL_CONTROL_PASSED'):
   status=events[-1]['status'];reason='prior terminal result';break
  if len(events)==len(items):reports.append(dict(id=chunk['id'],complete=True,closed=len(events),chain_sha256=chain));continue
  held=guard.check(force=True)
  if held:reason=held;break
  source=chunk['source_id']
  if source not in runtimes:
   spec=plan['sources'][source];candidate=read(b/spec['path'])
   if sha((b/spec['path']).read_bytes())!=spec['sha256']:raise ValueError('source raw hash changed')
   runtimes[source]=SourceRuntime(candidate,a.small_control)
  runtime=runtimes[source]
  for index in range(len(events),len(items)):
   held=guard.check(force=True)
   if held:reason=held;break
   if allocated(cd)+2*1024**2>CAP:reason='chunk128MiB storage reserve';break
   item=items[index];identity=dict(index=index,mask_sha256=digest(item),source_id=source,source_sha256=plan['sources'][source]['sha256'],config_sha256=config_sha)
   stem=f'{index:05d}-';number=len(list(attempts.glob(stem+'*.json.gz')));archive=attempts/f'{stem}{number:04d}.json.gz';prepared=None;rawresult=None;candidate=None;full=None;independent=None
   def hold_raw(why,after=True):
    value=dict(identity,status='UNKNOWN',after_cutoff=after,reason=why,case=item,core=prepared,raw_result=rawresult,candidate=candidate,full_verification=full,independent_verification=independent)
    late=attempts/f'{stem}{number:04d}-after-cutoff.json.gz'
    immutable(late,gzip.compress(raw(value),compresslevel=1,mtime=0));atomic(cd/'last-unknown.json',dict(identity,reason=why,after_cutoff=after,raw_archive=str(late.relative_to(cd)),raw_archive_sha256=sha(late.read_bytes())))
   try:
    prepared=runtime.prepare(item)
    held=guard.check(force=True)
    if held:reason=held;hold_raw(held);break
    if a.controls_only:rawresult=dict(status='CONTROL_PASSED',complete=True)
    else:
     queries+=1
     answer=guarded_call(solve_cp_core,guard,prepared['core'],prepared['shape'],item.get('target_local_products',7),item['free_axis']);rawresult=answer['raw_result']
     if rawresult is None:queries-=1
     if answer['reason']:reason=answer['reason'];hold_raw(reason,answer['after_cutoff']);break
    if rawresult['status']=='UNKNOWN':reason=rawresult.get('reason',rawresult.get('case','decoder incomplete'));hold_raw(reason,False);break
    if rawresult['status']=='SAT':
     products=[]
     for term in rawresult['products']:
      expanded=[]
      for coefficient,basis in zip(term,prepared['image_bases']):
       v=0
       for j in bits(coefficient):v^=basis[j]
       expanded.append(v)
      products.append(expanded)
     candidate,full=replace_and_verify(runtime.source,prepared['source_indices'],products,dict(method='guarded lazy exact CP7'))
     held=guard.check(force=True)
     if held:reason=held;hold_raw(held);break
     if a.small_control:
      if not full['valid'] or full['rank']!=7 or full['exact_entries_checked']!=64:raise ValueError('tiny full tensor gate')
      rawresult['status']='SMALL_CONTROL_PASSED'
     else:
      independent=verify_bytes(raw(candidate))
      held=guard.check(force=True)
      if held:reason=held;hold_raw(held);break
      if not independent['record_eligible'] or full['rank']>92 or full['exact_entries_checked']!=15625:raise ValueError('full independent record gate')
      rawresult['status']='VERIFIED_TARGET'
   except Exception as error:rawresult=dict(status='ERROR',complete=False,error_type=type(error).__name__,error=str(error))
   held=guard.check(force=True)
   if held:reason=held;hold_raw(held);break
   if rawresult['status']=='LOCAL_UNSAT' and rawresult.get('complete') is not True:raise ValueError('negative not complete')
   proof=dict(identity,case=item,core_sha256=prepared['core_sha256'] if prepared else None,basis_sha256=prepared['basis_sha256'] if prepared else None,
    result=rawresult,after_cutoff=False,candidate=candidate,full_verification=full,independent_verification=independent)
   immutable(archive,gzip.compress(raw(proof),compresslevel=1,mtime=0))
   held=guard.check(force=True)
   if held:reason=held;hold_raw(held);break
   if rawresult['status'] in ('VERIFIED_TARGET','SMALL_CONTROL_PASSED'):
    prefix='WINNER' if not a.small_control else 'SMALL_CONTROL'
    atomic(out/(prefix+'.verification.json'),full);atomic(out/(prefix+'.independent.verification.json'),independent)
    atomic(out/(prefix+'.proof.json'),dict(identity,core_sha256=prepared['core_sha256'],archive=str(archive),archive_sha256=sha(archive.read_bytes()),candidate_sha256=sha(raw(candidate)),
     files={name:sha((out/name).read_bytes()) for name in [prefix+'.verification.json',prefix+'.independent.verification.json']}))
    held=guard.check(force=True)
    if held:reason=held;hold_raw(held);break
    immutable(out/(prefix+'.json'),raw(candidate))
    if rawresult['status']=='VERIFIED_TARGET':status='VERIFIED_TARGET';reason='terminal verified target';break
   value=dict(identity,core_sha256=prepared['core_sha256'] if prepared else None,basis_sha256=prepared['basis_sha256'] if prepared else None,status=rawresult['status'],complete=rawresult.get('complete',False),after_cutoff=False,
    archive=str(archive.relative_to(cd)),archive_sha256=sha(archive.read_bytes()))
   event=dict(value=value,previous_sha256=chain);event['sha256']=digest(event);before=state['journal_bytes']
   with journal.open('ab') as f:f.write(raw(event));f.flush();os.fsync(f.fileno());end=f.tell()
   held=guard.check(force=True)
   if held:
    with journal.open('r+b') as f:f.truncate(before);f.flush();os.fsync(f.fileno())
    reason=held;hold_raw(held);break
   chain=event['sha256'];state.update(next_index=index+1,journal_bytes=end,chain_sha256=chain,status=rawresult['status']);atomic(statepath,state)
   if rawresult['status'] in ('ERROR','VERIFIED_TARGET','SMALL_CONTROL_PASSED'):status=rawresult['status'];reason='terminal result';break
  reports.append(dict(id=chunk['id'],complete=state['next_index']==len(items),closed=state['next_index'],chain_sha256=state['chain_sha256'],allocated_bytes=allocated(cd)))
  if reason:break
 if not reason and all(r['complete'] for r in reports) and len(reports)==len(chunks):status='CONTROLS_PASSED' if a.controls_only else 'LOCAL_PORTFOLIO_UNSAT'
 summary=dict(status=status,reason=reason,queries=queries,chunks=reports,planned_chunks=len(chunks),scope='Only planned exact residuals; timed out/open cases are not negatives.',elapsed_seconds=guard.clock()-guard.start)
 atomic(out/'summary.json',summary);print(json.dumps(summary,sort_keys=True));return 2 if status=='ERROR' else 0

if __name__=='__main__':raise SystemExit(main())
