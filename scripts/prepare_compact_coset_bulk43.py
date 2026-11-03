#!/usr/bin/env python3
"""Prepare sampled compact cases and exact prior-negative coverage; no decoding."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from collections import Counter

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mmsearch.compact_sat import compress_residual
from mmsearch.compact_eight43 import packed_tensor,opposite_pair_ranks
from mmsearch.sat_neighborhoods import factor_masks
from mmsearch.verify import verify_candidate
from mmsearch.koszul_p2 import koszul_p2_bounds

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prior-bundle',type=Path,required=True);p.add_argument('--prior-results',type=Path,required=True);p.add_argument('--sample',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();start=time.process_time();a.output.mkdir(exist_ok=False,parents=True)
 old=read(a.prior_bundle/'manifest.json')
 for name,h in old['files'].items():
  if sha(a.prior_bundle/name)!=h:raise ValueError('prior frozen input changed')
 priorplan=read(a.prior_bundle/'plan.json');summary=read(a.prior_results/'summary.json');cursor=read(a.prior_results/'cursor.json');prior={}
 if summary['status']!='LOCAL_PORTFOLIO_UNSAT' or cursor['next_case']!=12 or not cursor['terminal'] or read(a.prior_results/'config.json')['launch_manifest_sha256']!=sha(a.prior_bundle/'launch-manifest.json'):raise ValueError('prior complete negatives not established')
 for i,case in enumerate(priorplan['cases']):
  event=cursor['results'][i];resultpath=a.prior_results/event['result_file'];result=read(resultpath)
  if event['case']!=case['id'] or result['status']!='LOCAL_UNSAT' or not result['complete'] or event['result_sha256']!=sha(resultpath):raise ValueError('corrupt/incomplete prior negative')
  core=read(a.prior_bundle/case['core']);key=(sha(a.prior_bundle/case['source']),tuple(core['source_indices']))
  if result['core_sha256']!=digest(dict(shape=core['shape'],core=core['core'])):raise ValueError('prior core-result binding mismatch')
  prior[key]=dict(case=case,core=core,result=result,result_sha256=sha(resultpath),result_file=event['result_file'])
 config=read(a.sample/'config.json');state=read(a.sample/'cursor.json');raw=(a.sample/'sample.jsonl').read_bytes();rows=[json.loads(line) for line in raw.splitlines()]
 if len(rows)!=20000 or state['next_sample']!=20000 or state['committed_log_bytes']!=len(raw) or [r['sample_index'] for r in rows]!=list(range(20000)):raise ValueError('sample cursor/log corrupt')
 sources=[];terms=[];sourcehashes=[]
 for s in range(4):
  src=a.prior_bundle/f'source-{s}.json';source=read(src);h=sha(src)
  if h!=config['inputs'][str(s)]['source_sha256']:raise ValueError('sample/source mismatch')
  verified=verify_candidate(source,random_trials=0);masks=factor_masks(source)
  if not verified['valid'] or verified['rank']!=93 or verified['exact_entries_checked']!=15625 or opposite_pair_ranks(masks)!=[93,93,93]:raise ValueError('source/pair-rank control')
  sources.append(source);terms.append(masks);sourcehashes.append(h);shutil.copy2(src,a.output/f'source-{s}.json')
 p2bundle=Path(priorplan['prior_bundle'])
 if sha(p2bundle/'manifest.json')!=priorplan['prior_manifest_sha256']:raise ValueError('prior p2 bundle changed')
 p2summary=read(p2bundle/'portfolio-summary.json');p2prior={r['sample_index']:r['bound'] for r in p2summary['p2_rejections_before_selection']}
 cases=[];coverage=[];reused=[];reused_p2=[];unsupported=[];ambient_groups={};dimcounts=Counter()
 for row in rows:
  if row['tensor_rank_lower_bound']>7:continue
  if row['status']!='BOUND_PASSED_NOT_EXISTENCE':raise ValueError('sample UNKNOWN cannot be promoted')
  s=row['source'];ids=row['indices'];bases,core,shape,_=compress_residual(sources[s],ids);ambient=0
  for j in ids:ambient^=packed_tensor(terms[s][j])
  if hashlib.sha256(ambient.to_bytes(1954,'little')).hexdigest()!=row['residual_sha256'] or shape!=row['shape']:raise ValueError('sample/core exact source binding')
  axis=max(range(3),key=lambda a:(shape[a],-a));d=shape[axis];dimcounts[d]+=1
  item=dict(sample_index=row['sample_index'],source=s,source_sha256=sourcehashes[s],indices=ids,shape=shape,free_axis=axis,mode_rank=d,residual_sha256=row['residual_sha256'])
  ambient_groups.setdefault(row['residual_sha256'],[]).append(row['sample_index'])
  key=(sourcehashes[s],tuple(ids));data=dict(shape=shape,core=core,image_bases=[b.vectors for b in bases],source_indices=ids,outside_indices=[j for j in range(93) if j not in ids],expanded_entries_checked=15625)
  if key in prior:
   old=prior.pop(key)
   if any(data[k]!=old['core'][k] for k in ['shape','core','image_bases','source_indices','outside_indices']):raise ValueError('prior case changed image model')
   dest=Path('reused')/(old['case']['id']+'.result.json');write(a.output/dest,old['result'])
   item.update(status='REUSED_EXACT_LOCAL_UNSAT',prior_case=old['case']['id'],prior_result_sha256=old['result_sha256'],copied_result=str(dest));reused.append(item)
  elif row['sample_index'] in p2prior:
   oldbound=p2prior.pop(row['sample_index']);checked=koszul_p2_bounds(core,shape,target=7)
   if not checked['rejected'] or {k:v for k,v in checked.items() if k!='elapsed_seconds'}!={k:v for k,v in oldbound.items() if k!='elapsed_seconds'}:raise ValueError('prior p2 matrix/core witness changed')
   dest=Path('reused')/f'p2-sample-{row["sample_index"]:05d}.json';write(a.output/dest,oldbound)
   item.update(status='REUSED_EXACT_KOSZUL_P2_NEGATIVE',copied_bound=str(dest),tensor_rank_lower_bound=oldbound['tensor_rank_lower_bound']);reused_p2.append(item)
  elif 7>d+1:
   item.update(status='UNKNOWN_UNSUPPORTED_SURPLUS_GE2',surplus=7-d);unsupported.append(item)
  else:
   number=len(cases);dest=Path('cases')/f'case-{number:03d}.core.json';write(a.output/dest,data)
   opposite=[shape[j] for j in range(3) if j!=axis];allpoints=((1<<opposite[0])-1)*((1<<opposite[1])-1)
   case=dict(item,id=f'sample-{row["sample_index"]:05d}',source=f'source-{s}.json',source_products=93,source_local_products=8,target_local_products=7,core=str(dest),all_pair_points=allpoints,
    algorithm='fast_inside_rankone' if d==7 else 'complete_one_coset',planned_checks=(1<<d)-1 if d==7 else allpoints)
   if case['planned_checks']>3969:raise ValueError('query resource estimate too large')
   cases.append(case);item.update(status='PLANNED_COMPLETE_QUERY',case=case['id'])
  coverage.append(item)
 if prior or p2prior or len(coverage)!=449 or len(reused)!=12 or len(reused_p2)!=19:raise ValueError('coverage/prior identity count mismatch')
 write(a.output/'plan.json',dict(cases=cases,scope='Sampled exact residuals only; each proposed query is complete for its stated bound.'))
 write(a.output/'coverage.json',dict(total_sample=20000,rank_bound_passes=449,planned_new_queries=len(cases),reused_complete_negatives=reused,reused_complete_koszul_negatives=reused_p2,unsupported=unsupported,coverage=coverage,
  mode_rank_counts=dict(dimcounts),duplicate_ambient_groups=[v for v in ambient_groups.values() if len(v)>1],n5_decoder_queries_during_preparation=0))
 write(a.output/'input-bindings.json',dict(prior_bundle=str(a.prior_bundle.resolve()),prior_manifest_sha256=sha(a.prior_bundle/'manifest.json'),prior_results=str(a.prior_results.resolve()),prior_cursor_sha256=sha(a.prior_results/'cursor.json'),prior_summary_sha256=sha(a.prior_results/'summary.json'),sample_log_sha256=sha(a.sample/'sample.jsonl'),sample_config_sha256=sha(a.sample/'config.json'),preparation_CPU_seconds=time.process_time()-start))
 shutil.copytree(a.prior_bundle/'runtime',a.output/'runtime');shutil.copy2(ROOT/'mmsearch/compact_coset_fast43.py',a.output/'runtime/mmsearch/compact_coset_fast43.py');shutil.copy2(ROOT/'scripts/campaign_compact_coset_bulk43.py',a.output/'runtime/campaign_compact_coset_bulk43.py')
 for name in ['small-source.json','small-core.json','small-plan.json']:shutil.copy2(a.prior_bundle/name,a.output/name)
 shutil.copy2(Path(__file__),a.output/'prepare_compact_coset_bulk43.py');(a.output/'test_compact_coset_fast43.py').write_text((ROOT/'tests/test_compact_coset_fast43.py').read_text().replace('from tests.test_compact_coset43 import brute_tiny','from oracle.test_compact_coset43 import brute_tiny'))
 (a.output/'oracle').mkdir();shutil.copy2(ROOT/'tests/test_compact_coset43.py',a.output/'oracle/test_compact_coset43.py')
 for directory in sorted(a.output.rglob('__pycache__'),reverse=True):shutil.rmtree(directory)
 write(a.output/'launch-manifest.json',dict(files={str(path.relative_to(a.output)):sha(path) for path in a.output.rglob('*') if path.is_file()}))
 print(json.dumps(dict(coverage=len(coverage),new=len(cases),reused=len(reused),reused_p2=len(reused_p2),unsupported=len(unsupported),dimensions=dict(dimcounts),CPU=time.process_time()-start)))

if __name__=='__main__':main()
