"""Freeze selected campaign certificates, then solve within one wall budget."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.freeze_campaign_dictionary import dictionary_columns,json_bytes

ROOT=Path(__file__).resolve().parents[1]


def write_new(path,value):
    with Path(path).open('xb') as stream:
        stream.write(json_bytes(value))


def progress(output,manifest):
    temporary=output/'progress.json.tmp'
    temporary.write_bytes(json_bytes(manifest))
    temporary.replace(output/'progress.json')


def select_candidates(candidates,candidate_dirs,minimum_age,now):
    selected={};skipped=[]
    for path in candidates:
        path=Path(path).resolve()
        if not path.is_file():
            raise ValueError(f'explicit candidate is not a file: {path}')
        selected[path]=dict(path=str(path),selection='explicit')
    for directory in candidate_dirs:
        directory=Path(directory).resolve()
        if not directory.is_dir():
            raise ValueError(f'candidate directory is not a directory: {directory}')
        for path in sorted(directory.glob('*.json')):
            if not path.is_file():
                continue
            stat=path.stat();age=now-stat.st_mtime
            record=dict(path=str(path.resolve()),age_seconds=age,mtime_ns=stat.st_mtime_ns,size=stat.st_size)
            if age < minimum_age:
                skipped.append(record)
            else:
                selected.setdefault(path.resolve(),dict(record,selection='directory'))
    if not selected:
        raise ValueError('no selected certificates; at least one verified baseline is required')
    return [selected[path] for path in sorted(selected)],skipped


def _stop_group(process):
    try:
        os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=.5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    # A solver descendant can outlive an already reaped driver.
    try:
        os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_stage(command,log_path,timeout):
    """No shell or affinity/environment overrides; reap the owned process tree."""
    with Path(log_path).open('xb') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,
                                 shell=False,start_new_session=True)
        timed_out=False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True
            _stop_group(process)
        except BaseException:
            _stop_group(process)
            raise
    return dict(exit_code=process.returncode,timed_out=timed_out)


def run_phase(*,output_dir,seconds=900,candidates=(),candidate_dirs=(),extra_dictionaries=(),
              minimum_age=30,memory_mb=1536,conflicts=100000000,
              runner=None,clock=None,wall_clock=None):
    runner=runner or run_stage;clock=clock or time.monotonic;wall_clock=wall_clock or time.time
    if (not math.isfinite(seconds) or seconds<=0 or not math.isfinite(minimum_age)
            or minimum_age<0 or type(memory_mb) is not int or memory_mb<128
            or type(conflicts) is not int or conflicts<1):
        raise ValueError('invalid phase wall, age, memory, or conflict limits')
    started=clock();deadline=started+seconds
    output=Path(output_dir).resolve();output.mkdir(parents=True,exist_ok=False)
    code_paths=[Path(__file__).resolve(),ROOT/'scripts/freeze_campaign_dictionary.py',
                ROOT/'scripts/campaign_dictionary_preprocessed.py',ROOT/'scripts/campaign_recombine_sat.py']
    manifest=dict(seconds_budget=seconds,minimum_age_seconds=minimum_age,memory_mb=memory_mb,
                  conflicts=conflicts,code_sha256={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
                                                   for path in code_paths},stages=[])
    result=dict(status='ERROR',reason='phase did not complete')
    try:
        selected,skipped=select_candidates(candidates,candidate_dirs,minimum_age,wall_clock())
        manifest.update(selected=selected,skipped_young=skipped,extra_dictionaries=[])
        extra=None
        if extra_dictionaries:
            terms=set()
            for index,path in enumerate(extra_dictionaries):
                path=Path(path).resolve();raw=path.read_bytes();terms.update(dictionary_columns(raw,path))
                snapshot=output/f'extra-input-{index:03d}.json'
                with snapshot.open('xb') as stream:
                    stream.write(raw)
                snapshot.chmod(0o444)
                manifest['extra_dictionaries'].append(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),snapshot=str(snapshot)))
            extra=output/'merged-extra-dictionary.json'
            write_new(extra,sorted(terms));extra.chmod(0o444)
        command=[sys.executable,str(ROOT/'scripts/freeze_campaign_dictionary.py'),
                 '--output-dir',str(output/'frozen')]
        for record in selected:
            command.extend(['--candidate',record['path']])
        if extra is not None:
            command.extend(['--extra-dictionary',str(extra)])
        remaining=deadline-clock()
        if remaining<=0:
            result=dict(status='BUDGET_EXHAUSTED',reason='preparation exhausted total wall budget')
        else:
            stage=dict(name='freeze',command=command,timeout_seconds=remaining)
            manifest['stages'].append(stage)
            progress(output,manifest)
            stage.update(runner(command,output/'freeze.log',remaining))
            progress(output,manifest)
            if stage['exit_code']!=0 or stage.get('timed_out'):
                result=dict(status='BUDGET_EXHAUSTED' if stage.get('timed_out') else 'ERROR',
                            reason='dictionary freezer did not complete successfully',stage='freeze')
            else:
                remaining=deadline-clock()
                if remaining<=0:
                    result=dict(status='BUDGET_EXHAUSTED',reason='freezing exhausted total wall budget')
                else:
                    command=[sys.executable,str(ROOT/'scripts/campaign_dictionary_preprocessed.py'),
                             '--dictionary',str(output/'frozen/dictionary.json'),
                             '--baseline',str(output/'frozen/baseline.json'),
                             '--source-manifest',str(output/'frozen/pool.json'),
                             '--output-dir',str(output/'solve'),'--seconds',repr(remaining),
                             '--memory-mb',str(memory_mb),'--conflicts',str(conflicts),
                             '--control-seconds','5']
                    stage=dict(name='solve',command=command,timeout_seconds=remaining)
                    manifest['stages'].append(stage)
                    progress(output,manifest)
                    stage.update(runner(command,output/'solve.log',remaining))
                    progress(output,manifest)
                    solver_result=output/'solve/result.json'
                    if stage.get('timed_out'):
                        result=dict(status='BUDGET_EXHAUSTED',reason='solver reached total phase deadline',stage='solve')
                    elif stage['exit_code']!=0:
                        result=dict(status='ERROR',reason='dictionary solver failed',stage='solve')
                    elif not solver_result.is_file():
                        result=dict(status='ERROR',reason='solver exited without result.json',stage='solve')
                    else:
                        report=json.loads(solver_result.read_text())
                        result=dict(status=report.get('status','ERROR'),solver_result=str(solver_result),
                                    solver_result_sha256=hashlib.sha256(solver_result.read_bytes()).hexdigest(),
                                    scope='Frozen finite dictionary only; no global UNSAT claim.')
    except KeyboardInterrupt:
        result=dict(status='INTERRUPTED',reason='phase interrupted; owned child process group stopped')
    except Exception as exc:
        if manifest['stages'] and 'exit_code' not in manifest['stages'][-1]:
            manifest['stages'][-1].update(exit_code=None,error=f'{type(exc).__name__}: {exc}')
        result=dict(status='ERROR',reason=f'{type(exc).__name__}: {exc}')
    finally:
        result['elapsed_seconds']=clock()-started
        result['commands_executed']=len(manifest['stages'])
        write_new(output/'manifest.json',manifest)
        write_new(output/'result.json',result)
    return result


def main():
    def interrupted(signum,frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=900)
    parser.add_argument('--candidate',type=Path,action='append',default=[])
    parser.add_argument('--candidate-dir',type=Path,action='append',default=[])
    parser.add_argument('--extra-dictionary',type=Path,action='append',default=[])
    parser.add_argument('--minimum-age',type=float,default=30)
    parser.add_argument('--memory-mb',type=int,default=1536)
    parser.add_argument('--conflicts',type=int,default=100000000)
    args=parser.parse_args()
    result=run_phase(output_dir=args.output_dir,seconds=args.seconds,candidates=args.candidate,
                     candidate_dirs=args.candidate_dir,extra_dictionaries=args.extra_dictionary,
                     minimum_age=args.minimum_age,memory_mb=args.memory_mb,conflicts=args.conflicts)
    print(json.dumps(result,sort_keys=True))
    return 130 if result['status']=='INTERRUPTED' else (2 if result['status']=='ERROR' else 0)


if __name__=='__main__':
    raise SystemExit(main())
