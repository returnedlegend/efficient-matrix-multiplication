"""Hash-bound sampled observed rank3 spaces with resumable negative branches."""
import argparse
from collections import Counter
from datetime import datetime
import fcntl
import gzip
import hashlib
import json
from pathlib import Path
import signal
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.observed_rank342 import validate_space,lift_space,decode_space_hit
from mmsearch.observed_rank3_bounded42 import search_bounded
from mmsearch.observed_rank3_checkpoint42 import atomic_json,load_checkpoint,append_checkpoint,save_checkpoint
from mmsearch.free_factor_sat import decode_vectors
from mmsearch.recombine import digest
from mmsearch.verify import verify_candidate
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=480);p.add_argument('--per-case-seconds',type=float,default=60)
    p.add_argument('--memory-mb',type=int,default=1024);p.add_argument('--max-cases',type=int,default=0)
    p.add_argument('--case-id',action='append');p.add_argument('--controls-only',action='store_true');p.add_argument('--restart',action='store_true')
    p.add_argument('--branch-budget',type=int,default=0);p.add_argument('--deadline-utc',default='2026-11-04T21:31:16Z')
    args=p.parse_args();b=args.prepared_dir.resolve();out=args.output_dir.resolve()
    if not 0<args.per_case_seconds<=args.seconds or not 128<=args.memory_mb<=1536 or args.max_cases<0 or args.branch_budget<0:p.error('invalid resources')
    bindings=read_json((b/'integrity.json').read_bytes())
    for name,expected in bindings.items():
        if hashlib.sha256((b/name).read_bytes()).hexdigest()!=expected:raise ValueError('rank3 preparation binding mismatch: '+name)
    full_plan=read_json((b/'cases.json').read_bytes());plan=[case for case in full_plan if args.case_id is None or case['id'] in args.case_id]
    if args.case_id and set(args.case_id)!={case['id'] for case in plan}:raise ValueError('unknown sampled case')
    if args.max_cases:plan=plan[:args.max_cases]
    if not plan:raise ValueError('empty selected sample')
    out.mkdir(parents=True,exist_ok=args.restart);lock=(out/'.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    config=dict(prepared_integrity_sha256=hashlib.sha256((b/'integrity.json').read_bytes()).hexdigest(),plan_sha256=digest(plan),
        case_ids=[case['id'] for case in plan],controls_only=args.controls_only,decoder='rank3-weight5-checkpoint-v1',
        coverage='Only this explicit sampled observed-space plan; no complete rank3 image exclusion.')
    if args.restart:
        if read_json((out/'config.json').read_bytes())!=config:raise ValueError('source/plan/decoder resume binding changed')
    else:freeze(out/'config.json',json_bytes(config))
    cursor_path=out/'cursor.json';cursor=read_json(cursor_path.read_bytes()) if cursor_path.exists() else None
    if cursor and (cursor['config_sha256']!=digest(config) or not 0<=cursor['next_index']<=len(plan)):raise ValueError('global rank3 cursor corrupt')
    if (out/'WINNER.json').exists():
        checked=verify_candidate(read_json((out/'WINNER.json').read_bytes()),random_trials=0)
        if not checked['valid'] or checked['rank']>92 or checked['exact_entries_checked']!=15625:raise ValueError('retained winner invalid')
        print(json.dumps(dict(status='SAT',resumed_without_target_query=True)));return 0
    if cursor and cursor['last_status']=='ERROR':print(json.dumps(dict(status='ERROR',reason='prior error requires review')));return 2
    start=time.monotonic();cutoff=datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00')).timestamp();stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    def remaining():return max(0,min(args.seconds-(time.monotonic()-start),cutoff-time.time())-1)
    launch_dir=out/'launches';launch_dir.mkdir(exist_ok=True);launch=len(list(launch_dir.glob('*.json')))
    freeze(launch_dir/f'{launch:03d}.json',json_bytes(dict(seconds=args.seconds,per_case_seconds=args.per_case_seconds,memory_mb=args.memory_mb,
        branch_budget=args.branch_budget,deadline_utc=args.deadline_utc,initial_cursor=cursor,source_config_sha256=digest(config))))
    systems={};baselines={}
    for source in sorted({case['source_id'] for case in plan}):
        systems[source]=read_json((b/'sources'/source/'system.json').read_bytes());system=systems[source]
        checked=verify_candidate(decode_vectors(system,system['baseline_vectors']),random_trials=0)
        if not checked['valid'] or checked['rank']!=93 or checked['exact_entries_checked']!=15625:raise ValueError('invalid source baseline')
        baselines[source]=checked
    index=cursor['next_index'] if cursor else 0;counts=Counter(cursor['terminal_counts']) if cursor else Counter();queries=0;status='UNKNOWN'
    def save_global(index,last):atomic_json(cursor_path,dict(config_sha256=digest(config),next_index=index,terminal_counts=dict(counts),last_status=last))
    for index in range(index,len(plan)):
        if stopped or remaining()<=0:save_global(index,'UNKNOWN');break
        case=plan[index];directory=out/'cases'/case['id'];directory.mkdir(parents=True,exist_ok=True)
        q=read_json(gzip.decompress((b/case['quotient']).read_bytes()));system=systems[case['source_id']]
        validate_space(system,q)
        if q['quotient_sha256']!=case['quotient_sha256']:raise ValueError('sample quotient changed')
        result_path=directory/'result.json'
        if result_path.exists():
            result=read_json(result_path.read_bytes())
            if result['quotient_sha256']!=q['quotient_sha256']:raise ValueError('retained result source changed')
        else:
            old_entries=[[i,value] for i,value in enumerate(q['old_coordinates']) if value]
            control=lift_space(system,q,old_entries,require_gain=False)
            if control['rank_after']!=93 or control['coordinate_kernel_masks_hex']!=['0x0']*3:raise AssertionError('baseline three-coordinate lift changed source')
            if not (directory/'baseline.control.json').exists():freeze(directory/'baseline.control.json',json_bytes(dict(rank=93,weight=q['k'],
                kernel_masks=['0x0']*3,verification=baselines[case['source_id']],target_queries=0)))
            if args.controls_only:result=dict(status='CONTROL_PASSED',quotient_sha256=q['quotient_sha256'],target_queries=0)
            else:
                if q['weight_bound']>5:
                    result=dict(status='UNKNOWN',reason='requested budget>=6 unsupported/nonclosed',quotient_sha256=q['quotient_sha256'])
                else:
                    state=load_checkpoint(directory,q['quotient_sha256'])
                    result=search_bounded(q,seconds=min(args.per_case_seconds,remaining()),memory_mb=args.memory_mb,cursor=state,
                        on_progress=lambda record,cursor:append_checkpoint(directory,q['quotient_sha256'],record,cursor),
                        cancelled=lambda:stopped,branch_budget=args.branch_budget);queries+=1
                    save_checkpoint(directory,q['quotient_sha256'],result.get('cursor'))
                if result['status']=='HIT':
                    answer=decode_space_hit(system,q,result['entries'])
                    if answer['verification']['rank']>92 or answer['verification']['exact_entries_checked']!=15625:raise AssertionError('rank3 hit failed full target verification')
                    freeze(directory/'candidate.json',json_bytes(answer['candidate']));freeze(directory/'lift.json',json_bytes(answer['lift']))
                    freeze(directory/'verification.json',json_bytes(answer['verification']));freeze(out/'WINNER.json',json_bytes(answer['candidate']))
                    freeze(out/'WINNER.verification.json',json_bytes(answer['verification']));result.update(status='SAT',verification=answer['verification'])
                if result['status'] in ('UNKNOWN','PARTIAL_NO_WEIGHT_LE5'):
                    freeze(directory/f'unknown-launch{launch:03d}.json',json_bytes(result));save_global(index,'UNKNOWN');break
            freeze(result_path,json_bytes(result))
        counts[result['status']]+=1;save_global(index+1,result['status'])
        if result['status'] in ('SAT','ERROR'):status=result['status'];index+=1;break
    else:status='CONTROLS_PASSED' if args.controls_only else 'SAMPLED_PLAN_COMPLETE';index=len(plan)
    if not cursor_path.exists():save_global(index,status)
    latest=read_json(cursor_path.read_bytes())
    report=dict(status=status,next_index=latest['next_index'],selected_cases=len(plan),terminal_counts=dict(counts),target_queries_this_launch=queries,
        sampled_plan_only=True,full_observed_space_catalog_queried=False,elapsed_seconds=time.monotonic()-start,
        scope='Only this immutable sampled observed rank3-space plan on its fixed P/W. Exact weight<=5 cases may close; budgets>=6 stay nonclosed. '
              'No unrestricted rank or all-image-rank3 nonexistence conclusion follows.')
    freeze(out/f'report-launch{launch:03d}.json',json_bytes(report));print(json.dumps(report,sort_keys=True));return 2 if status=='ERROR' else 0


if __name__=='__main__':raise SystemExit(main())
