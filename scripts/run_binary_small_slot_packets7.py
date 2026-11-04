#!/usr/bin/env python3
"""One bounded S6 pilot: nine pinned d11 packets, no heuristic UNSAT claim."""
import argparse
from itertools import combinations
import json
import os
from pathlib import Path
import random
import resource
import signal
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(REPO))
from scripts import run_binary_block_packets7 as baseline
from mmsearch import binary_small_slot_repair7 as repair
from mmsearch import binary_block_descent7 as block
from mmsearch.binary_packet_adapter7 import C7,SOURCE,SOURCE_SHA,pinned,raw,sha,select_plan
from mmsearch.marathon7_cached_guard import CampaignGuard,CampaignHold
from scripts.run_c3_mixed12_pilot7 import run_case as guarded_run_case,freeze

OUTPUT_CAP=32*1024**2
SEED=7160600


def stratified_slots(seed,limit=600):
    """Stratify by least slot; proportional quotas, seeded within-stratum order."""
    if type(seed) is not int or type(limit) is not int or not 0<=limit<=600:
        raise ValueError('literal seed and cap0..600 required')
    groups={j:[] for j in range(9)}
    for slots in combinations(range(14),6):groups[slots[0]].append(list(slots))
    counts={j:len(g) for j,g in groups.items()};total=sum(counts.values())
    floor=1 if limit>=len(groups) else 0;remaining=limit-floor*len(groups)
    weights={j:counts[j]-floor for j in groups};denominator=sum(weights.values())
    quotas={j:floor+remaining*weights[j]//denominator for j in groups}
    for j in sorted(groups,key=lambda j:(-(remaining*weights[j]%denominator),j))[:limit-sum(quotas.values())]:quotas[j]+=1
    rng=random.Random(seed)
    for group in groups.values():rng.shuffle(group)
    chosen=[]
    for k in range(max(quotas.values(),default=0)):
        for j in groups:
            if k<quotas[j]:chosen.append(groups[j][k])
    return dict(seed=seed,population=total,limit=limit,strata='minimum selected slot',
                populations=counts,quotas=quotas,slots=chosen)


def selection_plan(plan):
    return dict(format='binary-small-slot-nine-s6-v1',selected_cases_sha256=plan['selected_cases_sha256'],
        core_manifest_sha256=plan['input_sha256'],initialization='original15 target; original min-volume-drop14 factors',
        cases=[dict(id=row['id'],**stratified_slots(SEED+i)) for i,row in enumerate(plan['cases'])])


def implementation_hashes():
    return baseline.implementation_hashes()


def slot_bridge(cache,selection,proof_cache=None,*,allow_tiny=False):
    """Reuse complete CP6 negatives by exact compact tensor, shape and budget."""
    proof_cache={} if proof_cache is None else proof_cache
    choices={row['id']:row for row in selection['cases']}
    def solve(core,shape,target,axis=0,max_vectors=65535,cancelled=None):
        if cache.current is None or (not allow_tiny and (target!=14 or shape!=[11]*3)):
            raise ValueError('only pinned rank14 d11 scope authorized')
        factors=cache.current['initial_factors'];entry=choices[cache.current_case]
        if len(factors)!=target or len(entry['slots'])>600:raise ValueError('slot selection scope differs')
        seen=set()
        for slots in entry['slots']:
            if (len(slots)!=6 or any(type(i) is not int or not 0<=i<len(factors) for i in slots)
                    or slots!=sorted(set(slots)) or tuple(slots) in seen):raise ValueError('distinct sorted literal S6 subsets required')
            seen.add(tuple(slots))
        guard=block._Guard(12,cancelled,block.DEADLINE)
        stats=dict(subsets_considered=0,mode_rank_exclusions=0,exact_decoder_exclusions=0,
            supported_decoder_calls=0,repair_calls=0,decoder_unknowns=0,negative_cache_hits=0,
            initial_loss=block.residual_loss(core,shape,factors),best_loss=block.residual_loss(core,shape,factors),
            best_factors=[list(t) for t in factors],subset_results=[],negative_proofs={})
        active_row=None;active_decoder=False
        def result(status,case,**extra):
            reason=guard.reason()
            if reason:status,case='UNKNOWN',reason
            return dict(status=status,complete=status=='SAT',case=case,**stats,**extra,
                limited_repair_family=True,no_global_unsat_claim=True,selection_sha256=sha(raw(entry)))
        try:
            for slots in entry['slots']:
                guard.check();stats['subsets_considered']+=1
                active_row=dict(slots=slots)
                outside=[term for i,term in enumerate(factors) if i not in set(slots)]
                residual=block._packed(core)^block._tensor(outside,shape)
                bases=repair._images(residual,shape,guard);dims=[len(b.vectors) for b in bases]
                row=active_row;row['actual_mode_shape']=dims
                if max(dims)>6:
                    guard.check();stats['mode_rank_exclusions']+=1
                    row.update(status='REPAIR_EXCLUDED',complete=True,case='mode_rank_bound')
                    stats['subset_results'].append(row);active_row=None;continue
                compact,dims=repair._compact(residual,shape,bases,guard)
                key=sha(raw(dict(shape=dims,core=compact,budget=6)))
                if key in proof_cache:
                    guard.check();proof=proof_cache[key]
                    stats['negative_cache_hits']+=1;stats['negative_proofs'][key]=proof
                    row.update(status='REPAIR_EXCLUDED',complete=True,case='cached_exact_CP6_negative',proof_sha256=sha(raw(proof)))
                    stats['subset_results'].append(row);active_row=None;continue
                d=max(dims)
                if 4<=d<=6:stats['supported_decoder_calls']+=1
                stats['repair_calls']+=1
                active_decoder=True
                observation=repair.repair_slots(core,shape,factors,slots,
                    timeout_seconds=max(0,12-(time.monotonic()-guard.started)),
                    cancelled=cancelled,max_vectors=1023,max_extensions=1533)
                # Retain raw child returns before the post-call cutoff barrier.
                stats['last_child_return']=observation
                guard.check()
                active_decoder=False
                row.update(status=observation['status'],complete=observation['complete'],case=observation['case'],
                           decoder_case=observation.get('decoder_case'))
                if observation['status']=='RAW_EXACT_COMPACT':
                    products=observation['factors']
                    block._validate(core,shape,products)
                    if len(products)>target or block.residual_loss(core,shape,products) or block.scalar_loss(core,shape,products):
                        raise ValueError('raw joint repair failed separate complete compact checks')
                    stats['best_loss']=0;stats['best_factors']=products;stats['subset_results'].append(row);active_row=None
                    return result('SAT','raw_exact_six_slot_repair',products=products,raw_repair=observation)
                if observation['status']=='REPAIR_EXCLUDED' and observation['complete']:
                    stats['exact_decoder_exclusions']+=1
                    proof=dict(shape=dims,core=compact,budget=6,key=key,observation=observation,
                        module_sha256=sha((REPO/'mmsearch/binary_small_slot_repair7.py').read_bytes()))
                    if observation['case']=='exact_selected_residual_negative':
                        proof_cache[key]=proof;stats['negative_proofs'][key]=proof;row['proof_sha256']=sha(raw(proof))
                else:stats['decoder_unknowns']+=1
                stats['subset_results'].append(row);active_row=None
            return result('UNKNOWN','bounded_six_slot_family_exhausted')
        except block._Stopped as exc:
            if active_row is not None:
                active_row.update(status='UNKNOWN',complete=False,case=str(exc))
                stats['subset_results'].append(active_row)
                if active_decoder:stats['decoder_unknowns']+=1
            return result('UNKNOWN',str(exc))
    return solve


class PacketCache(baseline.PacketCache):
    def core(self,case):
        result=super().core(case);self.current_case=case['id'];return result


def run_pilot(out,plan,selection,qa):
    code=implementation_hashes();guard=CampaignGuard(120,block.DEADLINE,campaign_dir=C7,guard_state=C7/'operations-v3/state.json')
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    results=[];stop_reason=None
    try:
        guard.check('pre_pilot');cache=PacketCache(plan,guard)
        freeze(out/'inputs/source.json',pinned(SOURCE));freeze(out/'source-verifications.json',dict(primary=cache.verified,independent=cache.independent))
        solver=slot_bridge(cache,selection)
        for row in plan['cases']:
            if guard.reason(force=True):break
            if implementation_hashes()!=code:raise ValueError('runtime closure changed')
            if sum(p.stat().st_size for p in out.rglob('*') if p.is_file())>OUTPUT_CAP-3*1024**2:
                raise CampaignHold('storage reserve','pre_case')
            case=dict(id=row['id'],source=SOURCE,source_sha256=SOURCE_SHA,source_products=93,
                source_local_products=15,target_local_products=14,source_indices=row['source_indices'],
                shape=[11]*3,mode_rank=11,free_axis=0,all_pair_points=2047**2,
                prep_ambient_sha256=row['branch_metadata']['ambient_sha256'])
            result=guarded_run_case(cache,case,out,guard,seconds=12,solver=solver)
            result.update(operator='joint_exact_S6',heuristic_failure_never_unsat=True)
            decoder=result.get('raw_decoder');late=out/'.raw-returns'/(case['id']+'.late-result.raw')
            if decoder is None and late.exists():decoder=json.loads(late.read_bytes()).get('raw_decoder')
            if decoder:result['best_compact_loss']=decoder.get('best_loss')
            if not (out/(case['id']+'.result.json')).exists():freeze(out/(case['id']+'.result.json'),result)
            results.append(result)
            if result['status'] in ('TARGET_EMITTED_TO_GLOBAL_GUARD','ERROR'):break
    except CampaignHold as exc:stop_reason=exc.reason
    except Exception as exc:results.append(dict(status='ERROR',complete=False,error=str(exc),error_type=type(exc).__name__))
    emitted=any(r['status']=='TARGET_EMITTED_TO_GLOBAL_GUARD' for r in results)
    status='TARGET_EMITTED_TO_GLOBAL_GUARD' if emitted else 'ERROR' if any(r['status']=='ERROR' for r in results) else 'UNKNOWN'
    if implementation_hashes()!=code:status='ERROR';stop_reason='runtime closure changed before summary'
    final_reason=guard.reason(force=True)
    return dict(status=status,complete=emitted,planned_cases=9,attempted_cases=len(results),
        queries_started=sum(bool(r.get('decoder_called')) for r in results),results=results,
        scope='at most600 selected S6 repairs/case; UNKNOWN closes no CP14 case',no_global_unsat_claim=True,
        global_record_freeze_owned_by_guard=True,stop_reason=final_reason or stop_reason,
        elapsed_seconds=guard.monotonic()-guard.started,guard=guard.observation(),
        implementation_sha256=code,selected_cases_sha256=plan['selected_cases_sha256'],
        selection_sha256=sha(raw(selection)),qa_report_sha256=sha(raw(qa)))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path);p.add_argument('--qa-report',type=Path);p.add_argument('--qa-sha256')
    p.add_argument('--core-pins',type=Path);p.add_argument('--core-pins-sha256')
    p.add_argument('--authorize-pilot',action='store_true');p.add_argument('--qa-approval',choices=('root-reviewed',));p.add_argument('--preview',action='store_true')
    a=p.parse_args(argv)
    if not a.preview and (not a.authorize_pilot or a.qa_approval!='root-reviewed'):
        print(json.dumps(dict(status='DISABLED',production_inputs_read=False,queries_started=0)));return 0
    plan=select_plan(core_pin_path=a.core_pins,core_pin_sha256=a.core_pins_sha256);selection=selection_plan(plan)
    preview=dict(implementation_sha256=implementation_hashes(),selected_cases_sha256=plan['selected_cases_sha256'],
        input_sha256=plan['input_sha256'],selection_sha256=sha(raw(selection)))
    if a.preview:
        print(json.dumps(dict(status='PREVIEW_NO_QUERY',queries_started=0,**preview),sort_keys=True));return 0
    if a.output_dir is None or a.qa_report is None or not a.qa_sha256 or not plan['core_pins_complete']:
        p.error('new output, exact QA pins and all9 cores required')
    qa_raw=a.qa_report.read_bytes();qa=json.loads(qa_raw)
    if sha(qa_raw)!=a.qa_sha256 or qa.get('status')!='PASS' or any(qa.get(k)!=v for k,v in preview.items()):
        raise ValueError('independent QA does not bind exact runtime, core and subset scope')
    os.sched_setaffinity(0,{1})
    if os.getpriority(os.PRIO_PROCESS,0)<10:os.nice(10-os.getpriority(os.PRIO_PROCESS,0))
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(OUTPUT_CAP,OUTPUT_CAP))
    out=a.output_dir.resolve()
    if out.exists() or not out.is_relative_to(C7):raise ValueError('fresh C7 output required')
    out.mkdir();freeze(out/'plan.json',plan);freeze(out/'selection.json',selection);freeze(out/'qa-report.json',qa_raw)
    for name,digest in preview['implementation_sha256'].items():
        data=(REPO/name).read_bytes()
        if sha(data)!=digest:raise ValueError('runtime changed during snapshot')
        freeze(out/'code'/name,data)
    freeze(out/'launch.json',dict(cpu=1,nice=os.getpriority(os.PRIO_PROCESS,0),seconds=120,case_seconds=12,
        outer_seconds=150,memory_limit_bytes=1024**3,subsets_per_case=600,**preview))
    result=run_pilot(out,plan,selection,qa);freeze(out/'summary.json',result)
    freeze(out/'checksums.json',{str(p.relative_to(out)):sha(p.read_bytes()) for p in out.rglob('*') if p.is_file()})
    print(json.dumps(dict(status=result['status'],attempted_cases=result['attempted_cases'],
        best_losses=[r.get('best_compact_loss') for r in result['results']],stop_reason=result['stop_reason'],
        elapsed_seconds=result['elapsed_seconds']),sort_keys=True))
    return 2 if result['status']=='ERROR' else 0


if __name__=='__main__':raise SystemExit(main())
