#!/usr/bin/env python3
"""Guarded fixed native-corpus sparse-cycle catalogue and optional one-hop scan."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import resource
import sys
import time

REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from mmsearch.tensor_code7 import strict_load,second_check,xor_columns,digest
from mmsearch.tensor_code7_extension import raw_sha
from mmsearch.tensor_code7_native_corpus import PREPARED_SCHEMA,load_root_pinned_native,candidate_from_atoms
from mmsearch.tensor_code7_sparse_cycles import enumerate_cycles,validate_catalogue,scan_seed_deltas
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import verify_bytes
from scripts.tensor_code7 import Stop,runtime,write_json
from scripts.tensor_code7_extension import code_hashes
from scripts.tensor_code7_extension_select import DirectGuard
from scripts.tensor_code7_native_corpus import Poll,output_check,OUTPUT_LIMIT

SCHEMA='tensor_code7.sparse_cycle_run.v1'
EXTRA=('mmsearch/tensor_code7_sparse_cycles.py','scripts/tensor_code7_sparse_cycle_run.py',
 'tests/test_tensor_code7_sparse_cycles.py','tests/test_tensor_code7_sparse_cycle_run.py',
 'research/tensor_code7_sparse_cycles.md')


def runtime_hashes():
 hashes=code_hashes();hashes.update({name:raw_sha((REPO/name).read_bytes()) for name in EXTRA})
 return hashes


def quarantine_candidates(root,reason):
 hidden=root/'.raw-candidates';hidden.mkdir(exist_ok=True)
 moved=[]
 for name in ('first-record-evidence','negatives'):
  path=root/name
  if path.exists():
   target=hidden/f'withheld-{name}-{time.monotonic_ns()}';path.rename(target);moved.append(str(target))
   for raw in target.rglob('raw.json'):
    value=strict_load(raw.read_bytes());value.update(status='UNKNOWN',complete=False,after_cutoff=True,
      no_within_budget_claim=True,stop_reason=str(reason));write_json(raw,value)
 return moved


def save_negative(root,document,item,guard,ordinal,target_weight):
 atoms=[tuple(a) for a in document['atoms']];n=document['dimension'];state=int(item['state_hex'],16)
 columns=[int(c,16) for c in document['columns_hex']]
 if xor_columns(columns,state)!=int(document['target_hex'],16):raise ValueError('negative candidate full syndrome differs')
 candidate=candidate_from_atoms([a for i,a in enumerate(atoms) if state>>i&1],n)
 candidate['metadata']=dict(method=SCHEMA,source_prepared_sha256=item['prepared_sha256'],move=item,
  rank=len(candidate['terms']),novelty_claim=False)
 encoded=(json.dumps(candidate,sort_keys=True,indent=2)+'\n').encode()
 staging=root/'.raw-candidates'/f'negative-{ordinal:04d}';staging.mkdir(parents=True,exist_ok=False)
 envelope=dict(status='UNKNOWN',complete=False,no_within_budget_claim=True,raw=dict(candidate=candidate,evidence=item))
 output_check(root,len(encoded)*2+256*1024);write_json(staging/'raw.json',envelope,exclusive=True)
 try:
  guard('pre_negative_full_tensor');primary=verify_candidate(candidate,random_trials=8,seed=ordinal)
  guard('post_negative_primary')
  independent=verify_bytes(encoded) if n==5 else second_check(candidate)
  guard('post_negative_independent')
  if not primary['valid'] or not independent['valid'] or primary['exact_entries_checked']!=n**6 or independent['exact_entries_checked']!=n**6 or primary['rank']!=item['new_weight']:
   raise ValueError('negative candidate failed independent full checks')
  if n==5 and independent['essential_rank']!=item['new_weight']:raise ValueError('independent rank differs')
  (staging/'candidate.json').write_bytes(encoded)
  write_json(staging/'verification.json',dict(primary=primary,independent=independent),exclusive=True)
  if raw_sha((staging/'candidate.json').read_bytes())!=raw_sha(encoded):raise ValueError('saved negative bytes differ')
  eligible=item['new_weight']<=target_weight
  destination=root/'first-record-evidence' if eligible else root/'negatives'/f'negative-{ordinal:04d}-rank{item["new_weight"]}'
  destination.parent.mkdir(parents=True,exist_ok=True)
  guard('pre_negative_publication');staging.rename(destination)
  try:guard('post_negative_publication')
  except Stop:
   destination.rename(staging);raise
  return dict(path=str(destination),rank=item['new_weight'],candidate_sha256=raw_sha(encoded),target=eligible)
 except Stop as exc:
  envelope.update(after_cutoff=True,stop_reason=str(exc));write_json(staging/'raw.json',envelope)
  raise


def run_pipeline(document,root,guard,args,prepared_sha256):
 atoms=[tuple(a) for a in document['atoms']];n=document['dimension'];catalogue=None;scan=None;saved=[];winner=False
 def cancelled():
  try:guard();return None
  except Stop as exc:return str(exc)
 def progress(value):
  guard('pre_cycle_checkpoint');write_json(root/'enumeration-checkpoint.json',dict(value,prepared_sha256=prepared_sha256,rng=None))
 try:
  catalogue=enumerate_cycles(atoms,n,args.max_trials,args.max_cycles,cancelled,progress)
  guard('post_enumeration');masks=validate_catalogue(catalogue,atoms,n);guard('post_catalogue_verification')
  encoded=(json.dumps(catalogue,sort_keys=True,indent=2)+'\n').encode()
  output_check(root,len(encoded)+1024**2);(root/'catalogue.json').write_bytes(encoded);guard('post_catalogue_publication')
 except Stop as exc:
  hidden=root/'.raw-enumeration';hidden.mkdir(exist_ok=True)
  if (root/'catalogue.json').exists():(root/'catalogue.json').unlink()
  write_json(hidden/'after-cutoff.json',dict(status='UNKNOWN',complete=False,after_cutoff=True,no_within_budget_claim=True,stop_reason=str(exc),raw=dict(catalogue=catalogue)),exclusive=True)
  raise
 if args.authorize_seed_scan:
  guard('pre_seed_scan');seen={}
  def negative(item):
   nonlocal winner
   guard('pre_negative_candidate');state=int(item['state_hex'],16)
   if state in seen:return False
   if len(saved)>=args.max_negative_candidates:raise Stop('negative_candidate_cap')
   record=save_negative(root,document,dict(item,prepared_sha256=prepared_sha256,code_sha256=getattr(args,'code_sha256',None)),guard,len(saved),args.target_weight)
   saved.append(record);seen[state]=record
   write_json(root/'negative-index.json',saved)
   if record['target']:winner=True;return True
   return False
  seeds=[int(state,16) for state in document['seed_states_hex']]
  write_json(root/'scan-dispatch.json',dict(optimization_started=True,prepared_sha256=prepared_sha256),exclusive=True)
  try:
   scan=scan_seed_deltas(seeds,masks,args.max_evaluations,cancelled,negative)
   guard('post_seed_scan');write_json(root/'scan.json',scan,exclusive=True);guard('post_scan_publication')
  except (Stop,Exception) as exc:
   hidden=root/'.raw-scan';hidden.mkdir(exist_ok=True)
   if (root/'scan.json').exists():(root/'scan.json').unlink()
   write_json(hidden/'incomplete.json',dict(status='UNKNOWN',complete=False,no_within_budget_claim=True,stop_reason=str(exc),raw=dict(scan=scan,saved=saved)),exclusive=True)
   quarantine_candidates(root,exc);raise
 return dict(status='FROZEN_DOUBLE_VERIFIED_TARGET' if winner else 'COMPLETE_FIXED_CATALOGUE_SCAN' if scan and scan['complete'] and catalogue['complete'] else 'CATALOGUE_PREPARED' if not scan and catalogue['complete'] else 'UNKNOWN',
  complete=winner or bool(catalogue['complete'] and (scan is None or scan['complete'])),winner=winner,saved=saved,
  enumeration_complete=catalogue['complete'],cycle_count=catalogue['cycle_count'],cycle_span_rank=catalogue['cycle_span_rank'],
  weight_distribution=catalogue['weight_distribution'],trials=catalogue['trials'],scan=scan,
  optimization_called=bool(args.authorize_seed_scan),scope='Only original verified seeds and the explicit bounded identity catalogue; no global minimum claim.')


def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--prepared',type=Path);p.add_argument('--prepared-sha256');p.add_argument('--sources',type=Path);p.add_argument('--sources-sha256')
 p.add_argument('--campaign-dir',type=Path,required=True);p.add_argument('--campaign-sha256');p.add_argument('--guard-state',type=Path)
 p.add_argument('--hard-utc',default='2026-11-03T19:24:17Z');p.add_argument('--seconds',type=float,default=120);p.add_argument('--outdir',type=Path,required=True)
 p.add_argument('--max-trials',type=int,default=2000000);p.add_argument('--max-cycles',type=int,default=10000)
 p.add_argument('--max-evaluations',type=int,default=360000);p.add_argument('--max-negative-candidates',type=int,default=128)
 p.add_argument('--authorize-cycle-enumeration',action='store_true');p.add_argument('--authorize-seed-scan',action='store_true')
 p.add_argument('--qa-receipt',type=Path);p.add_argument('--qa-sha256');p.add_argument('--inspect-runtime',action='store_true');a=p.parse_args(argv);a.target_weight=92
 if a.inspect_runtime:
  hashes=runtime_hashes();print(json.dumps(dict(code_sha256=hashes,runtime_closure_sha256=digest(hashes),production_inputs_read=False,optimization_called=False),sort_keys=True));return 0
 if not a.authorize_cycle_enumeration:
  print(json.dumps(dict(status='DISABLED',production_inputs_read=False,optimization_called=False),sort_keys=True));return 0
 for key in ('prepared','prepared_sha256','sources','sources_sha256','campaign_sha256','guard_state'):
  if getattr(a,key) is None:p.error('pinned inputs/freshguard required: '+key)
 if not 1<=a.max_trials<=2000000 or not 1<=a.max_cycles<=10000 or not 1<=a.max_evaluations<=360000 or not 1<=a.max_negative_candidates<=128:p.error('reviewed scope caps exceeded')
 if a.authorize_seed_scan and (not a.qa_receipt or not a.qa_sha256):p.error('seed optimization requires independent QA receipt/raw pin')
 direct=DirectGuard(a);guard=Poll(direct)
 try:guard('pre_dispatch')
 except Stop as exc:
  print(json.dumps(dict(status='UNKNOWN',complete=False,stop_reason=str(exc),optimization_called=False),sort_keys=True));return 0
 hashes=runtime_hashes()
 if a.authorize_seed_scan:
  qa_raw=a.qa_receipt.read_bytes()
  if raw_sha(qa_raw)!=a.qa_sha256:raise ValueError('QA receipt raw pin differs')
  qa=strict_load(qa_raw)
  expected=dict(status='PASS',prepared_sha256=a.prepared_sha256,sources_sha256=a.sources_sha256,
   sparse_core_sha256=raw_sha((REPO/'mmsearch/tensor_code7_sparse_cycles.py').read_bytes()),runtime_sha256=raw_sha(Path(__file__).read_bytes()),runtime_closure_sha256=digest(hashes))
  if any(qa.get(key)!=value for key,value in expected.items()):raise ValueError('independent QA does not bind this source/code scope')
 os.sched_setaffinity(0,{0})
 if os.getpriority(os.PRIO_PROCESS,0)<10:os.nice(10-os.getpriority(os.PRIO_PROCESS,0))
 resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(OUTPUT_LIMIT,OUTPUT_LIMIT))
 root=a.outdir.resolve();campaign=a.campaign_dir.resolve()
 if not root.is_relative_to(campaign) or root.is_relative_to(a.prepared.resolve().parent):raise ValueError('new C7 output outside frozen inputs required')
 root.mkdir(parents=True,exist_ok=False);guard.output=root;hidden=root/'.inputs';blobs=hidden/'blobs';blobs.mkdir(parents=True)
 def freeze(record,label):
  path=Path(record['path']).resolve();raw=path.read_bytes();h=raw_sha(raw)
  if h!=record['sha256']:raise ValueError('source/producer hash changed:'+label)
  target=blobs/h
  if not target.exists():output_check(root,len(raw)+1024**2);target.write_bytes(raw)
  return raw
 for name,h in hashes.items():
  target=root/'code'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((REPO/name).read_bytes())
  if raw_sha(target.read_bytes())!=h:raise ValueError('code changed during snapshot')
 write_json(root/'launch.json',dict(arguments={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()},runtime=runtime(),code_sha256=hashes),exclusive=True)
 a.code_sha256=hashes
 def bound_guard(stage='loop'):
  guard(stage)
  if stage in ('pre_negative_publication','pre_seed_scan','pre_final_sparse_receipt','post_final_sparse_receipt'):
   for name,h in hashes.items():
    if raw_sha((REPO/name).read_bytes())!=h:raise Stop('code_pin_changed:'+stage)
   if raw_sha(a.prepared.read_bytes())!=a.prepared_sha256 or raw_sha(a.sources.read_bytes())!=a.sources_sha256:raise Stop('input_pin_changed:'+stage)
   guard(stage)
 exit_code=0
 try:
  scratch=root/'.source-recheck';scratch.mkdir()
  document=load_root_pinned_native(a.prepared,a.prepared_sha256,a.sources,a.sources_sha256,campaign,scratch,freeze,bound_guard)
  (hidden/'prepared.json').write_bytes(a.prepared.read_bytes());(hidden/'sources.json').write_bytes(a.sources.read_bytes())
  bound_guard('post_source_authentication');result=run_pipeline(document,root,bound_guard,a,a.prepared_sha256)
 except Stop as exc:
  moved=quarantine_candidates(root,exc)
  result=dict(status='UNKNOWN',complete=False,stop_reason=str(exc),withheld_candidates=moved,
   optimization_called=(root/'scan-dispatch.json').exists())
 except Exception as exc:
  moved=quarantine_candidates(root,exc)
  result=dict(status='FAILED_CLOSED',complete=False,error_type=type(exc).__name__,error=str(exc),
   withheld_candidates=moved,optimization_called=(root/'scan-dispatch.json').exists());exit_code=2
 result.update(runtime=runtime(),elapsed_seconds=time.monotonic()-direct.started,code_sha256=hashes)
 try:bound_guard('pre_final_sparse_receipt')
 except Stop as exc:
  moved=quarantine_candidates(root,exc);result.update(status='UNKNOWN',complete=False,winner=False,stop_reason=str(exc),withheld_candidates=moved)
 write_json(root/'result.json',result,exclusive=True)
 write_json(root/'checksums.json',{str(path.relative_to(root)):raw_sha(path.read_bytes()) for path in sorted(root.rglob('*')) if path.is_file()},exclusive=True)
 try:bound_guard('post_final_sparse_receipt')
 except Stop as exc:
  moved=quarantine_candidates(root,exc)
  result.update(status='UNKNOWN',complete=False,winner=False,stop_reason=str(exc),after_cutoff=True,no_within_budget_claim=True,withheld_candidates=moved)
  write_json(root/'result.json',result)
  write_json(root/'checksums.json',{str(path.relative_to(root)):raw_sha(path.read_bytes()) for path in sorted(root.rglob('*')) if path.is_file() and path!=root/'checksums.json'})
 output_check(root)
 print(json.dumps(result,sort_keys=True));return exit_code


if __name__=='__main__':raise SystemExit(main())
