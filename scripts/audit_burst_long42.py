"""Read-only exact audit of completed burst exports; no search or publication.

Uses the frozen independent checker's strict parser/canonicalization. Tensor
evaluation here independently packs all 25 trace-output bits for each of the
625 input-basis pairs. No search, tensor or existing primary verifier imports.
"""
from __future__ import annotations
import argparse,collections,functools,hashlib,json,pathlib,sys,time
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.verify_record42_independent import parse_certificate,canonical_terms,verify_bytes

def sha(raw):return hashlib.sha256(raw).hexdigest()
def raw_json(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def masks(canonical):return tuple(sorted(tuple(sum(bit<<i for i,bit in enumerate(vector)) for vector in term) for term in canonical))
def term_hash(terms):return sha(''.join(f'{a} {b} {c}\n' for a,b,c in sorted(terms)).encode())

def exact_check(raw):
    parsed=parse_certificate(raw);canonical,zeros=canonical_terms(parsed);terms=masks(canonical)
    rows=[0]*625
    for u,v,w in terms:
        ubits=u
        while ubits:
            bit=ubits&-ubits;a=bit.bit_length()-1;ubits^=bit;vbits=v
            while vbits:
                bit=vbits&-vbits;b=bit.bit_length()-1;vbits^=bit;rows[a*25+b]^=w
    mismatches=observed=0
    for first in range(25):
        i,j=divmod(first,5)
        for second in range(25):
            k,l=divmod(second,5);expected=(1<<(l*5+i)) if j==k else 0
            actual=rows[first*25+second];mismatches+=(actual^expected).bit_count();observed+=actual.bit_count()
    report=dict(valid=mismatches==0,essential_rank=len(terms),mismatch_count=mismatches,
                basis_input_pairs_checked=625,exact_entries_checked=15625,observed_one_bits=observed,
                expected_one_bits=125,zero_input_products=zeros,nominal_input_products=len(parsed),
                duplicate_products_cancelled=len(parsed)-zeros-len(terms),candidate_source_sha256=sha(raw),
                term_set_sha256=term_hash(terms),record_eligible=mismatches==0 and len(terms)<=92,
                method='strict independent parser; exact 625 rows of25 trace-output bits')
    if report['record_eligible']:
        scalar=verify_bytes(raw)
        if not scalar['record_eligible'] or scalar['essential_rank']!=len(terms):raise ValueError('record scalar checker disagrees')
        report['independent_scalar_record_recheck']=scalar
    return terms,report

def rank(rows):
    basis={}
    for x in rows:
        while x:
            p=x.bit_length()-1
            if p not in basis:basis[p]=x;break
            x^=basis[p]
    return len(basis)

@functools.lru_cache(maxsize=32768)
def matrix_rank(mask):return rank((mask>>(5*i))&31 for i in range(5))

def structure(terms):
    histogram=collections.Counter('/'.join(str(matrix_rank(mask)) for mask in term) for term in terms)
    merged=[];groups=[]
    for a,b,c in [(0,1,2),(1,2,0),(2,0,1)]:
        pairs={}
        for term in terms:pairs[term[a],term[b]]=pairs.get((term[a],term[b]),0)^term[c]
        groups.append(len(pairs));merged.append(sum(bool(value) for value in pairs.values()))
    return dict(joint_factor_rank_histogram=dict(sorted(histogram.items())),factor_span_ranks=[rank(t[i] for t in terms) for i in range(3)],
                fixed_pair_group_counts_uv_vw_wu=groups,merged_active_counts_uv_vw_wu=merged)

def audit_batch(run,offset,count):
    start=time.process_time();summary_raw=(run/'summary.json').read_bytes();summary=json.loads(summary_raw)
    items=list(summary['exported_certificates'].items())[offset:offset+count];certificates={};rank_counts=collections.Counter();hist_counts=collections.Counter()
    for identity,item in items:
        path=pathlib.Path(item['path']);assert path.parent==run/'verified'
        raw=path.read_bytes();assert sha(raw)==item['sha256'];terms,report=exact_check(raw)
        assert report['valid'] and report['term_set_sha256']==identity and report['essential_rank']==item['rank'] and not report['record_eligible']
        details=structure(terms);rank_counts[str(len(terms))]+=1;hist=json.dumps(details['joint_factor_rank_histogram'],sort_keys=True,separators=(',',':'));hist_counts[hist]+=1
        metadata=json.loads(raw).get('metadata',{});parent=metadata.get('parent',{});phase=parent.get('phase')
        assert type(phase) is int and phase in range(len(summary['phases']))
        certificates[identity]=dict(path=str(path),raw_sha256=sha(raw),essential_rank=len(terms),phase=phase,
            source_term_hash=summary['phases'][phase]['source']['term_hash'],independent_check=report,**details)
    return dict(format='burst-long42-independent-audit-batch-v1',run=str(run),summary_sha256=sha(summary_raw),offset=offset,count=count,
                checked=len(items),exact_entries_checked=15625*len(items),rank_counts=dict(rank_counts),histogram_counts=dict(hist_counts),
                certificates=certificates,audit_cpu_seconds=time.process_time()-start,production_queries_started=0)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=pathlib.Path,required=True);p.add_argument('--offset',type=int,required=True);p.add_argument('--count',type=int,default=256);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
    if a.offset<0 or not 1<=a.count<=512:p.error('nonnegative offset and count1..512 required')
    result=audit_batch(a.run.resolve(),a.offset,a.count);a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('xb') as stream:stream.write(raw_json(result))
    print(json.dumps({k:result[k] for k in ['offset','checked','exact_entries_checked','rank_counts','audit_cpu_seconds']},sort_keys=True))
if __name__=='__main__':main()
