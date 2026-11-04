#!/usr/bin/env python3
"""Guarded exact small-component minimization in selected even flip-span cosets."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import resource
import sys
import time
import importlib.util

REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from mmsearch.tensor_code7 import strict_load,second_check,xor_columns,digest
from mmsearch.tensor_code7_extension import raw_sha
from mmsearch.tensor_code7_native_corpus import PREPARED_SCHEMA,load_root_pinned_native,candidate_from_atoms
from mmsearch.tensor_code7_sparse_cycles import validate_catalogue
from mmsearch.tensor_code7_even_components import minimize_components,select_starts
from mmsearch.tensor_code7_component_sat import minimize_local
from scripts.tensor_code7_sparse_cycle_run import save_negative,quarantine_candidates
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import verify_bytes
from scripts.tensor_code7 import Stop,runtime,write_json
from scripts.tensor_code7_extension import code_hashes
from scripts.tensor_code7_extension_select import DirectGuard
from scripts.tensor_code7_native_corpus import Poll,output_check,OUTPUT_LIMIT

SCHEMA='tensor_code7.even_components_run.v1'
EXTRA=('mmsearch/tensor_code7_sparse_cycles.py','scripts/tensor_code7_sparse_cycle_run.py',
 'mmsearch/tensor_code7_even_components.py','mmsearch/tensor_code7_component_sat.py',
 'scripts/tensor_code7_even_components.py','tests/test_tensor_code7_even_components.py',
 'tests/test_tensor_code7_even_components_run.py','tests/test_tensor_code7_component_sat.py','research/tensor_code7_even_components.md')

def dependency_hashes():
 paths=list((REPO/'.xor-deps').glob('*.so'))+list((REPO/'.xor-deps/pycryptosat.libs').glob('*'))
 for name in ('pysat','pysat.card','pysat.formula','pysat._fileio','pysat._utils','pycard'):
  paths.append(Path(importlib.util.find_spec(name).origin))
 return {str(p):raw_sha(p.read_bytes()) for p in sorted(set(paths))}

def runtime_hashes():
 hashes=code_hashes();hashes.update({name:raw_sha((REPO/name).read_bytes()) for name in EXTRA})
 return hashes

def run_pipeline(document,root,guard,args,prepared_sha256):
 atoms=[tuple(a) for a in document['atoms']];n=document['dimension'];saved=[];report=None
 def cancelled():
  try:guard();return None
  except Stop as exc:return str(exc)
 def checkpoint(value):
  output_check(root,1024**2)
  hidden=root/'.raw-components';hidden.mkdir(exist_ok=True)
  write_json(hidden/'checkpoint.json',dict(status='UNKNOWN',complete=False,no_within_budget_claim=True,raw=value))
  if 'components' in value:write_json(hidden/'component-prefix.json',dict(status='UNKNOWN',complete=False,no_within_budget_claim=True,raw=value))
  if 'solver_component_calls' in value:write_json(hidden/f'solver-call-{value["solver_component_calls"]:02d}.json',dict(status='UNKNOWN',complete=False,no_within_budget_claim=True,raw=value))
 try:
  guard('pre_catalogue');raw=args.catalogue.read_bytes()
  if raw_sha(raw)!=args.catalogue_sha256:raise ValueError('catalogue raw pin differs')
  catalogue=strict_load(raw);masks=validate_catalogue(catalogue,atoms,n)
  if not catalogue['complete'] or any(z.bit_count()!=4 for z in masks):raise ValueError('complete flip4 catalogue required')
  guard('post_catalogue_verification')
  starts=select_starts([int(x,16) for x in document['seed_states_hex']],[int(z,16) for z in document['kernel_hex']],max_starts=16,ceiling=98)
  columns=[int(x,16) for x in document['columns_hex']];target=int(document['target_hex'],16)
  if any(xor_columns(columns,int(t['state_hex'],16))!=target for t in starts):raise ValueError('even start syndrome differs')
  write_json(root/'starts.json',dict(starts=starts,odd_basis_weights=[int(z,16).bit_count() for z in document['kernel_hex'] if int(z,16).bit_count()%2]),exclusive=True)
  def found(item):
   record=save_negative(root,document,dict(item,prepared_sha256=prepared_sha256,code_sha256=args.code_sha256),guard,len(saved),args.target_weight)
   saved.append(record);return True
  guard('pre_seed_scan');write_json(root/'scan-dispatch.json',dict(optimization_started=True,prepared_sha256=prepared_sha256,catalogue_sha256=args.catalogue_sha256),exclusive=True)
  solver_cpu=0.;solver_calls=0
  def large_solver(local,basis,mask,ci,si):
   nonlocal solver_cpu,solver_calls
   guard('pre_local_solver')
   if solver_calls>=21 or solver_cpu>=59:
    return dict(status='UNKNOWN',complete=False,lower_bound=local.bit_count()%2,upper_bound=local.bit_count(),minimizer_hex=hex(local),stop_reason='portfolio solver budget')
   solver_calls+=1
   answer=minimize_local(local,basis,mask,seconds=min(5,59-solver_cpu),cancelled=cancelled)
   solver_cpu+=answer['cpu_seconds'];checkpoint(dict(status='UNKNOWN',complete=False,solver_cpu_seconds=solver_cpu,solver_component_calls=solver_calls,last=answer))
   guard('post_local_solver')
   if solver_cpu>60:raise Stop('solver_cpu_budget')
   return answer
  report=minimize_components([int(t['state_hex'],16) for t in starts],masks,args.max_rank,args.max_states,cancelled,checkpoint,found,args.target_weight,large_solver)
  report.update(solver_cpu_seconds=solver_cpu,solver_component_calls=solver_calls)
  if any(xor_columns(columns,int(x,16))!=target or int(x,16).bit_count()%2 for x in report['states_hex']):raise ValueError('composed state full15625 syndrome/parity differs')
  if report['complete'] and report['lower_bounds']!=report['weights']:raise ValueError('complete component bounds do not compose')
  guard('post_component_search');write_json(root/'components.json',report,exclusive=True);guard('post_components_publication')
 except Exception as exc:
  checkpoint(dict(status='UNKNOWN',complete=False,stop_reason=str(exc),raw_report=report,saved=saved))
  quarantine_candidates(root,exc);raise
 return dict(status='FROZEN_DOUBLE_VERIFIED_TARGET' if saved else report['status'],complete=bool(saved) or report['complete'],winner=bool(saved),saved=saved,optimization_called=True,component_report=report,scope='Only up to16 deterministic even starting cosets and computed support components of the pinned flip4 span; no full-code/global optimum claim.')


def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--prepared',type=Path);p.add_argument('--prepared-sha256');p.add_argument('--sources',type=Path);p.add_argument('--sources-sha256')
 p.add_argument('--campaign-dir',type=Path,required=True);p.add_argument('--campaign-sha256');p.add_argument('--guard-state',type=Path)
 p.add_argument('--hard-utc',default='2026-11-03T19:24:17Z');p.add_argument('--seconds',type=float,default=120);p.add_argument('--outdir',type=Path,required=True)
 p.add_argument('--catalogue',type=Path);p.add_argument('--catalogue-sha256')
 p.add_argument('--max-rank',type=int,default=20);p.add_argument('--max-states',type=int,default=10000000)
 p.add_argument('--authorize-component-search',action='store_true')
 p.add_argument('--qa-receipt',type=Path);p.add_argument('--qa-sha256');p.add_argument('--inspect-runtime',action='store_true');a=p.parse_args(argv);a.target_weight=92
 if a.inspect_runtime:
  hashes=runtime_hashes();print(json.dumps(dict(code_sha256=hashes,runtime_closure_sha256=digest(hashes),dependency_closure_sha256=digest(dependency_hashes()),production_inputs_read=False,optimization_called=False),sort_keys=True));return 0
 if not a.authorize_component_search:
  print(json.dumps(dict(status='DISABLED',production_inputs_read=False,optimization_called=False),sort_keys=True));return 0
 for key in ('prepared','prepared_sha256','sources','sources_sha256','campaign_sha256','guard_state','catalogue','catalogue_sha256'):
  if getattr(a,key) is None:p.error('pinned inputs/freshguard required: '+key)
 if not 1<=a.max_rank<=20 or not 1<=a.max_states<=10000000 or not 0<a.seconds<=120:p.error('reviewed scope caps exceeded')
 if a.authorize_component_search and (not a.qa_receipt or not a.qa_sha256):p.error('seed optimization requires independent QA receipt/raw pin')
 direct=DirectGuard(a);guard=Poll(direct)
 try:guard('pre_dispatch')
 except Stop as exc:
  print(json.dumps(dict(status='UNKNOWN',complete=False,stop_reason=str(exc),optimization_called=False),sort_keys=True));return 0
 hashes=runtime_hashes();dependencies=dependency_hashes()
 if a.authorize_component_search:
  qa_raw=a.qa_receipt.read_bytes()
  if raw_sha(qa_raw)!=a.qa_sha256:raise ValueError('QA receipt raw pin differs')
  qa=strict_load(qa_raw)
  expected=dict(status='PASS',prepared_sha256=a.prepared_sha256,sources_sha256=a.sources_sha256,
   component_core_sha256=raw_sha((REPO/'mmsearch/tensor_code7_even_components.py').read_bytes()),catalogue_sha256=a.catalogue_sha256,runtime_sha256=raw_sha(Path(__file__).read_bytes()),runtime_closure_sha256=digest(hashes),dependency_closure_sha256=digest(dependency_hashes()))
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
 for name,h in dependencies.items():
  raw=Path(name).read_bytes()
  if raw_sha(raw)!=h:raise ValueError('dependency changed during snapshot')
  target=root/'.dependencies'/h;target.parent.mkdir(exist_ok=True);output_check(root,len(raw)+1024**2);target.write_bytes(raw)
 write_json(root/'dependency-pins.json',dependencies,exclusive=True)
 a.code_sha256=hashes
 def bound_guard(stage='loop'):
  guard(stage)
  if stage in ('pre_negative_publication','pre_seed_scan','pre_final_sparse_receipt','post_final_sparse_receipt'):
   for name,h in dict(hashes,**dependencies).items():
    if raw_sha((REPO/name).read_bytes())!=h:raise Stop('code_pin_changed:'+stage)
   if raw_sha(a.prepared.read_bytes())!=a.prepared_sha256 or raw_sha(a.sources.read_bytes())!=a.sources_sha256 or raw_sha(a.catalogue.read_bytes())!=a.catalogue_sha256:raise Stop('input_pin_changed:'+stage)
   guard(stage)
 exit_code=0
 try:
  scratch=root/'.source-recheck';scratch.mkdir()
  document=load_root_pinned_native(a.prepared,a.prepared_sha256,a.sources,a.sources_sha256,campaign,scratch,freeze,bound_guard)
  (hidden/'prepared.json').write_bytes(a.prepared.read_bytes());(hidden/'sources.json').write_bytes(a.sources.read_bytes());(hidden/'catalogue.json').write_bytes(a.catalogue.read_bytes())
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
