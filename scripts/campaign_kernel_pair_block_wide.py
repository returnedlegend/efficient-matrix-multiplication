"""Wide3..128 exact two-direction scans on one frozen feasible free-factor model."""
import argparse
import datetime
import hashlib
import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.free_factor_kernel import decode_checked,pair_column
from mmsearch.free_factor_kernel_wide import native_input,validate_circuit
from mmsearch.free_factor_sat import audit,build_system
from mmsearch.kernel_pair_block_wide import validate_pair_solution
from scripts.campaign_kernel_walk_v2 import atomic_json,export_checkpoints,read_vectors
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json

ROOT=Path(__file__).resolve().parents[1]


def cursor_ordinal(count,i,j):
    total=count*(count-1)//2
    if i==count-1 and j==count:return total
    if not 0<=i<count-1 or not i<j<count:raise ValueError('invalid saved lexicographic cursor')
    return i*(2*count-i-1)//2+j-i-1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dictionary',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--circuits',type=Path,required=True);p.add_argument('--orientation',choices=('uv','vw','wu'),default='wu')
    p.add_argument('--outdir','--output-dir',dest='outdir',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=600);p.add_argument('--max-pairs',type=int,default=0)
    p.add_argument('--binary',type=Path,default=ROOT/'native/free_factor_pair_block_worker_wide')
    p.add_argument('--prepare-only',action='store_true');p.add_argument('--resume-from',type=Path)
    p.add_argument('--deadline-utc')
    args=p.parse_args()
    if not math.isfinite(args.seconds) or args.seconds<=2 or args.max_pairs<0:p.error('invalid scan budgets')
    started=time.monotonic();out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    if args.deadline_utc:
        cutoff=datetime.datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00')).timestamp()
        args.seconds=min(args.seconds,max(0,cutoff-time.time()))
        if args.seconds<=2:
            atomic_json(out/'summary.json',dict(status='UNKNOWN',reason='global deadline leaves no safe scan budget',native_dispatched=False))
            return 0
    inputs={name:path.read_bytes() for name,path in [('dictionary',args.dictionary),('baseline',args.baseline),('circuits',args.circuits)]}
    for name,raw in inputs.items():freeze(out/'inputs'/(name+'.json'),raw)
    baseline=read_json(inputs['baseline']);system=build_system(read_json(inputs['dictionary']),5,args.orientation,baseline)
    if system['metadata']['baseline']['canonical_rank']!=93:raise ValueError('main scan requires exact5x5 baseline93')
    decode_checked(system,system['baseline_vectors'])
    circuits=read_json(inputs['circuits']);columns=[pair_column(pair,25) for pair in system['pairs']];supports=set()
    for circuit in circuits:
        validate_circuit(columns,circuit['support']);key=tuple(sorted(circuit['support']))
        if key in supports:raise ValueError('duplicate circuit support in finite catalog')
        supports.add(key)
    if len(circuits)<2:raise ValueError('at least two distinct wide circuits required')
    raw_input=native_input(system,circuits);input_sha=hashlib.sha256(raw_input).hexdigest()
    freeze(out/'kernel_input.txt',raw_input);freeze(out/'system.json',json_bytes(system));freeze(out/'system.audit.json',json_bytes(audit(system)))
    names=['scripts/campaign_kernel_pair_block_wide.py','mmsearch/kernel_pair_block_wide.py','mmsearch/kernel_pair_block.py','mmsearch/free_factor_kernel_wide.py','native/free_factor_pair_block_worker_wide.cpp',
           'mmsearch/free_factor_kernel.py','mmsearch/free_factor_sat.py','scripts/campaign_kernel_walk_v2.py',
           'mmsearch/verify.py','mmsearch/search.py','mmsearch/recombine.py','scripts/scan_slice_compressions.py']
    code={name:(ROOT/name).read_bytes() for name in names}
    for name,raw in code.items():freeze(out/'code'/name,raw)
    binary_raw=args.binary.read_bytes();binary_sha=hashlib.sha256(binary_raw).hexdigest()
    binary=out/'native-worker';freeze(binary,binary_raw);binary.chmod(0o555)
    start_i,start_j=0,1;prior=0;resume_sha=None
    if args.resume_from:
        previous=args.resume_from.resolve();old=read_json((previous/'manifest.json').read_bytes())
        stats=read_json((previous/'native_final_stats.json').read_bytes());summary=read_json((previous/'summary.json').read_bytes())
        if old['input_sha256']!=input_sha or old['binary_sha256']!=binary_sha:raise ValueError('resume instance/code differs')
        if not summary['coverage']['contiguous_from_initial']:raise ValueError('resume prefix is not certified contiguous')
        start_i,start_j=stats['next_i'],stats['next_j'];prior=summary['coverage']['prefix_completed']
        if prior!=cursor_ordinal(len(circuits),start_i,start_j):raise ValueError('resume cursor/count mismatch')
        resume_sha=hashlib.sha256((previous/'summary.json').read_bytes()).hexdigest()
    total=len(circuits)*(len(circuits)-1)//2
    manifest=dict(input_sha256=input_sha,binary_sha256=binary_sha,source_paths=dict(dictionary=str(args.dictionary.resolve()),
                  baseline=str(args.baseline.resolve()),circuits=str(args.circuits.resolve())),
                  source_sha256={name:hashlib.sha256(raw).hexdigest() for name,raw in inputs.items()},
                  code_sha256={name:hashlib.sha256(raw).hexdigest() for name,raw in code.items()},
                  pairs_total=total,circuits=len(circuits),baseline_active=sum(bool(w) for w in system['baseline_vectors']),
                  resume_from=str(args.resume_from) if args.resume_from else None,resume_summary_sha256=resume_sha,
                  start_i=start_i,start_j=start_j,prefix_completed_before=prior,
                  scope='One frozen feasible W model and unordered pairs of supplied kernel directions; no global UNSAT claim.')
    if args.prepare_only:
        freeze(out/'manifest.json',json_bytes(manifest));print(json.dumps(dict(status='PREPARED',pairs_total=total,pair_count=len(columns),baseline_rank=manifest['baseline_active'])));return 0
    remaining=args.seconds-(time.monotonic()-started)-2
    if remaining<=0:
        freeze(out/'manifest.json',json_bytes(manifest));atomic_json(out/'summary.json',dict(status='UNKNOWN',reason='preparation exhausted budget'));return 0
    prefix=out/'phase-000/block_scan';prefix.parent.mkdir()
    command=[str(binary),'--input',str(out/'kernel_input.txt'),'--output',str(prefix),'--target','92',
             '--seconds',str(remaining),'--start-i',str(start_i),'--start-j',str(start_j),
             '--max-pairs',str(args.max_pairs),'--input-sha256',input_sha,'--baseline-sha256',manifest['source_sha256']['baseline']]
    manifest['command']=command;freeze(out/'manifest.json',json_bytes(manifest));stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    with (out/'worker.log').open('x') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        try:
            while process.poll() is None and not stopped:
                if prefix.with_suffix('.stats.json').exists():atomic_json(out/'progress.json',read_json(prefix.with_suffix('.stats.json').read_bytes()))
                time.sleep(.2)
        finally:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:process.kill();process.wait()
    if process.returncode!=0:
        atomic_json(out/'summary.json',dict(status='ERROR',exit_code=process.returncode));return 2
    raw=prefix.with_suffix('.stats.json').read_bytes();stats=read_json(raw);freeze(out/'native_final_stats.json',raw)
    if stats['input_sha256']!=input_sha:raise ValueError('native instance hash mismatch')
    if stats['status']=='MODEL_FOUND' and (Path(str(prefix)+'.solution.json')).exists():
        proof_raw=Path(str(prefix)+'.solution.json').read_bytes();proof=read_json(proof_raw)
        moved,candidate,report=validate_pair_solution(system,circuits,proof)
        if moved!=read_vectors(Path(str(prefix)+'.best.w.txt'),len(columns),25):raise ValueError('native model differs from block proof')
        freeze(out/'solution.json',proof_raw);freeze(out/'independent-block-optimum.json',json_bytes(report))
    checked=export_checkpoints(prefix,out,system,manifest,target=92,final=True)
    complete=prior+stats['pairs_considered'];next_ordinal=cursor_ordinal(len(circuits),stats['next_i'],stats['next_j'])
    if complete!=next_ordinal:raise ValueError('native lexicographic coverage/count mismatch')
    coverage=dict(pairs_total=total,pairs_completed_this_run=stats['pairs_considered'],prefix_completed=complete,
                  contiguous_from_initial=True,full_family_completed=stats['status']=='NO_TARGET' and complete==total,
                  last_complete_pair=[stats['last_complete_i'],stats['last_complete_j']],next_pair=[stats['next_i'],stats['next_j']])
    status='VERIFIED_TARGET' if checked['winner'] else stats['status']
    summary=dict(status=status,reason=stats['reason'],winner=checked['winner'],coverage=coverage,
                 disjoint_pruned=stats['disjoint_pruned'],bound_pruned=stats['bound_pruned'],
                 exact_evaluated=stats['exact_evaluated'],elapsed_seconds=time.monotonic()-started,scope=manifest['scope'])
    atomic_json(out/'summary.json',summary);print(json.dumps(summary,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
