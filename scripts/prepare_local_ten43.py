"""Freeze<=12 local10 cores after complete cheap and necessary-bound scans."""
import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mmsearch.local_ten43 import mask_indices,extension_shapes,native_row,point_domain,source_core,planted_small
from mmsearch.compact_eight43 import canonical_axis_form,opposite_pair_ranks,replace_and_verify,bits
from mmsearch.compact_coset43 import solve_core,expand_products
from mmsearch.koszul import koszul_bounds
from mmsearch.koszul_p2 import koszul_p2_bounds,koszul_p2_rows
from mmsearch.sat_neighborhoods import factor_masks,gf2_rank
from mmsearch.recombine import digest
from mmsearch.verify import verify_candidate


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def freeze(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    raw=value if isinstance(value,bytes) else (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    with path.open('xb') as stream:stream.write(raw)
    path.chmod(0o444)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--eight-bundle',type=Path,required=True);p.add_argument('--sample',type=Path,required=True)
    p.add_argument('--scan-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();started=time.process_time()
    resource.setrlimit(resource.RLIMIT_AS,(1024*1024**2,1024*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(40,41))
    old=a.eight_bundle.resolve();sample=a.sample.resolve();scan=a.scan_dir.resolve();out=a.output_dir.resolve()
    for name,expected in read(old/'manifest.json')['files'].items():
        if sha(old/name)!=expected:raise ValueError('frozen eight input changed: '+name)
    sampleconfig=read(sample/'config.json');samplecursor=read(sample/'cursor.json');rows=[json.loads(line) for line in (sample/'sample.jsonl').read_text().splitlines()]
    if len(rows)!=20000 or samplecursor['next_sample']!=20000 or samplecursor['committed_log_bytes']!=(sample/'sample.jsonl').stat().st_size:raise ValueError('incomplete sample')
    passing={r['sample_index']:r for r in rows if r['tensor_rank_lower_bound']<=7}
    if len(passing)!=449 or read(scan/'passing8.json')!=list(passing.values()):raise ValueError('449 sample provenance mismatch')
    cheapcursor=list(map(int,(scan/'cheap-scan.cursor').read_text().split()));boundcursor=list(map(int,(scan/'necessary-bounds.cursor').read_text().split()))
    if cheapcursor[0]!=449 or boundcursor[0]!=229594:raise ValueError('partial native scans remain UNKNOWN')
    sources=[read(old/f'source-{s}.json') for s in range(4)];masks=[factor_masks(s) for s in sources];sourcecontrols=[]
    for s,source in enumerate(sources):
        if sha(old/f'source-{s}.json')!=sampleconfig['inputs'][str(s)]['source_sha256']:raise ValueError('source/sample input mismatch')
        checked=verify_candidate(source,random_trials=0);pairranks=opposite_pair_ranks(masks[s])
        if not checked['valid'] or checked['rank']!=93 or checked['exact_entries_checked']!=15625 or pairranks!=[93]*3:raise ValueError('source exact/independence control failed')
        sourcecontrols.append(dict(source=s,verification=checked,opposite_pair_column_ranks=pairranks))
    candidates={s:[] for s in range(4)};counts={s:Counter() for s in range(4)};differential=[];allrows=[]
    for line in (scan/'necessary-bounds.tsv').open():
        row=native_row(line);s=row['source'];counts[s]['max8_examined']+=1
        if row['p1_passed']:counts[s]['p1_passed']+=1
        if row['p2_passed']:counts[s]['p2_passed']+=1;candidates[s].append(row)
        allrows.append(row)
    if len(allrows)!=229224 or [counts[s]['p2_passed'] for s in range(4)]!=[43246,33398,67088,49294]:raise ValueError('necessary count mismatch')
    controls=allrows[::max(1,len(allrows)//48)][:48]
    controls += [next(r for r in allrows if r['source']==s and not r['p2_passed']) for s in range(4)]
    for row in controls:
        ids=mask_indices(row['lo'],row['hi']);data,_=source_core(sources[row['source']],ids);p1=koszul_bounds(data['core'],data['shape'],9)
        if data['shape']!=row['shape'] or p1['flattening_ranks']!=row['shape']:raise ValueError('native/actual image rank mismatch')
        for mode,value in enumerate(row['p1_ranks']):
            if value==-999:continue
            actual=p1['bounds'][mode]['matrix_rank']
            if (value>=0 and value!=actual) or (value<0 and (actual<abs(value) or (abs(value)+row['shape'][mode]-2)//(row['shape'][mode]-1)<=9)):raise ValueError('native p1 mismatch')
        for mode,value in enumerate(row['p2_ranks']):
            if value==-999:continue
            matrix,_,_=koszul_p2_rows(data['core'],data['shape'],mode);actual=gf2_rank(matrix);contribution=(row['shape'][mode]-1)*(row['shape'][mode]-2)//2
            if (value>=0 and value!=actual) or (value<0 and (actual<abs(value) or (abs(value)+contribution-1)//contribution<=9)):raise ValueError('native p2 mismatch')
        differential.append(dict(source=row['source'],mask_lo=row['lo'],mask_hi=row['hi'],status='PASS',p1_passed=row['p1_passed'],p2_passed=row['p2_passed']))
    # The complete counts are retained before selecting/building the bounded portfolio.
    out.mkdir(parents=True,exist_ok=False)
    metrics=dict(extension_checks=1602930,passing_occurrences=230032,unique_all_modes_le8=229594,unique_max_mode8=229224,
        below_max8_not_in_pilot=370,p1_passed=229224,p2_passed=193026,p2_rejected=36198,per_source={s:dict(counts[s]) for s in range(4)},
        cheap_native_CPU_seconds=0.133941,necessary_native_CPU_seconds=9.8205,optional_p3='SKIPPED: no existing general p3 helper; no new p3 implementation',
        n5_target_queries=0,scope='All two-term extensions of exactly449 p1-passing eight-subsets in the frozen20000sample; not all C(93,10). Bound passes are necessary only.')
    freeze(out/'SCAN-COUNTS-BEFORE-PORTFOLIO.json',metrics)
    seenambient=set();seencore=set();seenaxis=set();cases=[];selected={};dedup=Counter()
    for s in range(4):
        candidates[s].sort(key=lambda r:(point_domain(r['shape'])[1],sum(r['shape']),r['shape'],r['hi'],r['lo']))
        for row in candidates[s]:
            ids=mask_indices(row['lo'],row['hi']);data,ambient=source_core(sources[s],ids);corehash=digest(dict(shape=data['shape'],core=data['core']));axishash=canonical_axis_form(data['core'],data['shape'])[2]
            ambienthash=hashlib.sha256(ambient.to_bytes(1954,'little')).hexdigest()
            if ambienthash in seenambient or corehash in seencore or axishash in seenaxis:dedup[s]+=1;continue
            p1=koszul_bounds(data['core'],data['shape'],9);p2=koszul_p2_bounds(data['core'],data['shape'],9)
            if p1['rejected'] or p2['rejected'] or p1['flattening_ranks']!=data['shape']:raise ValueError('selected necessary bounds/image mismatch')
            axis,points=point_domain(data['shape'])
            if data['shape'][axis]!=8 or points>65025 or max(data['shape'])>8:raise ValueError('selected core not one-surplus domain')
            unchanged,verification=replace_and_verify(sources[s],ids,[masks[s][i] for i in ids],dict(method='local10 source reconstruction control'))
            if verification['rank']!=93:raise ValueError('unchanged local10 source rank control failed')
            identifier=f'case-{len(cases):02d}';path=f'cases/{identifier}.core.json';data.update(p1=p1,p2=p2,source_local_products=10,target_local_products=9)
            freeze(out/path,data);freeze(out/f'controls/{identifier}.source.verification.json',verification)
            case=dict(id=identifier,source=f'source-{s}.json',source_id=s,source_products=93,source_local_products=10,target_local_products=9,core=path,
                free_axis=axis,mode_rank=8,all_pair_points=points,shape=data['shape'],core_sha256=corehash,axis_permutation_core_sha256=axishash,residual_sha256=ambienthash,
                original_source_indices=ids,source_sha256=sha(old/f'source-{s}.json'),old8_negatives_transferred=False)
            cases.append(case);selected[(s,row['lo'],row['hi'])]=case;seenambient.add(ambienthash);seencore.add(corehash);seenaxis.add(axishash)
            if sum(c['source_id']==s for c in cases)==3:break
    if len(cases)!=12:raise ValueError('fewer than12 distinct cores')
    for line in (scan/'cheap-scan.tsv').open():
        values=list(map(int,line.split()));key=tuple(values[:3])
        if key not in selected:continue
        case=selected[key];base=passing[values[3]];shape=extension_shapes(masks[key[0]],base['indices'],values[4],values[5])
        if shape!=case['shape'] or sorted(base['indices']+[values[4],values[5]])!=case['original_source_indices']:raise ValueError('selected extension provenance mismatch')
        case.update(parent_sample_index=values[3],parent8_indices=base['indices'],two_added_indices=values[4:6])
    if any('parent_sample_index' not in c for c in cases):raise ValueError('selected provenance notfound')
    freeze(out/'plan.json',dict(cases=cases,source_bundle=str(old),source_manifest_sha256=sha(old/'manifest.json'),sample_dir=str(sample),sample_sha256=sha(sample/'sample.jsonl'),
        sample_config_sha256=sha(sample/'config.json'),sample_cursor_sha256=sha(sample/'cursor.json'),scan_counts=metrics,source_counts=[3]*4,target_decoder_queries_during_preparation=0,
        scope='Twelve fixed-outside local10 residuals selected from the complete recorded extension subset. No old8 negative transfer; adding terms changes residual.'))
    freeze(out/'SOURCE-CONTROLS.json',sourcecontrols);freeze(out/'NATIVE-DIFFERENTIAL.json',differential)
    for s in range(4):freeze(out/f'source-{s}.json',(old/f'source-{s}.json').read_bytes())
    small,data,sourcecheck=planted_small();result=solve_core(data['core'],data['shape'],3,axis=0,max_points=65025)
    if result['status']!='SAT' or result['case']!='single_nonzero_coset_star_differences_span':raise ValueError('planted one-coset control did not exercise intended case')
    products=[]
    for term in result['products']:
        products.append([sum(0 for _ in []) for a in range(3)])
        for a,value in enumerate(term):
            for j in bits(value):products[-1][a]^=data['image_bases'][a][j]
    candidate,checked=replace_and_verify(small,data['source_indices'],products)
    if checked['rank']!=17 or checked['exact_entries_checked']!=64:raise ValueError('small full tensor lift failed')
    corrupt=[list(t) for t in products];corrupt[0][0]^=1
    try:replace_and_verify(small,data['source_indices'],corrupt)
    except AssertionError:rejected=True
    else:raise ValueError('corrupt planted lift accepted')
    freeze(out/'small-source.json',small);freeze(out/'small-core.json',data);freeze(out/'small-plan.json',dict(cases=[dict(id='small-W4to3',source='small-source.json',core='small-core.json',source_products=18,source_local_products=4,target_local_products=3,free_axis=0)]))
    for name,value in [('source-verification',sourcecheck),('decoder-result',result),('candidate',candidate),('verification',checked),('corrupt-lift-rejected',rejected)]:freeze(out/f'controls/planted-small/{name}.json',value)
    for directory in ('mmsearch','scripts'):
        for path in sorted((ROOT/directory).rglob('*.py')):freeze(out/'runtime'/path.relative_to(ROOT),path.read_bytes())
    freeze(out/'runtime/campaign_local_ten_coset43.py',(ROOT/'scripts/campaign_local_ten_coset43.py').read_bytes())
    freeze(out/'preprocessing/local10_scan43.cpp',(ROOT/'native/local10_scan43.cpp').read_bytes());freeze(out/'preprocessing/local10_bounds43.cpp',(ROOT/'native/local10_bounds43.cpp').read_bytes())
    freeze(out/'preprocessing/local10_scan43',Path('/tmp/local10_scan43').read_bytes());(out/'preprocessing/local10_scan43').chmod(0o555)
    freeze(out/'preprocessing/local10_bounds43',Path('/tmp/local10_bounds43').read_bytes());(out/'preprocessing/local10_bounds43').chmod(0o555)
    freeze(out/'INPUT-BINDINGS.json',dict(files={str(path):sha(path) for path in [old/'manifest.json',sample/'sample.jsonl',sample/'config.json',sample/'cursor.json',scan/'scan-input.txt',scan/'passing8.json',scan/'cheap-scan.tsv',scan/'cheap-scan.cursor',scan/'necessary-bounds.tsv',scan/'necessary-bounds.cursor']},
        cpp_cpu_limits=dict(cheap=12,necessary=40),preparation_n5_queries=0))
    freeze(out/'launch-manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    print(json.dumps(dict(status='PREPARED_NO_N5_TARGET_QUERY',cases=12,source_counts=[3]*4,shapes=[c['shape'] for c in cases],points=[c['all_pair_points'] for c in cases],
        p2_passed=193026,differential_controls=len(differential),planted_full_MM=[18,17,64],CPU_seconds=time.process_time()-started)))


if __name__=='__main__':main()
