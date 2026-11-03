"""Frozen standalone frontier runtime controls, without a campaign target scan."""
import argparse
import hashlib
import importlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json
from mmsearch.free_factor_kernel import decode_checked
from mmsearch.search import encode_candidate,naive_terms


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True)
    args=p.parse_args();b=args.bundle.resolve()
    for name,expected in read_json((b/'launch-closure.json').read_bytes()).items():
        if hashlib.sha256((b/'code'/name).read_bytes()).hexdigest()!=expected:raise ValueError('closure hash mismatch')
    tests=importlib.import_module('tests.test_kernel_quartet_frontier');tests.BINARY=b/'native-worker'
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    if not result.wasSuccessful():raise ValueError(stream.getvalue())
    freeze(b/'controls/unit-tests.log',stream.getvalue().encode())
    system,circuits,dictionary=tests.plateau_tensor()
    for name,value in (('dictionary',dictionary),('baseline',encode_candidate(naive_terms(2),2)),('circuits',circuits)):
        freeze(b/'controls/inputs'/(name+'.json'),json_bytes(value))
    freeze(b/'controls/inputs/quartets.txt',b'MMKQUARTETS1 1\n0 1 2 3\n')
    launcher=b/'code/scripts/campaign_kernel_quartet_frontier.py'
    common=[sys.executable,'-B',str(launcher),'--dimension','2','--target','7','--orientation','uv',
        '--dictionary',str(b/'controls/inputs/dictionary.json'),'--baseline',str(b/'controls/inputs/baseline.json'),
        '--circuits',str(b/'controls/inputs/circuits.json'),'--quartet-catalog',str(b/'controls/inputs/quartets.txt'),
        '--binary',str(b/'native-worker'),'--seconds','5','--seed','44']
    first=b/'controls/plateau-run';second=b/'controls/resume-run';commands=[]
    for dest,extra in ((first,[]),(second,['--resume-from',str(first)])):
        command=[*common,'--outdir',str(dest),*extra];commands.append(command)
        done=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=8)
        if done.returncode:raise ValueError(done.stderr)
        summary=read_json((dest/'summary.json').read_bytes())
        if summary['verified_frontier_exports']!=3 or summary['native_shortlist']!=3 or summary['winner']:raise ValueError('plateau export control failed')
    if (first/'native_frontier.txt').read_bytes()!=(second/'native_frontier.txt').read_bytes():raise ValueError('resume lost frontier state')
    exports=read_json((first/'frontier-index.json').read_bytes())
    changed=Path(exports[0]['path'])
    reject=[*common];reject[reject.index('--baseline')+1]=str(changed)
    reject+=['--outdir',str(b/'controls/rejected-fresh-model-resume'),'--resume-from',str(first)]
    done=subprocess.run(reject,cwd='/tmp',capture_output=True,text=True,timeout=8)
    if done.returncode==0:raise ValueError('changed W inherited old coverage')
    rejected=read_json((b/'controls/rejected-fresh-model-resume/summary.json').read_bytes())
    if rejected['status']!='ERROR' or (b/'controls/rejected-fresh-model-resume/phase-000').exists():raise ValueError('fresh-model rejection happened after dispatch')
    # A separate full-MM graft has quartet optimum9, yet cross-orientation
    # compression of an exported plateau tie reaches8 and must emit WINNER.
    split_system,split_circuits,split_dictionary=tests.plateau_tensor(split=True)
    from mmsearch.free_factor_sat import decode_vectors
    for name,value in (('dictionary',split_dictionary),('baseline',decode_vectors(split_system,split_system['baseline_vectors'])),('circuits',split_circuits)):
        freeze(b/'controls/split-inputs'/(name+'.json'),json_bytes(value))
    split_command=[*common]
    for key,name in (('--dictionary','dictionary'),('--baseline','baseline'),('--circuits','circuits')):
        split_command[split_command.index(key)+1]=str(b/'controls/split-inputs'/(name+'.json'))
    split_command[split_command.index('--target')+1]='8'
    split_command+=['--outdir',str(b/'controls/compression-winner-run')]
    done=subprocess.run(split_command,cwd='/tmp',capture_output=True,text=True,timeout=8)
    if done.returncode:raise ValueError(done.stderr)
    split_summary=read_json((b/'controls/compression-winner-run/summary.json').read_bytes())
    native_stats=read_json((b/'controls/compression-winner-run/native_final_stats.json').read_bytes())
    if split_summary['status']!='VERIFIED_TARGET' or split_summary['best_rank']!=8 or native_stats['status']!='NO_TARGET':raise ValueError('cross-orientation winner control failed')
    campaign=read_json((b/'inputs/system.json').read_bytes())
    _,report=decode_checked(campaign,campaign['baseline_vectors'])
    if report['rank']!=93 or report['exact_entries_checked']!=15625:raise ValueError('campaign baseline control failed')
    input_sha=hashlib.sha256((b/'inputs/kernel_input.txt').read_bytes()).hexdigest()
    cat_sha=hashlib.sha256((b/'inputs/quartets.txt').read_bytes()).hexdigest()
    native=[str(b/'native-worker'),'--input',str(b/'inputs/kernel_input.txt'),'--catalog',str(b/'inputs/quartets.txt'),
        '--output',str(b/'controls/native5-zero'),'--input-sha256',input_sha,'--catalog-sha256',cat_sha,'--seconds','0']
    done=subprocess.run(native,capture_output=True,text=True,timeout=4)
    if done.returncode:raise ValueError(done.stderr)
    stats=read_json((b/'controls/native5-zero.stats.json').read_bytes())
    if stats['quartets_considered']!=0 or stats['status']!='UNKNOWN':raise ValueError('native5 zero-row control failed')
    validation=dict(status='PASS',frozen_control_script=str(Path(__file__).resolve()),runtime_cwd='/tmp',
        self_contained_launch=True,plateau_full_MM_rank8_optimum_exports=2,xor_GAP1_raw_rank9_exports=1,
        all3_cross_orientation_compressed_rank8=True,small_MM_entries=64,campaign_baseline_entries=15625,
        same_model_resume_preserves_frontier=True,changed_W_resume_rejected_before_dispatch=True,
        invalid_export_rejected=True,native_shortlist_cap=128,verified_export_cap=16,
        no_all_tie_or_all_near_optimum_coverage_claim=True,campaign_target_quartets_evaluated=0,
        cross_orientation_compression_WINNER_control=True,compression_winner_raw_optimum=9,compression_winner_final_rank=8,commands=commands)
    freeze(b/'VALIDATION.json',json_bytes(validation));print(json.dumps(validation,sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
