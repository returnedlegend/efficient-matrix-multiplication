#!/usr/bin/env python3
"""Unite accepted closure ledgers for the exact111605-mask finite family."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,read,sha
from mmsearch.marathon7_local import select_plan
from mmsearch.observed_rank3_lazy42 import chain_read
from mmsearch.recombine import digest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--remaining-audit',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();c=a.campaign.resolve();b=a.bundle.resolve();last=a.remaining_audit.resolve();out=a.output_dir.resolve()
    final=read(last/'REPORT.json')
    if final['status']!='ALL90387_EXACT_FIXED_RESIDUAL_NEGATIVES_AUDITED' or final['cases']!=90387 or final['unknowns'] or final['errors'] or final['new_decoder_calls']!=0:raise ValueError('remaining finite family not closed')
    for root in [last,c/'local10-v5-next10000-audit-v1']:
        for name,expected in read(root/'manifest.json')['files'].items():
            if sha(root/name)!=expected:raise ValueError('accepted audit report changed')
    roots=[];rootids={};proofs={};sources=read(b/'plan.json')['sources'];categories=Counter();history=[]
    def add(s,lo,hi,file,result_sha,math_sha,input_sha,category):
        key=(s,lo,hi);mask=lo|(hi<<64)
        if key in proofs or mask>>93 or mask.bit_count()!=10:raise ValueError('duplicate or nonlocal10 proof key')
        directory=str(Path(file).parent)
        if directory not in rootids:rootids[directory]=len(roots);roots.append(directory)
        proofs[key]=[s,lo,hi,rootids[directory],Path(file).name,result_sha,math_sha,input_sha];categories[category]+=1
    release=b
    while True:
        release_manifest=read(release/'manifest.json')
        if sha(release/'plan.json')!=release_manifest['files']['plan.json']:raise ValueError('historical plan bytes changed')
        plan=read(release/'plan.json');history.append(dict(bundle=str(release),manifest_sha256=sha(release/'manifest.json')))
        ledger=release/'CLOSED-NEGATIVES.json.gz'
        if ledger.exists():
            if sha(ledger)!=release_manifest['files']['CLOSED-NEGATIVES.json.gz']:raise ValueError('historical closure ledger bytes changed')
            for record in json.loads(gzip.decompress(ledger.read_bytes())):
                if record['source_sha256']!=sources[str(record['source_id'])]['sha256'] or record['status']!='REUSED_IDENTICAL_SOURCE_MASK_EXACT_NEGATIVE':raise ValueError('historical source/model binding changed')
                add(record['source_id'],record['mask_lo'],record['mask_hi'],record['result_file'],record['result_sha256'],record['core_math_sha256'],record['core_input_sha256'],'historical_campaign_exact_negatives')
        previous=plan.get('previous_bundle')
        if not previous:break
        previous=Path(previous)
        if sha(previous/'manifest.json')!=plan['previous_bundle_manifest_sha256']:raise ValueError('parent closure release changed')
        release=previous
    if len(proofs)!=10706:raise ValueError('expected10706 historical campaign closures')
    if sha(release/'EXCLUSIONS.json')!=release_manifest['files']['EXCLUSIONS.json']:raise ValueError('old pilot exclusion registry changed')
    for record in read(release/'EXCLUSIONS.json'):
        if record['source_sha256']!=sources[str(record['source_id'])]['sha256'] or sha(record['result_file'])!=record['result_sha256']:raise ValueError('pilot source/result evidence changed')
        result=read(record['result_file'])
        if result['status']!='LOCAL_UNSAT' or result.get('complete') is not True or result['mode_rank']!=8 or result['target']!=9:raise ValueError('pilot is not exact matching negative')
        add(record['source_id'],record['mask_lo'],record['mask_hi'],record['result_file'],record['result_sha256'],record['core_sha256'],None,'old_exact_pilot')
    audit_inputs=[]
    for number,chunk in enumerate(read(b/'plan.json')['chunks']):
        if number==0:auditfile=c/'local10-v5-first500-binding-audit-v1.json'
        elif number<=20:auditfile=c/'local10-v5-next10000-audit-v1'/f'chunk-{number:03d}.json'
        else:auditfile=last/f'chunk-{number:03d}.json'
        audit=read(auditfile);cases=select_plan(b,chunk['id'])['cases'];output=c/f'marathon7-local-local10-v5-{number:03d}';records,chain=chain_read(output/'completed.jsonl',audit['config_sha256'])
        if audit['status']!='AUDITED_EXACT_FIXED_SOURCE_MASK_NEGATIVES' or not audit['all_exact_negative'] or audit['cases']!=len(cases) or len(records)!=len(cases) or chain!=audit['result_chain_sha256']:raise ValueError('v5 query-free proof audit differs')
        for i,(case,binding,record) in enumerate(zip(cases,audit['case_bindings'],records)):
            if binding['index']!=i or binding['case']!=case['id'] or record['case']!=case['id'] or record['status']!='LOCAL_UNSAT' or record['result_sha256']!=binding['result_sha256'] or binding['source_sha256']!=case['source_sha256']:raise ValueError('case/journal/audit binding differs')
            add(case['source_id'],case['mask_lo'],case['mask_hi'],output/record['result_file'],binding['result_sha256'],binding['core_math_sha256'],binding['core_input_sha256'],'v5_exact_negative')
        audit_inputs.append(dict(chunk=chunk['id'],cases=len(cases),audit_file=str(auditfile),audit_sha256=sha(auditfile),proof_chain_sha256=chain))
    baseplan=read(release/'plan.json');parent=Path(baseplan['parent']);catalog=parent/'survivors.tsv.gz'
    if sha(parent/'manifest.json')!=baseplan['parent_manifest_sha256'] or sha(catalog)!=read(parent/'manifest.json')['files']['survivors.tsv.gz']:raise ValueError('original finite catalogue changed')
    expected={tuple(map(int,line.split()[:3])) for line in gzip.decompress(catalog.read_bytes()).decode().splitlines()}
    if len(expected)!=111605 or set(proofs)!=expected or sum(categories.values())!=111605:raise ValueError('complete original finite catalogue is not closed')
    out.mkdir(parents=True,exist_ok=False);rows=[proofs[key] for key in sorted(proofs)];registry=dict(row_schema=['source_id','mask_lo','mask_hi','proof_root_id','result_filename','result_sha256','core_math_sha256','core_input_sha256_optional'],proof_roots=roots,source_sha256={s:item['sha256'] for s,item in sources.items()},
        common_model=dict(dimension=5,field=2,source_products=93,local_products=10,target_products=9,mode_rank=8),rows=rows)
    freeze(out/'EXACT-CLOSURE-REGISTRY.json.gz',gzip.compress(json.dumps(registry,separators=(',',':'),sort_keys=True).encode(),compresslevel=1,mtime=0));freeze(out/'AUDIT-INPUTS.json',audit_inputs);freeze(out/'HISTORICAL-RELEASES.json',history)
    report=dict(status='RETIRED_EXACT_FIXED_FAMILY_ALL111605_NEGATIVE',catalog_cases=111605,exact_negative_proofs=len(proofs),unknowns=0,errors=0,unvisited_catalog_masks=0,categories=dict(categories),source_counts=dict(Counter(key[0] for key in proofs)),
        original_catalog=str(catalog),original_catalog_sha256=sha(catalog),registry_sha256=sha(out/'EXACT-CLOSURE-REGISTRY.json.gz'),audit_inputs_sha256=sha(out/'AUDIT-INPUTS.json'),remaining_audit_manifest_sha256=sha(last/'manifest.json'),
        new_decoder_calls=0,new_sources_queried=0,new_construction_found=False,no_continuation=True,scope='Only the exact111605 recorded necessary-survivor local10/image8/target9 source masks are retired. No unrestricted rank lower bound or global optimality claim; global construction target92 remains a separate objective.')
    freeze(out/'RETIREMENT.json',report);freeze(out/'marathon7_local10_retire.py',Path(__file__).read_bytes());freeze(out/'manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    print(json.dumps({key:report[key] for key in ['status','catalog_cases','exact_negative_proofs','unknowns','unvisited_catalog_masks','categories','new_decoder_calls','no_continuation']},sort_keys=True))


if __name__=='__main__':main()
