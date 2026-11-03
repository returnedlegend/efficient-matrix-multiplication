"""Frozen empty-catalog launch and stop-on-winner batch controls."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.campaign_quartet_fresh_model_batch42 import run_cases,digest
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True)
    args=p.parse_args();b=args.bundle.resolve();plan=read_json((b/'batch.json').read_bytes())
    calls=[]
    def winner(case):calls.append(case);return dict(status='VERIFIED_TARGET',winner=True)
    if len(run_cases([1,2,3,4],winner))!=1 or calls!=[1]:raise ValueError('batch did not stop immediately on winner')
    fixture=b/'controls/empty-bundle';fixture.mkdir(parents=True)
    empty=b'MMKQUARTETS1 0\n';freeze(fixture/'quartets.txt',empty)
    test=copy.deepcopy(plan)
    test['files']={'../../'+name:value for name,value in plan['files'].items()}
    test['files']['quartets.txt']=digest(empty)
    for name in ('dictionary','circuits','binary','launcher'):test[name]='../../'+plan[name]
    test['catalog']='quartets.txt';test['catalog_sha256']=digest(empty)
    for case in test['cases']:case['baseline']='../../'+case['baseline']
    freeze(fixture/'batch.json',json_bytes(test))
    command=[sys.executable,'-B',str(b/'code/scripts/campaign_quartet_fresh_model_batch42.py'),
        '--bundle',str(fixture),'--output-dir',str(b/'controls/empty-batch-output'),'--seconds','15','--case-seconds','5']
    done=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=20)
    if done.returncode:raise ValueError(done.stderr)
    result=read_json((b/'controls/empty-batch-output/summary.json').read_bytes())
    if result['status']!='NO_TARGET' or len(result['cases'])!=len(plan['cases']) or any(case['coverage']['prefix_completed']!=0 for case in result['cases']):
        raise ValueError('empty fresh-model launch control failed')
    # A source hash claiming the old W must fail before any target child dispatch.
    bad=b/'controls/invalid-old-source-bundle';bad.mkdir()
    bad_plan=copy.deepcopy(test);bad_plan['cases'][0]['model_sha256']=bad_plan['original_model_sha256']
    freeze(bad/'quartets.txt',empty);freeze(bad/'batch.json',json_bytes(bad_plan))
    rejected=[*command];rejected[rejected.index('--bundle')+1]=str(bad);rejected[rejected.index('--output-dir')+1]=str(b/'controls/rejected-old-source-output')
    done=subprocess.run(rejected,cwd='/tmp',capture_output=True,text=True,timeout=10)
    if done.returncode==0:raise ValueError('old-model identity was accepted as a fresh case')
    if list((b/'controls/rejected-old-source-output').glob('case-*')):raise ValueError('invalid case was dispatched before rejection')
    report=dict(status='PASS',frozen_control_script=str(Path(__file__).resolve()),runtime_cwd='/tmp',
        stop_on_verified_winner_callback=True,full_empty_catalog_cases=len(plan['cases']),
        all_cases_checked15625=True,all_cases_start_row0=True,no_old_model_coverage_inherited=True,
        old_model_identity_rejected_before_dispatch=True,actual100k_target_rows_evaluated=0,command=command)
    freeze(b/'VALIDATION.json',json_bytes(report));print(json.dumps(report,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
