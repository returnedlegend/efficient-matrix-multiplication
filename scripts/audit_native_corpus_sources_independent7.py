"""Read-only independent selected-native-source/provenance verification."""
import collections
import hashlib
import json
from pathlib import Path
import re
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.marathon7_cancel_poller import CancelPoller
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import verify_bytes

C=ROOT/'artifacts/marathon7_20261103T122417Z'
SOURCE=C/'tensor-code-native-corpus-sources-v1/sources.json'
EXPECTED='9cdc5193b3fc9be8ff111bf46efd3e7990f7f82d8251fd1914ead556b33c5c51'
ANCHORS='26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8'
BASE='cf4644cab66d697f05d6724d919973b9884f17def9586c0e1220b9ea67554e2b'
APPROVAL='7354183ab6e9c89f76110e1c916738ced4856499632a2f317508b1d6bea7bb55'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(value):return sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode())
def read(path):return json.loads(Path(path).read_bytes())
def json_atoms(value):
    assert type(value['dimension']) is int and value['dimension']==5 and type(value['field']) is int and value['field']==2
    terms=[]
    for term in value['terms']:
        assert set(term)=={'u','v','w'}
        for vector in term.values():assert len(vector)==25 and all(type(v) is int and v in (0,1) for v in vector)
        terms.append(tuple(sum(v<<i for i,v in enumerate(term[axis])) for axis in ('u','v','w')))
    assert len(terms)==len(set(terms)) and all(all(t) for t in terms)
    return tuple(sorted(terms))
def native_atoms(raw):
    lines=raw.decode('ascii').splitlines();assert all(re.fullmatch(r'[1-9][0-9]* [1-9][0-9]* [1-9][0-9]*',line) for line in lines)
    terms=tuple(tuple(map(int,line.split())) for line in lines)
    assert terms and terms==tuple(sorted(set(terms))) and all(all(0<v<1<<25 for v in t) for t in terms)
    assert raw==native_bytes(terms)
    return terms
def native_bytes(atoms):return ''.join('%d %d %d\n'%t for t in atoms).encode()
def rank(columns):
    rows={}
    for value in columns:
        while value:
            bit=value.bit_length()-1
            if bit not in rows:rows[bit]=value;break
            value^=rows[bit]
    return len(rows)
def pair(left,right):return sum(right<<(25*i) for i in range(25) if left>>i&1)

def main():
    started=time.monotonic();guard=CampaignGuard(60,'2026-11-03T19:24:17Z',guard_state=C/'operations-v3/state.json',campaign_dir=C)
    guard.check('pre_independent_native_source_qa');poller=CancelPoller(guard,lambda:started+60);pins={}
    def check():
        if poller.cancelled():poller.force_check('independent_native_source_qa')
    def frozen(record):
        path=Path(record['path']);data=path.read_bytes();assert sha(data)==record['sha256'];pins[str(path)]=sha(data);return data
    assert sha(SOURCE.read_bytes())==EXPECTED;manifest=read(SOURCE);auth=manifest['authority']
    assert auth['base_prepared']['sha256']==BASE and auth['anchors']['sha256']==ANCHORS and auth['root_source_approval']['sha256']==APPROVAL
    old=json.loads(frozen(auth['base_prepared']));anchors=json.loads(frozen(auth['anchors']));approval=json.loads(frozen(auth['root_source_approval']))
    assert approval['owner']=='root' and approval['approved_manifest_sha256']==ANCHORS and approval['heldout_evaluation_excluded'] is True
    known={(row['sha256'],row['identity']['rl_source_sha256']):row for row in anchors['known_input_train_states']}
    prohibited=set(anchors['prohibited_identities']['heldout'])|set(anchors['prohibited_identities']['evaluation'])
    expected_runs={'baseline-native300-001','hold-rank-pilot-s01-flag0-K4-D128','hold-rank-pilot-s01-flag1-K4-D128','hold-rank-pilot-s02-flag0-K4-D128','hold-rank-pilot-s02-flag1-K4-D128'}
    assert set(manifest['runs'])==expected_runs
    contexts={}
    for name,run in manifest['runs'].items():
        check();directory=C/name;assert Path(run['directory'])==directory
        m=json.loads(frozen(run['manifest']));summary=json.loads(frozen(run['summary']))
        initial=frozen(run['input']);atoms=json_atoms(json.loads(initial));identity=digest(atoms)
        assert (sha(initial),identity) in known and identity not in prohibited
        assert native_atoms(frozen(run['native_input']))==atoms
        expected_binary=('6e7d6c63fa262bfc50acfe92fbe9c11adb74426e3868a5a6f7ad8d1bf569ac19' if name=='baseline-native300-001' else '3d20e4539cbd9966353629c396ef91cbc3994a5e88773fa51a3f919da6945244')
        assert sha(frozen(run['binary']))==expected_binary==m['binary_sha256']
        cpp={sha(frozen(item)) for item in run['cpp']};assert 'b65f0bda48a0c217d66d65a4db21e286c93448128373c439e8d66c3b8d8c8c1f' in cpp
        if name!='baseline-native300-001':assert '81388f969701b852b11575392d8734ec40f13d56ba5c7aa5e4a50733d2ed0222' in cpp
        for relative,pin in run['runtime_code_sha256'].items():frozen(dict(path=str(Path(run['runtime_root'])/relative),sha256=pin))
        command=summary.get('command',m.get('command'));assert len(command)%2==1 and len(set(command[1::2]))==len(command[1::2])
        args=dict(zip(command[1::2],command[2::2]));assert args['--n']=='5' and args['--target']=='92' and '--pool' not in args
        assert Path(command[0])==Path(run['binary']['path']) and Path(args['--input'])==Path(run['native_input']['path']) and Path(args['--output'])==directory/'native/walk'
        registry=json.loads(frozen(run['export_registry']));contexts[name]=(m,registry)
        if name=='baseline-native300-001':
            ready=json.loads(frozen(run['ready_manifest']));assert ready['runtime_code_sha256']==run['runtime_code_sha256'] and sha(frozen(run['source_audit']))==m['source_audit_sha256']
        else:assert m['runtime_code_sha256']==run['runtime_code_sha256']
    union=set();records=[];counts=collections.Counter();identities=set();pair_hist=collections.Counter()
    for index,record in enumerate(manifest['selected']):
        check();path=Path(record['path']);run=record['run'];m,registry=contexts[run]
        blob=frozen(dict(path=str(path),sha256=record['raw_sha256']))
        if record['kind']=='native-text':
            assert path.parent==C/run/'.raw-native-returns' and registry[record['raw_sha256']]==[record['raw_sha256'],record['rank']]
            atoms=native_atoms(blob)
        else:
            assert record['kind']=='verified-json' and path.parent==C/run/'verified'
            value=json.loads(blob);atoms=json_atoms(value);assert value['metadata']['parent']==m
            entry=next(row for row in registry['certificates'][run] if row[0]==path.stem)
            assert entry[1:3]==[record['raw_sha256'],record['rank']]
            report=json.loads(frozen(dict(path=str(path.with_name(path.stem+'.verification.json')),sha256=entry[3])))
            assert report['valid'] and report['rank']==record['rank'] and report['exact_entries_checked']==15625
        identity=sha(native_bytes(atoms));rl_identity=digest(atoms)
        assert identity==record['identity'] and rl_identity==record['rl_identity'] and rl_identity not in prohibited and identity not in identities
        identities.add(identity);assert type(record['rank']) is int and len(atoms)==record['rank'] and record['rank'] in (93,94)
        candidate=dict(dimension=5,field=2,terms=[{axis:[(t[j]>>i)&1 for i in range(25)] for j,axis in enumerate(('u','v','w'))} for t in atoms])
        primary=verify_candidate(candidate,random_trials=0);strict=verify_bytes(json.dumps(candidate,sort_keys=True).encode())
        assert primary['valid'] and strict['valid'] and primary['exact_entries_checked']==strict['exact_entries_checked']==15625 and strict['essential_rank']==len(atoms)
        pair_ranks=[]
        for axis in range(3):
            other=[j for j in range(3) if j!=axis];pair_ranks.append(rank([pair(t[other[0]],t[other[1]]) for t in atoms]))
        pair_hist[tuple(pair_ranks)]+=1;counts[len(atoms)]+=1;union.update(atoms)
        records.append(dict(index=index,run=run,rank=len(atoms),raw_sha256=record['raw_sha256'],identity=identity,primary_entries=15625,independent_entries=15625,pair_ranks=pair_ranks))
    assert counts=={93:32,94:4} and len(union)==522
    old_atoms={tuple(t) for t in old['atoms']};assert len(union&old_atoms)==224 and len(union-old_atoms)==298
    assert all(sha(Path(path).read_bytes())==pin for path,pin in pins.items()) and sha(SOURCE.read_bytes())==EXPECTED
    guard.check('post_independent_native_source_qa')
    result=dict(status='PASS_SOURCE_SELECTION_AND_PROVENANCE',sources_manifest_sha256=EXPECTED,rank_histogram=dict(counts),selected_sources=36,union_atoms=522,shared_old_atoms=224,new_atoms=298,
                distinct_pair_rank_histogram={str(k):v for k,v in pair_hist.items()},source_results=records,provenance_files_checked=len(pins),input_pins_unchanged=True,
                full_coefficients_checked=36*15625*2,solver_calls=0,decoder_calls=0,dictionary_builds=0,elapsed_seconds=time.monotonic()-started,
                scope='Selected sources/provenance only. Native codepreparation adapter not yet frozen/accepted; no performance or record claim.')
    out=C/'native-corpus-independent-source-qa-v1.json'
    with out.open('x') as stream:json.dump(result,stream,sort_keys=True,indent=2);stream.write('\n')
    out.chmod(0o444);print(json.dumps({k:result[k] for k in ('status','selected_sources','union_atoms','distinct_pair_rank_histogram','provenance_files_checked','elapsed_seconds')},sort_keys=True))


if __name__=='__main__':main()
