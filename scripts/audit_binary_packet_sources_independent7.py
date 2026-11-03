"""All-nine shared-core source audit; never dispatches an optimizer."""
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from mmsearch import binary_packet_adapter7 as adapter
from mmsearch.compact_eight43 import expand_core
from mmsearch.verify import verify_candidate
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.marathon7_cancel_poller import CancelPoller
from scripts.verify_record42_independent import verify_bytes
C=adapter.C7;P=C/'binary-block-nine-core-prep-001';PIN='f0487990ecff816bf6f3b51605071f22e35b32c9cc5d0cdfa8b8378daeffb571'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def rank(columns):
    rows={}
    for value in columns:
        while value:
            bit=value.bit_length()-1
            if bit not in rows:rows[bit]=value;break
            value^=rows[bit]
    return len(rows)
def coordinates(value,basis):
    rows={}
    for i,column in enumerate(basis):
        mask=1<<i
        while column:
            bit=column.bit_length()-1
            if bit not in rows:rows[bit]=(column,mask);break
            previous,witness=rows[bit];column^=previous;mask^=witness
    answer=0
    while value:
        bit=value.bit_length()-1
        if bit not in rows:raise ValueError('factor outside sharedimages')
        column,mask=rows[bit];value^=column;answer^=mask
    return answer
def main():
    started=time.monotonic();g=CampaignGuard(30,'2026-11-03T19:24:17Z',guard_state=C/'operations-v3/state.json',campaign_dir=C);g.check('pre_independent_ninecore_qa');poll=CancelPoller(g,lambda:started+30)
    def check():
        if poll.cancelled():poll.force_check('independent_ninecore_qa')
    assert sha((P/'manifest.json').read_bytes())==PIN;manifest=json.loads((P/'manifest.json').read_bytes())
    for name,pin in json.loads((P/'checksums.json').read_bytes()).items():assert sha((P/name).read_bytes())==pin
    source_raw=adapter.pinned(adapter.SOURCE);source=json.loads(source_raw);terms=adapter.literal_terms(source)
    primary=verify_candidate(source,random_trials=0);independent=verify_bytes(source_raw)
    assert primary['valid'] and independent['valid'] and primary['exact_entries_checked']==independent['exact_entries_checked']==15625 and independent['essential_rank']==93
    plan=adapter.select_plan(core_pin_path=P/'manifest.json',core_pin_sha256=PIN)
    assert plan['core_pins_complete'] and len(plan['cases'])==9
    native=json.loads(gzip.decompress(adapter.pinned(adapter.PREP+'/catalog.json.gz')))
    rows=[row for row in native['packets'] if row['branch_metadata']['d']==11]
    assert [row['id'] for row in rows]==[row['id'] for row in plan['cases']]
    receipts=[]
    for index,(row,entry) in enumerate(zip(plan['cases'],manifest['cases'])):
        check();data=adapter.build_packet_data(source,row,production=True);stored=json.loads((P/entry['core_file']).read_bytes())
        assert data==stored and sha(adapter.raw(data))==entry['core_input_sha256']
        basis=row['shared_mode_basis'];assert len(basis)==rank(basis)==11
        products=[tuple(coordinates(v,basis) for v in terms[i]) for i in row['source_indices']]
        assert [list(t) for t in products]==data['original_compact_products']
        core=[sum(((a>>i)&1)*((b>>j)&1)*((c>>k)&1) for a,b,c in products)%2 for i,j,k in itertools.product(range(11),repeat=3)]
        assert core==data['core'] and sha(bytes(core))==entry['core_sha256']
        flat=[]
        for axis in range(3):
            other=[a for a in range(3) if a!=axis];slices=[]
            for a in range(11):
                value=0
                for b,c in itertools.product(range(11),repeat=2):
                    xyz=[0,0,0];xyz[axis]=a;xyz[other[0]]=b;xyz[other[1]]=c
                    value|=core[(xyz[0]*11+xyz[1])*11+xyz[2]]<<(b*11+c)
                slices.append(value)
            flat.append(rank(slices))
        assert flat==[11]*3==entry['actual_mode_ranks']
        ambient=0
        for i in range(25):
            for j in range(25):
                rowbits=0
                for position in row['source_indices']:
                    a,b,c=terms[position]
                    if (a>>i)&(b>>j)&1:rowbits^=c
                ambient|=rowbits<<((i*25+j)*25)
        assert sha(ambient.to_bytes(1954,'little'))==entry['ambient_sha256']
        assert expand_core(core,[11]*3,[basis]*3,25)==ambient
        volumes=[a.bit_count()*b.bit_count()*c.bit_count() for a,b,c in products]
        removed=min(range(15),key=lambda i:(volumes[i],row['source_indices'][i]))
        assert data['removed_local_index']==removed and data['initial_factors']==[list(t) for i,t in enumerate(products) if i!=removed]
        assert data['initial_loss']==volumes[removed]==entry['initial_loss'] and len(data['initial_factors'])==14 and data['full_target_unchanged']
        receipts.append(dict(case=row['id'],source_indices=row['source_indices'],actual_mode_ranks=flat,core_sha256=entry['core_sha256'],ambient_sha256=entry['ambient_sha256'],core_input_sha256=entry['core_input_sha256'],initial_loss=data['initial_loss']))
    assert sha((P/'manifest.json').read_bytes())==PIN;g.check('post_independent_ninecore_qa')
    result=dict(status='PASS_SOURCE_CORES_ONLY',source_sha256=adapter.SOURCE_SHA,all9core_manifest_sha256=PIN,cases=9,case_results=receipts,primary_source_entries=15625,
      independent_source_entries=15625,independent_core_entries_checked=9*1331,full_ambient_entries_checked=9*15625,all_targets_full15_products=True,
      local_target14_slots=True,raw_original_source_indices_preserved=True,initialization='remove single minimumvolume product from initialfactors only; fulltargetunchanged',optimizer_calls=0,solver_calls=0,elapsed_seconds=time.monotonic()-started)
    out=C/'binary-packet-independent-source-qa-v1.json'
    with out.open('x') as stream:json.dump(result,stream,sort_keys=True,indent=2);stream.write('\n')
    out.chmod(0o444);print(json.dumps({k:result[k] for k in ('status','cases','independent_core_entries_checked','full_ambient_entries_checked','optimizer_calls','elapsed_seconds')},sort_keys=True))
if __name__=='__main__':main()
