#!/usr/bin/env python3
"""Freeze a disabled atmost25case local12 surplus-two pilot after bounded prep."""
import argparse
from collections import deque
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,read,sha
from scripts.phase_coordinator42_v2 import validate_job
from mmsearch.recombine import digest
from mmsearch.observed_rank3_lazy42 import chain_read


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prep',type=Path,required=True);p.add_argument('--small-bundle',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();prep=a.prep.resolve();out=a.output_dir.resolve()
    manifest='manifest.json' if (prep/'manifest.json').exists() else 'PARTIAL-MANIFEST.json'
    for name,expected in read(prep/manifest)['files'].items():
        if sha(prep/name)!=expected:raise ValueError('prep release changed')
    report=read(prep/'REPORT.json');inputplan=read(prep/'INPUT-PLAN.json');records,chain=chain_read(prep/'candidates.jsonl',report['config_sha256'])
    if report['status'] not in ('PREPARED_BOUNDED_SAMPLE','UNKNOWN') or report['decoder_queries']!=0 or report['result_chain_sha256']!=chain or len(records)!=report['committed']:raise ValueError('prep completed-prefix journal differs')
    retained=[r for r in records if r['disposition']=='RETAINED']
    if [r['case'] for r in retained]!=report['retained_cases']:raise ValueError('retainedcase registry differs')
    queues={s:deque(r for r in retained if r['case']['source_id']==s) for s in range(4)};selected=[]
    while len(selected)<25 and any(queues.values()):
        for s in range(4):
            if queues[s] and len(selected)<25:selected.append(queues[s].popleft())
    if not selected:raise ValueError('no surviving case; do not create empty query pilot')
    out.mkdir(parents=True,exist_ok=False)
    for s in range(4):freeze(out/f'source-{s}.json',(prep/f'source-{s}.json').read_bytes())
    for name in ['small-source.json','small-core.json','small-plan.json']:freeze(out/name,(a.small_bundle/name).read_bytes())
    freeze(out/'plan.json',dict(cases=[r['case'] for r in selected],family=dict(local_products=12,mode_rank=9,target_products=11,max_vectors=1023,max_extensions=1533),
        prep=str(prep),prep_manifest_file=manifest,prep_manifest_sha256=sha(prep/manifest),prep_census_status=report['status'],prep_completed_filter_records=len(records),prep_unfinished_candidate_excluded=report['pending'],prep_result_chain_sha256=chain,prep_config_sha256=report['config_sha256'],
        decoder_sha256=sha(ROOT/'mmsearch/surplus_two7.py'),rank3_filter=report['rank3_filter'],scope='Atmost25explicit local12/image9/target11 residuals; no oldlocal10negative transfer. UNKNOWN remains open.'))
    freeze(out/'SELECTED-PREP-RECORDS.json',selected)
    for path in (ROOT/'mmsearch').glob('*.py'):freeze(out/'runtime/mmsearch'/path.name,path.read_bytes())
    for name in ['__init__.py','verify_record42_independent.py','marathon7_local_campaign.py','marathon7_local12_campaign.py']:
        path=ROOT/'scripts'/name;freeze(out/'runtime/scripts'/name,path.read_bytes() if path.exists() else b'')
    freeze(out/'runtime/marathon7_local12_campaign.py',(ROOT/'scripts/marathon7_local12_campaign.py').read_bytes())
    freeze(out/'runtime/tests/__init__.py',b'')
    for name in ['test_marathon7_local.py','test_marathon7_local12.py','test_marathon7_local12_runtime.py']:freeze(out/'runtime/tests'/name,(ROOT/'tests'/name).read_bytes())
    freeze(out/'marathon7_local12_bundle.py',Path(__file__).read_bytes())
    freeze(out/'launch-manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    job=dict(id='marathon7-local12-pilot025-v1',enabled=False,cpu=1,memory_mb=1024,seconds=530,command=['python3','-B',str(out/'runtime/marathon7_local12_campaign.py'),'--bundle',str(out),'--output-dir',str(out.parent/'marathon7-local12-pilot025-v1'),'--chunk-id','000',
        '--seconds','500','--per-case-seconds','20','--memory-mb','1024','--deadline-utc','2026-11-03T19:24:17Z','--guard-state',inputplan['guard_state']])
    validate_job(job);freeze(out/'PROPOSED-JOB.json',job)
    freeze(out/'READY.json',dict(status='DISABLED_PENDING_INDEPENDENT_PREP_AND_RUNTIME_QA',cases=len(selected),prep_candidates=report['unique_masks_before_filter'],prep_retained=len(retained),decoder_queries=0,job_schema_validated=True,launch_manifest_sha256=sha(out/'launch-manifest.json')))
    freeze(out/'manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    print(__import__('json').dumps(dict(status='DISABLED_PENDING_INDEPENDENT_PREP_AND_RUNTIME_QA',cases=len(selected),manifest_sha256=sha(out/'manifest.json'),proposal_sha256=sha(out/'PROPOSED-JOB.json'),decoder_queries=0)))


if __name__=='__main__':main()
