"""Run one frozen expanded local case in one persistent, bounded solver child."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import importlib
import json
import math
import resource
from pathlib import Path
import signal
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from mmsearch.local_eliminated42sat import baseline_assumptions,build_problem,solve as solve_control
from mmsearch.persistent42sat import solve_staged
from scripts.campaign_local_eliminated42sat import frozen_json,save_result

SOURCE_FILES = ['scripts/campaign_persistent42sat.py','mmsearch/persistent42sat.py',
    'mmsearch/local_eliminated42sat.py','mmsearch/local_free_factor_sat.py',
    'mmsearch/free_factor_sat.py','mmsearch/recombine.py','mmsearch/recombine_sat.py',
    'mmsearch/verify.py','mmsearch/tensor.py','mmsearch/__init__.py',
    'scripts/campaign_local_eliminated42sat.py']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-dir',type=Path,required=True)
    parser.add_argument('--case',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--stage-seconds',type=float,nargs='+',default=[180,720,2700])
    parser.add_argument('--wall-seconds',type=float,default=3630)
    parser.add_argument('--conflicts',type=int,default=1000000000)
    parser.add_argument('--memory-mb',type=int,default=1536)
    parser.add_argument('--deadline-utc',default='2026-11-04T21:31:16Z')
    parser.add_argument('--controls-only',action='store_true')
    parser.add_argument('--restart-from-formula',action='store_true',
        help='explicit fresh-solver restart after interruption/UNKNOWN; no solver state is restored')
    args = parser.parse_args(argv)
    if (not args.stage_seconds or any(not math.isfinite(v) or v<=0 for v in [args.wall_seconds,*args.stage_seconds])
            or not 128<=args.memory_mb<=2048 or args.conflicts<1 or '/' in args.case):
        parser.error('invalid limits or case')
    _,inherited_memory_hard = resource.getrlimit(resource.RLIMIT_AS)
    effective_memory_mb = args.memory_mb if inherited_memory_hard==resource.RLIM_INFINITY else min(
        args.memory_mb,inherited_memory_hard//1024**2)
    if effective_memory_mb<128:
        parser.error('inherited hard memory cap is below128MiB')
    absolute = datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00'))
    if absolute.tzinfo is None:
        parser.error('deadline must have a timezone')
    absolute = absolute.timestamp()
    integrity_path = args.prepared_dir/'integrity.json'
    manifest = json.loads(integrity_path.read_text())
    for relative,expected in manifest.items():
        if hashlib.sha256((args.prepared_dir/relative).read_bytes()).hexdigest()!=expected:
            raise ValueError(f'prepared artifact changed: {relative}')
    case = args.prepared_dir/'cases'/args.case
    system = json.loads((case/'system.json').read_text())
    groups = json.loads((case/'plan.json').read_text())['free_groups']
    source_hashes = {name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in SOURCE_FILES}
    deps = {}
    for name in ['pycryptosat','pysat','pysat.card','pysolvers']:
        module = importlib.import_module(name)
        path = Path(module.__file__)
        deps[name]=dict(path=str(path),version=getattr(module,'__version__',None),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    config = dict(prepared_dir=str(args.prepared_dir.resolve()),case=args.case,
        stages=args.stage_seconds,wall_seconds=args.wall_seconds,memory_mb=args.memory_mb,
        effective_memory_mb=effective_memory_mb,inherited_memory_hard_bytes=inherited_memory_hard,
        conflicts=args.conflicts,deadline_utc=args.deadline_utc,
        prepared_integrity_sha256=hashlib.sha256(integrity_path.read_bytes()).hexdigest(),
        source_sha256=source_hashes,dependencies=deps,
        lifecycle='one solver object loaded once across cooperative UNKNOWN slices in a bounded child',
        restart_policy='fresh solver from frozen formula and assumptions; no learned-clause serialization')
    root = args.output_dir
    root.mkdir(parents=True,exist_ok=args.restart_from_formula)
    if args.restart_from_formula:
        if json.loads((root/'config.json').read_text())!=config:
            raise ValueError('restart configuration/source/dependencies changed')
    else:
        frozen_json(root/'config.json',config)
        for name in SOURCE_FILES:
            path = root/'code'/name
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:
                stream.write((REPO/name).read_bytes())
            path.chmod(0o444)
    stopped = False
    def stop(signum,frame):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    def wall_remaining():
        return max(0,min(args.wall_seconds,absolute-time.time()-2))
    attempts = root/'attempts'
    attempts.mkdir(exist_ok=True)
    for existing in sorted(attempts.glob('*/target.result.json')):
        status = json.loads(existing.read_text())['status']
        if status in ['SAT','LOCAL_UNSAT']:
            raise ValueError(f'previous target already ended {status}; do not repeat unchanged terminal case')
    index = len(list(attempts.iterdir()))
    attempt = attempts/f'{index:03d}'
    attempt.mkdir(exist_ok=False)
    frozen_json(attempt/'restart.json',dict(fresh_solver_instance=True,
        restored_solver_internal_state=False,restarted_from_formula=args.restart_from_formula,
        previous_attempt_count=index,stages_start_again_from_first_slice=True))
    for rank,kind in [(93,'control'),(92,'target')]:
        problem = build_problem(system,groups,rank,max_formula_mb=128)
        expected = json.loads((case/(kind+'.formula.json')).read_text())
        if json.loads(json.dumps({k:v for k,v in problem.items() if k!='system'}))!=expected:
            raise AssertionError('rebuilt formula differs from frozen prepared state')
        if wall_remaining()<=0 or stopped:
            frozen_json(attempt/'stopped.json',dict(status='UNKNOWN',reason='deadline or stop before solver call'))
            return 0
        if kind=='control':
            # The rank93 feasibility control is a separate solver/formula.
            result = solve_control(problem,seconds=min(5,wall_remaining()),memory_mb=effective_memory_mb,
                assumptions=baseline_assumptions(problem),log_path=attempt/'control.solver.log',
                cancelled=lambda:stopped)
            result = save_result(root,f'attempts/{index:03d}/control',result)
            if result['status']!='SAT' or result['verification']['rank']!=93:
                print(json.dumps(dict(status='ERROR',reason='positive control failed',control=result)),flush=True)
                return 2
            if args.controls_only:
                frozen_json(attempt/'control-only.json',dict(status='CONTROLS_PASSED',target_queries=0))
                print(json.dumps(dict(status='CONTROLS_PASSED',target_queries=0)),flush=True)
                return 0
        else:
            frozen_json(attempt/'target.manifest.json',dict(formula_sha256=problem['metadata']['formula_sha256'],
                assumptions=[],stages=args.stage_seconds,conflicts=args.conflicts,
                hard_wall_seconds=wall_remaining(),memory_mb=effective_memory_mb,
                solver_internal_checkpoint=False,same_solver_across_slices=True))
            def progress(event):
                print(json.dumps(event,sort_keys=True),flush=True)
            result = solve_staged(problem,args.stage_seconds,wall_seconds=wall_remaining(),
                conflict_limits=args.conflicts,memory_mb=effective_memory_mb,
                log_path=attempt/'target.solver.log',checkpoint_path=attempt/'checkpoint.json',
                cancelled=lambda:stopped,on_progress=progress)
            result = save_result(root,f'attempts/{index:03d}/target',result)
            print(json.dumps(dict(status=result['status'],elapsed_seconds=result['elapsed_seconds'],
                completed_slices=len(result['slice_history']),worker_reaped=result['worker_reaped'])),flush=True)
            return 2 if result['status']=='ERROR' else 0
    return 0


if __name__=='__main__':
    raise SystemExit(main())
