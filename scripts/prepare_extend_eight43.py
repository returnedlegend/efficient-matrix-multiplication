"""Freeze fresh8-term residuals extending all460 passing6sets; no N5 queries."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import random
import resource
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,read,sha
from mmsearch.local_ten43 import mask_indices,extension_shapes,native_row,point_domain,source_core
from mmsearch.compact_eight43 import canonical_axis_form,opposite_pair_ranks,factor_core,replace_and_verify,bits
from mmsearch.compact_extend843 import planted_eight_to_seven_n3
from mmsearch.compact_coset43 import solve_core
from mmsearch.koszul import koszul_bounds
from mmsearch.koszul_p2 import koszul_p2_bounds,koszul_p2_rows
from mmsearch.lowrank_span43 import lowrank_span
from mmsearch.sat_neighborhoods import factor_masks,gf2_rank
from mmsearch.recombine import digest
from mmsearch.verify import verify_candidate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inventory',type=Path,required=True);p.add_argument('--scan-dir',type=Path,required=True);p.add_argument('--guard-runtime',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    resource.setrlimit(resource.RLIMIT_AS,(1024*1024**2,1024*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(45,46));started=time.process_time()
    inv=a.inventory.resolve();scan=a.scan_dir.resolve();out=a.output_dir.resolve();guardruntime=a.guard_runtime.resolve()
    for name,expected in read(inv/'manifest.json')['files'].items():
        if sha(inv/name)!=expected:raise ValueError('original inventory changed: '+name)
    for name,expected in read(guardruntime/'manifest.json')['files'].items():
        if sha(guardruntime/name)!=expected:raise ValueError('guard runtime changed: '+name)
    original=[json.loads(x) for x in (inv/'six-term-analysis.jsonl').read_text().splitlines()]
    bases=[dict(row,analysis_ordinal=i) for i,row in enumerate(original) if row['Koszul_lower_bound']<=5]
    if len(bases)!=460 or bases!=read(scan/'passing6.json'):raise ValueError('460 passing6 scope changed')
    basebyid={r['analysis_ordinal']:r for r in bases};sources=[read(inv/f'source-{s}.json') for s in range(4)];terms=[factor_masks(s) for s in sources];sourcecontrols=[]
    for s,source in enumerate(sources):
        checked=verify_candidate(source,random_trials=0);pairranks=opposite_pair_ranks(terms[s])
        if not checked['valid'] or checked['rank']!=93 or checked['exact_entries_checked']!=15625 or pairranks!=[93]*3:raise ValueError('source fullT/pair-independence failed')
        sourcecontrols.append(dict(source=s,verification=checked,all_opposite_pair_ranks=pairranks,source_sha256=sha(inv/f'source-{s}.json')))
    cheap=read(scan/'cheap-scan.report.json');boundreport=read(scan/'necessary-bounds.report.json')
    if cheap['status']!='CHEAP_SCAN_COMPLETE' or cheap['next_base']!=460 or boundreport['status']!='NECESSARY_BOUND_SCAN_COMPLETE' or boundreport['next_cheap_ordinal']!=7528:raise ValueError('partial scan remains UNKNOWN')
    allcheap={};fresh=set();defer=set();existing_bindings={}
    for line in (scan/'cheap-scan.tsv').open():
        row=list(map(int,line.split()));s,lo,hi,parent,x,y,*shape=row;key=(s,lo,hi);indices=mask_indices(lo,hi);base=basebyid[parent]
        if len(indices)!=8 or s!=base['source'] or x==y or x in base['indices'] or y in base['indices'] or sorted(base['indices']+[x,y])!=indices or max(shape)>6:raise ValueError('extension identity invalid')
        if extension_shapes(terms[s],base['indices'],x,y)!=shape:raise ValueError('independent cheap rank differential failed')
        if key in allcheap:raise ValueError('duplicate cheap mask')
        allcheap[key]=dict(source=s,lo=lo,hi=hi,parent=parent,x=x,y=y,shape=shape)
    for name,keys in [('cheap-scan.new.tsv',fresh),('cheap-scan.deferred.tsv',defer)]:
        for line in (scan/name).open():
            vals=list(map(int,line.split()));key=tuple(vals[:3])
            if key not in allcheap or key in keys:raise ValueError('new/deferred catalog identity invalid')
            keys.add(key)
    if fresh&defer or fresh|defer!=set(allcheap) or len(fresh)!=7528 or len(defer)!=699 or len(allcheap)!=8227:raise ValueError('new/deferred partition mismatch')
    oldcounts=[244374,248940,256489,231673]
    for s in range(4):
        file=inv/f'unions.source-{s}.k8.txt';registry=set()
        for line in file.open():
            lo,hi=map(int,line.split());mask=lo|(hi<<64)
            if mask.bit_count()!=8 or mask>>93 or mask in registry:raise ValueError('original full8 registry invalid')
            registry.add(mask)
        if len(registry)!=oldcounts[s]:raise ValueError('original full8 count mismatch')
        existing_bindings[str(s)]=dict(path=str(file),sha256=sha(file),count=len(registry),source_sha256=sha(inv/f'source-{s}.json'))
        for key in [k for k in allcheap if k[0]==s]:
            present=(key[1]|(key[2]<<64)) in registry
            if present!=(key in defer):raise ValueError('incorrect overlap classification')
    # Independent sampled checks include native rejections, not just emitted passes.
    rng=random.Random(843460);reject_probes=Counter()
    for base in bases:
        outside=[i for i in range(93) if i not in base['indices']]
        for probe in range(5):
            x,y=sorted(rng.sample(outside,2));shape=extension_shapes(terms[base['source']],base['indices'],x,y);mask=sum(1<<i for i in [*base['indices'],x,y]);key=(base['source'],mask&((1<<64)-1),mask>>64)
            if (max(shape)<=6)!=(key in allcheap):raise ValueError('native omitted/included wrong extension')
            reject_probes['pass' if max(shape)<=6 else 'reject']+=1
    boundrows=[native_row(line) for line in (scan/'necessary-bounds.tsv').open()]
    if len(boundrows)!=7528 or {(r['source'],r['lo'],r['hi']) for r in boundrows}!=fresh:raise ValueError('necessary scan did not cover every fresh mask')
    p2pass=[r for r in boundrows if r['p2_passed']]
    if len(p2pass)!=6902:raise ValueError('p2 count changed')
    differential=[];probes=boundrows[::max(1,len(boundrows)//48)][:48]+[next(r for r in boundrows if r['source']==s and not r['p2_passed']) for s in range(4)]
    for row in probes:
        ids=mask_indices(row['lo'],row['hi']);b,core,shape=factor_core(terms[row['source']],ids);p1=koszul_bounds(core,shape,7)
        if shape!=row['shape'] or p1['flattening_ranks']!=shape:raise ValueError('actual mode-image rank mismatch')
        for mode,value in enumerate(row['p1_ranks']):
            if value==-999:continue
            actual=p1['bounds'][mode]['matrix_rank']
            if value>=0 and value!=actual or value<0 and (actual<abs(value) or (abs(value)+shape[mode]-2)//(shape[mode]-1)<=7):raise ValueError('p1 native/Python mismatch')
        for mode,value in enumerate(row['p2_ranks']):
            if value==-999:continue
            matrix,_,_=koszul_p2_rows(core,shape,mode);actual=gf2_rank(matrix);unit=(shape[mode]-1)*(shape[mode]-2)//2
            if value>=0 and value!=actual or value<0 and (actual<abs(value) or (abs(value)+unit-1)//unit<=7):raise ValueError('p2 native/Python mismatch')
        differential.append(dict(source=row['source'],lo=row['lo'],hi=row['hi'],status='PASS'))
    # Reuse the independently reviewed lowrank-span lemma; never a decoder.
    lowcache={};lowrecords=[];survivors={s:[] for s in range(4)};lowcounts={s:Counter() for s in range(4)}
    for row in p2pass:
        s=row['source'];ids=mask_indices(row['lo'],row['hi']);_,core,shape=factor_core(terms[s],ids);key=(tuple(shape),bytes(core))
        if key not in lowcache:
            checks=[]
            for axis in range(3):
                if shape[axis]!=6:continue
                result=lowrank_span(core,shape,7,axis);checks.append(result)
                if result['status']=='LOWRANK_SPAN_EXCLUDES':break
            lowcache[key]=checks
        checks=lowcache[key];excluded=any(c['status']=='LOWRANK_SPAN_EXCLUDES' for c in checks);lowcounts[s]['checked']+=1;lowcounts[s]['excluded' if excluded else 'necessary_passed']+=1
        lowrecords.append(dict(source=s,lo=row['lo'],hi=row['hi'],shape=shape,excluded_rank7=excluded,checks=checks))
        if not excluded:survivors[s].append(row)
    out.mkdir(parents=True,exist_ok=False)
    metrics=dict(parent6_p1_passing=460,extensions_checked=1720860,passing_occurrences=10482,unique_modes_le6=8227,
        DEFER_TO_EXISTING_PORTFOLIO=699,new_masks=7528,new_p1_passed=7528,new_p2_passed=6902,new_p2_rejected=626,
        new_max_mode_histogram=dict(Counter(max(r['shape']) for r in boundrows)),p2_max_mode_histogram=dict(Counter(max(r['shape']) for r in p2pass)),
        maxd5_surplus2=0,unsupported_lower=0,lowrank2_counts={s:dict(v) for s,v in lowcounts.items()},after_lowrank2=sum(len(v) for v in survivors.values()),
        original_full8_count=981476,original_full8_bindings=existing_bindings,cheap_scan=cheap,necessary_scan=boundreport,
        old6_rank5_negatives_transferred=False,overlap_is_not_negative=True,N5_decoder_queries=0,scope='Every two-term extension of exactly460 passing6subsets; not all C(93,8).')
    freeze(out/'COUNTS-BEFORE-PORTFOLIO.json',metrics);freeze(out/'SOURCE-CONTROLS.json',sourcecontrols);freeze(out/'NATIVE-DIFFERENTIAL.json',dict(positive_masks_verified=8227,random_parent_pair_probes=dict(reject_probes),p1p2=differential))
    freeze(out/'DEFER-EXISTING.json.gz',gzip.compress(json.dumps([dict(source=s,lo=lo,hi=hi,status='DEFER_TO_EXISTING_PORTFOLIO',negative_proof_transferred=False) for s,lo,hi in sorted(defer)],sort_keys=True).encode(),compresslevel=1,mtime=0))
    freeze(out/'LOWRANK-BOUND.jsonl.gz',gzip.compress(('\n'.join(json.dumps(r,sort_keys=True) for r in lowrecords)+'\n').encode(),compresslevel=1,mtime=0))
    for s in range(4):freeze(out/f'source-{s}.json',(inv/f'source-{s}.json').read_bytes())
    selected=[];ambient_seen=set();core_seen=set();axis_seen=set();lowbyid={(r['source'],r['lo'],r['hi']):r for r in lowrecords};catalog=[]
    for s in range(4):
        survivors[s].sort(key=lambda r:(point_domain(r['shape'])[1],sum(r['shape']),r['shape'],r['hi'],r['lo']))
        for row in survivors[s]:
            axis,points=point_domain(row['shape']);catalog.append(' '.join(map(str,[s,row['lo'],row['hi'],*row['shape'],axis,points]))+'\n')
        for row in survivors[s]:
            if sum(case['source_id']==s for case in selected)>=3:break
            ids=mask_indices(row['lo'],row['hi']);data,ambient=source_core(sources[s],ids);corehash=digest(dict(shape=data['shape'],core=data['core']));axishash=canonical_axis_form(data['core'],data['shape'])[2];ambienthash=hashlib.sha256(ambient.to_bytes(1954,'little')).hexdigest()
            if ambienthash in ambient_seen or corehash in core_seen or axishash in axis_seen:continue
            axis,points=point_domain(data['shape'])
            if max(data['shape'])!=6 or points>3969:raise ValueError('unsupported pilot mode/domain')
            p1=koszul_bounds(data['core'],data['shape'],7);p2=koszul_p2_bounds(data['core'],data['shape'],7)
            if p1['rejected'] or p2['rejected'] or p1['flattening_ranks']!=data['shape']:raise ValueError('selected core bounds failed')
            _,verification=replace_and_verify(sources[s],ids,[terms[s][i] for i in ids],dict(method='extended8 source reconstruction control'))
            if verification['rank']!=93:raise ValueError('source control rank changed')
            identifier=f'case-{len(selected):02d}';path=f'cases/{identifier}.core.json';data.update(p1=p1,p2=p2,lowrank_span=lowbyid[(s,row['lo'],row['hi'])]['checks'])
            freeze(out/path,data);freeze(out/f'controls/{identifier}.source.verification.json',verification);prior=allcheap[(s,row['lo'],row['hi'])];base=basebyid[prior['parent']]
            selected.append(dict(id=identifier,source_id=s,source=f'source-{s}.json',source_sha256=sha(inv/f'source-{s}.json'),source_products=93,source_local_products=8,target_local_products=7,
                core=path,free_axis=axis,mode_rank=6,all_pair_points=points,shape=data['shape'],source_indices=ids,parent_analysis_ordinal=prior['parent'],parent6_indices=base['indices'],added_indices=[prior['x'],prior['y']],
                core_sha256=corehash,axis_permutation_core_sha256=axishash,residual_sha256=ambienthash,original_full8_overlap=False,old6_negative_transferred=False))
            ambient_seen.add(ambienthash);core_seen.add(corehash);axis_seen.add(axishash)
    if not selected:raise ValueError('no supported novel pilot core remains')
    freeze(out/'survivors.tsv.gz',gzip.compress(''.join(catalog).encode(),compresslevel=1,mtime=0))
    freeze(out/'plan.json',dict(cases=selected,source_counts=[sum(c['source_id']==s for c in selected) for s in range(4)],metrics=metrics,
        target_decoder_queries_during_preparation=0,scope='Explicit novel masks only; overlap deferred to existing portfolio, not a negative. No old6negative transfer.'))
    small,data,checked=planted_eight_to_seven_n3();answer=solve_core(data['core'],data['shape'],7,axis=0,max_points=3969)
    if answer['status']!='SAT' or answer['case']!='single_nonzero_coset_star_differences_span' or len(answer['products'])!=7:raise ValueError('small actual8to7 one-coset control failed')
    products=[]
    for product in answer['products']:
        expanded=[]
        for coordinates,basis in zip(product,data['image_bases']):
            value=0
            for bit in bits(coordinates):value^=basis[bit]
            expanded.append(value)
        products.append(expanded)
    candidate,verified=replace_and_verify(small,data['source_indices'],products)
    if verified['rank']!=48 or verified['exact_entries_checked']!=729:raise ValueError('n3 full control failed')
    bad=[list(t) for t in products];bad[0][0]^=1
    try:replace_and_verify(small,data['source_indices'],bad)
    except AssertionError:corrupt_rejected=True
    else:raise ValueError('corrupt small lift accepted')
    freeze(out/'small-source.json',small);freeze(out/'small-core.json',data);freeze(out/'small-plan.json',dict(cases=[dict(id='small-n3-Wplus4diagonals8to7',source='small-source.json',core='small-core.json',source_products=49,source_local_products=8,target_local_products=7,free_axis=0)]))
    for name,value in [('source-verification',checked),('decoder-result',answer),('candidate',candidate),('verification',verified),('corrupt-lift-rejected',corrupt_rejected)]:freeze(out/f'controls/planted-small/{name}.json',value)
    for path in (guardruntime/'runtime').rglob('*.py'):
        if str(path.relative_to(guardruntime/'runtime')) not in ['mmsearch/compact_extend843.py','scripts/campaign_extend_eight_guard43.py']:freeze(out/'runtime'/path.relative_to(guardruntime/'runtime'),path.read_bytes())
    freeze(out/'runtime/mmsearch/compact_extend843.py',(ROOT/'mmsearch/compact_extend843.py').read_bytes());freeze(out/'runtime/campaign_extend_eight_guard43.py',(ROOT/'scripts/campaign_extend_eight_guard43.py').read_bytes());freeze(out/'runtime/scripts/campaign_extend_eight_guard43.py',(ROOT/'scripts/campaign_extend_eight_guard43.py').read_bytes())
    freeze(out/'runtime/scripts/prepare_extend_eight43.py',Path(__file__).read_bytes())
    for name in ['extend8_scan43.cpp','extend8_bounds43.cpp']:freeze(out/'preprocessing'/name,(ROOT/'native'/name).read_bytes())
    for name in ['extend8_scan43','extend8_bounds43']:freeze(out/'preprocessing'/name,Path('/tmp',name).read_bytes());(out/'preprocessing'/name).chmod(0o555)
    for name in ['scan-input.txt','passing6.json','cheap-scan.cursor','cheap-scan.report.json','necessary-bounds.cursor','necessary-bounds.report.json']:freeze(out/'preprocessing'/name,(scan/name).read_bytes())
    for name in ['cheap-scan.tsv','cheap-scan.new.tsv','cheap-scan.deferred.tsv','necessary-bounds.tsv']:freeze(out/'preprocessing'/(name+'.gz'),gzip.compress((scan/name).read_bytes(),compresslevel=1,mtime=0))
    freeze(out/'INPUT-BINDINGS.json',dict(inventory_manifest_sha256=sha(inv/'manifest.json'),six_analysis_sha256=sha(inv/'six-term-analysis.jsonl'),guard_parent_manifest_sha256=sha(guardruntime/'manifest.json'),
        original_full8=existing_bindings,preparation_CPU_seconds=time.process_time()-started,new_source_files_only=True,N5_decoder_queries=0))
    freeze(out/'launch-manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    print(json.dumps(dict(status='PREPARED_NO_N5_DECODER_QUERY',cases=len(selected),sources=[sum(c['source_id']==s for c in selected) for s in range(4)],domains=[c['all_pair_points'] for c in selected],
        shapes=[c['shape'] for c in selected],lowrank_counts={s:dict(v) for s,v in lowcounts.items()},CPU_seconds=time.process_time()-started)))


if __name__=='__main__':main()
