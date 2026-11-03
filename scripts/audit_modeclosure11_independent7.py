"""Independent source/closure/core/queue audit; never invokes a decoder."""
import collections
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
CAMPAIGN=ROOT/'artifacts/marathon7_20261103T122417Z'
BUNDLE=CAMPAIGN/'modeclosure11-ready-v1'
PREP=CAMPAIGN/'modeclosure11-prep-v1'
sys.path.insert(0,str(BUNDLE/'runtime'));sys.path.insert(1,str(ROOT));sys.dont_write_bytecode=True
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.marathon7_cancel_poller import CancelPoller
from mmsearch.marathon7_modeclosure11_runtime import SourceCache,select_plan,tuple_binding
from mmsearch.sat_neighborhoods import factor_masks
from mmsearch.compact_coset43 import mode_slices
from mmsearch.recombine import digest
from scripts.verify_record42_independent import verify_bytes
_spec=importlib.util.spec_from_file_location('independent_actual_queue_validator',ROOT/'scripts/phase_coordinator42_v2.py')
_queue=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_queue)
validate_job=_queue.validate_job


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def rank(vectors):
    pivots={}
    for value in vectors:
        while value:
            bit=value.bit_length()-1
            if bit not in pivots:pivots[bit]=value;break
            value^=pivots[bit]
    return len(pivots)
def expand(columns,mask):
    value=0
    for i,column in enumerate(columns):
        if mask>>i&1:value^=column
    return value
def member(value,columns):
    pivots={}
    for column in columns:
        while column:
            bit=column.bit_length()-1
            if bit not in pivots:pivots[bit]=column;break
            column^=pivots[bit]
    while value:
        bit=value.bit_length()-1
        if bit not in pivots:return False
        value^=pivots[bit]
    return True
def pair(left,right):return sum(right<<(i*25) for i in range(25) if left>>i&1)


def main():
    started=time.monotonic();guard=CampaignGuard(90,'2026-11-03T19:24:17Z',guard_state=CAMPAIGN/'operations-v3/state.json',campaign_dir=CAMPAIGN)
    guard.check('pre_independent_qa');poller=CancelPoller(guard,lambda:started+90)
    def check():
        if poller.cancelled():poller.force_check('independent_qa')
    before={str(p.relative_to(ROOT)):sha(p) for p in [BUNDLE/'manifest.json',PREP/'manifest.json',BUNDLE/'runtime/marathon7_modeclosure11_campaign.py',BUNDLE/'runtime/mmsearch/marathon7_modeclosure11_runtime.py']}
    assert sha(BUNDLE/'manifest.json')=='76e3fd35fa2baf9df9d92d05449ba0694833a09e8d44f137b39817f8ae1f8aec'
    assert sha(PREP/'manifest.json')=='be5cf0a9c05e9eb7fde60df3f9b84bb4f55140424fd4b801edfbe47c97a0f433'
    checked_files=0
    for directory in [PREP,BUNDLE]:
        for name,expected in read(directory/'manifest.json')['files'].items():
            check();assert sha(directory/name)==expected;checked_files+=1
    inputs=read(PREP/'INPUT-PLAN.json');parent=Path(inputs['parent']);pm=read(parent/'manifest.json')
    assert sha(parent/'manifest.json')==inputs['parent_manifest_sha256']
    assert sha(parent/'survivors.tsv.gz')==inputs['catalog_sha256']==pm['files']['survivors.tsv.gz']
    rows=[list(map(int,line.split())) for line in gzip.decompress((parent/'survivors.tsv.gz').read_bytes()).decode().splitlines()]
    assert len(rows)==111605
    # Recompute the seed/order without importing preparation or any decoder.
    import random
    selected=[];groups=[]
    for s in range(4):
        source=sorted([r for r in rows if r[0]==s],key=lambda r:(r[7],sum(r[3:6]),r[3:6],r[2],r[1]))
        cut=max(8,len(source)//4);rng=random.Random(7121109+s)
        groups.append(rng.sample(source[:cut],8)+rng.sample(source[cut:],8))
    selected=[groups[s][i] for i in range(16) for s in range(4)]
    assert selected==inputs['parents']
    certificates=read(PREP/'SOURCE-CERTIFICATES.json');terms={};source_results=[]
    for s in range(4):
        check();path=BUNDLE/f'source-{s}.json'
        assert sha(path)==sha(parent/path.name)==inputs['source_sha256'][str(s)]==pm['files'][path.name]
        source=read(path);literal=[tuple(sum((bit%2)<<i for i,bit in enumerate(term[axis])) for axis in ('u','v','w')) for term in source['terms']]
        terms[s]=factor_masks(source);assert terms[s]==literal and len(literal)==len(set(literal))==93
        strict=verify_bytes(path.read_bytes());assert strict['valid'] and strict['essential_rank']==93 and strict['exact_entries_checked']==15625
        cert=certificates[s];assert cert['source_id']==s and cert['source_sha256']==sha(path)
        for axis,record in enumerate(cert['opposite_pair_certificates']):
            other=[j for j in range(3) if j!=axis];columns=[pair(t[other[0]],t[other[1]]) for t in literal]
            assert columns==[int(v,16) for v in record['original_columns']]
            basis=[int(v,16) for v in record['basis']];coords=[int(v,16) for v in record['original_coordinates']]
            assert rank(columns)==rank(basis)==93
            assert all(expand(basis,mask)==value for mask,value in zip(coords,columns))
        source_results.append(dict(source=s,sha256=sha(path),strict_entries=15625,pair_ranks=[93]*3))
    closures=read(PREP/'PARENT-CLOSURES.json');assert len(closures)==64
    expected_cases={};hist=collections.Counter();raw=0
    for ordinal,(row,closure) in enumerate(zip(selected,closures)):
        check();s,lo,hi=row[:3];mask=lo|(hi<<64);ids=[i for i in range(93) if mask>>i&1]
        assert len(ids)==10 and ids==closure['parent_indices'] and closure['source_id']==s and closure['parent_ordinal']==ordinal
        bases=[[terms[s][i][axis] for i in ids] for axis in range(3)]
        assert [rank(v) for v in bases]==row[3:6]==closure['shape']
        expected=[i for i,t in enumerate(terms[s]) if all(member(t[a],bases[a]) for a in range(3))]
        assert expected==[p['source_index'] for p in closure['closure']]
        assert set(ids)<=set(expected)
        for record in closure['basis_witnesses']:
            axis=record['axis'];original=[terms[s][i][axis] for i in record['original_independent_indices']]
            assert rank(original)==len(original)==len(record['basis'])
            assert all(expand(original,mask)==value for mask,value in zip(record['basis_from_original_coordinates'],record['basis']))
        for point in closure['closure']:
            assert [expand(closure['basis_witnesses'][axis]['basis'],point['factor_coordinates'][axis]) for axis in range(3)]==list(terms[s][point['source_index']])
        hist[len(expected)]+=1;raw+=93-len(ids)
        for added in sorted(set(expected)-set(ids)):
            fullids=sorted(ids+[added]);key=(s,sum(1<<i for i in fullids))
            expected_cases.setdefault(key,dict(parent_ordinal=ordinal,added=added,ids=fullids))
    assert dict(hist)=={10:55,11:9} and raw==5312 and len(expected_cases)==9
    selection=select_plan(BUNDLE,'000');cases=selection['cases'];assert len(cases)==9
    actualkeys={(case['source_id'],case['mask_lo']|(case['mask_hi']<<64)) for case in cases}
    assert actualkeys==set(expected_cases)
    origins=read(BUNDLE/'CASE-ORIGINS.json');cache=SourceCache(BUNDLE);core_results=[]
    for case,origin in zip(cases,origins):
        check();key=(case['source_id'],case['mask_lo']|(case['mask_hi']<<64));e=expected_cases[key]
        assert case['source_indices']==e['ids'] and origin['parent_ordinal']==e['parent_ordinal'] and origin['added_source_index']==e['added']
        assert origin['case']==case['id']
        source,data,verified,sourcehash,corehash,inputhash=cache.core(case)
        assert all(case[k]==v for k,v in tuple_binding(terms[case['source_id']],case['source_indices']).items())
        canonical=sorted(terms[case['source_id']]);selectedtuples=[terms[case['source_id']][i] for i in case['source_indices']]
        assert sorted(selectedtuples)==[canonical[i] for i in case['canonical_source_indices']]
        assert [rank(mode_slices(data['core'],data['shape'],a)[0]) for a in range(3)]==case['shape']
        assert max(case['shape'])==8 and len(case['source_indices'])==11 and case['target_local_products']==10
        core_results.append(dict(case=case['id'],shape=case['shape'],core_math_sha256=corehash,core_input_sha256=inputhash,ambient_entries_checked=15625))
    job=read(BUNDLE/'PROPOSED-JOB.json');validate_job(job)
    assert set(job)=={'id','enabled','cpu','memory_mb','seconds','command'} and not job['enabled']
    assert (job['cpu'],job['memory_mb'],job['seconds'])==(1,1024,230)
    control=read(CAMPAIGN/'modeclosure11-n4-control-v1/summary.json')
    assert control['status']=='SMALL_CONTROL_PASSED' and control['queries_this_invocation']==1
    receipt=control['results'][0];cp=CAMPAIGN/'modeclosure11-n4-control-v1'/receipt['result_file'];assert sha(cp)==receipt['result_sha256']
    cr=read(cp);assert cr['algorithm_case']=='repeated_coset_pair_extension'
    primary=read(CAMPAIGN/'modeclosure11-n4-control-v1/SMALL_CONTROL.verification.json');strict=read(CAMPAIGN/'modeclosure11-n4-control-v1/SMALL_CONTROL.independent.json')
    assert primary['rank']==63 and primary['valid'] and primary['exact_entries_checked']==4096 and strict['mismatch_count']==0 and strict['output_bits_checked']==4096
    assert all(sha(ROOT/name)==pin for name,pin in before.items());guard.check('post_independent_qa')
    result=dict(status='PASS',pinned_files_checked=checked_files,parents=64,raw_source_memberships=raw,closure_size_histogram=dict(hist),unique_new_11_masks=9,
      source_results=source_results,actual_core_results=core_results,n4_control=dict(status=control['status'],global_rank=63,primary_entries=4096,independent_entries=4096),
      actual_job_validator=True,optional_filter_called=False,production_n5_decoder_calls=0,solver_calls=0,pins_unchanged=True,pins=before,elapsed_seconds=time.monotonic()-started,
      scope='Only nine new11-to10 fixed-outside residuals; no old10-to9 negative transfer or global lower bound.')
    path=CAMPAIGN/'modeclosure11-independent-prep-qa-v1.json'
    with path.open('x') as stream:json.dump(result,stream,sort_keys=True,indent=2);stream.write('\n')
    path.chmod(0o444);print(json.dumps({k:result[k] for k in ('status','pinned_files_checked','parents','raw_source_memberships','unique_new_11_masks','elapsed_seconds','production_n5_decoder_calls')},sort_keys=True))


if __name__=='__main__':main()
