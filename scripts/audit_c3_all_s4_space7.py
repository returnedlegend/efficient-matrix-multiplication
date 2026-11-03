"""One authorized all346-S4 joint linear-space audit, no optimization."""
import argparse
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from mmsearch import cyclic_tensor_code7 as c
from mmsearch.compact_sat import BinaryBasis
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.marathon7_cancel_poller import CancelPoller
from scripts.audit_c3_cube_space7 import column_basis,intersection_witnesses,seal_check
from scripts.audit_c3_mixed_s4_space7 import (BASE,BASE_DICT,BASE_MANIFEST,CAMPAIGN,CAMPAIGN_SHA,CAP,DEADLINE,code_pins,sha)
from scripts.audit_cyclic_tensor_code7 import independent_orbit_tensor,raw
OUT=CAMPAIGN/'c3-all-s4-space-audit-001'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--authorize-all346-static-audit',action='store_true');a=p.parse_args(argv)
    if not a.authorize_all346_static_audit:p.error('explicit root-authorized all346 static audit required')
    started=time.monotonic();cpu_started=time.process_time()
    if OUT.exists() or sha(CAMPAIGN/'campaign.json')!=CAMPAIGN_SHA:raise ValueError('new output/matching campaign required')
    os.sched_setaffinity(0,{1});os.setpriority(os.PRIO_PROCESS,0,10)
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    guard=CampaignGuard(60,DEADLINE,guard_state=CAMPAIGN/'operations-v3/state.json',campaign_dir=CAMPAIGN)
    guard.check('pre_static_inputs');poller=CancelPoller(guard,lambda:started+60)
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    def check(name='loop'):
        if name=='loop':
            if poller.cancelled():poller.force_check(name)
        else:poller.force_check(name)
    seal_check(BASE,BASE_DICT,BASE_MANIFEST);pins=code_pins();OUT.mkdir();progress={'completed_spaces':0,'raw_columns':0}
    def save(name,value):
        check('pre_publication');payload=raw(value)
        if sum(q.stat().st_size for q in OUT.iterdir() if q.is_file())+len(payload)>CAP:raise RuntimeError('32MiB aggregate audit cap')
        with (OUT/name).open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        check('post_publication')
    def alarm(*_):raise TimeoutError('60s all346 static audit alarm')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,max(.001,60-(time.monotonic()-started)))
    try:
        save('config.json',dict(format='c3-all346-s4-static-config-v1',base_dictionary_sha256=BASE_DICT,base_manifest_sha256=BASE_MANIFEST,
             max_factor_spans=346,max_raw_columns=8304,seconds=60,cpu=1,nice=10,memory_mib=1024,output_bytes=CAP,runtime_code_sha256=pins,
             solver_calls=0,decoder_calls=0,optimization_calls=0))
        base=json.loads((BASE/'dictionary.json').read_bytes());forms=[t[0] for t,w in zip(base['representatives'],base['weights']) if w==1]
        if forms!=[4096,262208,16777217] or base['rank']!=201:raise ValueError('approved oldcube/base span differs')
        factor_basis=BinaryBasis(forms);seen=set();directions=[]
        for index,term in enumerate(base['representatives']):
            for axis,value in enumerate(term):
                residue=value^factor_basis.expand(factor_basis.coordinates(value))
                if residue and residue not in seen:
                    seen.add(residue);directions.append(dict(ordinal=len(directions),base_representative_index=index,factor_axis=axis,external_factor=value,quotient_residue_hex=hex(residue)))
        if len(directions)!=346:raise ValueError('exact previously inventoried346 directions required')
        previous=json.loads((CAMPAIGN/'c3-mixed-s4-space-audit-001/directions.json').read_bytes())
        if [d['quotient_residue_hex'] for d in directions[:32]]!=[d['quotient_residue_hex'] for d in previous]:raise ValueError('previous prefix order differs')
        save('directions.json',directions)
        descriptors=[coords[0] for coords in c.coordinate_orbits(4)];pivots={};joint=[];origins=[]
        for direction in directions:
            basis_forms=forms+[direction['external_factor']];space=[]
            for index,descriptor in enumerate(descriptors):
                check();coords=(descriptor//16,descriptor//4%4,descriptor%4);term=tuple(basis_forms[i] for i in coords)
                original=c.orbit_tensor(term,5);space.append(original)
                if direction['ordinal']==0 and original!=independent_orbit_tensor(c.orbit(term,5),25):raise ValueError('independent first-space fullcoefficients differ')
                value=original
                while value:
                    bit=value.bit_length()-1
                    if bit not in pivots:
                        pivots[bit]=value;joint.append(original)
                        origins.append(dict(space_ordinal=direction['ordinal'],space_column=index,coordinate_representative=coords,factor_representative=term,full_tensor_hex=hex(original)))
                        break
                    value^=pivots[bit]
                progress['raw_columns']+=1
            if len(column_basis(space,check)[0])!=24:raise ValueError('dependentS4 invariant basis')
            progress['completed_spaces']+=1
        if progress!={'completed_spaces':346,'raw_columns':8304}:raise ValueError('incomplete finitepool census')
        check('pre_joint_intersection');result=intersection_witnesses([int(v,16) for v in base['full_columns_hex']],joint,check);check('post_joint_intersection')
        cubes=[i for i,w in enumerate(base['weights']) if w==1];cube_columns=[int(base['full_columns_hex'][i],16) for i in cubes]
        cube_span={}
        for mask in range(8):
            value=0
            for i,col in enumerate(cube_columns):
                if mask>>i&1:value^=col
            cube_span[value]=mask
        noncube=0
        for witness in result['intersection_witnesses']:
            oldmask=int(witness['base_mask_hex'],16);smask=int(witness['space_mask_hex'],16);tensor=int(witness['tensor_hex'],16)
            ids=[i for i in range(len(base['weights'])) if oldmask>>i&1]
            witness.update(old_orbit_indices=ids,old_orbit_weights=[base['weights'][i] for i in ids],old_product_weight=sum(base['weights'][i] for i in ids),
                           contributing_spaces=sorted({origins[i]['space_ordinal'] for i in range(len(joint)) if smask>>i&1}))
            if tensor in cube_span:
                mask=cube_span[tensor];witness.update(normalized_cube_mask_hex=hex(mask),normalized_cube_indices=[cubes[i] for i in range(3) if mask>>i&1],normalized_cube_product_weight=mask.bit_count())
            else:noncube+=1
        if result['base_rank']!=201 or result['space_rank']!=len(joint) or result['intersection_dimension']<3:raise ValueError('base/joint/cube rank invariant failed')
        save('joint-independent-basis.json',origins);save('rank-intersection-witness.json',result)
        seal_check(BASE,BASE_DICT,BASE_MANIFEST)
        if any(sha(ROOT/name)!=pin for name,pin in pins.items()):raise ValueError('runtime changed during audit')
        dimension=result['intersection_dimension']
        if dimension==3 and noncube:raise ValueError('three-dimensional intersection differs fromoldcubes')
        manifest=dict(format='c3-all346-s4-static-audit-v1',status='SEALED_STATIC_AUDIT',base_dictionary_sha256=BASE_DICT,base_manifest_sha256=BASE_MANIFEST,
            factor_spans=346,raw_columns=8304,joint_rank=len(joint),base_rank=201,union_rank=result['union_rank'],intersection_dimension=dimension,
            noncube_intersection_basis_witnesses=noncube,joint_family_dominated=dimension==3,coupling_potential_only=dimension>3,
            independent_first_space_entries_checked=375000,joint_basis_sha256=sha(OUT/'joint-independent-basis.json'),witness_sha256=sha(OUT/'rank-intersection-witness.json'),
            directions_sha256=sha(OUT/'directions.json'),runtime_code_sha256=pins,guard=guard.observation(),poller=poller.metrics(),
            elapsed_seconds=time.monotonic()-started,process_cpu_seconds=time.process_time()-cpu_started,solver_calls=0,decoder_calls=0,optimization_calls=0,extended_dictionaries_generated=0,
            scope='Joint invariant linear span ofall346 finite approvedbase-factorS4 spaces. Coupling potential is not an improvement or globaltarget/rank claim. No other factorpool or generalS6 authorized.')
        save('manifest.json',manifest);save('checksums.json',{q.name:sha(q) for q in OUT.iterdir() if q.is_file()});save('COMPLETE.json',dict(manifest_sha256=sha(OUT/'manifest.json'),checksums_sha256=sha(OUT/'checksums.json')))
        for q in OUT.iterdir():
            if q.is_file():q.chmod(0o444)
        print(json.dumps({k:manifest[k] for k in ('status','factor_spans','raw_columns','joint_rank','intersection_dimension','union_rank','joint_family_dominated','noncube_intersection_basis_witnesses','elapsed_seconds','process_cpu_seconds')},sort_keys=True));return 0
    except Exception as error:
        with (OUT/'UNKNOWN.json').open('xb') as stream:stream.write(raw(dict(status='UNKNOWN_STATIC_AUDIT',reason=type(error).__name__+': '+str(error),progress=progress,solver_calls=0,decoder_calls=0)))
        raise
    finally:signal.setitimer(signal.ITIMER_REAL,0)


if __name__=='__main__':raise SystemExit(main())
