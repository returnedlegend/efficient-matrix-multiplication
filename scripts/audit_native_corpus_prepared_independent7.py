"""Independent arithmetic/seed checks on the new522-atom prepared artifact."""
import collections
import hashlib
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.marathon7_cancel_poller import CancelPoller
C=ROOT/'artifacts/marathon7_20261103T122417Z';P=C/'tensor-code-native-corpus-prep-001'
EXPECTED='2302ae5e82fe7afd1845dd50ffd5c12f17e1efb56b8f4adf1ed09bd31a71e886'
SOURCE_SHA='9cdc5193b3fc9be8ff111bf46efd3e7990f7f82d8251fd1914ead556b33c5c51'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(value):return sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode())
def rank(columns):
    rows={}
    for value in columns:
        while value:
            bit=value.bit_length()-1
            if bit not in rows:rows[bit]=value;break
            value^=rows[bit]
    return len(rows)
def xor(columns,mask):
    answer=0
    for i,column in enumerate(columns):
        if mask>>i&1:answer^=column
    return answer
def main():
    started=time.monotonic();g=CampaignGuard(30,'2026-11-03T19:24:17Z',guard_state=C/'operations-v3/state.json',campaign_dir=C);g.check('pre_prepared_static_qa');poll=CancelPoller(g,lambda:started+30)
    def check():
        if poll.cancelled():poll.force_check('prepared_static_qa')
    raw=(P/'prepared.json').read_bytes();assert sha(raw)==EXPECTED;d=json.loads(raw);receipt=json.loads((P/'result.json').read_bytes())
    assert receipt['complete'] is True and receipt['status']=='NATIVE_CORPUS_PREPARED_NO_OPTIMIZATION' and receipt['prepared_sha256']==EXPECTED
    source=json.loads((C/'tensor-code-native-corpus-sources-v1/sources.json').read_bytes());assert sha((C/'tensor-code-native-corpus-sources-v1/sources.json').read_bytes())==SOURCE_SHA
    for name,pin in json.loads((P/'checksums.json').read_bytes()).items():assert sha((P/name).read_bytes())==pin
    assert d['schema']=='tensor_code7.native_corpus_prepared.v1' and type(d['field']) is int and d['field']==2 and d['dimension']==5
    atoms=[tuple(t) for t in d['atoms']];assert len(atoms)==len(set(atoms))==522 and all(len(t)==3 and all(type(v) is int and 0<v<1<<25 for v in t) for t in atoms)
    columns=[]
    for a,b,c in atoms:
        check();column=0
        for i in range(25):
            for j in range(25):
                if (a>>i)&(b>>j)&1:column|=c<<((25*i+j)*25)
        columns.append(column)
    assert columns==[int(v,16) for v in d['columns_hex']] and digest(atoms)==d['dictionary_sha256'] and digest(d['columns_hex'])==d['columns_sha256']
    target=sum(1<<(((i*5+j)*25+j*5+k)*25+k*5+i) for i in range(5) for j in range(5) for k in range(5))
    assert target==int(d['target_hex'],16);r=rank(columns);kernel=[int(v,16) for v in d['kernel_hex']]
    assert (r,len(kernel),rank(kernel))==(338,184,184) and r+len(kernel)==522
    for value in kernel:
        check();assert value>0 and value>>522==0 and xor(columns,value)==0
    assert any(v.bit_count()%2 for v in kernel) and d['parity_broken'] is True
    seeds=[int(v,16) for v in d['seed_states_hex']];assert len(seeds)==36 and collections.Counter(s.bit_count() for s in seeds)=={93:32,94:4}
    all_atoms=set()
    for i,(seed,record,selected) in enumerate(zip(seeds,d['source_records'],source['selected'])):
        check();weight=seed.bit_count();assert xor(columns,seed)==target and record['rank']==weight and record['raw_sha256']==selected['raw_sha256']
        cert=P/'certificates'/f'seed-{i:02d}-rank{weight}.json';raw_cert=cert.read_bytes();candidate=json.loads(raw_cert)
        terms=tuple(sorted(tuple(sum(v<<j for j,v in enumerate(t[a])) for a in ('u','v','w')) for t in candidate['terms']))
        assert set(terms)=={atoms[j] for j in range(522) if seed>>j&1} and len(terms)==weight
        assert sha(raw_cert)==record['canonical_certificate_sha256']
        identity=sha(''.join('%d %d %d\n'%t for t in terms).encode());assert identity==selected['identity']
        all_atoms.update(terms)
        for checkname in ('primary','independent'):assert record[checkname]['valid'] and record[checkname]['exact_entries_checked']==15625
    assert all_atoms==set(atoms) and sha((P/'prepared.json').read_bytes())==EXPECTED;g.check('post_prepared_static_qa')
    result=dict(status='PASS_PREPARED_STATIC_ARITHMETIC',prepared_sha256=EXPECTED,sources_manifest_sha256=SOURCE_SHA,columns=522,full_column_entries_checked=522*15625,
                exact_rank=338,kernel_dimension=184,independent_kernel_rank=184,full_kernel_syndromes_checked=184,seed_states_checked=36,seed_weights=dict(collections.Counter(s.bit_count() for s in seeds)),
                odd_kernel_direction_present=True,normalized_seed_certificates_match_exact_native_exports=True,solver_calls=0,decoder_calls=0,optimization_calls=0,elapsed_seconds=time.monotonic()-started)
    out=C/'native-corpus-independent-prepared-qa-v1.json'
    with out.open('x') as stream:json.dump(result,stream,sort_keys=True,indent=2);stream.write('\n')
    out.chmod(0o444);print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
