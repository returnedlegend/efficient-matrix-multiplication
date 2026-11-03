"""Frozen coupled-encoder controls, with no n=5 target solving."""
import argparse
import importlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json
from mmsearch.two_color_affine_sat42 import build_problem,witness_assignment,validate_decode
from mmsearch.search import encode_candidate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True)
    args=p.parse_args();b=args.bundle.resolve();sys.path.insert(0,str(b/'deps'))
    tests=importlib.import_module('tests.test_two_color_affine_sat42')
    if not tests.CMS:raise ValueError('frozen CryptoMiniSat unavailable')
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    if not result.wasSuccessful():raise ValueError(stream.getvalue())
    freeze(b/'controls/tests.log',stream.getvalue().encode())
    before=encode_candidate(tests.CONTROL,2);problem=build_problem(before,2,10,12,(1,1,0))
    assignment=witness_assignment(problem,[False]*5,[False]*5,[(12,1),(1,10)])
    after,checked=validate_decode(problem,assignment)
    freeze(b/'controls/two-color.before.json',json_bytes(before));freeze(b/'controls/two-color.after.json',json_bytes(after))
    freeze(b/'controls/two-color.model.json',json_bytes(assignment));freeze(b/'controls/two-color.verification.json',json_bytes(checked))
    command=[sys.executable,'-B',str(b/'code/scripts/campaign_two_color_affine42.py'),'--bundle',str(b),
        '--output-dir',str(b/'controls/n5-original-color-controls'),'--controls-only','--seconds','40',
        '--query-seconds','1','--control-seconds','2','--memory-mb','1536','--seed','424601']
    done=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=45)
    if done.returncode:raise ValueError(done.stderr)
    summary=read_json((b/'controls/n5-original-color-controls/summary.json').read_bytes())
    if summary['status']!='CONTROLS_PASSED' or summary['target_queries_dispatched']!=0 or summary['positive_control_spaces']!=6:
        raise ValueError('positive original-color runtime controls failed')
    validation=dict(status='PASS',tests=result.testsRun,tiny_affine_profile_comparisons=80,
        width2_shared_gate_coupling_test=True,rank2_monochrome_skip_verified=True,rank1_monochrome_retained=True,
        all_three_free_axes_full_small_MM=True,root_small_source_rank=8,root_small_target_rank=7,root_small_entries=64,
        small_active_pair_column_rank=8,small_one_color_rank_zero_exclusions=24,
        zero_factor_padding_tested=True,corruption_timeout_ERROR_reaping_tested=True,
        original_color_n5_control_spaces=6,n5_target_profile_references=len(summary['cases']),n5_control_entries_each=15625,
        target_n5_queries_dispatched=0,self_contained_runtime_cwd='/tmp',
        frozen_control_script=str(Path(__file__).resolve()),command=command)
    freeze(b/'VALIDATION.json',json_bytes(validation));print(json.dumps(validation,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
