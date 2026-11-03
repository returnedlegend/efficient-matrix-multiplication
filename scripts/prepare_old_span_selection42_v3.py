"""Freeze a small selection overlay; old-span math/runtime remain immutable v2."""
import argparse
import datetime as dt
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mmsearch import hyperplane_rankone42 as hp
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json
from scripts.campaign_hyperplane_catalog42 import pid_ticks
from scripts.prepare_old_span_census_support42 import manifest
import os


def sha(raw):return hashlib.sha256(raw).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--upstream',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();old=a.upstream.resolve();out=a.output_dir.resolve()
    out.mkdir(parents=True,exist_ok=False);catalog=read_json((old/'catalog.json').read_bytes());byid={x['id']:x for x in catalog['cases']}
    def source(case):return hp.prepare_source(read_json((old/case['source_file']).read_bytes()),case['free_axis'])
    deferred=[];removed=set()
    for axis in [1,2]:
        rep=f'source-0-axis-{axis}';duplicate=f'source-1-axis-{axis}';left=source(byid[rep]);right=source(byid[duplicate])
        lb=hp.canonical_span(left['A_columns']);rb=hp.canonical_span(right['A_columns'])
        if not(lb==rb and left['target_columns']==right['target_columns']and left['free_axis']==right['free_axis']):raise AssertionError('physical S/target not exactly equal')
        witness=dict(representative=rep,deferred=duplicate,free_axis=axis,canonical_basis_reference=lb,
            canonical_basis_deferred=rb,target_columns_reference=left['target_columns'],target_columns_deferred=right['target_columns'],
            exact_basis_equality=True,exact_target_equality=True,rank=93,
            reference_columns_in_canonical_basis=[hp.coordinates(lb,c)for c in left['A_columns']],
            deferred_columns_in_canonical_basis=[hp.coordinates(lb,c)for c in right['A_columns']],
            negative_coverage_transferred=False,
            scope='Deferred and unsearched. A representative complete census plus support UNSAT would exclude this same S/axis/target. Partial-catalog negatives do not transfer.')
        for columns,reps in [(left['A_columns'],witness['reference_columns_in_canonical_basis']),(right['A_columns'],witness['deferred_columns_in_canonical_basis'])]:
            if any(c is None or hp.combine(lb,c)!=column for column,c in zip(columns,reps)):raise AssertionError('span-coordinate witness failed')
        freeze(out/f'witnesses/deferred-axis-{axis}.json',json_bytes(witness));deferred.append(dict(id=duplicate,representative=rep,witness=f'witnesses/deferred-axis-{axis}.json',status='DEFERRED_UNSEARCHED',negative_coverage_transferred=False));removed.add(duplicate)
    selected=[x['id']for x in catalog['cases']if x['id']not in removed]
    if len(selected)!=10:raise AssertionError('selection not10')
    # Exact canonical rows, not a hash-only deduplication.
    exact_keys=[(x['free_axis'],hp.canonical_span(source(x)['A_columns']),source(x)['target_columns'])for x in catalog['cases']if x['id']in selected]
    if any(exact_keys[i]==exact_keys[j]for i in range(10)for j in range(i)):raise AssertionError('selected physicalS duplicates')
    reuse=dict(upstream_bundle=str(old),upstream_manifest_sha256=sha((old/'manifest.json').read_bytes()),
        upstream_full_manifest_sha256=sha((old/'full-manifest.json').read_bytes()),runtime_root=str(old/'runtime'),
        math_runtime_changed=False,model_formulas_changed=False)
    freeze(out/'REUSE.json',json_bytes(reuse));freeze(out/'selection.json',json_bytes(dict(representative_ids=selected,deferred=deferred,
         original_models=12,distinct_physical_S_axis_target=10,negative_coverage_transferred=False)))
    driver=out/'runtime/scripts/campaign_old_span_census_support42_v3.py'
    freeze(driver,(ROOT/'scripts/campaign_old_span_census_support42_v3.py').read_bytes())
    freeze(out/'provenance/prepare_old_span_selection42_v3.py',Path(__file__).read_bytes())
    # Selection-only controls use the unchanged v2 n2 formulas/decoder.
    small=out/'controls/small-overlay';smallold=old/'controls/small-bundle';smallcatalog=read_json((smallold/'catalog.json').read_bytes())
    freeze(small/'REUSE.json',json_bytes(dict(upstream_bundle=str(smallold),upstream_manifest_sha256=sha((smallold/'manifest.json').read_bytes()),runtime_root=str(old/'runtime'))))
    freeze(small/'selection.json',json_bytes(dict(representative_ids=[x['id']for x in smallcatalog['cases']])));manifest(small)
    controlout=out/'controls/filtered-native-cli';guard=out/'controls/guard.json'
    for name in ['positive-partial8','positive-partial10']:
        freeze(controlout/f'cases/{name}/census/checkpoint.json',(old/f'controls/actual-native-cli/cases/{name}/census/checkpoint.json').read_bytes())
    guard.write_bytes(json_bytes(dict(updated_utc=dt.datetime.now(dt.timezone.utc).isoformat(),pid=os.getpid(),
         process_identity=dict(start_ticks=pid_ticks(os.getpid())),campaign_allocated_bytes=int(4.25*1024**3),rss_bytes=128*1024**2,filesystem_free_bytes=16*1024**3,stop_reason=None)))
    manifest(out)
    command=['python3','-B',str(driver),'--bundle',str(small),'--output-dir',str(controlout),'--guard',str(guard),
       '--small-controls','--seed','2026110343301','--case-id','positive-partial8','--case-id','positive-partial10']
    run=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=20)
    freeze(out/'controls/filtered-first.log',(run.stdout+run.stderr).encode())
    if run.returncode:raise RuntimeError('filtered frozen CLI failed')
    summary=read_json((controlout/'summary.json').read_bytes())
    if summary['coverage_counts']!={'PARTIAL_CATALOG_UNSAT':1,'CONTROL_PASSED':1}or summary['phase_queries']!=2 or summary['cursor']!=0:raise AssertionError('filtered cursor/control failed')
    again=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=10)
    freeze(out/'controls/filtered-resume.log',(again.stdout+again.stderr).encode())
    resumed=read_json((controlout/'summary.json').read_bytes())
    if again.returncode or resumed['phase_queries']:raise AssertionError('filtered resume queried')
    before=(controlout/'coverage.json').read_bytes()
    changed=subprocess.run(command[:-2],cwd='/tmp',capture_output=True,text=True,timeout=10)
    freeze(out/'controls/changed-selection.log',(changed.stdout+changed.stderr).encode())
    if changed.returncode==0 or (controlout/'coverage.json').read_bytes()!=before:raise AssertionError('changed selection was not rejected before cursor mutation')
    # There is no production query in preparation, and no mathematical module copy.
    report=dict(status='PASS',selected_cases=10,deferred_duplicates=2,exact_canonical_basis_and_target_checks=True,
        unchanged_v2_math_runtime=True,n2_filtered_native_queries=2,n2_resume_queries=0,filtered_cursor=0,
        changed_selection_rejected_without_cursor_mutation=True,production_queries=0)
    freeze(out/'controls/CONTROL_REPORT.json',json_bytes(report))
    freeze(out/'PROOF.md',('The v2 PROOF.md and all mathematical encoders/decoders remain unchanged and pinned by REUSE.json. '
        'This selection-only driver delegates run_case/source_for/verify_export directly to immutable v2 runtime. '
        'Ten selected representatives have distinct exact canonical old-span bases with free-axis/target. '
        'Two duplicates remain DEFERRED_UNSEARCHED. Their witnesses store both actual canonical bases, actual target columns, and exact span coordinates. '
        'No negative result is transferred during prep. Only a representative complete-census plus support-UNSAT result permits a same-S exclusion; partial-catalog UNSAT never transfers. '
        'Coverage identity includes the ordered selected IDs, upstream catalog and both manifests. A changed selection on existing output is rejected before cursor mutation.\n').encode())
    # Refresh launch manifest after controls: runtime identity remains immutable.
    (out/'manifest.json').unlink();manifest(out)
    job=read_json((old/'PROPOSED-JOB.json').read_bytes());job.update(id='old-span-census-support42-pilot3',command=[
       'python3','-B',str(driver),'--bundle',str(out),'--output-dir',str(out.parent/'old-span-census-support42-state-v3'),
       '--guard',str(out.parent/'operations-v3/state.json'),'--seconds','1800','--census-seconds','60','--support-seconds','60',
       '--oracle-seconds','5','--memory-mb','1536','--phase-mb','128','--cap','4096','--seed','2026110343301',
       '--stop-file',str(out.parent/'WINNER.json'),'--deadline-utc','2026-11-04T21:31:16Z']+sum([['--case-id',x]for x in selected],[]))
    freeze(out/'PROPOSED-JOB.json',json_bytes(job));ready=dict(status='READY_UNLAUNCHED',selected_cases=10,deferred_same_S_cases=2,
        negative_coverage_transferred=False,production_queries=0,math_runtime='immutable preferred v2',
        control_report=report,manifest_sha256=sha((out/'manifest.json').read_bytes()),driver_sha256=sha(driver.read_bytes()),
        upstream_READY_sha256=sha((old/'READY.json').read_bytes()),upstream_full_manifest_sha256=reuse['upstream_full_manifest_sha256'])
    freeze(out/'READY.json',json_bytes(ready));freeze(out/'full-manifest.json',json_bytes(dict(files={str(x.relative_to(out)):sha(x.read_bytes())for x in out.rglob('*')if x.is_file()and'__pycache__'not in x.parts})))
    for file in out.rglob('*'):
        if file.is_file():file.chmod(0o444)
    print(json_bytes(ready).decode())


if __name__=='__main__':main()
