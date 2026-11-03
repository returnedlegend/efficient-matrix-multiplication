"""Bounded observed-plane pilot with exact witnesses and a hashed resume cursor."""
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
from mmsearch.observed_plane42 import (decode_plane_hit,lift_plane,plane_plan,prepare_plane,
    search_plane_bounded,validate_active_certificate)
from mmsearch.free_factor_sat import decode_vectors
from mmsearch.recombine import digest
from mmsearch.verify import verify_candidate

SOURCE_FILES=['scripts/campaign_observed_plane42.py','mmsearch/observed_plane42.py',
    'mmsearch/common_delta42.py','mmsearch/free_factor_sat.py','mmsearch/recombine.py',
    'mmsearch/recombine_sat.py','mmsearch/verify.py','mmsearch/__init__.py']


def frozen_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:json.dump(value,stream,sort_keys=True,indent=2);stream.write('\n')
    path.chmod(0o444)


def atomic_json(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n');temporary.replace(path)


def resume_terminal(root,cursor):
    """A resume must never move past a verified winner or a prior ERROR."""
    winner=Path(root)/'WINNER.json'
    if winner.exists():
        report=verify_candidate(json.loads(winner.read_text()),random_trials=0)
        if not report['valid'] or report['rank']>92 or report['exact_entries_checked']!=15625:
            raise AssertionError('retained winner failed independent exact verification')
        return 'SAT'
    if cursor is not None and cursor.get('last_status')=='ERROR':return 'ERROR'
    return None


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-dir',type=Path,required=True)
    parser.add_argument('--case',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=900)
    parser.add_argument('--per-plane-seconds',type=float,default=5)
    parser.add_argument('--max-planes',type=int,default=0)
    parser.add_argument('--memory-mb',type=int,default=1024)
    parser.add_argument('--deadline-utc',default='2026-11-04T21:31:16Z')
    parser.add_argument('--controls-only',action='store_true')
    parser.add_argument('--restart',action='store_true')
    args=parser.parse_args(argv)
    if (any(not math.isfinite(v) or v<=0 for v in [args.seconds,args.per_plane_seconds])
            or not 128<=args.memory_mb<=1024 or args.max_planes<0 or '/' in args.case):
        parser.error('invalid resource limits or case')
    absolute=datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00'))
    if absolute.tzinfo is None:parser.error('timezone required')
    absolute=absolute.timestamp();started=time.monotonic()
    integrity=args.prepared_dir/'integrity.json'
    for relative,expected in json.loads(integrity.read_text()).items():
        if hashlib.sha256((args.prepared_dir/relative).read_bytes()).hexdigest()!=expected:
            raise ValueError(f'frozen observed-plane preparation changed: {relative}')
    source=args.prepared_dir/'cases'/args.case
    system=json.loads((source/'system.json').read_text())
    certificate=json.loads((source/'active-certificate.json').read_text())
    validate_active_certificate(system,certificate)
    plan=json.loads((source/'plan.json').read_text())
    if plane_plan(system)!=plan:raise AssertionError('observed-plane plan differs from exact baseline')
    all_planes=len(plan)
    if args.max_planes:plan=plan[:args.max_planes]
    plan_hash=digest(plan);certificate_hash=digest(certificate)
    config=dict(case=args.case,source_system_sha256=digest(system),plan_sha256=plan_hash,
        full_plan_sha256=digest(json.loads((source/'plan.json').read_text())),
        active_certificate_sha256=certificate_hash,max_planes=args.max_planes,
        controls_only=args.controls_only,prepared_integrity_sha256=hashlib.sha256(integrity.read_bytes()).hexdigest(),
        source_sha256={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in SOURCE_FILES},
        decoder='independently implemented exact group-weight<=3 rank0/rank1/rank2 cases',
        larger_bound_policy='NO_WEIGHT_LE3 is partial when k-gain>3; no complete fallback implemented')
    root=args.output_dir;root.mkdir(parents=True,exist_ok=args.restart)
    if args.restart:
        if json.loads((root/'config.json').read_text())!=config:raise ValueError('resume source/plan/configuration changed')
    else:
        frozen_json(root/'config.json',config)
        for name in SOURCE_FILES:
            path=root/'code'/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((REPO/name).read_bytes());path.chmod(0o444)
    cursor_path=root/'cursor.json';config_hash=digest(config)
    if cursor_path.exists():
        cursor=json.loads(cursor_path.read_text())
        if cursor['config_sha256']!=config_hash or cursor['plan_sha256']!=plan_hash:
            raise ValueError('resume cursor hash mismatch')
        next_index=cursor['next_index'];counts=Counter(cursor['terminal_counts'])
        if not 0<=next_index<=len(plan):raise ValueError('resume cursor outside immutable plan')
    else:cursor=None;next_index=0;counts=Counter()
    terminal=resume_terminal(root,cursor)
    if terminal is not None:
        print(json.dumps(dict(status=terminal,resumed_without_target_search=True,
            reason='verified retained winner' if terminal=='SAT' else 'prior ERROR requires review')),flush=True)
        return 2 if terminal=='ERROR' else 0
    launches=root/'launches';launches.mkdir(exist_ok=True)
    launch_id=len(list(launches.glob('*.json')))
    frozen_json(launches/f'{launch_id:03d}.json',dict(seconds=args.seconds,per_plane_seconds=args.per_plane_seconds,
        memory_mb=args.memory_mb,deadline_utc=args.deadline_utc,restart=args.restart,
        initial_cursor=next_index,config_sha256=config_hash,solver_state_restored=False))
    stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    def remaining():return max(0,min(args.seconds-(time.monotonic()-started),absolute-time.time())-1)
    def save_cursor(index,last):
        atomic_json(cursor_path,dict(config_sha256=config_hash,plan_sha256=plan_hash,
            next_index=index,terminal_counts=dict(counts),last_status=last,launch_id=launch_id,
            elapsed_seconds=time.monotonic()-started,saved_solver_internal_state=False,
            replay='Immutable full P/W, plane plan and exact quotient/lift witnesses; no learned state or pair maps restored'))
    baseline=verify_candidate(decode_vectors(system,system['baseline_vectors']),random_trials=0)
    if not baseline['valid'] or baseline['rank']!=93 or baseline['exact_entries_checked']!=15625:
        raise AssertionError('source baseline is not independently exact rank93')
    if not (root/'baseline.control.json').exists():frozen_json(root/'baseline.control.json',baseline)
    target_calls=0;status='UNKNOWN'
    for index in range(next_index,len(plan)):
        if stopped or remaining()<=0:break
        item=plan[index];result_path=root/'results'/f'{index:04d}.json'
        if result_path.exists():
            result=json.loads(result_path.read_text())
            if result['status']=='SAT':status='SAT';break
        elif not args.controls_only and certificate['independent'] and item['weight_bound']<2:
            if len(item['observed_values'])<2:raise AssertionError('observed plane lacks two independent old values')
            result=dict(status='NO_GAIN_RANK_BOUND',complete_for_requested_gain=True,
                plane=item['plane'],k=item['k'],weight_bound=item['weight_bound'],target_rank_lower_bound=2,
                proof='Active P columns are independent. Quotient by the other active columns preserves the two-dimensional old coordinate target rank. Group weight is at least target rank.',
                active_certificate_sha256=certificate_hash,plan_sha256=plan_hash)
            frozen_json(result_path,result)
        else:
            directory=root/'planes'/f'{index:04d}';directory.mkdir(parents=True,exist_ok=True)
            q=prepare_plane(system,item['plane'],gain=1)
            if (q['k'],q['weight_bound'])!=(item['k'],item['weight_bound']):raise AssertionError('wrong plane D multiplicity')
            compressed=gzip.compress(json.dumps(q,sort_keys=True,separators=(',',':')).encode(),mtime=0)
            q_path=directory/'quotient.json.gz'
            if q_path.exists():
                if q_path.read_bytes()!=compressed:raise AssertionError('resumed quotient witnesses changed')
            else:
                q_path.write_bytes(compressed);q_path.chmod(0o444)
                frozen_json(directory/'quotient.sha256.json',dict(quotient_sha256=q['quotient_sha256'],
                    compressed_file_sha256=hashlib.sha256(compressed).hexdigest()))
            baseline_entries=[[i,v] for i,v in enumerate(q['old_coordinates']) if v]
            control=lift_plane(system,q,baseline_entries,require_gain=False)
            if control['coordinate_kernel_masks_hex']!=['0x0','0x0'] or control['rank_after']!=93:
                raise AssertionError('plane weight-k baseline control failed')
            if not (directory/'baseline.control.json').exists():frozen_json(directory/'baseline.control.json',dict(
                status='FEASIBLE_CONTROL',weight=len(baseline_entries),budget=q['k'],entries=baseline_entries,
                coordinate_kernel_masks_hex=control['coordinate_kernel_masks_hex'],rank=control['rank_after']))
            if args.controls_only:
                result=dict(status='CONTROL_PASSED',plane=item['plane'],quotient_sha256=q['quotient_sha256'],
                    k=q['k'],target_rank=q['target_rank'],weight_bound=q['weight_bound'],neutral_rank=q['neutral_rank'])
            else:
                if stopped or remaining()<=0:save_cursor(index,'UNKNOWN');break
                result=search_plane_bounded(q,seconds=min(args.per_plane_seconds,remaining()),
                    memory_mb=args.memory_mb,cancelled=lambda:stopped);target_calls+=1
                result.update(plane=item['plane'],k=q['k'],weight_bound=q['weight_bound'],target_rank=q['target_rank'],
                    full_case=item['full_case_at_weight3'])
                if result['status']=='HIT':
                    answer=decode_plane_hit(system,q,result['entries'])
                    if answer['verification']['rank']>92 or answer['verification']['exact_entries_checked']!=15625:
                        raise AssertionError('plane target failed full rank92 verification')
                    frozen_json(directory/'candidate.json',answer['candidate'])
                    frozen_json(directory/'verification.json',answer['verification'])
                    frozen_json(directory/'lift.json',answer['lift'])
                    result.update(status='SAT',verification=answer['verification'])
                    if not (root/'WINNER.json').exists():
                        frozen_json(root/'WINNER.json',answer['candidate'])
                        frozen_json(root/'WINNER.verification.json',answer['verification'])
                elif result['status']=='UNKNOWN':
                    frozen_json(directory/f'unknown-launch{launch_id:03d}.json',result)
                    save_cursor(index,'UNKNOWN');break
            frozen_json(result_path,result)
        counts[result['status']]+=1
        next_index=index+1;save_cursor(next_index,result['status'])
        if result['status'] in ['SAT','ERROR']:
            status=result['status'];break
        if index%50==0 or result['status'] not in ['NO_GAIN_RANK_BOUND']:
            print(json.dumps(dict(index=index,total=len(plan),plane=item['plane'],status=result['status'],
                elapsed_seconds=time.monotonic()-started)),flush=True)
    else:status='CONTROLS_PASSED' if args.controls_only else 'ENUMERATED_PLAN_COMPLETE'
    report=dict(status=status,next_index=next_index,total_selected_planes=len(plan),all_observed_planes=all_planes,
        terminal_counts=dict(counts),target_decoder_calls_this_launch=target_calls,
        complete_cases_no_gain=counts['NO_GAIN_RANK_BOUND']+counts['NO_ONE_SUBSPACE_GAIN'],
        bounded_partial_cases=counts['NO_WEIGHT_LE3'],elapsed_seconds=time.monotonic()-started,
        scope='Plane-valued updates only on this fixed-pair system. Each NO_WEIGHT_LE3 at k-1>3 is a bounded subfamily negative. Full image-rank<=2 coverage additionally requires the rank-one families and complete treatment of every larger-bound plane; no unrestricted rank claim.',
        stopped_by_signal=stopped,plan_sha256=plan_hash,config_sha256=config_hash)
    frozen_json(root/f'report-launch{launch_id:03d}.json',report)
    if not cursor_path.exists():save_cursor(next_index,status)
    print(json.dumps(report),flush=True)
    return 2 if status=='ERROR' else 0


if __name__=='__main__':raise SystemExit(main())
