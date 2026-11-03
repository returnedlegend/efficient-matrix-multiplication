"""Run a bounded all-support, one-common-delta quotient pilot from frozen inputs."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import signal
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from mmsearch.common_delta42 import decode_hit,lift_hit,prepare_quotient,search_bounded,validate_quotient
from mmsearch.free_factor_sat import decode_vectors
from mmsearch.verify import verify_candidate

SOURCE_FILES=['scripts/campaign_common_delta42.py','mmsearch/common_delta42.py',
    'mmsearch/free_factor_sat.py','mmsearch/recombine.py','mmsearch/recombine_sat.py',
    'mmsearch/verify.py','mmsearch/__init__.py']


def frozen_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:
        json.dump(value,stream,sort_keys=True,indent=2);stream.write('\n')
    path.chmod(0o444)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-dir',type=Path,required=True)
    parser.add_argument('--case',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=120)
    parser.add_argument('--per-delta-seconds',type=float,default=5)
    parser.add_argument('--max-deltas',type=int,default=0,help='zero means all observed nonzero deltas')
    parser.add_argument('--memory-mb',type=int,default=768)
    parser.add_argument('--max-work-mb',type=float,default=512)
    parser.add_argument('--max-weight',type=int,default=4)
    parser.add_argument('--deadline-utc',default='2026-11-04T21:31:16Z')
    parser.add_argument('--controls-only',action='store_true')
    parser.add_argument('--restart',action='store_true',help='skip persisted completed deltas; no solver state or pair map is restored')
    args=parser.parse_args(argv)
    if (any(not math.isfinite(v) or v<=0 for v in [args.seconds,args.per_delta_seconds,args.max_work_mb])
            or not 128<=args.memory_mb<=768 or args.max_deltas<0 or not 0<=args.max_weight<=4
            or '/' in args.case):parser.error('invalid resource limits or case')
    absolute=datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00'))
    if absolute.tzinfo is None:parser.error('timezone required')
    absolute=absolute.timestamp();started=time.monotonic()
    integrity_path=args.prepared_dir/'integrity.json'
    for relative,expected in json.loads(integrity_path.read_text()).items():
        if hashlib.sha256((args.prepared_dir/relative).read_bytes()).hexdigest()!=expected:
            raise ValueError(f'frozen preparation changed: {relative}')
    source_case=args.prepared_dir/'cases'/args.case
    system=json.loads((source_case/'system.json').read_text())
    plan=json.loads((source_case/'plan.json').read_text())
    counts=Counter(v for v in system['baseline_vectors'] if v)
    expected_plan=[dict(delta=d,delta_hex=hex(d),k=k,weight_bound=k-1) for d,k in
        sorted(counts.items(),key=lambda item:(-item[1],item[0]))]
    if plan!=expected_plan:raise AssertionError('delta multiplicity plan does not match exact baseline')
    if args.max_deltas:plan=plan[:args.max_deltas]
    root=args.output_dir;root.mkdir(parents=True,exist_ok=args.restart)
    config=dict(case=args.case,prepared_dir=str(args.prepared_dir.resolve()),max_deltas=args.max_deltas,
        memory_mb=args.memory_mb,max_work_mb=args.max_work_mb,max_weight=args.max_weight,
        per_delta_seconds=args.per_delta_seconds,deadline_utc=args.deadline_utc,
        prepared_integrity_sha256=hashlib.sha256(integrity_path.read_bytes()).hexdigest(),
        code_sha256={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in SOURCE_FILES})
    if args.restart:
        if json.loads((root/'config.json').read_text())!=config:raise ValueError('restart configuration/code changed')
    else:
        frozen_json(root/'config.json',config)
        for name in SOURCE_FILES:
            path=root/'code'/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((REPO/name).read_bytes());path.chmod(0o444)
    stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    def remaining():return max(0,min(args.seconds-(time.monotonic()-started),absolute-time.time())-1)
    baseline_candidate=decode_vectors(system,system['baseline_vectors'])
    baseline_report=verify_candidate(baseline_candidate,random_trials=0)
    if not baseline_report['valid'] or baseline_report['rank']!=93 or baseline_report['exact_entries_checked']!=15625:
        raise AssertionError('full baseline control is not exact rank93')
    if not (root/'baseline.control.json').exists():frozen_json(root/'baseline.control.json',baseline_report)
    statuses=[]
    for index,item in enumerate(plan):
        if stopped or remaining()<=0:break
        directory=root/'deltas'/f'{index:03d}-{item["delta"]:07x}'
        directory.mkdir(parents=True,exist_ok=True)
        result_path=directory/'result.json'
        if result_path.exists():
            result=json.loads(result_path.read_text());statuses.append(result['status'])
            if result['status']=='SAT':return 0
            continue
        q=prepare_quotient(system,item['delta'],gain=1)
        if (q['k'],q['weight_bound'])!=(item['k'],item['weight_bound']):raise AssertionError('wrong quotient multiplicity')
        q_path=directory/'quotient.json'
        if q_path.exists():
            if json.loads(q_path.read_text())!=q:raise AssertionError('quotient differs from retained restart state')
        else:frozen_json(q_path,q)
        baseline_y=[i for i,g in enumerate(q['relevant_groups']) if g in q['delta_groups']]
        baseline_lift=lift_hit(system,q,baseline_y)
        if baseline_lift['z_hex']!='0x0' or baseline_lift['rank_after']!=93:
            raise AssertionError('weight-k baseline quotient control failed')
        if not (directory/'baseline.control.json').exists():frozen_json(directory/'baseline.control.json',dict(
            status='FEASIBLE_CONTROL',y_indices=baseline_y,weight=len(baseline_y),budget=q['k'],
            lift=baseline_lift,quotient_sha256=q['quotient_sha256']))
        if args.controls_only:
            statuses.append('CONTROL_PASSED');continue
        if stopped or remaining()<=0:break
        result=search_bounded(q,seconds=min(args.per_delta_seconds,remaining()),memory_mb=args.memory_mb,
            max_work_mb=args.max_work_mb,max_weight=args.max_weight,cancelled=lambda:stopped)
        if result['status']=='HIT':
            answer=decode_hit(system,q,result['y_indices'])
            if answer['verification']['rank']>92 or answer['verification']['exact_entries_checked']!=15625:
                raise AssertionError('target repair failed exact rank92/full tensor requirement')
            frozen_json(directory/'candidate.json',answer['candidate'])
            frozen_json(directory/'verification.json',answer['verification'])
            frozen_json(directory/'lift.json',answer['lift'])
            result.update(status='SAT',verification=answer['verification'])
            frozen_json(result_path,result)
            if not (root/'WINNER.json').exists():
                frozen_json(root/'WINNER.json',answer['candidate'])
                frozen_json(root/'WINNER.verification.json',answer['verification'])
            print(json.dumps(dict(status='SAT',delta_hex=item['delta_hex'],rank=answer['verification']['rank'])),flush=True)
            return 0  # Stop before preparing or searching another delta.
        frozen_json(result_path,result);statuses.append(result['status'])
        print(json.dumps(dict(delta_hex=item['delta_hex'],k=q['k'],status=result['status'],
            operations=result.get('operations'),elapsed_seconds=result['elapsed_seconds'])),flush=True)
        if result['status']=='ERROR':break
    complete=len(statuses)==len(plan)
    if args.controls_only:status='CONTROLS_PASSED' if complete else 'UNKNOWN'
    elif 'ERROR' in statuses:status='ERROR'
    elif not complete or 'UNKNOWN' in statuses:status='UNKNOWN'
    elif all(s=='NO_ONE_DELTA_GAIN' for s in statuses):status='NO_ONE_DELTA_GAIN_FOR_ENUMERATED_DELTAS'
    else:status='NO_WEIGHT_LE4_FOR_ENUMERATED_DELTAS'
    report=dict(status=status,enumerated_deltas=len(plan),completed_deltas=len(statuses),
        observed_deltas=len(counts),covers_all_observed_deltas=complete and len(plan)==len(counts),
        statuses=Counter(statuses),elapsed_seconds=time.monotonic()-started,stopped_by_signal=stopped,
        target_queries=0 if args.controls_only else len(statuses),
        scope='Only one common delta at a time on the complete supplied fixed-pair dictionary. For k-1>4, a negative weight<=4 search is partial. No unrestricted rank impossibility claim.')
    path=root/('controls.json' if args.controls_only else 'result.json');attempt=0
    while path.exists():attempt+=1;path=root/f'report{attempt}.json'
    frozen_json(path,report);print(json.dumps(report),flush=True)
    return 2 if status=='ERROR' else 0


if __name__=='__main__':raise SystemExit(main())
