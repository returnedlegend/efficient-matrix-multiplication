"""Close only nine hash-bound recorded weight-four plane gaps."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
import signal
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from mmsearch.observed_plane42 import decode_plane_hit,lift_plane
from mmsearch.observed_weight442 import search_weight4_bounded,validate_prior_family,validate_prior_gap
from mmsearch.free_factor_sat import decode_vectors
from mmsearch.recombine import digest
from mmsearch.verify import verify_candidate
from scripts.campaign_observed_plane42 import atomic_json,frozen_json,resume_terminal

SOURCE_FILES=['scripts/campaign_observed_weight442.py','mmsearch/observed_weight442.py',
    'scripts/campaign_observed_plane42.py','mmsearch/observed_plane42.py','mmsearch/common_delta42.py',
    'mmsearch/free_factor_sat.py','mmsearch/recombine.py','mmsearch/recombine_sat.py',
    'mmsearch/verify.py','mmsearch/__init__.py']


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=300)
    parser.add_argument('--per-case-seconds',type=float,default=30)
    parser.add_argument('--memory-mb',type=int,default=1024)
    parser.add_argument('--max-cases',type=int,default=0)
    parser.add_argument('--deadline-utc',default='2026-11-04T21:31:16Z')
    parser.add_argument('--controls-only',action='store_true')
    parser.add_argument('--restart',action='store_true')
    args=parser.parse_args(argv)
    if (any(not math.isfinite(v) or v<=0 for v in [args.seconds,args.per_case_seconds])
            or not 128<=args.memory_mb<=1024 or args.max_cases<0):parser.error('invalid limits')
    absolute=datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00'))
    if absolute.tzinfo is None:parser.error('timezone required')
    absolute=absolute.timestamp();started=time.monotonic()
    manifest_path=args.prepared_dir/'integrity.json'
    for relative,expected in json.loads(manifest_path.read_text()).items():
        if hashlib.sha256((args.prepared_dir/relative).read_bytes()).hexdigest()!=expected:
            raise ValueError(f'prepared weight4 closure changed: {relative}')
    plan=json.loads((args.prepared_dir/'gaps.json').read_text())
    if len(plan)!=9 or len({item['id'] for item in plan})!=9:
        raise AssertionError('extension must bind exactly nine distinct prior partial cases')
    families={}
    for label in sorted({item['source_case'] for item in plan}):
        source=args.prepared_dir/'sources'/label
        family={name:json.loads((source/(name+'.json')).read_text()) for name in
            ['system','prior-config','prior-plan','prior-cursor','prior-report','prior-results-manifest']}
        validate_prior_family(family['system'],family['prior-config'],family['prior-plan'],
            family['prior-cursor'],family['prior-report'],family['prior-results-manifest'])
        for relative,expected in family['prior-config']['source_sha256'].items():
            if hashlib.sha256((REPO/relative).read_bytes()).hexdigest()!=expected:
                raise AssertionError(f'prior source closure mismatch: {relative}')
        expected={item['index'] for item in family['prior-results-manifest'] if item['status']=='NO_WEIGHT_LE3'}
        selected={item['prior_index'] for item in plan if item['source_case']==label}
        if selected!=expected:raise AssertionError('selected extension differs from exact prior partial set')
        report=verify_candidate(decode_vectors(family['system'],family['system']['baseline_vectors']),random_trials=0)
        if not report['valid'] or report['rank']!=93 or report['exact_entries_checked']!=15625:
            raise AssertionError('extension source baseline is not exact rank93')
        family['baseline_report']=report;families[label]=family
    if args.max_cases:plan=plan[:args.max_cases]
    plan_hash=digest(plan)
    config=dict(plan_sha256=plan_hash,max_cases=args.max_cases,controls_only=args.controls_only,
        prepared_integrity_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        source_sha256={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in SOURCE_FILES},
        family='Only the nine previously partial k5/requiredweight4 cases; no completed full negative family is searched')
    config_hash=digest(config);root=args.output_dir;root.mkdir(parents=True,exist_ok=args.restart)
    if args.restart:
        if json.loads((root/'config.json').read_text())!=config:raise ValueError('resume extension/configuration hash mismatch')
    else:
        frozen_json(root/'config.json',config)
        for name in SOURCE_FILES:
            path=root/'code'/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((REPO/name).read_bytes());path.chmod(0o444)
    cursor_path=root/'cursor.json'
    if cursor_path.exists():
        cursor=json.loads(cursor_path.read_text())
        if cursor['config_sha256']!=config_hash or cursor['plan_sha256']!=plan_hash:
            raise ValueError('weight4 resume cursor hash mismatch')
        next_index=cursor['next_index'];counts=Counter(cursor['terminal_counts'])
        if not 0<=next_index<=len(plan):raise ValueError('cursor outside extension plan')
    else:cursor=None;next_index=0;counts=Counter()
    terminal=resume_terminal(root,cursor)
    if terminal is not None:
        print(json.dumps(dict(status=terminal,resumed_without_target_search=True)),flush=True)
        return 2 if terminal=='ERROR' else 0
    launches=root/'launches';launches.mkdir(exist_ok=True);launch_id=len(list(launches.glob('*.json')))
    frozen_json(launches/f'{launch_id:03d}.json',dict(seconds=args.seconds,per_case_seconds=args.per_case_seconds,
        memory_mb=args.memory_mb,deadline_utc=args.deadline_utc,initial_cursor=next_index,
        config_sha256=config_hash,solver_state_restored=False))
    stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    def remaining():return max(0,min(args.seconds-(time.monotonic()-started),absolute-time.time())-1)
    def save_cursor(index,last):
        atomic_json(cursor_path,dict(config_sha256=config_hash,plan_sha256=plan_hash,next_index=index,
            terminal_counts=dict(counts),last_status=last,launch_id=launch_id,
            elapsed_seconds=time.monotonic()-started,saved_solver_internal_state=False))
    calls=0;status='UNKNOWN'
    for index in range(next_index,len(plan)):
        if stopped or remaining()<=0:break
        binding=plan[index];source=args.prepared_dir/'gaps'/binding['id'];family=families[binding['source_case']]
        system=family['system'];prior=json.loads((source/'prior.result.json').read_text())
        compressed=(source/'quotient.json.gz').read_bytes()
        if hashlib.sha256(compressed).hexdigest()!=binding['compressed_quotient_sha256']:
            raise AssertionError('prior compressed quotient hash mismatch')
        q=json.loads(gzip.decompress(compressed));prior_index=binding['prior_index']
        record=family['prior-results-manifest'][prior_index]
        if (record['status']!='NO_WEIGHT_LE3' or record['canonical_sha256']!=digest(prior)
                or record['file_sha256']!=hashlib.sha256((source/'prior.result.json').read_bytes()).hexdigest()):
            raise AssertionError('partial result is not the bound prior indexed result')
        validate_prior_gap(system,q,prior,family['prior-plan'][prior_index],binding)
        directory=root/'cases'/binding['id'];directory.mkdir(parents=True,exist_ok=True)
        result_path=directory/'result.json'
        if result_path.exists():result=json.loads(result_path.read_text())
        else:
            entries=[[i,v] for i,v in enumerate(q['old_coordinates']) if v]
            control=lift_plane(system,q,entries,require_gain=False)
            if control['coordinate_kernel_masks_hex']!=['0x0','0x0'] or control['rank_after']!=93:
                raise AssertionError('prior quotient baseline lift is not unchanged rank93')
            if not (directory/'baseline.control.json').exists():frozen_json(directory/'baseline.control.json',dict(
                status='FEASIBLE_CONTROL',weight=len(entries),budget=q['k'],kernel_masks=['0x0','0x0'],
                rank=control['rank_after'],full_tensor_verification=family['baseline_report']))
            if args.controls_only:
                result=dict(status='CONTROL_PASSED',quotient_sha256=q['quotient_sha256'],plane=q['plane'],
                    prior_result_canonical_sha256=digest(prior),target_queries=0)
            else:
                if stopped or remaining()<=0:save_cursor(index,'UNKNOWN');break
                result=search_weight4_bounded(q,seconds=min(args.per_case_seconds,remaining()),
                    memory_mb=args.memory_mb,cancelled=lambda:stopped);calls+=1
                result.update(plane=q['plane'],prior_result_canonical_sha256=digest(prior),
                    source_system_sha256=digest(system),complete_for_selected_gain=q['weight_bound']==4)
                if result['status']=='HIT':
                    answer=decode_plane_hit(system,q,result['entries'])
                    if answer['verification']['rank']>92 or answer['verification']['exact_entries_checked']!=15625:
                        raise AssertionError('weight4 repair failed full rank92 verification')
                    frozen_json(directory/'candidate.json',answer['candidate'])
                    frozen_json(directory/'verification.json',answer['verification'])
                    frozen_json(directory/'lift.json',answer['lift'])
                    if not (root/'WINNER.json').exists():
                        frozen_json(root/'WINNER.json',answer['candidate']);frozen_json(root/'WINNER.verification.json',answer['verification'])
                    result.update(status='SAT',verification=answer['verification'])
                elif result['status']=='UNKNOWN':
                    frozen_json(directory/f'unknown-launch{launch_id:03d}.json',result);save_cursor(index,'UNKNOWN');break
            frozen_json(result_path,result)
        counts[result['status']]+=1;next_index=index+1;save_cursor(next_index,result['status'])
        print(json.dumps(dict(id=binding['id'],status=result['status'],pairs=result.get('eligible_pairs_tried'),
            precondition=result.get('precondition_weight3',{}).get('status'))),flush=True)
        if result['status'] in ['SAT','ERROR']:status=result['status'];break
    else:status='CONTROLS_PASSED' if args.controls_only else 'NINE_RECORDED_WEIGHT4_CASES_COMPLETE'
    report=dict(status=status,next_index=next_index,total_selected_cases=len(plan),terminal_counts=dict(counts),
        target_queries_this_launch=calls,elapsed_seconds=time.monotonic()-started,stopped_by_signal=stopped,
        scope='Only the selected formerly partial rank2/k5 plane cases on the bound fixedP1553 systems. Weight4 negatives are complete for gain1 in these cases. Broader conclusions require the prior complete-family and rank-one results; no unrestricted rank claim.')
    frozen_json(root/f'report-launch{launch_id:03d}.json',report)
    if not cursor_path.exists():save_cursor(next_index,status)
    print(json.dumps(report),flush=True);return 2 if status=='ERROR' else 0


if __name__=='__main__':raise SystemExit(main())
