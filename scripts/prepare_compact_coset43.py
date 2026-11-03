#!/usr/bin/env python3
"""Freeze compact one-coset inputs without making n5 decoder queries."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mmsearch.compact_sat import compress_residual
from mmsearch.recombine import encode
from mmsearch.sat_neighborhoods import factor_masks
from mmsearch.tensor import strassen_candidate
from mmsearch.verify import verify_candidate

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--eight-bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True)
 old=json.loads((a.eight_bundle/'manifest.json').read_bytes())
 for name,h in old['files'].items():
  if sha(a.eight_bundle/name)!=h:raise ValueError('old frozen compact8 input changed')
 cases=[]
 for s in range(4):shutil.copy2(a.eight_bundle/f'source-{s}.json',a.output/f'source-{s}.json')
 for i,prior in enumerate(json.loads((a.eight_bundle/'portfolio-summary.json').read_bytes())['cases']):
  corefile=Path(prior['target']).parent/'core.json';data=json.loads((a.eight_bundle/corefile).read_bytes());shape=data['shape'];axis=max(range(3),key=lambda j:(shape[j],-j));d=shape[axis]
  if d not in (6,7):raise ValueError('unexpected shape boundary')
  opposite=[shape[j] for j in range(3) if j!=axis];points=((1<<opposite[0])-1)*((1<<opposite[1])-1)
  if points>3969:raise ValueError('unexpected model size')
  dest=Path('cases')/f'case-{i:02d}.core.json';write(a.output/dest,data)
  cases.append(dict(id=f'case-{i:02d}',source=f'source-{prior["source"]}.json',source_products=93,source_local_products=8,
   target_local_products=7,core=str(dest),free_axis=axis,mode_rank=d,all_pair_points=points,prior_formula_sha256=prior['target_formula_sha256']))
 write(a.output/'plan.json',dict(cases=cases,prior_bundle=str(a.eight_bundle.resolve()),prior_manifest_sha256=sha(a.eight_bundle/'manifest.json'),n5_target_queries_during_preparation=0))
 # Tiny end-to-end supported control: split one Strassen product, then repair2→1.
 original=factor_masks(strassen_candidate(2));u,v,w=original[0];left=1 if w!=1 else 2
 split=[(u,v,left),(u,v,w^left)];source=encode(split+original[1:],2);checked=verify_candidate(source,random_trials=0)
 if not checked['valid'] or checked['rank']!=8 or checked['exact_entries_checked']!=64:raise ValueError('small source')
 ids=[factor_masks(source).index(term) for term in split]
 bases,core,shape,_=compress_residual(source,ids);write(a.output/'small-source.json',source)
 write(a.output/'small-core.json',dict(core=core,shape=shape,image_bases=[b.vectors for b in bases],source_indices=ids,outside_indices=[i for i in range(8) if i not in ids]))
 write(a.output/'small-plan.json',dict(cases=[dict(id='small-split-strassen',source='small-source.json',source_products=8,source_local_products=2,target_local_products=1,core='small-core.json',free_axis=0)]))
 shutil.copytree(a.eight_bundle/'runtime',a.output/'runtime')
 shutil.copy2(ROOT/'mmsearch/compact_coset43.py',a.output/'runtime/mmsearch/compact_coset43.py')
 shutil.copy2(ROOT/'scripts/campaign_compact_coset43.py',a.output/'runtime/campaign_compact_coset43.py')
 shutil.copy2(Path(__file__),a.output/'prepare_compact_coset43.py');shutil.copy2(ROOT/'tests/test_compact_coset43.py',a.output/'test_compact_coset43.py')
 for directory in sorted(a.output.rglob('__pycache__'),reverse=True):shutil.rmtree(directory)
 write(a.output/'launch-manifest.json',dict(files={str(p.relative_to(a.output)):sha(p) for p in a.output.rglob('*') if p.is_file()}))
 print(json.dumps(dict(cases=len(cases),sizes=[c['all_pair_points'] for c in cases],n5_queries=0)))

if __name__=='__main__':main()
