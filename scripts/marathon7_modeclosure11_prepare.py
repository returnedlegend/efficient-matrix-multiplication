#!/usr/bin/env python3
"""Bounded metadata-first MODE-CLOSURE11 census; no decomposition calls."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import resource
import signal
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,read,sha
from scripts.marathon7_local12_prepare import parents,SEED
from mmsearch.marathon7_modeclosure11 import factor_image_closure
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.marathon7_local import SourceCache
from mmsearch.compact_sat import BinaryBasis
from mmsearch.compact_coset43 import pair_column
from mmsearch.recombine import digest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',type=Path,required=True);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();started=time.monotonic()
    resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(120,121))
    parent=a.parent.resolve();c=a.campaign.resolve();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    guard=CampaignGuard(120,'2026-11-03T19:24:17Z',campaign_dir=c,guard_state=c/'operations-v3/state.json');signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    def barrier(label):
        guard.check(label)
        if sum(p.stat().st_size for p in out.rglob('*') if p.is_file())+1024**2>32*1024**2:raise RuntimeError('32MiB output cap/reserve')
    rows=[list(map(int,line.split())) for line in gzip.decompress((parent/'survivors.tsv.gz').read_bytes()).decode().splitlines()]
    if len(rows)!=111605:raise ValueError('parent catalogue scope differs')
    selected=parents(rows);plan=dict(seed=SEED,parents=selected,parent=str(parent),parent_manifest_sha256=sha(parent/'manifest.json'),catalog_sha256=sha(parent/'survivors.tsv.gz'),
        source_sha256={str(s):sha(parent/f'source-{s}.json') for s in range(4)},limits=dict(parents=64,raw_extensions=5312,unique_masks_before_filters=500,wall_seconds=120,memory_mb=512,output_bytes=32*1024**2),
        module_sha256=sha(ROOT/'mmsearch/marathon7_modeclosure11.py'),deadline_utc='2026-11-03T19:24:17Z',optional_rank2_span_filter_applied=False)
    freeze(out/'INPUT-PLAN.json',plan);freeze(out/'marathon7_modeclosure11_prepare.py',Path(__file__).read_bytes());freeze(out/'marathon7_modeclosure11.py',(ROOT/'mmsearch/marathon7_modeclosure11.py').read_bytes())
    for s in range(4):freeze(out/f'source-{s}.json',(parent/f'source-{s}.json').read_bytes())
    cache=SourceCache(out);terms={};certificates=[];closures=[];raw=0;hist=Counter();reason=None
    try:
        for s in range(4):
            barrier('pre_source');source,verified,t,_,sourcehash=cache.load(dict(source=f'source-{s}.json',source_products=93,source_sha256=plan['source_sha256'][str(s)]));terms[s]=t;paircert=[]
            for axis in range(3):
                other=[j for j in range(3) if j!=axis];columns=[pair_column(term[other[0]],term[other[1]],25) for term in t];space=BinaryBasis(columns)
                if len(space.vectors)!=93:raise ValueError('source opposite-pair image not independent93')
                coordinates=[space.coordinates(column,require_member=True) for column in columns]
                if any(space.expand(mask)!=column for mask,column in zip(coordinates,columns)):raise ValueError('source pair-basis witness failed')
                paircert.append(dict(axis=axis,other_axes=other,rank=93,encoding='hex strings',original_columns=[hex(v) for v in columns],basis=[hex(v) for v in space.vectors],original_coordinates=[hex(v) for v in coordinates]))
            certificates.append(dict(source_id=s,source_sha256=sourcehash,full_verification=verified,opposite_pair_certificates=paircert));barrier('post_source')
        freeze(out/'SOURCE-CERTIFICATES.json',certificates)
        for ordinal,row in enumerate(selected):
            barrier('pre_parent');s,lo,hi=row[:3];mask=lo|(hi<<64);ids=[i for i in range(93) if mask>>i&1]
            answer=factor_image_closure(terms[s],ids,cancelled=lambda:guard.reason() is not None);barrier('post_parent')
            if answer['status']!='COMPLETE':raise RuntimeError('incomplete closure membership census')
            if answer['shape']!=row[3:6] or max(answer['shape'])!=8:raise ValueError('parent image dimensions changed')
            raw+=answer['raw_other_products_tested'];hist[answer['closure_size']]+=1
            closures.append(dict(answer,parent_ordinal=ordinal,source_id=s,parent_mask_lo=lo,parent_mask_hi=hi))
        if raw!=5312 or len(closures)!=64:raise ValueError('finite raw-extension coverage differs')
        freeze(out/'PARENT-CLOSURES.json',closures)
        cases=[];origins=[];seen={}
        for rank in range(83):
            for closure in closures:
                if rank>=len(closure['other_products']):continue
                entry=closure['other_products'][rank];s=closure['source_id'];ids=sorted(closure['parent_indices']+[entry['source_index']]);mask=sum(1<<i for i in ids);key=(s,mask&((1<<64)-1),mask>>64)
                if key in seen:continue
                if len(cases)==500:break
                shape=closure['shape'];axis=next(a for a,d in enumerate(shape) if d==8);other=[j for j in range(3) if j!=axis]
                case=dict(id=f's{s}-{key[2]:08x}{key[1]:016x}',source=f'source-{s}.json',source_id=s,source_sha256=plan['source_sha256'][str(s)],source_products=93,source_local_products=11,target_local_products=10,
                    mask_lo=key[1],mask_hi=key[2],source_indices=ids,shape=shape,free_axis=axis,mode_rank=8,all_pair_points=((1<<shape[other[0]])-1)*((1<<shape[other[1]])-1))
                seen[key]=len(cases);cases.append(case);origins.append(dict(case=case['id'],parent_ordinal=closure['parent_ordinal'],parent_mask_lo=closure['parent_mask_lo'],parent_mask_hi=closure['parent_mask_hi'],added_source_index=entry['source_index'],added_factor_coordinates=entry['factor_coordinates']))
            if len(cases)==500:break
        freeze(out/'CASES.json',cases);freeze(out/'CASE-ORIGINS.json',origins)
        controls=[];per_source=Counter()
        for case,origin in zip(cases,origins):
            if per_source[case['source_id']]>=3:continue
            barrier('pre_control');source,data,verified,sourcehash,corehash,inputhash=cache.core(case);barrier('post_control')
            parent_closure=closures[origin['parent_ordinal']]
            for axis,basis in enumerate(data['image_bases']):
                parentbasis=BinaryBasis(parent_closure['basis_witnesses'][axis]['basis'])
                if any(parentbasis.expand(parentbasis.coordinates(value))!=value for value in basis):raise ValueError('actual image escaped fixed parent image')
            name=f'controls/source-{case["source_id"]}-{per_source[case["source_id"]]}.core.json';freeze(out/name,data)
            controls.append(dict(case=case['id'],source_id=case['source_id'],core_file=name,source_sha256=sourcehash,core_math_sha256=corehash,core_input_sha256=inputhash,exact_ambient_entries_checked=15625,actual_mode_images=data['shape'],parent_images_unchanged=True,decoder_queries=0));per_source[case['source_id']]+=1
        freeze(out/'ACTUAL-CORE-CONTROLS.json',controls);barrier('pre_ready')
        report=dict(status='COMPLETE_BOUNDED_MODE_CLOSURE11_PREP',parents=64,raw_extensions=raw,unique_masks_admitted_before_filters=len(cases),unique_cap_reached=len(cases)==500,eligible_extension_occurrences=sum(len(item['other_products']) for item in closures),
            closure_size_histogram=dict(hist),closure_size_histogram_by_source={str(s):dict(Counter(item['closure_size'] for item in closures if item['source_id']==s)) for s in range(4)},parent_shape_histogram={str(shape):sum(tuple(item['shape'])==shape for item in closures) for shape in {tuple(item['shape']) for item in closures}},
            admitted_source_counts=dict(Counter(case['source_id'] for case in cases)),actual_core_controls=len(controls),controls_per_source=dict(per_source),source_opposite_pair_ranks=[93]*3,source_full_entries_each=15625,
            local_products=11,target_products=10,mode_rank=8,outside_products=82,optional_rank2_span_filter_applied=False,optional_filter_reason='Deferred pending exact reviewed implementation identification; membership census does not imply existence.',
            supported_routes=['Reviewed surplus_two7: exact prior CP(d+1), exact corank-one backbone, otherwise complete repeated-pair extension to child rank9/target10.'],complete_caps=dict(max_vectors=511,max_extensions=765),
            decoder_queries=0,pilot_cases=min(25,len(cases)),elapsed_seconds=time.monotonic()-started,logical_bytes=sum(p.stat().st_size for p in out.rglob('*') if p.is_file()),
            scope='New11-term masks in fixed parent images; no old10-to9 negative transfer, no decomposition or global rank claim.')
        freeze(out/'REPORT.json',report);freeze(out/'manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}));print(json.dumps({key:report[key] for key in ['status','raw_extensions','unique_masks_admitted_before_filters','closure_size_histogram','actual_core_controls','pilot_cases','decoder_queries','elapsed_seconds','logical_bytes']},sort_keys=True))
    except Exception as error:
        freeze(out/'UNKNOWN.json',dict(status='UNKNOWN',complete=False,reason=type(error).__name__+': '+str(error),parents_complete=len(closures),raw_extensions=raw,decoder_queries=0,elapsed_seconds=time.monotonic()-started));raise


if __name__=='__main__':main()
