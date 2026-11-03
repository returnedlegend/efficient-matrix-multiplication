"""Run a frozen finite quartet catalog independently on verified fresh W models."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.free_factor_kernel import decode_checked
from mmsearch.free_factor_sat import build_system
from mmsearch.verify import verify_candidate
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json


_CREATED_OUTPUT=None

def digest(raw):return hashlib.sha256(raw).hexdigest()


def run_cases(cases,invoke):
    results=[]
    for case in cases:
        result=invoke(case);results.append(result)
        if result['winner'] or result['status'] not in ('NO_TARGET',):break
    return results


def main():
    global _CREATED_OUTPUT
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=240);p.add_argument('--case-seconds',type=float,default=90)
    p.add_argument('--deadline-utc')
    args=p.parse_args();b=args.bundle.resolve();out=args.output_dir.resolve()
    if not 3<args.seconds<=3600 or not 3<args.case_seconds<=args.seconds:p.error('invalid batch budgets')
    out.mkdir(parents=True,exist_ok=False);_CREATED_OUTPUT=out;started=time.monotonic()
    plan=read_json((b/'batch.json').read_bytes())
    for name,expected in plan['files'].items():
        if digest((b/name).read_bytes())!=expected:raise ValueError('frozen batch binding mismatch: '+name)
    dictionary=b/plan['dictionary'];circuits=b/plan['circuits'];catalog=b/plan['catalog'];binary=b/plan['binary']
    dictionary_value=read_json(dictionary.read_bytes());model_hashes=set()
    for case in plan['cases']:
        baseline=b/case['baseline']
        system=build_system(dictionary_value,5,plan['orientation'],read_json(baseline.read_bytes()))
        _,report=decode_checked(system,system['baseline_vectors'])
        raw=''.join(str(w)+'\n' for w in system['baseline_vectors']).encode();model_sha=digest(raw)
        if (report['rank']!=93 or report['exact_entries_checked']!=15625 or model_sha!=case['model_sha256'] or
                model_sha==plan['original_model_sha256'] or model_sha in model_hashes):
            raise ValueError('batch case is not a distinct verified new raw93 W model')
        model_hashes.add(model_sha)
    freeze(out/'batch-plan.json',json_bytes(plan));results=[]
    def invoke(case):
        remaining=args.seconds-(time.monotonic()-started)-2
        if remaining<=3:return dict(case_id=case['id'],status='UNKNOWN',winner=False,reason='batch budget before dispatch')
        destination=out/case['id']
        command=[sys.executable,'-B',str(b/plan['launcher']),'--dictionary',str(dictionary),'--baseline',str(b/case['baseline']),
            '--circuits',str(circuits),'--quartet-catalog',str(catalog),'--binary',str(binary),'--orientation',plan['orientation'],
            '--outdir',str(destination),'--seconds',str(min(args.case_seconds,remaining))]
        if args.deadline_utc:command+=['--deadline-utc',args.deadline_utc]
        freeze(out/(case['id']+'.command.json'),json_bytes(command))
        done=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=remaining+5)
        freeze(out/(case['id']+'.stdout.log'),done.stdout.encode());freeze(out/(case['id']+'.stderr.log'),done.stderr.encode())
        if done.returncode:return dict(case_id=case['id'],status='ERROR',winner=False,exit_code=done.returncode)
        summary=read_json((destination/'summary.json').read_bytes());manifest=read_json((destination/'manifest.json').read_bytes())
        if (manifest['input_sha256']!=case['input_sha256'] or manifest['catalog_sha256']!=plan['catalog_sha256'] or
                manifest['binary_sha256']!=plan['binary_sha256'] or manifest['start_row']!=0 or manifest['resume_from'] is not None):
            raise ValueError('case inherited coverage or differs from its frozen model/catalog/binary')
        if summary['winner']:
            winner_raw=(destination/'WINNER.json').read_bytes();winner=read_json(winner_raw)
            report=verify_candidate(winner,random_trials=0)
            if winner.get('dimension')!=5 or report['rank']>92 or not report['valid'] or report['exact_entries_checked']!=15625:
                raise ValueError('batch winner failed independent full5x5 verification')
            freeze(out/'WINNER.json',winner_raw);freeze(out/'WINNER.verification.json',json_bytes(report))
        return dict(case_id=case['id'],model_sha256=case['model_sha256'],status=summary['status'],winner=summary['winner'],
                    coverage=summary['coverage'],exact_entries_checked=summary['exact_entries_checked'])
    results=run_cases(plan['cases'],invoke)
    winner=any(result['winner'] for result in results)
    status='VERIFIED_TARGET' if winner else ('NO_TARGET' if len(results)==len(plan['cases']) and all(result['status']=='NO_TARGET' for result in results) else results[-1]['status'])
    summary=dict(status=status,winner=winner,cases=results,planned_cases=len(plan['cases']),
        inherited_old_model_coverage=False,each_case_started_at_row0=True,elapsed_seconds=time.monotonic()-started,
        scope='The same explicit finite quartet catalog is scanned separately on each listed new raw93 W model. '
              'Coverage belongs only to that exact input hash; no old-model exclusions or negative credit transfer. '
              'NO_TARGET is finite-catalog only. Batch stops before the next case on a verified winner or incomplete/error case.')
    freeze(out/'summary.json',json_bytes(summary));print(json.dumps(summary,sort_keys=True));return 0 if status!='ERROR' else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        if _CREATED_OUTPUT is not None and not (_CREATED_OUTPUT/'summary.json').exists():
            freeze(_CREATED_OUTPUT/'summary.json',json_bytes(dict(status='ERROR',winner=False,reason=str(error))))
        raise
