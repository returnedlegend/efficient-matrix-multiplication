"""Exact63-element old wedge-kernel metadata; no decoder/optimization calls."""
import collections
import itertools
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from mmsearch import cyclic_tensor_code7 as c
from mmsearch.compact_sat import image_bases
from mmsearch.compact_eight43 import bits,expand_core,packed_tensor
from mmsearch.compact_coset43 import mode_slices,digest
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.marathon7_cancel_poller import CancelPoller
from scripts.audit_c3_cube_space7 import column_basis,seal_check,xor
from scripts.audit_c3_mixed_s4_space7 import BASE,BASE_DICT,BASE_MANIFEST,CAMPAIGN,CAMPAIGN_SHA,CAP,DEADLINE,code_pins,sha
from scripts.audit_cyclic_tensor_code7 import raw
OUT=CAMPAIGN/'c3-wedge-kernel63-prep-v1'
ORBITS=[135,254,274,136,137,170]


def main():
    started=time.monotonic();cpu_started=time.process_time()
    if OUT.exists() or sha(CAMPAIGN/'campaign.json')!=CAMPAIGN_SHA:raise ValueError('new output/matching campaign required')
    os.sched_setaffinity(0,{1});os.setpriority(os.PRIO_PROCESS,0,10)
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    guard=CampaignGuard(30,DEADLINE,guard_state=CAMPAIGN/'operations-v3/state.json',campaign_dir=CAMPAIGN)
    guard.check('pre_static_kernel63');poller=CancelPoller(guard,lambda:started+30)
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    def check(stage='loop'):
        if stage=='loop':
            if poller.cancelled():poller.force_check(stage)
        else:poller.force_check(stage)
    seal_check(BASE,BASE_DICT,BASE_MANIFEST);pins=code_pins();OUT.mkdir();progress={'cases':0}
    def save(name,value):
        check('pre_publication');payload=raw(value)
        if sum(q.stat().st_size for q in OUT.rglob('*') if q.is_file())+len(payload)>CAP:raise RuntimeError('32MiB aggregate cap')
        path=OUT/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        check('post_publication')
    def alarm(*_):raise TimeoutError('30s kernel63 static preparation alarm')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,max(.001,30-(time.monotonic()-started)))
    try:
        base=json.loads((BASE/'dictionary.json').read_bytes());full=[int(base['full_columns_hex'][i],16) for i in ORBITS]
        if len(column_basis(full)[0])!=6:raise ValueError('original six tensors are not independent')
        oldpath=CAMPAIGN/'tensor-code-prep-001/prepared.json'
        if sha(oldpath)!='cf4644cab66d697f05d6724d919973b9884f17def9586c0e1220b9ea67554e2b':raise ValueError('approvedseedauthority differs')
        old=json.loads(oldpath.read_bytes());atomids={tuple(t):i for i,t in enumerate(old['atoms'])};seeds=[int(v,16) for v in old['seed_states_hex']]
        records=[];hist=collections.Counter();contains=0;ambient_seen=set()
        for mask in range(1,64):
            check();orbitids=[ORBITS[i] for i in range(6) if mask>>i&1];products=[t for i in orbitids for t in c.orbit(base['representatives'][i],5)]
            cost=sum(base['weights'][i] for i in orbitids)
            if len(products)!=len(set(products)) or len(products)!=cost:raise ValueError('oldweightedcost/orbit disjointness differs')
            tensor=xor(full,mask);literal=0
            for term in products:literal^=packed_tensor(term,25)
            if literal!=tensor:raise ValueError('original oldbasisproduct equality failed')
            values=[(tensor>>i)&1 for i in range(15625)];bases=image_bases(values,25);shape=[len(b.vectors) for b in bases]
            core=[0]*(shape[0]*shape[1]*shape[2])
            for term in products:
                coordinates=[b.coordinates(v) for b,v in zip(bases,term)]
                for i,j,k in itertools.product(*(bits(v) for v in coordinates)):core[(i*shape[1]+j)*shape[2]+k]^=1
            if expand_core(core,shape,[b.vectors for b in bases],25)!=tensor:raise ValueError('actualmode compactification failedfullambient equality')
            actual=[len(column_basis(mode_slices(core,shape,a)[0])[0]) for a in range(3)]
            if actual!=shape or len(set(shape))!=1:raise ValueError('actualC3 modeimages inconsistent')
            d=max(shape);target=cost-1
            route='FLATTENING_PROVES_OLD_COST_OPTIMAL' if d>target else 'CP(d)' if target==d else 'CP(d+1)' if target==d+1 else 'CP(d+2)' if target==d+2 and d<=9 else 'UNSUPPORTED_KEEP_UNKNOWN'
            productmask=sum(1<<atomids[t] for t in products) if all(t in atomids for t in products) else None
            eligible=[i for i,seed in enumerate(seeds) if productmask is not None and seed&productmask==productmask]
            contains+=bool(eligible);hist[route]+=1
            ambient_sha=__import__('hashlib').sha256(tensor.to_bytes(1954,'little')).hexdigest()
            if ambient_sha in ambient_seen:raise ValueError('independent6Dspace hasduplicate tensor')
            ambient_seen.add(ambient_sha)
            case=dict(id=f'kernel6-{mask:02x}',kernel_basis_mask_hex=hex(mask),old_orbit_indices=orbitids,old_weight=cost,target=target,shape=shape,mode_rank=d,route=route,
                old_products=[list(t) for t in products],image_bases=[b.vectors for b in bases],core=core,ambient_tensor_hex=hex(tensor),ambient_sha256=ambient_sha,
                core_math_sha256=digest(dict(shape=shape,core=core)),exact_ambient_entries_checked=15625,approved93_seed_indices_containing_old_products=eligible,
                approved_seed_product_mask_hex=hex(productmask) if productmask is not None else None,decoder_called=False,status='CLOSED_BY_FLATTENING' if d>target else 'NOT_QUERIED')
            save(f'cases/{mask:02x}.json',case);records.append({k:v for k,v in case.items() if k not in ('core','image_bases','ambient_tensor_hex','old_products')});progress['cases']=len(records)
        seal_check(BASE,BASE_DICT,BASE_MANIFEST)
        if any(sha(ROOT/name)!=pin for name,pin in pins.items()):raise ValueError('runtime changed')
        save('catalog.json',records)
        manifest=dict(format='c3-wedge-kernel63-static-prep-v1',status='SEALED_METADATA_NO_QUERIES',base_dictionary_sha256=BASE_DICT,basis_orbit_indices=ORBITS,basis_weights=[1,1,1,3,3,3],basis_rank=6,cases=63,
             route_counts=dict(hist),cases_contained_in_approved93_seeds=contains,exact_ambient_entries_checked=63*15625,catalog_sha256=sha(OUT/'catalog.json'),
             runtime_code_sha256=pins,guard=guard.observation(),elapsed_seconds=time.monotonic()-started,process_cpu_seconds=time.process_time()-cpu_started,
             decoder_calls=0,solver_calls=0,optimization_calls=0,scope='Partial tensors Y inoldB; no assumption ofglobalM5source. Nonflattening cases remain unqueried. Any later query requires scoped dedup/tinypositive/late gates; globalcandidate requires genuine seedcontainment andfullpersisted checks.')
        save('manifest.json',manifest);save('checksums.json',{str(q.relative_to(OUT)):sha(q) for q in OUT.rglob('*') if q.is_file()});save('COMPLETE.json',dict(manifest_sha256=sha(OUT/'manifest.json'),checksums_sha256=sha(OUT/'checksums.json')))
        for q in OUT.rglob('*'):
            if q.is_file():q.chmod(0o444)
        print(json.dumps({k:manifest[k] for k in ('status','cases','route_counts','cases_contained_in_approved93_seeds','elapsed_seconds','process_cpu_seconds')},sort_keys=True))
    except Exception as error:
        with (OUT/'UNKNOWN.json').open('xb') as stream:stream.write(raw(dict(status='UNKNOWN_PREPARATION',reason=type(error).__name__+': '+str(error),progress=progress,decoder_calls=0)))
        raise
    finally:signal.setitimer(signal.ITIMER_REAL,0)


if __name__=='__main__':main()
