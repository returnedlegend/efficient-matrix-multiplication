#!/usr/bin/env python3
"""One exact conditional-C3 attempt for the seven pinned b<=6,d11 packets."""
import argparse
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(REPO))
from scripts import run_binary_block_packets7 as baseline
from mmsearch import conditional_surplus_three7 as decoder
from mmsearch import binary_block_descent7 as block
from mmsearch.binary_packet_adapter7 import C7,SOURCE,SOURCE_SHA,pinned,raw,sha,select_plan as base_plan
from mmsearch.compact_coset43 import mode_slices
from mmsearch.marathon7_cached_guard import CampaignGuard,CampaignHold
from scripts.run_c3_mixed12_pilot7 import run_case as guarded_run_case,freeze

METADATA='c3-surplus3-pair-metadata-nine-v1'
META_PINS={
    'manifest.json':'959b97aaf3e95df8a0933143bf935bdd1cfae7c625b191c22cad7b75a75cb4d9',
    'checksums.json':'e6e2737f3e420059ac4fbb52ae18d7333db6348531aa3780a90f13a95f4bb576',
    'COMPLETE.json':'6ddec5c6cdbc72ce356cfd9a8bfc378a4fa4f01a58ed8ad8352919469eef41d3'}
OUTPUT_CAP=32*1024**2
LIMITS=dict(cpu=1,memory_mib=1024,inner_seconds=230,outer_seconds=260,per_case_seconds=30,
    parent_mode_rank=11,child_mode_rank=12,parent_vectors=2047,parent_cosets=40,
    child_vectors=8191,child_extensions=24573,max_cases=7,max_parent_children=194)


def restrict_plan(base,manifest,metadata,input_pins):
    if not base.get('core_pins_complete') or len(base['cases'])!=9 or len(metadata)!=9:
        raise ValueError('all nine exact source/core and metadata pins required')
    if (manifest.get('input_core_manifest_sha256')!='f0487990ecff816bf6f3b51605071f22e35b32c9cc5d0cdfa8b8378daeffb571'
            or manifest.get('source_sha256')!=SOURCE_SHA or type(manifest.get('decoder_calls')) is not int
            or manifest.get('decoder_calls')!=0):
        raise ValueError('conditional metadata source/core lineage differs')
    selected=[];excluded=[]
    for ordinal,(row,meta) in enumerate(zip(base['cases'],metadata)):
        if (meta['case']!=row['id'] or type(meta['ordinal']) is not int or meta['ordinal']!=ordinal
                or meta['shape']!=[11]*3 or any(type(v) is not int for v in meta['shape'])
                or type(meta['image_rank']) is not int or meta['image_rank']!=11
                or meta['native_core_sha256']!=row['branch_metadata']['actual_core_sha256']
                or meta['input_core_sha256']!=row['branch_metadata']['core_input_sha256']
                or meta['ambient_sha256']!=row['branch_metadata']['ambient_sha256']
                or type(meta['axis']) is not int or meta['axis']!=0):
            raise ValueError('literal metadata/source core binding differs')
        b=meta['backbone_rank'];count=meta['distinct_child_count']
        if type(b) is not int or type(count) is not int or not 0<=b<=11 or not 0<=count<=40:
            raise ValueError('literal backbone rank/parent coset cap required')
        cosets=[int(r['coset_hex'],16) for r in meta['distinct_child_cosets']]
        if len(cosets)!=count or len(set(cosets))!=count or any(x<=0 for x in cosets):
            raise ValueError('metadata coset set incomplete or duplicated')
        applies=b<=6
        if meta['conditional_forced_pair_complete'] is not applies:raise ValueError('conditional bound classification differs')
        if applies:selected.append(dict(row,conditional_metadata=meta))
        else:excluded.append(row['id'])
    if len(selected)!=7 or len(excluded)!=2 or sum(r['conditional_metadata']['distinct_child_count'] for r in selected)!=194:
        raise ValueError('only root-authorized seven parents/194 children')
    return dict(format='conditional-c3-seven-v1',cases=selected,excluded_b7_cases=excluded,
        core_pins_complete=True,source_nine_plan_sha256=base['selected_cases_sha256'],
        selected_cases_sha256=sha(raw(selected)),input_sha256=dict(base['input_sha256'],**input_pins),
        limits=LIMITS,no_extension_of_s6_family=True)


def select_plan(core_pin_path=None,core_pin_sha256=None):
    base=base_plan(core_pin_path=core_pin_path,core_pin_sha256=core_pin_sha256)
    blobs={};input_pins={}
    for name,digest in META_PINS.items():
        payload=(C7/METADATA/name).read_bytes()
        if sha(payload)!=digest:raise ValueError('conditional metadata pin differs: '+name)
        blobs[name]=json.loads(payload);input_pins[METADATA+'/'+name]=digest
    if (blobs['COMPLETE.json']['manifest_sha256']!=META_PINS['manifest.json']
            or blobs['COMPLETE.json']['checksums_sha256']!=META_PINS['checksums.json']):
        raise ValueError('conditional metadata seal differs')
    metadata=[]
    for ordinal in range(9):
        name=f'case-{ordinal:02d}.json';payload=(C7/METADATA/name).read_bytes();digest=sha(payload)
        if digest!=blobs['checksums.json'][name]:raise ValueError('sealed metadata case changed')
        input_pins[METADATA+'/'+name]=digest;metadata.append(json.loads(payload))
    return restrict_plan(base,blobs['manifest.json'],metadata,input_pins)


def implementation_hashes():return baseline.implementation_hashes()


class PacketCache(baseline.PacketCache):
    def core(self,case):
        result=super().core(case);data=result[1];meta=self.rows[case['id']]['conditional_metadata']
        slices,_=mode_slices(data['core'],data['shape'],0)
        if slices!=[int(v,16) for v in meta['raw_slices_hex']]:
            raise ValueError('metadata slice coordinates differ from actual original core')
        self.current_metadata=meta
        return result


def conditional_bridge(cache,*,allow_tiny=False):
    def solve(core,shape,target,axis=0,max_vectors=65535,cancelled=None):
        if not allow_tiny and (shape!=[11]*3 or target!=14 or axis!=0):
            raise ValueError('only root-authorized d11 rank14 axis0 family')
        observation=decoder.solve_core(core,shape,target,axis=axis,
            max_vectors=2047,max_extensions=40,max_child_vectors=8191,max_child_extensions=24573,
            max_mode_rank=11,timeout_seconds=30,cancelled=cancelled,deadline_utc=block.DEADLINE)
        if observation['status']=='SAT':
            products=observation['products'];block._validate(core,shape,products)
            if len(products)>target or block.residual_loss(core,shape,products) or block.scalar_loss(core,shape,products):
                raise ValueError('conditional decoder failed separate full compact checks')
        elif observation['status']=='LOCAL_UNSAT' and observation.get('complete') is True:
            meta=cache.current_metadata;expected=sorted(int(r['coset_hex'],16) for r in meta['distinct_child_cosets'])
            if (observation.get('case')!='all_conditional_repeated_pair_extensions_negative'
                    or observation.get('target_rank')!=11 or observation.get('inside_rank')!=meta['backbone_rank']
                    or observation.get('conditional_pair_theorem_applies') is not True
                    or observation.get('budget')!=14 or observation.get('total_extensions')!=meta['distinct_child_count']
                    or observation.get('extension_cursor')!=len(expected) or observation.get('extension_cosets')!=expected
                    or len(observation.get('tested_extensions',[]))!=len(expected)
                    or sorted(r['coset'] for r in observation['tested_extensions'])!=expected
                    or any(r['status']!='LOCAL_UNSAT' for r in observation['tested_extensions'])
                    or not observation.get('prior_result_sha256')):
                raise ValueError('completed parent proof differs from qualified metadata or misses prior/children')
        elif observation['status']!='UNKNOWN' or observation.get('complete') is not False:
            raise ValueError('unsupported decoder status cannot close a case')
        return observation
    return solve


def run_pilot(out,plan,qa):
    code=implementation_hashes();cpu_started=time.process_time()
    guard=CampaignGuard(230,block.DEADLINE,campaign_dir=C7,guard_state=C7/'operations-v3/state.json')
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    results=[];stop_reason=None
    try:
        guard.check('pre_pilot');cache=PacketCache(plan,guard);solver=conditional_bridge(cache)
        freeze(out/'inputs/source.json',pinned(SOURCE));freeze(out/'source-verifications.json',dict(primary=cache.verified,independent=cache.independent))
        for row in plan['cases']:
            if guard.reason(force=True):break
            if implementation_hashes()!=code:raise ValueError('runtime closure changed')
            if sum(p.stat().st_size for p in out.rglob('*') if p.is_file())>OUTPUT_CAP-3*1024**2:
                raise CampaignHold('storage reserve','pre_case')
            case=dict(id=row['id'],source=SOURCE,source_sha256=SOURCE_SHA,source_products=93,
                source_local_products=15,target_local_products=14,source_indices=row['source_indices'],
                shape=[11]*3,mode_rank=11,free_axis=0,all_pair_points=2047**2,
                prep_ambient_sha256=row['branch_metadata']['ambient_sha256'])
            result=guarded_run_case(cache,case,out,guard,seconds=30,solver=solver)
            result.update(algorithm='exact conditional CPd3 via all repeated-pair LargeS2 children',
                qualified_backbone_rank=row['conditional_metadata']['backbone_rank'],
                expected_parent_children=row['conditional_metadata']['distinct_child_count'])
            if not (out/(case['id']+'.result.json')).exists():freeze(out/(case['id']+'.result.json'),result)
            results.append(result)
            if result['status'] in ('TARGET_EMITTED_TO_GLOBAL_GUARD','ERROR'):break
    except CampaignHold as exc:stop_reason=exc.reason
    except Exception as exc:results.append(dict(status='ERROR',complete=False,error=str(exc),error_type=type(exc).__name__))
    final_reason=guard.reason(force=True);unchanged=implementation_hashes()==code
    emitted=any(r['status']=='TARGET_EMITTED_TO_GLOBAL_GUARD' for r in results)
    all_negative=len(results)==7 and all(r['status']=='LOCAL_UNSAT' and r['complete'] for r in results)
    if final_reason or stop_reason or not unchanged:all_negative=False
    status=('TARGET_EMITTED_TO_GLOBAL_GUARD' if emitted else 'ERROR' if not unchanged or any(r['status']=='ERROR' for r in results)
            else 'ALL_SEVEN_CONDITIONAL_CP14_LOCAL_UNSAT' if all_negative else 'UNKNOWN')
    return dict(status=status,complete=emitted or all_negative,planned_cases=7,attempted_cases=len(results),
        queries_started=sum(bool(r.get('decoder_called')) for r in results),results=results,
        closed_parent_cases=[r['case'] for r in results if r['status']=='LOCAL_UNSAT' and r['complete']],
        excluded_b7_cases=plan['excluded_b7_cases'],global_record_freeze_owned_by_guard=True,
        scope='Only seven pinned d11 b<=6 packets; priorCP13 AND every requiredchildCP14 must complete negative',
        no_global_rank_lower_bound=True,stop_reason=final_reason or stop_reason,
        elapsed_seconds=guard.monotonic()-guard.started,process_cpu_seconds=time.process_time()-cpu_started,
        guard=guard.observation(),implementation_sha256=code,limits=LIMITS,
        selected_cases_sha256=plan['selected_cases_sha256'],qa_report_sha256=sha(raw(qa)))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path);p.add_argument('--qa-report',type=Path);p.add_argument('--qa-sha256')
    p.add_argument('--core-pins',type=Path);p.add_argument('--core-pins-sha256')
    p.add_argument('--authorize-pilot',action='store_true');p.add_argument('--qa-approval',choices=('root-reviewed',));p.add_argument('--preview',action='store_true')
    a=p.parse_args(argv)
    if not a.preview and (not a.authorize_pilot or a.qa_approval!='root-reviewed'):
        print(json.dumps(dict(status='DISABLED',production_inputs_read=False,queries_started=0)));return 0
    plan=select_plan(a.core_pins,a.core_pins_sha256)
    preview=dict(implementation_sha256=implementation_hashes(),selected_cases_sha256=plan['selected_cases_sha256'],
        input_sha256=plan['input_sha256'],limits=LIMITS)
    if a.preview:
        print(json.dumps(dict(status='PREVIEW_NO_QUERY',queries_started=0,**preview),sort_keys=True));return 0
    if a.output_dir is None or a.qa_report is None or not a.qa_sha256:p.error('fresh output and exact independent QA required')
    qa_raw=a.qa_report.read_bytes();qa=json.loads(qa_raw)
    if sha(qa_raw)!=a.qa_sha256 or qa.get('status')!='PASS' or any(qa.get(k)!=v for k,v in preview.items()):
        raise ValueError('QA does not bind exact code, inputs, qualified seven cases and resource scope')
    os.sched_setaffinity(0,{1})
    if os.getpriority(os.PRIO_PROCESS,0)<10:os.nice(10-os.getpriority(os.PRIO_PROCESS,0))
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(OUTPUT_CAP,OUTPUT_CAP));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    out=a.output_dir.resolve()
    if out.exists() or not out.is_relative_to(C7):raise ValueError('fresh C7 output required')
    out.mkdir();freeze(out/'plan.json',plan);freeze(out/'qa-report.json',qa_raw)
    for name,digest in preview['implementation_sha256'].items():
        payload=(REPO/name).read_bytes()
        if sha(payload)!=digest:raise ValueError('code changed while snapshotting')
        freeze(out/'code'/name,payload)
    freeze(out/'launch.json',dict(nice=os.getpriority(os.PRIO_PROCESS,0),pid=os.getpid(),**preview))
    result=run_pilot(out,plan,qa);freeze(out/'summary.json',result)
    freeze(out/'checksums.json',{str(p.relative_to(out)):sha(p.read_bytes()) for p in out.rglob('*') if p.is_file()})
    print(json.dumps(dict(status=result['status'],attempted_cases=result['attempted_cases'],
        closed_parents=len(result['closed_parent_cases']),stop_reason=result['stop_reason'],
        elapsed_seconds=result['elapsed_seconds'],process_cpu_seconds=result['process_cpu_seconds']),sort_keys=True))
    return 2 if result['status']=='ERROR' else 0


if __name__=='__main__':raise SystemExit(main())
