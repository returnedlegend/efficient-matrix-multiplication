"""Static joint span of the previously sealed32 S4 spaces; no optimization."""
import argparse
import collections
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from mmsearch.compact_sat import BinaryBasis
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.marathon7_cancel_poller import CancelPoller
from scripts.audit_c3_cube_space7 import column_basis,intersection_witnesses,seal_check
from scripts.audit_c3_mixed_s4_space7 import (BASE,BASE_DICT,BASE_MANIFEST,CAMPAIGN,
    CAMPAIGN_SHA,CAP,DEADLINE,code_pins,sha)
from scripts.audit_cyclic_tensor_code7 import raw

PREVIOUS=CAMPAIGN/'c3-mixed-s4-space-audit-001'
PREVIOUS_MANIFEST='10fc4f65538ef95ea5920737ac996a0084ea93c5881f586d3133214999d715b9'
OUT=CAMPAIGN/'c3-joint-s4-space-audit-001'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--authorize-static-joint-audit',action='store_true');a=p.parse_args(argv)
    if not a.authorize_static_joint_audit:p.error('explicit root static joint audit authorization required')
    started=time.monotonic();cpu_started=time.process_time()
    if OUT.exists() or sha(CAMPAIGN/'campaign.json')!=CAMPAIGN_SHA:
        raise ValueError('new output/matching campaign required')
    os.sched_setaffinity(0,{1});os.setpriority(os.PRIO_PROCESS,0,10)
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    guard=CampaignGuard(30,DEADLINE,guard_state=CAMPAIGN/'operations-v3/state.json',campaign_dir=CAMPAIGN)
    guard.check('pre_static_inputs');poller=CancelPoller(guard,lambda:started+30)
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    def check(name='loop'):
        if name=='loop':
            if poller.cancelled():poller.force_check(name)
        else:poller.force_check(name)
    def validate_previous():
        if sha(PREVIOUS/'manifest.json')!=PREVIOUS_MANIFEST or (PREVIOUS/'UNKNOWN.json').exists():
            raise ValueError('previous sealed S4 audit differs')
        seal=json.loads((PREVIOUS/'COMPLETE.json').read_bytes())
        if seal['manifest_sha256']!=PREVIOUS_MANIFEST or sha(PREVIOUS/'checksums.json')!=seal['checksums_sha256']:
            raise ValueError('previous audit seal differs')
        receipt=json.loads((PREVIOUS/'manifest.json').read_bytes())
        for item in receipt['all_results']:
            if sha(PREVIOUS/f"spaces/{item['ordinal']:02d}-basis.json")!=item['basis_sha256']:
                raise ValueError('previous24-column basis differs')
        return receipt
    seal_check(BASE,BASE_DICT,BASE_MANIFEST);previous=validate_previous()
    if previous['completed_spaces']!=32:raise ValueError('exact authorized32-space prefix required')
    pins=code_pins();OUT.mkdir();progress={}
    def save(name,value):
        check('pre_publication');payload=raw(value)
        if sum(q.stat().st_size for q in OUT.rglob('*') if q.is_file())+len(payload)>CAP:
            raise RuntimeError('32MiB aggregate audit cap')
        with (OUT/name).open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        check('post_publication')
    def alarm(*_):raise TimeoutError('30s joint static audit alarm')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,max(.001,30-(time.monotonic()-started)))
    try:
        save('config.json',dict(format='c3-joint-s4-static-config-v1',previous_manifest_sha256=PREVIOUS_MANIFEST,
             base_dictionary_sha256=BASE_DICT,base_manifest_sha256=BASE_MANIFEST,max_raw_columns=768,
             seconds=30,cpu=1,nice=10,memory_mib=1024,runtime_code_sha256=pins,
             solver_calls=0,decoding_calls=0,candidate_optimization_calls=0))
        base=json.loads((BASE/'dictionary.json').read_bytes());raw_columns=[];origins=[]
        for item in previous['all_results']:
            check();ordinal=item['ordinal']
            payload=json.loads((PREVIOUS/f'spaces/{ordinal:02d}-basis.json').read_bytes())
            if len(payload)!=24:raise ValueError('exact24-column basis required')
            for index,column in enumerate(payload):
                raw_columns.append(int(column['full_tensor_hex'],16))
                origins.append(dict(space_ordinal=ordinal,column=index))
        if len(raw_columns)!=768:raise ValueError('exact768 rawcolumns required')
        progress['stage']='joint_basis';_,selected=column_basis(raw_columns,check)
        joint=[raw_columns[index] for index in selected]
        save('joint-basis-origins.json',[dict(raw_column_index=index,**origins[index]) for index in selected])
        progress.update(stage='intersection',joint_rank=len(joint))
        check('pre_joint_intersection')
        result=intersection_witnesses([int(v,16) for v in base['full_columns_hex']],joint,check)
        check('post_joint_intersection')
        if result['base_rank']!=201 or result['space_rank']!=len(joint) or result['intersection_dimension']<3:
            raise ValueError('base/joint/cube inclusion rank invariant failed')
        for witness in result['intersection_witnesses']:
            oldmask=int(witness['base_mask_hex'],16);jointmask=int(witness['space_mask_hex'],16)
            old_indices=[i for i in range(len(base['weights'])) if oldmask>>i&1]
            witness.update(old_orbit_indices=old_indices,
                old_orbit_weights=[base['weights'][i] for i in old_indices],
                old_product_weight=sum(base['weights'][i] for i in old_indices),
                contributing_spaces=sorted({origins[selected[j]]['space_ordinal'] for j in range(len(joint)) if jointmask>>j&1}))
        save('rank-intersection-witness.json',result)
        old_forms=[term[0] for term,weight in zip(base['representatives'],base['weights']) if weight==1]
        old_basis=BinaryBasis(old_forms);directions={}
        for index,term in enumerate(base['representatives']):
            for axis,value in enumerate(term):
                residue=value^old_basis.expand(old_basis.coordinates(value))
                if residue:directions.setdefault(residue,dict(base_representative_index=index,factor_axis=axis,external_factor=value))
        selected_residues={int(item['quotient_residue_hex'],16) for item in previous['all_results']}
        if not selected_residues<=directions.keys():raise ValueError('previous direction inventory differs')
        inventory=dict(total_distinct_external_S4_spans=len(directions),tested_spans=32,
             remaining_distinct_spans=len(directions)-32,metadata_only=True,
             remaining=[dict(quotient_residue_hex=hex(residue),**point) for residue,point in directions.items() if residue not in selected_residues])
        save('remaining-direction-inventory.json',inventory)
        validate_previous();seal_check(BASE,BASE_DICT,BASE_MANIFEST)
        if any(sha(ROOT/name)!=digest for name,digest in pins.items()):raise ValueError('runtime code changed')
        dimension=result['intersection_dimension']
        manifest=dict(format='c3-joint-s4-static-audit-v1',status='SEALED_STATIC_AUDIT',
            previous_manifest_sha256=PREVIOUS_MANIFEST,base_dictionary_sha256=BASE_DICT,
            raw_columns=768,joint_rank=len(joint),base_rank=201,union_rank=result['union_rank'],
            intersection_dimension=dimension,joint_family_dominated=dimension==3,
            coupling_potential_only=dimension>3,witness_sha256=sha(OUT/'rank-intersection-witness.json'),
            joint_basis_origins_sha256=sha(OUT/'joint-basis-origins.json'),
            remaining_direction_inventory_sha256=sha(OUT/'remaining-direction-inventory.json'),
            total_distinct_external_S4_spans=len(directions),remaining_distinct_spans=len(directions)-32,
            elapsed_seconds=time.monotonic()-started,process_cpu_seconds=time.process_time()-cpu_started,
            runtime_code_sha256=pins,guard=guard.observation(),poller=poller.metrics(),
            solver_calls=0,decoding_calls=0,candidate_optimization_calls=0,extended_dictionaries_generated=0,
            scope='Joint linear span of these same32 sealedS4 spaces only. Dimension>3 is coupling potential only, not a weight improvement or global target/rank claim. Remaining directions only inventoried.')
        save('manifest.json',manifest)
        save('checksums.json',{q.name:sha(q) for q in OUT.iterdir() if q.is_file()})
        save('COMPLETE.json',dict(manifest_sha256=sha(OUT/'manifest.json'),checksums_sha256=sha(OUT/'checksums.json')))
        for q in OUT.iterdir():
            if q.is_file():q.chmod(0o444)
        print(json.dumps({k:manifest[k] for k in ('status','joint_rank','intersection_dimension','union_rank',
            'joint_family_dominated','total_distinct_external_S4_spans','remaining_distinct_spans','elapsed_seconds','process_cpu_seconds')},sort_keys=True))
        return 0
    except Exception as error:
        with (OUT/'UNKNOWN.json').open('xb') as stream:
            stream.write(raw(dict(status='UNKNOWN_STATIC_AUDIT',reason=type(error).__name__+': '+str(error),progress=progress,solver_calls=0,decoding_calls=0)))
        raise
    finally:signal.setitimer(signal.ITIMER_REAL,0)


if __name__=='__main__':raise SystemExit(main())
