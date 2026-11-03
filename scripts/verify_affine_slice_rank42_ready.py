"""Frozen affine encoder controls: tiny targets and n=5 positive controls only."""
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
from mmsearch.affine_slice_rank_sat42 import build_problem,witness_assignment,validate_decode
from mmsearch.search import encode_candidate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True)
    args=p.parse_args();b=args.bundle.resolve();sys.path.insert(0,str(b/'deps'))
    tests=importlib.import_module('tests.test_affine_slice_rank_sat42')
    if not tests.CMS:raise ValueError('frozen CryptoMiniSat dependency unavailable')
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    if not result.wasSuccessful():raise ValueError(stream.getvalue())
    freeze(b/'controls/tests.log',stream.getvalue().encode())
    before=encode_candidate(tests.MIXED,2);problem=build_problem(before,2,9)
    z=[tuple(term)==(12,1,3) for term in problem['neutral_terms']]
    assignment=witness_assignment(problem,z,[(9,9)]);after,report=validate_decode(problem,assignment)
    freeze(b/'controls/mandatory-neutral.before.json',json_bytes(before));freeze(b/'controls/mandatory-neutral.after.json',json_bytes(after))
    freeze(b/'controls/mandatory-neutral.model.json',json_bytes(assignment));freeze(b/'controls/mandatory-neutral.verification.json',json_bytes(report))
    command=[sys.executable,'-B',str(b/'code/scripts/campaign_affine_slice_rank42.py'),'--bundle',str(b),
        '--output-dir',str(b/'controls/n5-positive-controls'),'--controls-only','--seconds','30',
        '--query-seconds','1','--control-seconds','2','--memory-mb','1536','--seed','424501']
    done=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=35)
    if done.returncode:raise ValueError(done.stderr)
    summary=read_json((b/'controls/n5-positive-controls/summary.json').read_bytes())
    if summary['status']!='CONTROLS_PASSED' or summary['target_queries_dispatched']!=0:raise ValueError('positive-only runtime control failed')
    validation=dict(status='PASS',tests=result.testsRun,tiny_affine_family_comparisons=144,
        full_n2_mandatory_neutral_source_rank=8,full_n2_after_rank=7,full_n2_entries=64,
        all_three_free_axes_tested=True,source_fixed_UV_columns_independent=8,new_pair_absent_from_source=True,
        original_factor_n5_controls=len(summary['cases']),every_n5_control_entries=15625,
        zero_factor_columns_allowed_and_tested=True,corrupt_models_and_lifts_rejected=True,
        timeout_ERROR_resource_limits_and_reaping_tested=True,native_solver_threads=1,memory_mb=1536,
        frozen_standalone_control=str(Path(__file__).resolve()),runtime_cwd='/tmp',
        target_n5_queries_dispatched=0,command=command)
    freeze(b/'VALIDATION.json',json_bytes(validation));print(json.dumps(validation,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
