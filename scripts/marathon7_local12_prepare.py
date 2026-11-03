#!/usr/bin/env python3
"""Root-approved bounded query-free N5 local12/image9/target11 preparation."""
import argparse
from collections import Counter
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import random
import resource
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,read,sha
from scripts.marathon7_local_campaign import atomic
from mmsearch.marathon7_local import CampaignGuard,CampaignHold,SourceCache
from mmsearch.marathon7_local12 import rank_three_span
from mmsearch.compact_sat import BinaryBasis
from mmsearch.koszul_p2 import koszul_p2_rows
from mmsearch.sat_neighborhoods import gf2_rank
from mmsearch.recombine import digest
from mmsearch.observed_rank3_lazy42 import chain_append,chain_read

SEED=7121109


def parents(rows):
    chosen=[]
    for s in range(4):
        source=sorted([r for r in rows if r[0]==s],key=lambda r:(r[7],sum(r[3:6]),r[3:6],r[2],r[1]));cut=max(8,len(source)//4);rng=random.Random(SEED+s)
        selected=rng.sample(source[:cut],8)+rng.sample(source[cut:],8)
        chosen.append(selected)
    return [chosen[s][i] for i in range(16) for s in range(4)]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',type=Path,required=True);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--guard-state',type=Path,required=True);p.add_argument('--rank3-review',type=Path);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--resume',action='store_true');a=p.parse_args()
    resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2));parent=a.parent.resolve();out=a.output_dir.resolve();started=time.monotonic()
    pins={str(path.relative_to(ROOT)):sha(path) for path in [Path(__file__).resolve(),ROOT/'mmsearch/marathon7_local12.py',ROOT/'mmsearch/marathon7_local.py',ROOT/'mmsearch/extend_eight_bulk43.py',ROOT/'mmsearch/koszul_p2.py',ROOT/'mmsearch/compact_eight43.py']}
    rank3review=None
    if a.rank3_review:
        rank3review=read(a.rank3_review)
        if rank3review.get('status')!='PASS' or rank3review.get('module_sha256')!=sha(ROOT/'mmsearch/marathon7_local12.py'):raise ValueError('independent rank3 review missing or wrong implementation')
    inputplan=dict(version=1,seed=SEED,parent=str(parent),parent_manifest_sha256=sha(parent/'manifest.json'),parent_catalog_sha256=sha(parent/'survivors.tsv.gz'),
        source_sha256={str(s):sha(parent/f'source-{s}.json') for s in range(4)},pins=pins,campaign=str(a.campaign.resolve()),guard_state=str(a.guard_state.resolve()),
        limits=dict(parents=64,unique_shape_masks_before_filter=500,raw_pairs=217792,wall_seconds=120,AS_bytes=512*1024**2,output_bytes=32*1024**2),
        rank3_filter=bool(rank3review),rank3_review_sha256=sha(a.rank3_review) if a.rank3_review else None,deadline_utc='2026-11-03T19:24:17Z')
    rows=[list(map(int,line.split())) for line in gzip.decompress((parent/'survivors.tsv.gz').read_bytes()).decode().splitlines()]
    if len(rows)!=111605:raise ValueError('parent catalogue scope differs')
    inputplan['selected_parents']=parents(rows);configsha=digest(inputplan)
    if a.resume:
        if read(out/'INPUT-PLAN.json')!=inputplan:raise ValueError('resume input/seed/order/caps/code changed')
        state=read(out/'cursor.json')
    else:
        for name,expected in read(parent/'manifest.json')['files'].items():
            if sha(parent/name)!=expected:raise ValueError('historical input changed')
        out.mkdir(parents=True,exist_ok=False)
        freeze(out/'INPUT-PLAN.json',inputplan)
        for s in range(4):freeze(out/f'source-{s}.json',(parent/f'source-{s}.json').read_bytes())
        freeze(out/'marathon7_local12_prepare.py',Path(__file__).read_bytes());freeze(out/'marathon7_local12.py',(ROOT/'mmsearch/marathon7_local12.py').read_bytes())
        if a.rank3_review:freeze(out/'RANK3-INDEPENDENT-REVIEW.json',a.rank3_review.read_bytes())
        state=dict(config_sha256=configsha,positions=[0]*64,next_parent=0,raw_pairs=0,unique_masks=0,committed=0,elapsed_seconds=0.,terminal=False,pending=None)
        atomic(out/'cursor.json',state)
    if state['config_sha256']!=configsha:raise ValueError('cursor configuration changed')
    records,chain=chain_read(out/'candidates.jsonl',configsha)
    if len(records)<state['committed']:raise ValueError('cursor ahead of journal')
    if len(records)>state['committed']:state=records[-1]['cursor_after'];state['committed']=len(records);state['pending']=None
    if state['terminal']:
        print(json.dumps(dict(status='PREPARED_BOUNDED_SAMPLE',terminal_resume=True,decoder_queries=0,records=len(records))));return
    remaining=120-state['elapsed_seconds'];guard=CampaignGuard(max(.0001,remaining),'2026-11-03T19:24:17Z',guard_state=a.guard_state,campaign_dir=a.campaign)
    import signal
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    if guard.resources is None:raise ValueError('fresh guard required for N5 prep')
    oldelapsed=state['elapsed_seconds']
    def checkpoint():state['elapsed_seconds']=oldelapsed+time.monotonic()-started;atomic(out/'cursor.json',state)
    def barrier(label):
        guard.check(label)
        if oldelapsed+time.monotonic()-started>=120:raise CampaignHold('cumulative prep120second cap',label)
        if sum(path.stat().st_size for path in out.rglob('*') if path.is_file())+1024**2>32*1024**2:raise CampaignHold('prep32MiB cap/reserve',label)
    cache=SourceCache(out);terms={};sourcecontrols=[]
    for s in range(4):
        barrier('pre_source')
        source,full,t,_,sourcehash=cache.load(dict(source=f'source-{s}.json',source_products=93,source_sha256=inputplan['source_sha256'][str(s)]))
        terms[s]=t;sourcecontrols.append(dict(source_id=s,source_sha256=sourcehash,full_entries=full['exact_entries_checked'],rank=full['rank']))
        barrier('post_source')
    if not (out/'SOURCE-CONTROLS.json').exists():freeze(out/'SOURCE-CONTROLS.json',sourcecontrols)
    prepared=[]
    for ordinal,row in enumerate(inputplan['selected_parents']):
        s,lo,hi=row[:3];mask=lo|(hi<<64);ids=[i for i in range(93) if mask>>i&1]
        if len(ids)!=10:raise ValueError('invalid parent support')
        bases=[BinaryBasis([terms[s][i][axis] for i in ids]) for axis in range(3)]
        if [len(b.vectors) for b in bases]!=row[3:6]:raise ValueError('parent factor/image dimension changed')
        outside=[i for i in range(93) if i not in ids];pairs=list(itertools.combinations(outside,2));random.Random(SEED+1000+ordinal).shuffle(pairs)
        residues={i:[terms[s][i][axis]^b.expand(b.coordinates(terms[s][i][axis])) for axis,b in enumerate(bases)] for i in outside}
        prepared.append((row,ids,pairs,residues))
    seen={(r['case']['source_id'],r['case']['mask_lo'],r['case']['mask_hi']) for r in records};reason=None
    try:
        while state['unique_masks']<500 or state['pending']:
            barrier('pre_next')
            if state['pending']:
                candidate=state['pending'];case=candidate['case']
            else:
                if state['raw_pairs']>=217792 or all(position==3403 for position in state['positions']):break
                ordinal=state['next_parent'];state['next_parent']=(ordinal+1)%64
                if state['positions'][ordinal]>=3403:continue
                row,ids,pairs,residues=prepared[ordinal];pairordinal=state['positions'][ordinal];x,y=pairs[pairordinal];state['positions'][ordinal]+=1;state['raw_pairs']+=1
                shape=[row[3+axis]+(0 if not residues[x][axis] and not residues[y][axis] else 1 if not residues[x][axis] or not residues[y][axis] or residues[x][axis]==residues[y][axis] else 2) for axis in range(3)]
                if max(shape)!=9 or any(d>9 for d in shape):
                    if state['raw_pairs']%256==0:checkpoint()
                    continue
                selected=sorted(ids+[x,y]);mask=sum(1<<i for i in selected);key=(row[0],mask&((1<<64)-1),mask>>64)
                if key in seen:continue
                if len(selected)!=12 or len(set(selected))!=12:raise ValueError('invalid generated12 mask')
                axis=next(axis for axis,d in enumerate(shape) if d==9);other=[j for j in range(3) if j!=axis]
                case=dict(id=f's{key[0]}-{key[2]:08x}{key[1]:016x}',source=f'source-{key[0]}.json',source_id=key[0],source_sha256=inputplan['source_sha256'][str(key[0])],source_products=93,source_local_products=12,target_local_products=11,
                    mask_lo=key[1],mask_hi=key[2],source_indices=selected,shape=shape,free_axis=axis,mode_rank=9,all_pair_points=((1<<shape[other[0]])-1)*((1<<shape[other[1]])-1))
                candidate=dict(case=case,parent_ordinal=ordinal,parent_mask_lo=row[1],parent_mask_hi=row[2],added_indices=[x,y],pair_ordinal=pairordinal)
                state['unique_masks']+=1;state['pending']=candidate;checkpoint()
            barrier('pre_core')
            source,data,full,sourcehash,corehash,inputhash=cache.core(case);barrier('post_core')
            p2=[]
            import math
            for mode in range(3):
                barrier('pre_p2');matrix,columns,rowcount=koszul_p2_rows(data['core'],data['shape'],mode);rank=gf2_rank(matrix);contribution=math.comb(data['shape'][mode]-1,2)
                if contribution<=0:raise ValueError('all p2 modes must be nontrivial/computed')
                p2.append(dict(mode=mode,status='COMPUTED',rows=rowcount,columns=columns,matrix_rank=rank,rank_one_contribution=contribution,lower_bound=(rank+contribution-1)//contribution,matrix_sha256=digest(matrix)));barrier('post_p2')
            lowrank=[];disposition='P2_EXCLUDED' if any(item['lower_bound']>11 for item in p2) else 'RETAINED'
            if disposition=='RETAINED' and rank3review:
                for mode,d in enumerate(data['shape']):
                    if d!=9:continue
                    barrier('pre_rank3');answer=rank_three_span(data['core'],data['shape'],mode,cancelled=lambda:guard.reason() is not None);barrier('post_rank3')
                    if answer['status']=='UNKNOWN':raise CampaignHold('rank3 filter incomplete','post_rank3')
                    lowrank.append(answer)
                    if answer['status']=='LOWRANK_SPAN_EXCLUDES':disposition='RANK3_SPAN_EXCLUDED';break
            barrier('pre_commit')
            control=out/'controls'/f'source-{case["source_id"]}.core.json'
            if not control.exists():freeze(control,data)
            state['pending']=None;state['committed']+=1
            record=dict(candidate,disposition=disposition,p2=p2,rank3=lowrank,source_sha256=sourcehash,core_math_sha256=corehash,core_input_sha256=inputhash,full_ambient_entries_checked=15625,
                decoder_queries=0,cursor_after=json.loads(json.dumps(state)))
            chain=chain_append(out/'candidates.jsonl',record,chain);records.append(record);seen.add((case['source_id'],case['mask_lo'],case['mask_hi']));checkpoint()
    except CampaignHold as hold:reason=dict(reason=hold.reason,barrier=hold.barrier)
    finished=reason is None and (state['unique_masks']==500 or state['raw_pairs']==217792 or all(v==3403 for v in state['positions']))
    state['terminal']=finished;checkpoint();counts=Counter(r['disposition'] for r in records)
    report=dict(status='PREPARED_BOUNDED_SAMPLE' if finished else 'UNKNOWN',terminal=finished,config_sha256=configsha,raw_pairs=state['raw_pairs'],unique_masks_before_filter=state['unique_masks'],committed=len(records),pending=bool(state['pending']),
        dispositions=dict(counts),retained_cases=[r['case'] for r in records if r['disposition']=='RETAINED'],rank3_filter=bool(rank3review),decoder_queries=0,result_chain_sha256=chain,stop_reason=reason,elapsed_seconds=state['elapsed_seconds'],logical_bytes=sum(path.stat().st_size for path in out.rglob('*') if path.is_file()),
        scope='Only bounded sampled12product residuals; necessary filters only, no decomposition query or prior10negative transfer.')
    atomic(out/'REPORT.json',report)
    if finished and not (out/'manifest.json').exists():freeze(out/'manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    print(json.dumps({key:report[key] for key in ['status','raw_pairs','unique_masks_before_filter','committed','dispositions','rank3_filter','decoder_queries','elapsed_seconds','logical_bytes','stop_reason']},sort_keys=True))


if __name__=='__main__':main()
