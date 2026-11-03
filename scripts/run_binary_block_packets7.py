#!/usr/bin/env python3
"""Nine pinned d11 binary-block attempts through the reviewed mixed12 lifecycle.

No local WINNER marker: the canonical C7 global guard owns record freeze/stop.
Every failed heuristic remains UNKNOWN and closes no mathematical case.
"""
import argparse
import importlib
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
from mmsearch.binary_packet_adapter7 import (C7,PINS,SOURCE,SOURCE_SHA,build_packet_data,
    literal_terms,pinned,raw,select_plan,sha)
from mmsearch.binary_block_controller7 import run_controller
from mmsearch import binary_block_descent7 as block
from mmsearch.extend_eight_bulk43 import SourceCache
from mmsearch.marathon7_cached_guard import CampaignGuard,CampaignHold
from scripts.run_c3_mixed12_pilot7 import run_case as guarded_run_case,freeze
from scripts.verify_record42_independent import verify_bytes

# Prime lazy mathematical dependencies before either preview or QA hashing.
for _name in ('mmsearch.sat','mmsearch.free_factor_sat','mmsearch.recombine_sat'):
    importlib.import_module(_name)
CODE=('mmsearch/binary_block_descent7.py','mmsearch/binary_block_controller7.py',
      'mmsearch/binary_packet_adapter7.py','scripts/run_binary_block_packets7.py',
      'scripts/run_c3_mixed12_pilot7.py')
OUTPUT_CAP=32*1024**2


def implementation_hashes():
    names=set(CODE)
    for module in tuple(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if name:
            path=Path(name).resolve()
            if path.is_relative_to(REPO) and path.suffix=='.py' and path.relative_to(REPO).parts[0] in ('mmsearch','scripts'):
                names.add(str(path.relative_to(REPO)))
    return {name:sha((REPO/name).read_bytes()) for name in sorted(names)}


class PacketCache:
    def __init__(self,plan,guard):
        self.rows={row['id']:row for row in plan['cases']};self.guard=guard;self.current=None
        guard.check('pre_literal_source')
        source_raw=pinned(SOURCE);literal_terms(json.loads(source_raw))
        self.cache=SourceCache(C7)
        self.source,self.verified,self.terms,self.tensors,self.source_sha=self.cache.load(
            dict(source=SOURCE,source_sha256=SOURCE_SHA,source_products=93))
        self.independent=verify_bytes(source_raw)
        guard.check('post_literal_source_full_checks')
        if (self.source_sha!=SOURCE_SHA or self.source['dimension']!=5 or self.source['field']!=2
                or len(self.terms)!=93 or not self.verified['valid'] or self.verified['exact_entries_checked']!=15625
                or not self.independent['valid'] or self.independent['exact_entries_checked']!=15625
                or self.independent['essential_rank']!=93):raise ValueError('approved source failed both full checks')

    def core(self,case):
        row=self.rows[case['id']]
        data=build_packet_data(self.source,row,production=True)
        self.current=data
        return self.source,data,self.verified,self.source_sha,sha(raw(dict(shape=data['shape'],core=data['core']))),sha(raw(data))


def controller_bridge(cache,global_guard,max_actions=10000):
    def solve(core,shape,target,axis=0,max_vectors=65535,cancelled=None):
        if target!=14 or shape!=[11]*3 or cache.current is None:raise ValueError('only fixed14 d11 packet scope authorized')
        remaining=min(12,max(0,global_guard.seconds-(global_guard.monotonic()-global_guard.started)))
        observation=run_controller(core,shape,14,initial_factors=cache.current['initial_factors'],
            source_product_count=15,mode='fixed',training=False,seed=771400,
            max_actions=max_actions,timeout_seconds=remaining,cancelled=cancelled)
        if observation['status']=='RAW_EXACT_COMPACT':
            products=observation['raw_compact']['products']
            block._validate(core,shape,products)
            if len(products)>target or block.residual_loss(core,shape,products) or block.scalar_loss(core,shape,products):
                raise ValueError('controller zero observation failed separate compact bridge check')
            return dict(status='SAT',complete=True,products=products,case='raw_exact_binary_block',
                        best_loss=0,controller_observation=observation)
        return dict(status='UNKNOWN',complete=False,case=observation.get('case','heuristic_incomplete'),
                    best_loss=observation['best_loss'],controller_observation=observation)
    return solve


def run_pilot(out,plan,qa,*,seconds=120,case_seconds=12,max_actions=10000):
    if not plan.get('core_pins_complete'):raise ValueError('all nine exact core pins required')
    code=implementation_hashes()
    guard=CampaignGuard(seconds,'2026-11-03T19:24:17Z',campaign_dir=C7,guard_state=C7/'operations-v3/state.json')
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    results=[];cache=None;stop_reason=None
    try:
        guard.check('pre_pilot')
        cache=PacketCache(plan,guard)
        freeze(out/'inputs/source.json',pinned(SOURCE))
        freeze(out/'source-verifications.json',dict(primary=cache.verified,independent=cache.independent))
        solver=controller_bridge(cache,guard,max_actions)
        for row in plan['cases']:
            if guard.reason(force=True):break
            if implementation_hashes()!=code:raise ValueError('runtime closure changed before dispatch')
            if sum(path.stat().st_size for path in out.rglob('*') if path.is_file())>OUTPUT_CAP-2*1024**2:
                raise CampaignHold('pilot storage reserve','pre_case')
            case=dict(id=row['id'],source=SOURCE,source_sha256=SOURCE_SHA,source_products=93,
                source_local_products=15,target_local_products=14,source_indices=row['source_indices'],
                shape=[11]*3,mode_rank=11,free_axis=0,all_pair_points=(2047**2),
                prep_ambient_sha256=row['branch_metadata']['ambient_sha256'])
            # The unchanged reviewed lifecycle owns all post-solve/full-check/
            # publication barriers, CancelPoller and late/error quarantine.
            result=guarded_run_case(cache,case,out,guard,seconds=case_seconds,solver=solver)
            result.update(policy='fixed',trained_policy_promoted=False,
                fixed_target_rank=14,heuristic_failure_never_unsat=True,
                algorithm='exact GF2 factor-block minimization with discrete fixed controller')
            decoder=result.get('raw_decoder')
            late=out/'.raw-returns'/(case['id']+'.late-result.raw')
            if decoder is None and late.exists():decoder=json.loads(late.read_bytes()).get('raw_decoder')
            if decoder:result['best_compact_loss']=decoder.get('best_loss')
            if not (out/(case['id']+'.result.json')).exists():freeze(out/(case['id']+'.result.json'),result)
            results.append(result)
            if result['status'] in ('TARGET_EMITTED_TO_GLOBAL_GUARD','ERROR'):break
        stop_reason=guard.reason(force=True)
    except CampaignHold as exc:
        stop_reason=exc.reason
    except Exception as exc:
        results.append(dict(status='ERROR',complete=False,error_type=type(exc).__name__,error=str(exc)))
    emitted=any(r['status']=='TARGET_EMITTED_TO_GLOBAL_GUARD' for r in results)
    status='TARGET_EMITTED_TO_GLOBAL_GUARD' if emitted else 'ERROR' if any(r['status']=='ERROR' for r in results) else 'UNKNOWN'
    # A summary is diagnostic, never an additional canonical-candidate view.
    if implementation_hashes()!=code:
        status='ERROR';stop_reason='runtime closure changed before summary'
    final_reason=guard.reason(force=True)
    return dict(status=status,complete=emitted,planned_cases=9,attempted_cases=len(results),
        queries_started=sum(bool(r.get('decoder_called')) for r in results),results=results,
        policy='fixed',trained_policy_promoted=False,scope='nine attempted heuristics only; UNKNOWN closes no case',
        unresolved_cases=None if emitted else 9,no_global_unsat_claim=True,target_sat_called=False,
        stop_reason=final_reason or stop_reason,global_record_freeze_owned_by_guard=True,
        elapsed_seconds=guard.monotonic()-guard.started,guard=guard.observation(),
        implementation_sha256=code,selected_cases_sha256=plan['selected_cases_sha256'],qa_report_sha256=sha(raw(qa)))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path);p.add_argument('--qa-report',type=Path);p.add_argument('--qa-sha256')
    p.add_argument('--core-pins',type=Path);p.add_argument('--core-pins-sha256')
    p.add_argument('--authorize-pilot',action='store_true');p.add_argument('--qa-approval',choices=('root-reviewed',));p.add_argument('--preview',action='store_true')
    a=p.parse_args(argv)
    if not a.preview and (not a.authorize_pilot or a.qa_approval!='root-reviewed'):
        print(json.dumps(dict(status='DISABLED',production_inputs_read=False,queries_started=0)));return 0
    plan=select_plan(core_pin_path=a.core_pins,core_pin_sha256=a.core_pins_sha256)
    if a.preview:
        print(json.dumps(dict(status='PREVIEW_NO_QUERY',queries_started=0,
            cases=[r['id'] for r in plan['cases']],selected_cases_sha256=plan['selected_cases_sha256'],
            implementation_sha256=implementation_hashes(),input_sha256=plan['input_sha256'],
            core_pins_complete=plan['core_pins_complete']),sort_keys=True));return 0
    if a.output_dir is None or a.qa_report is None or not a.qa_sha256 or not plan['core_pins_complete']:
        p.error('new output, root-pinned independent QA and all9 exact core pins required')
    qa_raw=a.qa_report.read_bytes()
    if sha(qa_raw)!=a.qa_sha256:raise ValueError('independent QA bytes changed')
    qa=json.loads(qa_raw)
    if (qa.get('status')!='PASS' or qa.get('implementation_sha256')!=implementation_hashes()
            or qa.get('selected_cases_sha256')!=plan['selected_cases_sha256'] or qa.get('input_sha256')!=plan['input_sha256']):
        raise ValueError('independent QA does not bind this exact source/core/runtime scope')
    os.sched_setaffinity(0,{1})
    if os.getpriority(os.PRIO_PROCESS,0)<10:os.nice(10-os.getpriority(os.PRIO_PROCESS,0))
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(OUTPUT_CAP,OUTPUT_CAP))
    out=a.output_dir.resolve()
    if out.exists() or not out.is_relative_to(C7):raise ValueError('fresh C7 output required')
    out.mkdir();freeze(out/'plan.json',plan);freeze(out/'qa-report.json',qa_raw)
    for name,expected in implementation_hashes().items():
        data=(REPO/name).read_bytes()
        if sha(data)!=expected:raise ValueError('runtime changed while snapshotting')
        freeze(out/'code'/name,data)
    freeze(out/'launch.json',dict(cpu=1,nice=os.getpriority(os.PRIO_PROCESS,0),seconds=120,case_seconds=12,
        outer_seconds=150,memory_limit_bytes=resource.getrlimit(resource.RLIMIT_AS)[0],
        implementation_sha256=implementation_hashes(),input_sha256=plan['input_sha256']))
    result=run_pilot(out,plan,qa)
    freeze(out/'summary.json',result)
    freeze(out/'checksums.json',{str(path.relative_to(out)):sha(path.read_bytes()) for path in out.rglob('*') if path.is_file()})
    print(json.dumps(dict(status=result['status'],attempted_cases=result['attempted_cases'],queries_started=result['queries_started'],
                         best_losses=[r.get('best_compact_loss') for r in result['results']],
                         stop_reason=result['stop_reason'],elapsed_seconds=result['elapsed_seconds']),sort_keys=True))
    return 2 if result['status']=='ERROR' else 0


if __name__=='__main__':raise SystemExit(main())
