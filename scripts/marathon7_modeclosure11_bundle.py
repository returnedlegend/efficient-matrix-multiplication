#!/usr/bin/env python3
"""Freeze the nine new11/image8/target10 cases and a genuine N4 c2 control."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,read,sha
from scripts.phase_coordinator42_v2 import validate_job
from mmsearch.marathon7_modeclosure11_runtime import tuple_binding
from mmsearch.sat_neighborhoods import factor_masks
from mmsearch.compact_eight43 import factor_core
from tests.test_compactification7_independent import planted_n4


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prep',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();prep=a.prep.resolve();out=a.output_dir.resolve();report=read(prep/'REPORT.json');inputs=read(prep/'INPUT-PLAN.json')
    for name,expected in read(prep/'manifest.json')['files'].items():
        if sha(prep/name)!=expected:raise ValueError('prep release changed')
    parent=Path(inputs['parent']);parentmanifest=read(parent/'manifest.json')
    if sha(parent/'manifest.json')!=inputs['parent_manifest_sha256'] or inputs['catalog_sha256']!=parentmanifest['files']['survivors.tsv.gz']:raise ValueError('approved parent catalogue differs')
    for s in range(4):
        if inputs['source_sha256'][str(s)]!=parentmanifest['files'][f'source-{s}.json']:raise ValueError('approved source identity differs')
    if report['status']!='COMPLETE_BOUNDED_MODE_CLOSURE11_PREP' or report['raw_extensions']!=5312 or report['unique_masks_admitted_before_filters']!=9 or report['decoder_queries']!=0:raise ValueError('unexpected bounded prep scope')
    out.mkdir(parents=True,exist_ok=False);cases=read(prep/'CASES.json')
    for s in range(4):freeze(out/f'source-{s}.json',(prep/f'source-{s}.json').read_bytes())
    for case in cases:case.update(tuple_binding(factor_masks(read(out/case['source'])),case['source_indices']))
    freeze(out/'plan.json',dict(cases=cases,prep=str(prep),prep_manifest_sha256=sha(prep/'manifest.json'),family=dict(local_products=11,mode_rank=8,target_products=10,max_vectors=511,max_extensions=765),canonical_tuple_mask_binding_required=True,optional_necessary_filter_applied=False))
    freeze(out/'CASE-ORIGINS.json',(prep/'CASE-ORIGINS.json').read_bytes())
    small,terms,case=planted_n4(4);raw=factor_masks(small)
    if raw!=terms:raise ValueError('planted control source tuple order changed')
    bases,core,shape=factor_core(raw,case['source_indices']);ids=case['source_indices'];mask=sum(1<<i for i in ids);case.update(source='small-source.json',mask_lo=mask&((1<<64)-1),mask_hi=mask>>64,source_sha256=None,all_pair_points=255*255)
    freeze(out/'small-source.json',small);case['source_sha256']=sha(out/'small-source.json');case.update(tuple_binding(raw,ids));case['core']='small-core.json'
    data=dict(shape=shape,core=core,image_bases=bases,source_indices=ids,outside_indices=[i for i in range(64) if i not in ids]);freeze(out/'small-core.json',data);freeze(out/'small-plan.json',dict(cases=[case]))
    for path in (ROOT/'mmsearch').glob('*.py'):freeze(out/'runtime/mmsearch'/path.name,path.read_bytes())
    for name in ['__init__.py','verify_record42_independent.py','marathon7_modeclosure11_campaign.py']:
        path=ROOT/'scripts'/name;freeze(out/'runtime/scripts'/name,path.read_bytes() if path.exists() else b'')
    freeze(out/'runtime/marathon7_modeclosure11_campaign.py',(ROOT/'scripts/marathon7_modeclosure11_campaign.py').read_bytes())
    freeze(out/'runtime/tests/__init__.py',b'')
    for name in ['test_marathon7_modeclosure11.py','test_compactification7_independent.py']:freeze(out/'runtime/tests'/name,(ROOT/'tests'/name).read_bytes())
    freeze(out/'marathon7_modeclosure11_bundle.py',Path(__file__).read_bytes());freeze(out/'launch-manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    job=dict(id='marathon7-modeclosure11-pilot9-v1',enabled=False,cpu=1,memory_mb=1024,seconds=230,command=['python3','-B',str(out/'runtime/marathon7_modeclosure11_campaign.py'),'--bundle',str(out),'--output-dir',str(out.parent/'marathon7-modeclosure11-pilot9-v1'),'--chunk-id','000','--seconds','200','--per-case-seconds','20','--memory-mb','1024','--deadline-utc','2026-11-03T19:24:17Z','--guard-state',str(out.parent/'operations-v3/state.json')])
    validate_job(job);freeze(out/'PROPOSED-JOB.json',job);freeze(out/'READY.json',dict(status='DISABLED_PENDING_INDEPENDENT_PREP_AND_N4_CONTROL_QA',cases=9,new_n5_decoder_queries=0,source_mask_canonical_binding=True,exact_backend_sha256=sha(out/'runtime/mmsearch/surplus_two7.py'),expected_global_positive_upper_bound=92))
    freeze(out/'manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}));print(__import__('json').dumps(dict(cases=9,status='DISABLED_PENDING_INDEPENDENT_PREP_AND_N4_CONTROL_QA',manifest_sha256=sha(out/'manifest.json'),proposal_sha256=sha(out/'PROPOSED-JOB.json'))))


if __name__=='__main__':main()
