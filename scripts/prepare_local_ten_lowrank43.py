"""Freeze the separate complete lowrank2-span necessary-bound ledger."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import resource
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import read,sha,freeze
from mmsearch.local_ten43 import native_row,mask_indices,source_core,point_domain
from mmsearch.lowrank_span43 import lowrank_span,matrix_rank
from mmsearch.compact_coset43 import mode_slices
from mmsearch.sat_neighborhoods import gf2_rank


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pilot-bundle',type=Path,required=True);p.add_argument('--scan-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--prefix',default='lowrank-span-v2');a=p.parse_args()
    resource.setrlimit(resource.RLIMIT_AS,(1024*1024**2,1024*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(25,26))
    old=a.pilot_bundle.resolve();scan=a.scan_dir.resolve();out=a.output_dir.resolve()
    for name,expected in read(old/'manifest.json')['files'].items():
        if sha(old/name)!=expected:raise ValueError('frozen pilot changed')
    for path,expected in read(old/'INPUT-BINDINGS.json')['files'].items():
        if sha(path)!=expected:raise ValueError('source/preprocessing changed: '+path)
    if list(map(int,(scan/(a.prefix+'.cursor')).read_text().split()))[0]!=229224:raise ValueError('lowrank scan incomplete UNKNOWN')
    plan=read(old/'plan.json');sources=[read(old/f'source-{s}.json') for s in range(4)];pilot={}
    for case in plan['cases']:
        mask=sum(1<<i for i in case['original_source_indices']);pilot[(case['source_id'],mask&((1<<64)-1),mask>>64)]=case['id']
    counts={s:Counter() for s in range(4)};hist=Counter();survivors=[];selected=[];pilot_rows=[];native_rows=0
    lowrank=(scan/(a.prefix+'.tsv')).open();previous=None
    for line in (scan/'necessary-bounds.tsv').open():
        bound=native_row(line)
        if not bound['p2_passed']:continue
        row=list(map(int,next(lowrank).split()));native_rows+=1
        if len(row)!=37 or row[:3]!=[bound['source'],bound['lo'],bound['hi']]:raise ValueError('native bound scope/order mismatch')
        key=tuple(row[:3])
        if previous is not None and key==previous:raise ValueError('duplicate native bound identity')
        previous=key;s=row[0];counts[s]['checked']+=1;bad=False
        for axis in range(3):
            span,tested,points=row[4+axis*11:7+axis*11];witness=[x for x in row[7+axis*11:15+axis*11] if x]
            if span==-1:
                if tested or points or witness:raise ValueError('uncomputed mode has data')
                continue
            if bound['shape'][axis]!=8 or not 0<=span<=8 or gf2_rank(witness)!=span:raise ValueError('lowrank coordinate basis invalid')
            if span<8 and tested!=255:raise ValueError('partial enumeration cannot exclude')
            if not 1<=tested<=255 or not span<=points<=tested:raise ValueError('lowrank counts invalid')
            hist[(axis,span)]+=1;bad|=span<8
        if bool(row[3])!=bad:raise ValueError('exclusion flag mismatch')
        if bad:counts[s]['excluded_rank9']+=1
        else:
            if any(bound['shape'][axis]==8 and row[4+axis*11]!=8 for axis in range(3)):raise ValueError('pass skipped a mode8')
            counts[s]['bound_passed_not_existence']+=1;axis,points=point_domain(bound['shape'])
            survivors.append(' '.join(map(str,[*row[:3],*bound['shape'],axis,points,native_rows-1]))+'\n')
        record=dict(native=row,bound=bound)
        if (native_rows-1)%3001==0 or (bad and not any(x['native'][0]==s and x['native'][3] for x in selected)):selected.append(record)
        if key in pilot:record['pilot_id']=pilot[key];pilot_rows.append(record);selected.append(record)
    if next(lowrank,None) is not None or native_rows!=193026 or sum(v['excluded_rank9'] for v in counts.values())!=81421 or len(survivors)!=111605:raise ValueError('complete lowrank count mismatch')
    differential=[];pilot_results=[]
    for record in selected:
        row=record['native'];bound=record['bound'];source,lo,hi=row[:3];data,_=source_core(sources[source],mask_indices(lo,hi));mode_controls=[]
        for axis in range(3):
            span,tested,points=row[4+axis*11:7+axis*11]
            if span<0:continue
            reference=lowrank_span(data['core'],data['shape'],9,axis)
            if reference['lowrank_span_rank']!=span or (span<8 and reference['lowrank_points']!=points) or reference['lowrank_points']<points:raise ValueError('native/Python lowrank mismatch')
            slices,other=mode_slices(data['core'],data['shape'],axis)
            for coordinate in row[7+axis*11:15+axis*11]:
                matrix=0
                for bit,slice in enumerate(slices):
                    if coordinate>>bit&1:matrix^=slice
                if matrix_rank(matrix,data['shape'][other[0]],data['shape'][other[1]])>2:raise ValueError('native lowrank witness not rank<=2')
            mode_controls.append(dict(axis=axis,native_span_rank=span,native_points_tested=tested,reference=reference))
        checked=dict(source=source,mask_lo=lo,mask_hi=hi,native_excluded=bool(row[3]),modes=mode_controls,status='PASS')
        differential.append(checked)
        if 'pilot_id' in record:
            checked=dict(checked,pilot_id=record['pilot_id']);pilot_results.append(checked)
    if len(pilot_results)!=12 or any(r['native_excluded'] for r in pilot_results):raise ValueError('unexpected pilot bound scope/outcome')
    out.mkdir(parents=True,exist_ok=False)
    for s in range(4):freeze(out/f'source-{s}.json',(old/f'source-{s}.json').read_bytes())
    freeze(out/'survivors.tsv.gz',gzip.compress(''.join(survivors).encode(),compresslevel=1,mtime=0))
    freeze(out/'native-lowrank-ledger.tsv.gz',gzip.compress((scan/(a.prefix+'.tsv')).read_bytes(),compresslevel=1,mtime=0))
    freeze(out/'preprocessing/necessary-bounds.tsv.gz',gzip.compress((scan/'necessary-bounds.tsv').read_bytes(),compresslevel=1,mtime=0))
    freeze(out/'preprocessing/scan-input.txt',(scan/'scan-input.txt').read_bytes());freeze(out/'preprocessing/native.cursor',(scan/(a.prefix+'.cursor')).read_bytes())
    for name in ('local10_lowrank_span43.cpp','local10_bounds43.cpp'):freeze(out/'preprocessing'/name,(ROOT/'native'/name).read_bytes())
    freeze(out/'preprocessing/local10_lowrank_span43',Path('/tmp/local10_lowrank_span43').read_bytes());(out/'preprocessing/local10_lowrank_span43').chmod(0o555)
    for path in (old/'runtime').rglob('*.py'):freeze(out/'runtime'/path.relative_to(old/'runtime'),path.read_bytes())
    freeze(out/'runtime/mmsearch/lowrank_span43.py',(ROOT/'mmsearch/lowrank_span43.py').read_bytes())
    freeze(out/'runtime/tests/test_lowrank_span43.py',(ROOT/'tests/test_lowrank_span43.py').read_bytes());freeze(out/'runtime/tests/__init__.py',b'')
    freeze(out/'runtime/prepare_local_ten_lowrank43.py',Path(__file__).read_bytes())
    proof=old.parent/'lowrank-span-independent-review-v1'
    for path in proof.rglob('*'):
        if path.is_file():freeze(out/'independent-proof'/path.relative_to(proof),path.read_bytes())
    freeze(out/'NATIVE-DIFFERENTIAL.json',differential);freeze(out/'PILOT12-BOUND-CONTROLS.json',pilot_results)
    ready=dict(status='COMPLETE_NECESSARY_BOUND_PASS_NO_DECOMPOSITION_QUERY',input_candidates=193026,excluded_rank9=81421,bound_passed_not_existence=111605,
        source_counts={s:dict(v) for s,v in counts.items()},mode_span_rank_histogram={str(k):v for k,v in hist.items()},native_CPU_seconds=read(scan/(a.prefix+'.report.json'))['CPU_seconds'],
        all_pilot12_pass=True,native_python_differential_cases=len(differential),source_pilot_bundle=str(old),source_pilot_manifest_sha256=sha(old/'manifest.json'),
        native_input_sha256=sha(scan/'necessary-bounds.tsv'),native_ledger_sha256=sha(scan/(a.prefix+'.tsv')),survivor_catalog_sha256=sha(out/'survivors.tsv.gz'),
        row_schema='source lo hi shape0 shape1 shape2 freeaxis pairpointdomain native-row-ordinal',
        negative_rule='At least one mode8 has rank<8 among coordinate vectors of ALL255 nonzeroS matrices of matrixrank<=2.',
        pass_rule='Every mode8 has eight independent explicit rank<=2 witnesses; passing is necessary only.',
        cutoff='Complete finite193026case pass. No pending cursor/timeout. No rank-one dictionary point/decomposition query.',production_decomposition_queries=0,queue_edits=0)
    freeze(out/'READY.json',ready);freeze(out/'README.md',b'''# Separate low-matrix-rank span necessary bound

For a rank-d mode image S, a CP decomposition of length<=d+c gives an independent opposite rank-one basis Q of size r<=d+c containing S. Quotienting Q by S leaves k=r-d<=c dimensions. Relative to k independent quotient columns, each remaining column gives one independent S-vector using<=k+1 rank-one matrices. Thus matrices of rank<=c+1 must span S. Here d8,target9,c1: all rank<=2 points must span8. Failure excludes rank9 exactly on this residual. Passing provides no decomposition or existence evidence.

This immutable pass covers every193,026p1/p2-surviving maxmode8 local10candidate from the recorded449sample8 extensions. It excludes81,421 and retains111,605. Native negative axes exhaust all255nonzeroS points; native passing axes can stop after eight explicit independent lowrank2witnesses. Every mode8 is checked until the first exclusion. -1 mode-span fields mean uncomputed. The compressed native ledger retains coordinate witnesses, tested/accepted-point counts and source masks for deterministic replay from source+core construction. survivors.tsv.gz is an explicit future-bulk catalogue; its row schema is in READY.json. No decomposition query or queue change was made.

All12previouspilot cores pass this necessary bound; their immutable data/worker remain separate. NATIVE-DIFFERENTIAL.json compares sampled real-input results and all12pilot cores against the full-enumeration Python reference and independently checks each native coordinate witness has matrixrank<=2. The independent proof/oracle includes positive CP-derived families, the span(I3)negative, a basis-only unsafe-rejection control and a passing-but-infeasible nonconverse control. Four pure Python control groups run without production model decoding.

Native input and ledger hashes, source/candidate masks and the complete finite cursor are retained. The native CLI is preprocessing only. To replay, decompress preprocessing/necessary-bounds.tsv.gz, use preprocessing/scan-input.txt and the frozen binary with a fresh output prefix and CPU budget. A CPU cutoff is UNKNOWN with next_bound_ordinal; never call a partial pass complete. The supplied pass itself completed. No all-C(93,10), all-image, or unrestricted rank conclusion follows.
''')
    freeze(out/'manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    print(json.dumps(dict(status=ready['status'],excluded=81421,passed_not_existence=111605,differential_cases=len(differential),manifest_sha256=sha(out/'manifest.json'),production_queries=0)))


if __name__=='__main__':main()
