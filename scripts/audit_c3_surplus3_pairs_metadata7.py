"""Nine d11 rank-one backbones and conditional forced-pair metadata only."""
import collections
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from mmsearch.compact_sat import BinaryBasis
from mmsearch.compact_coset43 import mode_slices,pair_column
from mmsearch.compact_rank2_edges43 import matrix_rank_at_most_two,rank_two_splits,rankone_factors
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.marathon7_cancel_poller import CancelPoller
from scripts.audit_c3_mixed_s4_space7 import CAMPAIGN,CAMPAIGN_SHA,CAP,DEADLINE,code_pins,sha
from scripts.audit_cyclic_tensor_code7 import raw
PREP=CAMPAIGN/'binary-block-nine-core-prep-001'
PREP_SHA='f0487990ecff816bf6f3b51605071f22e35b32c9cc5d0cdfa8b8378daeffb571'
OUT=CAMPAIGN/'c3-surplus3-pair-metadata-nine-v1'


def main():
    started=time.monotonic();cpu_started=time.process_time()
    if OUT.exists() or sha(CAMPAIGN/'campaign.json')!=CAMPAIGN_SHA:raise ValueError('new output/matching campaign required')
    os.sched_setaffinity(0,{3});os.setpriority(os.PRIO_PROCESS,0,10)
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    guard=CampaignGuard(30,DEADLINE,guard_state=CAMPAIGN/'operations-v3/state.json',campaign_dir=CAMPAIGN)
    guard.check('pre_surplus3_metadata');poller=CancelPoller(guard,lambda:started+30)
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    def check(stage='loop'):
        if stage=='loop':
            if poller.cancelled():poller.force_check(stage)
        else:poller.force_check(stage)
    if sha(PREP/'manifest.json')!=PREP_SHA:raise ValueError('all9source/core receipt differs')
    m=json.loads((PREP/'manifest.json').read_bytes())
    for name,pin in json.loads((PREP/'checksums.json').read_bytes()).items():
        if sha(PREP/name)!=pin:raise ValueError('frozen9core file differs')
    if len(m['cases'])!=9:raise ValueError('exact9case scope required')
    pins=code_pins();OUT.mkdir();progress={'completed_cases':0}
    def save(name,value):
        check('pre_publication');payload=raw(value)
        if sum(q.stat().st_size for q in OUT.iterdir() if q.is_file())+len(payload)>CAP:raise RuntimeError('32MiB aggregate metadata cap')
        with (OUT/name).open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        check('post_publication')
    def alarm(*_):raise TimeoutError('30s metadata alarm')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,max(.001,30-(time.monotonic()-started)))
    try:
        save('config.json',dict(format='c3-surplus3-nine-conditional-metadata-v1',input_core_manifest_sha256=PREP_SHA,cpu=3,nice=10,memory_mib=1024,seconds=30,max_cases=9,subspace_vectors_per_case=2047,
          runtime_code_sha256=pins,decoder_calls=0,solver_calls=0,scope='Count/retain rankonebackbones and conditional forcedrank2pair cosets only; noCP13orCP14query.'))
        results=[]
        for ordinal,entry in enumerate(m['cases']):
            check('pre_case');data=json.loads((PREP/entry['core_file']).read_bytes());slices,other=mode_slices(data['core'],data['shape'],0)
            space=BinaryBasis(slices);d=len(space.vectors)
            if data['shape']!=[11]*3 or d!=11:raise ValueError('only pinned actuald11image accepted')
            inside=[];rank_two=[];classes=collections.Counter()
            for coordinates in range(1,2048):
                check();value=space.expand(coordinates);r,_=matrix_rank_at_most_two(value,11,11);classes[r]+=1
                if r==1:
                    left,right=rankone_factors(value,11,11)
                    inside.append(dict(space_coordinates_hex=hex(coordinates),matrix_hex=hex(value),left=left,right=right))
                elif r==2:rank_two.append((coordinates,value))
                elif r!=3:raise ValueError('nonzeroimage classifiedzero')
            b0=BinaryBasis([int(p['space_coordinates_hex'],16) for p in inside]);b=len(b0.vectors);relevant=[];splits=[];candidates={}
            for coordinates,value in rank_two:
                check()
                if coordinates==b0.expand(b0.coordinates(coordinates)):continue
                relevant.append(dict(space_coordinates_hex=hex(coordinates),matrix_hex=hex(value)))
                for split in rank_two_splits(value,11,11):
                    p,q=split['p'],split['q'];coset=p^space.expand(space.coordinates(p))
                    if not coset or coset!=(q^space.expand(space.coordinates(q))) or p^q!=value:raise ValueError('conditionalpair endpoint/coset proof failed')
                    if pair_column(split['p_left'],split['p_right'],11)!=p or pair_column(split['q_left'],split['q_right'],11)!=q:raise ValueError('originalrankone endpoint witness differs')
                    splits.append([hex(coordinates),hex(p),hex(q),split['p_left'],split['p_right'],split['q_left'],split['q_right'],hex(coset)])
                    candidates.setdefault(coset,dict(space_coordinates_hex=hex(coordinates),difference_hex=hex(value),p_hex=hex(p),q_hex=hex(q),
                        p_left=split['p_left'],p_right=split['p_right'],q_left=split['q_left'],q_right=split['q_right']))
            if len(splits)!=3*len(relevant):raise ValueError('complete3split census differs')
            for coset,seed in candidates.items():
                if len(BinaryBasis(space.vectors+[int(seed['p_hex'],16)]).vectors)!=12:raise ValueError('childextensiondimension differs')
            case=dict(case=entry['case'],ordinal=ordinal,input_core_file=str(PREP/entry['core_file']),input_core_sha256=entry['core_input_sha256'],native_core_sha256=entry['core_sha256'],ambient_sha256=entry['ambient_sha256'],
                shape=data['shape'],axis=0,image_rank=d,raw_slices_hex=[hex(v) for v in slices],space_basis_hex=[hex(v) for v in space.vectors],rank_class_counts={str(k):v for k,v in sorted(classes.items())},
                rankone_points=inside,rankone_point_count=len(inside),backbone_rank=b,backbone_coordinate_basis_hex=[hex(v) for v in b0.vectors],
                rank2_difference_count=len(rank_two),rank2_differences_outside_backbone=relevant,relevant_difference_count=len(relevant),all3splits_count=len(splits),
                split_row_fields=['difference_S_coordinates_hex','p_hex','q_hex','p_left','p_right','q_left','q_right','quotient_coset_hex'],all_original_rank2_splits=splits,
                distinct_child_cosets=[dict(coset_hex=hex(coset),seed=seed) for coset,seed in sorted(candidates.items())],distinct_child_count=len(candidates),
                conditional_forced_pair_complete=b<=6,prior_CP_le13_status='NOT_QUERIED',child_CP_le14_status='NOT_QUERIED',
                status='METADATA_ONLY_NO_FEASIBILITY_DECISION',scope='Forcedpair completeness requires b<=6 plus complete priorCP<=13 andcompleteall childdim12CP<=14 decisions. Ifb>=7 retainUNKNOWN; noqueryauthorizedhere.')
            save(f'case-{ordinal:02d}.json',case)
            results.append({k:case[k] for k in ('case','ordinal','image_rank','backbone_rank','rankone_point_count','rank2_difference_count','relevant_difference_count','all3splits_count','distinct_child_count','conditional_forced_pair_complete')})
            progress['completed_cases']=len(results)
        if sha(PREP/'manifest.json')!=PREP_SHA or any(sha(ROOT/name)!=pin for name,pin in pins.items()):raise ValueError('inputs/runtime changed')
        manifest=dict(format='c3-surplus3-nine-metadata-v1',status='SEALED_METADATA_NO_QUERIES',input_core_manifest_sha256=PREP_SHA,source_sha256=m['source_sha256'],cases=9,case_results=results,
            backbone_rank_histogram={str(k):v for k,v in sorted(collections.Counter(r['backbone_rank'] for r in results).items())},
            conditional_complete_cases=sum(r['conditional_forced_pair_complete'] for r in results),distinct_children_total=sum(r['distinct_child_count'] for r in results),
            runtime_code_sha256=pins,elapsed_seconds=time.monotonic()-started,process_cpu_seconds=time.process_time()-cpu_started,guard=guard.observation(),
            decoder_calls=0,solver_calls=0,optimization_calls=0,scope='Only these9pinned d11 sourcecores; noCP<=13/14feasibility query or globalrankclaim.')
        save('manifest.json',manifest);save('checksums.json',{q.name:sha(q) for q in OUT.iterdir() if q.is_file()});save('COMPLETE.json',dict(manifest_sha256=sha(OUT/'manifest.json'),checksums_sha256=sha(OUT/'checksums.json')))
        for q in OUT.iterdir():
            if q.is_file():q.chmod(0o444)
        print(json.dumps({k:manifest[k] for k in ('status','cases','backbone_rank_histogram','conditional_complete_cases','distinct_children_total','elapsed_seconds','process_cpu_seconds')},sort_keys=True))
    except Exception as error:
        with (OUT/'UNKNOWN.json').open('xb') as stream:stream.write(raw(dict(status='UNKNOWN_METADATA',reason=type(error).__name__+': '+str(error),progress=progress,decoder_calls=0)))
        raise
    finally:signal.setitimer(signal.ITIMER_REAL,0)


if __name__=='__main__':main()
