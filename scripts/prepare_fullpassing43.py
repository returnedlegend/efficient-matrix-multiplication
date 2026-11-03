#!/usr/bin/env python3
"""Prepare raw sources and lazy masks from the completed exact full scan."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mmsearch.compact_coset43 import digest
from mmsearch.compact_eight43 import factor_core,packed_tensor,opposite_pair_ranks
from mmsearch.sat_neighborhoods import factor_masks
from mmsearch.tensor import strassen_candidate
from mmsearch.verify import verify_candidate

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,sort_keys=True,indent=2);f.write('\n')
def packed(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(gzip.compress(json.dumps(v,sort_keys=True,separators=(',',':')).encode(),compresslevel=1,mtime=0))

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scan',type=Path,required=True);p.add_argument('--bulk-bundle',type=Path,required=True);p.add_argument('--bulk-results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True)
 scan=read(a.scan/'config.json');state=read(a.scan/'cursor.json');bounds=(a.scan/'all-bounds.bin').read_bytes();log=(a.scan/'sample.jsonl').read_bytes();rows=[json.loads(line) for line in log.splitlines()]
 if state['processed']!=981476 or state['next_sample']!=981476 or len(bounds)!=7*981476 or state['committed_bounds_bytes']!=len(bounds) or state['committed_log_bytes']!=len(log) or state['config_sha256']!=digest(scan):raise ValueError('full scan not complete/hash-bound')
 counts=Counter(bounds[6::7]);passing=sum(n for b,n in counts.items() if b<=7)
 if counts!=Counter({int(k):v for k,v in state['lower_bound_counts'].items()}) or passing!=len(rows) or passing!=21829:raise ValueError('full binary/pass log count mismatch')
 bm=read(a.bulk_bundle/'manifest.json')
 for name,h in bm['files'].items():
  if sha(a.bulk_bundle/name)!=h:raise ValueError('bulk frozen source changed')
 bplan=read(a.bulk_bundle/'plan.json');bcursor=read(a.bulk_results/'cursor.json');bsummary=read(a.bulk_results/'summary.json')
 if bsummary['status']!='LOCAL_PORTFOLIO_UNSAT' or bcursor['next_case']!=418 or not bcursor['terminal'] or read(a.bulk_results/'config.json')['launch_manifest_sha256']!=sha(a.bulk_bundle/'launch-manifest.json'):raise ValueError('all449 exact negatives not established')
 prior={}
 def add(item,path,kind):
  mask=sum(1<<i for i in item['indices']);key=(item['source_sha256'],mask)
  if key in prior:raise ValueError('duplicate prior source/mask proof')
  prior[key]=dict(source_sha256=key[0],mask_lo=mask&((1<<64)-1),mask_hi=mask>>64,target_local_products=7,residual_sha256=item['residual_sha256'],kind=kind,proof_path=str(path.resolve()),proof_sha256=sha(path))
 for case,event in zip(bplan['cases'],bcursor['results']):
  path=a.bulk_results/event['result_file'];result=read(path);core=read(a.bulk_bundle/case['core'])
  if event['case']!=case['id'] or sha(path)!=event['result_sha256'] or result['status']!='LOCAL_UNSAT' or not result['complete'] or result['core_sha256']!=digest(dict(core=core['core'],shape=core['shape'])):raise ValueError('prior CP7 result/source/core corruption')
  add(case,path,'EXACT_CP7_LOCAL_UNSAT')
 coverage=read(a.bulk_bundle/'coverage.json')
 for item in coverage['reused_complete_negatives']:
  path=a.bulk_bundle/item['copied_result'];v=read(path)
  if v['status']!='LOCAL_UNSAT' or not v['complete']:raise ValueError('prior micro incomplete')
  add(item,path,'EXACT_CP7_MICRO_LOCAL_UNSAT')
 for item in coverage['reused_complete_koszul_negatives']:
  path=a.bulk_bundle/item['copied_bound'];v=read(path)
  if not v['rejected'] or v['tensor_rank_lower_bound']<8 or v['target']!=7 or v['image_shape']!=item['shape']:raise ValueError('prior p2 certificate mismatch')
  add(item,path,'EXACT_KOSZUL_P2_LOWER8')
 if len(prior)!=449:raise ValueError('wrong prior coverage')
 sources={};sourcehash={};prefix=[0,244374,493314,749803,981476]
 for s in range(4):
  path=a.bulk_bundle/f'source-{s}.json';candidate=read(path);h=sha(path);checked=verify_candidate(candidate,random_trials=0)
  if h!=scan['inputs'][str(s)]['source_sha256'] or not checked['valid'] or checked['rank']!=93 or checked['exact_entries_checked']!=15625 or opposite_pair_ranks(factor_masks(candidate))!=[93]*3:raise ValueError('raw source provenance/control mismatch')
  dest=Path('sources')/f'source-{s}.json';destpath=a.output/dest;destpath.parent.mkdir(exist_ok=True);shutil.copy2(path,destpath);sources[f's{s}']=dict(path=str(dest),sha256=h);sourcehash[s]=h
 groups={};excluded=[];dims=Counter();newdims=Counter();seen=set();source_scatter=Counter();max_surplus=0
 for row in rows:
  ordinal=row['global_union_ordinal'];s=row['source'];mask=row['mask_lo']|(row['mask_hi']<<64);key=(sourcehash[s],mask)
  if key in seen or not prefix[s]<=ordinal<prefix[s+1] or mask.bit_count()!=8 or mask>>93:raise ValueError('full pass source/order/mask invalid')
  seen.add(key)
  if list(bounds[7*ordinal:7*ordinal+7])!=row['shape']+row['koszul_p1_matrix_ranks']+[row['tensor_rank_lower_bound']] or row['status']!='BOUND_PASSED_NOT_EXISTENCE':raise ValueError('pass metadata not exact binary record')
  d=max(row['shape']);dims[d]+=1;source_scatter[(s,d)]+=1;axis=max(range(3),key=lambda j:(row['shape'][j],-j));max_surplus=max(max_surplus,7-d)
  if key in prior:
   proof=prior.pop(key)
   if proof['residual_sha256']!=row['residual_sha256']:raise ValueError('prior exact source/mask residual changed')
   excluded.append(proof);continue
  case=dict(id=f'u{ordinal:06d}',global_union_ordinal=ordinal,mask_lo=row['mask_lo'],mask_hi=row['mask_hi'],shape=row['shape'],free_axis=axis,residual_sha256=row['residual_sha256'],native_p1_matrix_ranks=row['koszul_p1_matrix_ranks'],native_rank_lower_bound=row['tensor_rank_lower_bound'])
  groups.setdefault((s,d),[]).append(case);newdims[d]+=1
 if prior or len(excluded)!=449:raise ValueError('not all449 exact masks found')
 chunks=[];parts={}
 for (s,d),items in sorted(groups.items()):
  for number,start in enumerate(range(0,len(items),256)):
   selected=items[start:start+256];name=f's{s}-d{d}-{number:03d}';dest=Path('chunks')/(name+'.json.gz');packed(a.output/dest,selected)
   parts.setdefault(d,{}).setdefault(s,[]).append(dict(id=name,source_id=f's{s}',mode_rank=d,case_count=len(selected),plan=str(dest),plan_sha256=digest(selected),compressed_sha256=sha(a.output/dest)))
 for d in sorted(parts,reverse=True):
  number=0
  while any(number<len(v) for v in parts[d].values()):
   for s in range(4):
    values=parts[d].get(s,[])
    if number<len(values):chunks.append(values[number])
   number+=1
 plan=dict(sources=sources,chunks=chunks,case_count=sum(c['case_count'] for c in chunks),source_masks_only=True,decoder='fast_rank_d_or_complete_onecoset; reviewed_generic_surplus2_only_if_needed',mode_rank_counts=dict(newdims),unsupported_surplus_gt2=sum(n for d,n in newdims.items() if 7-d>2),generic_surplus2_cases=sum(n for d,n in newdims.items() if 7-d==2))
 write(a.output/'plan.json',plan);write(a.output/'excluded449.json',excluded)
 write(a.output/'SCATTER.json',dict(full_union_count=981476,p1_rank8_exclusions=959647,passing=21829,passing_mode_rank_counts=dict(dims),new_mode_rank_counts=dict(newdims),source_by_mode={f's{s}-d{d}':n for (s,d),n in source_scatter.items()},exact_prior_masks_excluded=449,new_cases=plan['case_count'],chunks=len(chunks),generic_surplus2_cases=plan['generic_surplus2_cases'],unsupported_surplus_gt2=plan['unsupported_surplus_gt2'],passing_is_existence=False))
 write(a.output/'INPUT-BINDINGS.json',dict(full_scan=str(a.scan.resolve()),files={str(p.resolve()):sha(p) for p in [a.scan/'config.json',a.scan/'cursor.json',a.scan/'all-bounds.bin',a.scan/'sample.jsonl',a.bulk_bundle/'manifest.json',a.bulk_results/'cursor.json',a.bulk_results/'summary.json']},prior_bulk_proofs='418actual completeCP7 +12micro +19p2; exact originalsource/mask/residual only'))
 # Tiny supported actual-image control: three selected Strassen terms, target3.
 small=strassen_candidate(2);terms=factor_masks(small);ids=[0,2,5];_,core,shape=factor_core(terms,ids);ambient=0
 for i in ids:ambient^=packed_tensor(terms[i],4)
 mask=sum(1<<i for i in ids);smallcase=dict(id='tiny-positive',mask_lo=mask,mask_hi=0,shape=shape,free_axis=0,residual_sha256=hashlib.sha256(ambient.to_bytes(8,'little')).hexdigest(),source_local_products=3,target_local_products=3)
 write(a.output/'small-source.json',small);packed(a.output/'small-chunk.json.gz',[smallcase]);write(a.output/'small-plan.json',dict(sources={'tiny':dict(path='small-source.json',sha256=sha(a.output/'small-source.json'))},chunks=[dict(id='tiny',source_id='tiny',case_count=1,plan='small-chunk.json.gz',plan_sha256=digest([smallcase]))]))
 shutil.copytree(a.bulk_bundle/'runtime',a.output/'runtime')
 for name in ['fullpassing43.py','forced_span43.py']:shutil.copy2(ROOT/'mmsearch'/name,a.output/'runtime/mmsearch'/name)
 shutil.copy2(ROOT/'scripts/campaign_fullpassing43.py',a.output/'runtime/campaign_fullpassing43.py');shutil.copy2(Path(__file__),a.output/'prepare_fullpassing43.py')
 for directory in sorted(a.output.rglob('__pycache__'),reverse=True):shutil.rmtree(directory)
 write(a.output/'launch-manifest.json',dict(files={str(p.relative_to(a.output)):sha(p) for p in a.output.rglob('*') if p.is_file()}))
 print(json.dumps(read(a.output/'SCATTER.json'),sort_keys=True))

if __name__=='__main__':main()
