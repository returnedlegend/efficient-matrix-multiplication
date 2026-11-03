"""Bounded common-delta then observed-plane coverage for one fresh baseline."""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from mmsearch.recombine import digest
from mmsearch.verify import verify_candidate
from scripts.campaign_common_delta42 import SOURCE_FILES as COMMON_FILES
from scripts.campaign_observed_plane42 import SOURCE_FILES as PLANE_FILES,atomic_json,frozen_json,resume_terminal

SOURCE_FILES=sorted(set(COMMON_FILES+PLANE_FILES+['scripts/campaign_breadth43.py','mmsearch/breadth43.py']))


def run_child(command,budget,log_path,cancelled=None):
    """Bound the whole child process group; reap adopted descendants on Linux."""
    if not math.isfinite(budget) or budget<=0:raise ValueError('positive child wall budget required')
    subreaper=False
    if sys.platform.startswith('linux'):
        subreaper=ctypes.CDLL(None).prctl(36,1,0,0,0)==0
    start=time.monotonic();reason='completed';reaped=0
    with Path(log_path).open('xb') as stream:
        child=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            while child.poll() is None:
                if time.monotonic()-start>=budget or (cancelled is not None and cancelled()):
                    reason='wall limit or parent stop'
                    try:child.send_signal(signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:child.wait(timeout=1)
                    except subprocess.TimeoutExpired:pass
                    break
                time.sleep(.05)
        finally:
            # Normal legacy runners reap their own workers. This also removes
            # descendants if an uncooperative child outlives a hard stop.
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            child.wait()
            if subreaper:
                cleanup_deadline=time.monotonic()+.5
                while time.monotonic()<cleanup_deadline:
                    try:
                        pid,_=os.waitpid(-child.pid,os.WNOHANG)
                    except ChildProcessError:break
                    if pid:reaped+=1
                    else:time.sleep(.01)
    return dict(exit_code=child.returncode,reason=reason,elapsed_seconds=time.monotonic()-start,
        child_pid=child.pid,child_reaped=True,subreaper_enabled=subreaper,adopted_descendants_reaped=reaped)


def latest_stage_report(directory,controls=False):
    directory=Path(directory);paths=[]
    first=directory/('controls.json' if controls else 'result.json')
    if first.exists():paths.append((0,first))
    for path in directory.glob('report*.json'):
        number=path.stem.removeprefix('report-launch').removeprefix('report')
        if number.isdigit():paths.append((int(number)+1,path))
    if not paths:return None,None
    path=max(paths,key=lambda item:item[0])[1]
    return json.loads(path.read_text()),path


def export_winner(child_dir,root):
    path=Path(child_dir)/'WINNER.json'
    if not path.exists():return None
    candidate=json.loads(path.read_text());report=verify_candidate(candidate,random_trials=0)
    if not report['valid'] or report['rank']>92 or report['exact_entries_checked']!=15625:
        raise AssertionError('child winner failed independent exact verification')
    if not (Path(root)/'WINNER.json').exists():
        frozen_json(Path(root)/'WINNER.json',candidate);frozen_json(Path(root)/'WINNER.verification.json',report)
    return report


def stage_outcome(child,report,winner):
    if winner is not None:return 'SAT'
    if child['reason']!='completed':return 'UNKNOWN'
    if child['exit_code']!=0 or report is None or report.get('status')=='SAT':return 'ERROR'
    return report['status']


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-dir',type=Path,required=True)
    parser.add_argument('--case',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=900)
    parser.add_argument('--common-seconds',type=float,default=240)
    parser.add_argument('--per-query-seconds',type=float,default=5)
    parser.add_argument('--deadline-utc',default='2026-11-04T21:31:16Z')
    parser.add_argument('--controls-only',action='store_true')
    parser.add_argument('--restart',action='store_true')
    args=parser.parse_args(argv)
    if any(not math.isfinite(v) or v<=0 for v in [args.seconds,args.common_seconds,args.per_query_seconds]) or '/' in args.case:
        parser.error('invalid limits or case')
    absolute=datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00'))
    if absolute.tzinfo is None:parser.error('timezone required')
    absolute=absolute.timestamp();started=time.monotonic()
    integrity=args.prepared_dir/'integrity.json'
    for relative,expected in json.loads(integrity.read_text()).items():
        if hashlib.sha256((args.prepared_dir/relative).read_bytes()).hexdigest()!=expected:
            raise ValueError(f'frozen breadth preparation changed: {relative}')
    cases={item['case']:item for item in json.loads((args.prepared_dir/'selected.json').read_text())}
    if args.case not in cases:raise ValueError('case is not one of the four frozen new models')
    selected=cases[args.case]
    config=dict(case=args.case,model_sha256=selected['model_sha256'],term_hash=selected['term_hash'],
        controls_only=args.controls_only,prepared_integrity_sha256=hashlib.sha256(integrity.read_bytes()).hexdigest(),
        source_sha256={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in SOURCE_FILES},
        order=['common','plane'],coverage_policy='Fresh model only; no prior negative transfer. Common<=4 and plane<=3 are bounded where required weight is larger.')
    config_hash=digest(config);root=args.output_dir;root.mkdir(parents=True,exist_ok=args.restart)
    if args.restart:
        if json.loads((root/'config.json').read_text())!=config:raise ValueError('breadth resume source/model/configuration mismatch')
    else:
        frozen_json(root/'config.json',config)
        for name in SOURCE_FILES:
            path=root/'code'/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((REPO/name).read_bytes());path.chmod(0o444)
    cursor_path=root/'cursor.json'
    if cursor_path.exists():
        cursor=json.loads(cursor_path.read_text())
        if cursor['config_sha256']!=config_hash:raise ValueError('breadth resume cursor hash mismatch')
    else:cursor=dict(config_sha256=config_hash,next_stage=0,stage_results={},last_status='UNSTARTED')
    if type(cursor['next_stage']) is not int or not 0<=cursor['next_stage']<=2:
        raise ValueError('breadth cursor stage is outside the immutable two-stage plan')
    for completed in ['common','plane'][:cursor['next_stage']]:
        if completed not in cursor['stage_results']:raise ValueError('breadth cursor lacks its completed-stage evidence')
    terminal=resume_terminal(root,cursor)
    if terminal is not None:
        print(json.dumps(dict(status=terminal,resumed_without_target_search=True)),flush=True)
        return 2 if terminal=='ERROR' else 0
    launches=root/'launches';launches.mkdir(exist_ok=True);launch=len(list(launches.glob('*.json')))
    frozen_json(launches/f'{launch:03d}.json',dict(seconds=args.seconds,common_seconds=args.common_seconds,
        per_query_seconds=args.per_query_seconds,deadline_utc=args.deadline_utc,restart=args.restart,
        initial_stage=cursor['next_stage'],config_sha256=config_hash))
    stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    def remaining():return max(0,min(args.seconds-(time.monotonic()-started),absolute-time.time())-2)
    status='UNKNOWN'
    for index in range(cursor['next_stage'],2):
        if stopped or remaining()<=0:break
        stage=['common','plane'][index];output=root/stage
        winner=export_winner(output,root)
        if winner is not None:status='SAT';cursor['last_status']='SAT';atomic_json(cursor_path,cursor);break
        budget=min(args.common_seconds,remaining()) if stage=='common' else remaining()
        script='campaign_common_delta42.py' if stage=='common' else 'campaign_observed_plane42.py'
        command=[sys.executable,str(REPO/'scripts'/script),'--prepared-dir',str(args.prepared_dir/stage),
            '--case',args.case,'--output-dir',str(output),'--seconds',str(max(.001,budget-1)),
            '--deadline-utc',args.deadline_utc]
        if stage=='common':
            command+=['--per-delta-seconds',str(args.per_query_seconds),'--memory-mb','768','--max-work-mb','512','--max-weight','4']
            if args.controls_only:command+=['--controls-only','--max-deltas','2']
        else:
            command+=['--per-plane-seconds',str(args.per_query_seconds),'--memory-mb','1024']
            if args.controls_only:command+=['--controls-only','--max-planes','2']
        if output.exists():command.append('--restart')
        stem=f'launch{launch:03d}-{stage}'
        frozen_json(root/(stem+'.manifest.json'),dict(command=command,wall_budget=budget,model_sha256=selected['model_sha256']))
        child=run_child(command,budget,root/(stem+'.log'),cancelled=lambda:stopped)
        winner=export_winner(output,root)
        report,path=latest_stage_report(output,args.controls_only)
        stage_status=stage_outcome(child,report,winner)
        record=dict(status=stage_status,child=child,report=report,
            report_path=str(path) if path else None,
            report_sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path else None)
        frozen_json(root/(stem+'.result.json'),record);cursor['stage_results'][stage]=record
        if stage_status in ['SAT','ERROR']:
            status=stage_status;cursor['last_status']=stage_status;atomic_json(cursor_path,cursor);break
        if stage=='plane' and stage_status=='UNKNOWN':
            cursor['last_status']='UNKNOWN';atomic_json(cursor_path,cursor);break
        # A bounded common pass may have partial/UNKNOWN outcomes. Preserve
        # its exact report and continue fresh plane coverage with remaining time.
        cursor['next_stage']=index+1;cursor['last_status']=stage_status;atomic_json(cursor_path,cursor)
        print(json.dumps(dict(stage=stage,status=stage_status,remaining_seconds=remaining())),flush=True)
    else:status='CONTROLS_PASSED' if args.controls_only else 'BOUNDED_PIPELINE_FINISHED'
    if not cursor_path.exists():atomic_json(cursor_path,cursor)
    result=dict(status=status,case=args.case,model_sha256=selected['model_sha256'],term_hash=selected['term_hash'],
        next_stage=cursor['next_stage'],stages=cursor['stage_results'],elapsed_seconds=time.monotonic()-started,
        stopped_by_signal=stopped,scope=selected['scope'],target_queries=0 if args.controls_only else 'See independent per-stage reports')
    frozen_json(root/f'report-launch{launch:03d}.json',result)
    print(json.dumps(dict(status=status,case=args.case,next_stage=cursor['next_stage'])),flush=True)
    return 2 if status=='ERROR' else 0


if __name__=='__main__':raise SystemExit(main())
