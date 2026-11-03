#!/usr/bin/env python3
"""Freeze at most twelve sampled exact compact 8-to-7 cases; no n5 solving."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mmsearch.compact_sat import compress_residual
from mmsearch.compact_eight43 import canonical_axis_form,expand_core,factor_core,packed_tensor
from mmsearch.koszul import koszul_bounds
from mmsearch.koszul_p2 import koszul_p2_bounds
from mmsearch.sat_neighborhoods import factor_masks
from mmsearch.xor_sat import build_xor_cnf,validate_model
from mmsearch.sat import decode_model
from mmsearch.tensor import naive_candidate
from mmsearch.verify import verify_candidate

def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(value):return sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode())
def write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')

def propagate(problem):
 values={abs(v):v>0 for v in problem['phases']}
 changed=True
 while changed:
  changed=False
  for row in problem['clauses']:
   if any(abs(v) in values and values[abs(v)]==(v>0) for v in row):continue
   unknown=[v for v in row if abs(v) not in values]
   if not unknown:raise ValueError('fixed source CNF contradiction')
   if len(unknown)==1:values[abs(unknown[0])]=unknown[0]>0;changed=True
  for row,rhs in problem['xors']:
   unknown=[v for v in row if v not in values];parity=bool(sum(values[v] for v in row if v in values)%2)
   if not unknown and parity!=rhs:raise ValueError('fixed source XOR contradiction')
   if len(unknown)==1:values[unknown[0]]=bool(parity^rhs);changed=True
 if len(values)!=problem['nv']:raise ValueError('incomplete source assignment')
 model=[i if values[i] else -i for i in range(1,problem['nv']+1)]
 validate_model(problem,model);checked=verify_candidate(decode_model(problem,model),random_trials=0)
 if not checked['valid'] or checked['rank']!=problem['metadata']['rank']:raise ValueError('source control failed')
 return model,checked

def make_case(out,source,row,caseid,small=False):
 ids=row['indices'];bases,core,shape,masks=compress_residual(source,ids)
 ambient=0
 for i in ids:ambient^=packed_tensor(masks[i],source['dimension']**2)
 if expand_core(core,shape,[b.vectors for b in bases],source['dimension']**2)!=ambient:raise AssertionError('image-core expansion')
 if not small and sha(ambient.to_bytes(1954,'little'))!=row['residual_sha256']:raise ValueError('sample/source ambient binding mismatch')
 p1=koszul_bounds(core,shape,target=7);p2=koszul_p2_bounds(core,shape,target=7)
 if p1['rejected'] or p2['rejected']:raise ValueError('selected Koszul negative')
 target=build_xor_cnf(source,rank=len(source['terms'])-1,active_terms=ids[:-1],drop_term=ids[-1],symmetry='none')
 padded=copy.deepcopy(source);padded['terms'].append({a:[0]*source['dimension']**2 for a in ['u','v','w']})
 control=build_xor_cnf(padded,rank=len(source['terms']),active_terms=ids,drop_term=len(source['terms']),symmetry='none')
 control['clauses'] += [[v] for v in control['phases']];control['metadata']['clauses']=len(control['clauses'])
 model,verified=propagate(control)
 directory=out/caseid
 for name,value in [('target.json',target),('control.json',control),('control.model.json',model),('control.verification.json',verified),
  ('core.json',dict(shape=shape,core=core,image_bases=[b.vectors for b in bases],source_indices=ids,
   outside_indices=[i for i in range(len(source['terms'])) if i not in ids],expanded_entries_checked=source['dimension']**6,p1=p1,p2=p2))]:write(directory/name,value)
 return dict(row,id=caseid,target=str((directory/'target.json').relative_to(out)),control=str((directory/'control.json').relative_to(out)),
  control_model=str((directory/'control.model.json').relative_to(out)),target_formula_sha256=digest({k:target[k] for k in ['nv','clauses','xors']}),
  shape=shape,source_local_products=8,target_local_products=7,global_target=7 if small else 92,
  target_variables=target['nv'],target_CNF=len(target['clauses']),target_XOR=len(target['xors']),
  control_global_products=8 if small else 93,compressed_sha256=digest(dict(core=core,shape=shape)),
  axis_permutation_core_sha256=canonical_axis_form(core,shape)[2])

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inventory',type=Path,required=True);p.add_argument('--sample',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 started=time.process_time();a.output.mkdir(parents=True,exist_ok=False)
 rows=[json.loads(line) for line in (a.sample/'sample.jsonl').read_text().splitlines()]
 cursor=json.loads((a.sample/'cursor.json').read_bytes());config=json.loads((a.sample/'config.json').read_bytes())
 if len(rows)!=20000 or cursor['next_sample']!=20000 or [r['sample_index'] for r in rows]!=list(range(20000)):raise ValueError('incomplete/corrupt sample')
 restart=json.loads((a.sample/'restart-control.json').read_bytes())
 if sha((a.sample/'sample.jsonl').read_bytes()[:restart['committed_prefix_bytes']])!=restart['committed_prefix_sha256']:raise ValueError('restart prefix mismatch')
 sources=[json.loads((a.inventory/f'source-{s}.json').read_bytes()) for s in range(4)]
 for s in range(4):
  if sha((a.inventory/f'source-{s}.json').read_bytes())!=config['inputs'][str(s)]['source_sha256']:raise ValueError('source/sample checksum mismatch')
 if cursor['committed_log_bytes']!=(a.sample/'sample.jsonl').stat().st_size:raise ValueError('uncommitted sample tail')
 # Independent Python validation of native rejection and pass records on real inputs.
 controls=[]
 for row in rows[::313]:
  _,core,shape=factor_core(factor_masks(sources[row['source']]),row['indices']);bound=koszul_bounds(core,shape,target=7)
  if shape!=row['shape'] or bound['tensor_rank_lower_bound']!=row['tensor_rank_lower_bound'] or [b['matrix_rank'] for b in bound['bounds']]!=row['koszul_p1_matrix_ranks']:raise ValueError('native/Python differential mismatch')
  controls.append(dict(sample_index=row['sample_index'],status='PASS'))
 candidates={s:sorted([r for r in rows if r['source']==s and r['tensor_rank_lower_bound']<=7],key=lambda r:(math.prod(r['shape']),sum(r['shape']),r['shape'],r['indices'])) for s in range(4)}
 selected=[];seen_ambient=set();seen_core=set();seen_axis=set();positions=[0]*4;p2_rejected=[];deduplicated=[]
 while len(selected)<12:
  progress=False
  for s in range(4):
   while positions[s]<len(candidates[s]):
    row=candidates[s][positions[s]];positions[s]+=1
    bases,core,shape,_=compress_residual(sources[s],row['indices']);corehash=digest(dict(shape=shape,core=core));axishash=canonical_axis_form(core,shape)[2]
    if row['residual_sha256'] in seen_ambient or corehash in seen_core or axishash in seen_axis:deduplicated.append(row['sample_index']);continue
    bound=koszul_p2_bounds(core,shape,target=7)
    if bound['rejected']:p2_rejected.append(dict(sample_index=row['sample_index'],bound=bound));continue
    selected.append(row);seen_ambient.add(row['residual_sha256']);seen_core.add(corehash);seen_axis.add(axishash);progress=True;break
   if len(selected)==12:break
  if not progress:break
 if len(selected)!=12:raise ValueError('fewer than twelve distinct passing samples')
 cases=[make_case(a.output,sources[r['source']],r,f'portfolio/case-{i:02d}') for i,r in enumerate(selected)]
 for i,case in enumerate(cases):case['id']=f'case-{i:02d}'
 # Small real matrix multiplication, arbitrary rank-seven SAT target; fixed rank-eight positive control.
 small=make_case(a.output/'planted-eight-to-seven',naive_candidate(2),dict(indices=list(range(8))), 'case-00',small=True)
 for key in ['target','control','control_model']:small[key]='planted-eight-to-seven/'+small[key]
 write(a.output/'planted-eight-to-seven/portfolio-summary.json',dict(cases=[small]))
 write(a.output/'portfolio-summary.json',dict(format='sampled-eight-to-seven-v1',cases=cases,case_count=len(cases),target_SAT_queries=0,
  sample_count=len(rows),sample_passes=sum(r['tensor_rank_lower_bound']<=7 for r in rows),source_counts=[sum(c['source']==s for c in cases) for s in range(4)],
  p2_rejections_before_selection=p2_rejected,deduplicated_sample_indices=deduplicated,preparation_CPU_seconds=time.process_time()-started,
  scope='Only twelve fixed-outside eight-term residuals; no old-six negative transfer or general GL-isomorphism claim.'))
 write(a.output/'native-differential-controls.json',controls)
 shutil.copy2(a.inventory/'sources.json',a.output/'sources.json')
 for s in range(4):shutil.copy2(a.inventory/f'source-{s}.json',a.output/f'source-{s}.json')
 shutil.copytree(a.inventory/'runtime',a.output/'runtime');shutil.copytree(a.inventory/'deps',a.output/'deps')
 worker=(a.output/'runtime/repair_worker.py').read_text().replace('planted-six-to-five','planted-eight-to-seven').replace('known six-product','known eight-product').replace('fixed-outside six-term','fixed-outside eight-term').replace('target5_queries','target7_queries').replace('rank-five bounds','rank-seven bounds')
 (a.output/'runtime/repair_worker.py').chmod(0o644);(a.output/'runtime/repair_worker.py').write_text(worker)
 for name in ['compact_eight43.py','koszul_p2.py']:shutil.copy2(ROOT/'mmsearch'/name,a.output/'runtime/mmsearch'/name)
 shutil.copy2(Path(__file__),a.output/'prepare_compact_eight43.py')
 write(a.output/'input-bindings.json',dict(inventory=str(a.inventory.resolve()),sample=str(a.sample.resolve()),
  files={str(path.resolve()):sha(path.read_bytes()) for path in [a.inventory/'manifest.json',a.inventory/'sources.json',a.sample/'config.json',a.sample/'cursor.json',a.sample/'sample.jsonl']},
  config=config,restart_prefix_verified=True,actual_source_controls=12,n5_target_solver_calls=0))
 files={str(path.relative_to(a.output)):sha(path.read_bytes()) for path in a.output.rglob('*') if path.is_file() and '__pycache__' not in path.parts}
 write(a.output/'launch-manifest.json',dict(files=files))
 print(json.dumps(dict(selected=len(cases),sources=[c['source'] for c in cases],shapes=[c['shape'] for c in cases],p2_rejected=len(p2_rejected),CPU=time.process_time()-started)))

if __name__=='__main__':main()
