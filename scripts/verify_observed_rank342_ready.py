"""Frozen rank3 tests, trueweight5 small-MM control and no-query n5 lifts."""
import argparse
import importlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.observed_rank342 import prepare_space,decode_rank3,decode_space_hit
from mmsearch.observed_rank3_bounded42 import search_bounded
from mmsearch.observed_rank3_checkpoint42 import append_checkpoint,load_checkpoint,save_checkpoint
from mmsearch.recombine import digest
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared-dir',type=Path,required=True)
    args=p.parse_args();b=args.prepared_dir.resolve();tests=importlib.import_module('tests.test_observed_rank342')
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    if not result.wasSuccessful():raise ValueError(stream.getvalue())
    freeze(b/'controls/tests.log',stream.getvalue().encode())
    system=tests.small_MM();q=prepare_space(system,[9,10,12]);columns=[int(v,16) for v in q['column_syndromes_hex']];targets=[int(v,16) for v in q['targets_hex']]
    negative=decode_rank3(columns,targets,4,1);hit=decode_rank3(columns,targets,5,1);answer=decode_space_hit(system,q,hit['entries'])
    if tests.brute_weight(columns,targets)!=5 or negative['status']!='NO_WEIGHT_LE4' or answer['verification']['rank']!=7:raise AssertionError('small trueweight5 control failed')
    for name,value in (('system',system),('quotient',q),('negative-le4',negative),('hit-weight5',hit),('candidate',answer['candidate']),
                       ('verification',answer['verification']),('lift',answer['lift'])):freeze(b/'controls/small-MM'/(name+'.json'),json_bytes(value))
    toy=dict(column_syndromes_hex=list(map(hex,[1,2,4,8,16,32])),targets_hex=list(map(hex,[3,12,48])),weight_bound=5)
    toy['quotient_sha256']=digest(toy);directory=b/'controls/branch-ledger';cursor=None
    for attempt in range(3):
        report=search_bounded(toy,seconds=1,memory_mb=256,cursor=cursor,branch_budget=1,
            on_progress=lambda record,state:append_checkpoint(directory,toy['quotient_sha256'],record,state))
        save_checkpoint(directory,toy['quotient_sha256'],report.get('cursor'));cursor=load_checkpoint(directory,toy['quotient_sha256'])
        freeze(directory/f'attempt-{attempt}.json',json_bytes(report))
    if report['status']!='NO_ONE_SUBSPACE_GAIN' or cursor['next_branch']!=3:raise AssertionError('branch checkpoint did not close exact prefix')
    launcher=b/'code/scripts/campaign_observed_rank342.py';out=b/'controls/runtime-controls'
    command=[sys.executable,'-B',str(launcher),'--prepared-dir',str(b),'--output-dir',str(out),'--controls-only',
        '--seconds','60','--per-case-seconds','2','--memory-mb','1024']
    done=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=65)
    if done.returncode:raise ValueError(done.stderr)
    report=read_json((out/'report-launch000.json').read_bytes())
    if report['status']!='CONTROLS_PASSED' or report['target_queries_this_launch']!=0:raise AssertionError('runtime source lifts queried a target')
    done=subprocess.run([*command,'--restart'],cwd='/tmp',capture_output=True,text=True,timeout=15)
    if done.returncode:raise ValueError(done.stderr)
    resumed=read_json((out/'report-launch001.json').read_bytes())
    if resumed['target_queries_this_launch']!=0 or resumed['next_index']!=report['next_index']:raise AssertionError('terminal restart changed coverage')
    bad=b/'controls/bad-global-cursor';bad.mkdir();freeze(bad/'config.json',(out/'config.json').read_bytes())
    corrupt=read_json((out/'cursor.json').read_bytes());corrupt['config_sha256']='corrupt';freeze(bad/'cursor.json',json_bytes(corrupt))
    reject=[*command,'--restart'];reject[reject.index('--output-dir')+1]=str(bad)
    done=subprocess.run(reject,cwd='/tmp',capture_output=True,text=True,timeout=10)
    if done.returncode==0:raise AssertionError('corrupt global cursor accepted')
    validation=dict(status='PASS',tests=result.testsRun,exhaustive_small_column_families=4845,random_subset_oracle_families=350,
        inside_and_same_coset_pair_branches_tested=True,distinct_cosets_never_combined_for_weight4=True,
        branch_budget_UNKNOWN_resume_and_ledger_tested=True,corrupt_cursor_and_lift_rejected=True,unsupported_budget6_nonclosed=True,
        small_MM_source_rank=8,small_MM_target_rank=7,small_MM_exact_minimum_groupweight=5,small_MM_tensor_entries=64,
        all3original_coordinate_kernels_verified=True,n5_baseline_lift_controls=report['next_index'],n5_entries_each=15625,
        campaign_target_decoder_queries=0,terminal_restart_queries=0,corrupt_global_cursor_rejected=True,
        frozen_control_script=str(Path(__file__).resolve()),runtime_cwd='/tmp',command=command)
    freeze(b/'VALIDATION.json',json_bytes(validation));print(json.dumps(validation,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
