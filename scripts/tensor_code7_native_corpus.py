#!/usr/bin/env python3
"""Native-export corpus selection/preparation; no target optimization mode."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import resource
import shutil
import sys
import time

REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from mmsearch.tensor_code7 import strict_load
from mmsearch.tensor_code7_extension import raw_sha
from mmsearch.tensor_code7_native_corpus import (SOURCES_SCHEMA,PREPARED_SCHEMA,ALLOWED_RUNS,parse_native,
 parse_json_candidate,choose_diverse,load_sources,build_prepared)
from scripts.tensor_code7 import Stop,runtime,write_json
from scripts.tensor_code7_extension import code_hashes
from scripts.tensor_code7_extension_select import DirectGuard

EXTRA=('mmsearch/tensor_code7_native_corpus.py','scripts/tensor_code7_native_corpus.py',
 'tests/test_tensor_code7_native_corpus.py','research/tensor_code7_native_corpus.md','scripts/tensor_code7_native_corpus.schema.json')


OUTPUT_LIMIT=32*1024**2


def allocated(root):
 return sum(max(p.stat().st_size,p.stat().st_blocks*512) for p in [root,*root.rglob('*')]) if root.exists() else 0


def output_check(root,reserve=0):
 if allocated(root)+reserve>OUTPUT_LIMIT:raise Stop('native_output32MiB_limit')


class Poll:
 def __init__(self,guard):self.guard=guard;self.last=-float('inf');self.output=None
 def __call__(self,stage='loop'):
  if datetime.now(timezone.utc).timestamp()>=self.guard.hard.timestamp()-3:raise Stop('hard_utc_postcheck_reserve:'+stage)
  if stage!='loop' and self.output is not None:output_check(self.output)
  if stage!='loop' or time.monotonic()-self.last>=.1:
   self.guard(stage);self.last=time.monotonic()
  elif self.guard.canonical.signal_stop or time.monotonic()-self.guard.started>=self.guard.seconds:
   raise Stop('signal_or_invocation_cutoff:'+stage)


def pin(path):return dict(path=str(path.resolve()),sha256=raw_sha(path.read_bytes()))


def make_manifest(root,inventory):
 old=root/'tensor-code-prep-001/prepared.json';old_doc=strict_load(old.read_bytes())
 def load(record):
  raw=Path(record['path']).read_bytes()
  if raw_sha(raw)!=record['raw_sha256']:raise ValueError('inventory source raw hash changed')
  return parse_native(raw) if record['kind']=='native-text' else parse_json_candidate(raw)[0]
 selected,selection=choose_diverse(inventory,load,32,4,[tuple(a) for a in old_doc['atoms']])
 runs={}
 for name in sorted({row['run'] for row in selected}):
  directory=root/name;m=strict_load((directory/'manifest.json').read_bytes())
  baseline=name=='baseline-native300-001'
  runtime_root=(root/'baseline-native300-ready-v1/code') if baseline else directory/'frozen/runtime'
  ready=strict_load((root/'baseline-native300-ready-v1/manifest.json').read_bytes()) if baseline else None
  cp=(REPO/'artifacts/rl_campaign42_20261103T033116Z/plus-burst42-pilot-ready-v1/code/native/flip_worker_plus_burst42.cpp') if baseline else runtime_root/'native/flip_worker_plus_burst42.cpp'
  cpp=[pin(cp)]
  if not baseline:cpp.append(pin(runtime_root/'native/flip_worker_dwell_hold_rank.cpp'))
  run=dict(directory=str(directory.resolve()),manifest=pin(directory/'manifest.json'),summary=pin(directory/'summary.json'),
   input=pin(directory/'input.json'),native_input=pin(directory/'native/input.txt'),binary=pin(directory/'frozen/native-worker'),
   runtime_root=str(runtime_root.resolve()),runtime_code_sha256=ready['runtime_code_sha256'] if baseline else m['runtime_code_sha256'],cpp=cpp,
   export_registry=pin(root/('baseline-native300-analysis-v1/raw-export-pins.json' if baseline else 'dwell-hold-rank-analysis-v1/certificate-pins.json')))
  if baseline:run.update(ready_manifest=pin(root/'baseline-native300-ready-v1/manifest.json'),source_audit=pin(root/'cyclic-orbit-code7-prototype-v1/source-audit.json'))
  runs[name]=run
 return dict(schema=SOURCES_SCHEMA,dimension=5,field=2,authority=dict(base_prepared=pin(old),
  anchors=pin(root/'tensor-code-source-anchors-v1/manifest.json'),approved_root=str((root/'tensor-code-source-anchors-v1').resolve()),
  root_source_approval=pin(root/'root-review-decisions/tensor-code-source-anchors-approved.json')),
  runs=runs,selected=selected,selection=selection,scope='Selection metadata only until fresh complete tensor checks pass.')


def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('select','prepare'))
 p.add_argument('--campaign-dir',type=Path,required=True);p.add_argument('--campaign-sha256')
 p.add_argument('--guard-state',type=Path);p.add_argument('--hard-utc',default='2026-11-03T19:24:17Z')
 p.add_argument('--seconds',type=float,default=120);p.add_argument('--inventory',type=Path)
 p.add_argument('--manifest',type=Path);p.add_argument('--manifest-sha256');p.add_argument('--outdir',type=Path,required=True)
 p.add_argument('--authorize-native-preparation',action='store_true');a=p.parse_args(argv)
 root=a.campaign_dir.resolve();out=a.outdir.resolve()
 if not out.is_relative_to(root):p.error('C7 output required')
 if a.mode=='select':
  if not a.inventory:p.error('selection needs inventory')
  manifest=make_manifest(root,strict_load(a.inventory.read_bytes()));out.mkdir(parents=True,exist_ok=False)
  write_json(out/'sources.json',manifest,exclusive=True);write_json(out/'selection.json',manifest['selection'],exclusive=True)
  print(json.dumps(dict(status='UNVERIFIED_SELECTION_ONLY',manifest_sha256=raw_sha((out/'sources.json').read_bytes()),selection=manifest['selection']),sort_keys=True));return 0
 if not a.authorize_native_preparation:
  print(json.dumps(dict(status='DISABLED_PENDING_NATIVE_PREPARATION_AUTHORIZATION',production_inputs_read=False,optimization_called=False),sort_keys=True));return 0
 if not all((a.manifest,a.manifest_sha256,a.campaign_sha256,a.guard_state)):p.error('preparation needs independently pinned manifest/campaign and freshguard')
 direct=DirectGuard(a);guard=Poll(direct)
 try:guard('pre_dispatch')
 except Stop as exc:
  print(json.dumps(dict(status='UNKNOWN',complete=False,stop_reason=str(exc),optimization_called=False),sort_keys=True));return 0
 os.sched_setaffinity(0,{0})
 if os.getpriority(os.PRIO_PROCESS,0)<10:os.nice(10-os.getpriority(os.PRIO_PROCESS,0))
 resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
 resource.setrlimit(resource.RLIMIT_FSIZE,(OUTPUT_LIMIT,OUTPUT_LIMIT))
 raw=a.manifest.read_bytes()
 if raw_sha(raw)!=a.manifest_sha256:raise ValueError('native sources manifest pin differs')
 manifest=strict_load(raw);out.mkdir(parents=True,exist_ok=False);guard.output=out
 hidden=out/'.inputs';blobs=hidden/'blobs';blobs.mkdir(parents=True);(hidden/'sources.json').write_bytes(raw)
 provenance={}
 def freeze(record,label):
  path=Path(record['path']).resolve();data=path.read_bytes();h=raw_sha(data)
  if h!=record['sha256']:raise ValueError('frozen producer/export/source hash mismatch:'+label)
  target=blobs/h
  if not target.exists():
   output_check(out,len(data)+1024**2);target.write_bytes(data)
  provenance[str(path)]=dict(sha256=h,snapshot=str(target.relative_to(out)),label=label)
  return data
 scratch=out/'.source-recheck';scratch.mkdir()
 hashes=code_hashes();hashes.update({name:raw_sha((REPO/name).read_bytes()) for name in EXTRA})
 for name,h in hashes.items():
  path=out/'code'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((REPO/name).read_bytes())
  if raw_sha(path.read_bytes())!=h:raise ValueError('code changed during snapshot')
 write_json(out/'launch.json',dict(code_sha256=hashes,runtime=runtime(),arguments={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()}),exclusive=True)
 exit_code=0
 try:
  candidates,records,old,receipt=load_sources(manifest,a.manifest_sha256,root,scratch,freeze,guard)
  authority_dir=Path(manifest['authority']['base_prepared']['path']).parent
  output_check(out,allocated(authority_dir)+4*1024**2)
  shutil.copytree(authority_dir,hidden/'source-authority-base');guard('post_authority_snapshot')
  document=build_prepared(candidates,records,a.manifest_sha256,old,guard,receipt)
  # Serialize/reparse so the frozen representation is checked as data.
  encoded=(json.dumps(document,sort_keys=True,indent=2)+'\n').encode();assert strict_load(encoded)==document
  output_check(out,len(encoded)+1024**2)
  guard('pre_native_prepared_publication');(out/'prepared.json').write_bytes(encoded);guard('post_native_prepared_publication')
  for i,candidate in enumerate(candidates):
   guard('pre_native_certificate_publication');output_check(out,128*1024)
   certificate=out/'certificates'/f'seed-{i:02d}-rank{len(candidate["terms"])}.json'
   write_json(certificate,candidate,exclusive=True)
   if raw_sha(certificate.read_bytes())!=records[i]['canonical_certificate_sha256']:raise ValueError('saved normalized source differs from fresh checked certificate')
  for name,h in hashes.items():
   if raw_sha((REPO/name).read_bytes())!=h:raise ValueError('code pin changed during preparation')
  for name,item in provenance.items():
   if raw_sha(Path(name).read_bytes())!=item['sha256']:raise ValueError('source/producer pin changed during preparation')
  guard('post_all_native_publications')
  result=dict(status='NATIVE_CORPUS_PREPARED_NO_OPTIMIZATION',complete=True,prepared_sha256=raw_sha(encoded),dictionary_size=document['dictionary_size'],rank=document['rank'],nullity=document['nullity'],
   parity_broken=document['parity_broken'],seed_weights=document['seed_weights'],old406_comparison=document['old406_comparison'],optimization_called=False)
 except Stop as exc:
  if (out/'prepared.json').exists():(out/'prepared.json').rename(hidden/'after-cutoff-prepared.json')
  if (out/'certificates').exists():(out/'certificates').rename(hidden/'after-cutoff-certificates')
  result=dict(status='UNKNOWN',complete=False,stop_reason=str(exc),after_cutoff=True,no_within_budget_claim=True,optimization_called=False)
 except Exception as exc:
  if (out/'prepared.json').exists():(out/'prepared.json').rename(hidden/'failed-prepared.json')
  if (out/'certificates').exists():(out/'certificates').rename(hidden/'failed-certificates')
  result=dict(status='FAILED_CLOSED',complete=False,error_type=type(exc).__name__,error=str(exc),optimization_called=False);exit_code=2
 result.update(runtime=runtime(),elapsed_seconds=time.monotonic()-direct.started,code_sha256=hashes)
 write_json(out/'provenance-index.json',provenance,exclusive=True)
 if result.get('complete'):
  try:guard('pre_final_native_result')
  except Stop as exc:
   if (out/'prepared.json').exists():(out/'prepared.json').rename(hidden/'after-cutoff-prepared.json')
   if (out/'certificates').exists():(out/'certificates').rename(hidden/'after-cutoff-certificates')
   result.update(status='UNKNOWN',complete=False,stop_reason=str(exc),after_cutoff=True,no_within_budget_claim=True)
 write_json(out/'result.json',result,exclusive=True)
 write_json(out/'checksums.json',{str(path.relative_to(out)):raw_sha(path.read_bytes()) for path in sorted(out.rglob('*')) if path.is_file()},exclusive=True)
 if result.get('complete'):
  try:
   for name,h in hashes.items():
    if raw_sha((REPO/name).read_bytes())!=h:raise Stop('code_pin_changed_at_final_barrier')
   guard('post_final_native_result')
  except Stop as exc:
   if (out/'prepared.json').exists():(out/'prepared.json').rename(hidden/'after-cutoff-prepared.json')
   if (out/'certificates').exists():(out/'certificates').rename(hidden/'after-cutoff-certificates')
   result.update(status='UNKNOWN',complete=False,stop_reason=str(exc),after_cutoff=True,no_within_budget_claim=True)
   write_json(out/'result.json',result)
   write_json(out/'checksums.json',{str(path.relative_to(out)):raw_sha(path.read_bytes()) for path in sorted(out.rglob('*')) if path.is_file() and path!=out/'checksums.json'})
 output_check(out)
 print(json.dumps(result,sort_keys=True));return exit_code


if __name__=='__main__':raise SystemExit(main())
