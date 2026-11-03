#!/usr/bin/env python3
"""Query-free audit: exact journal, source/mask binding and lazy core replay."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mmsearch.marathon7_local import SourceCache,select_plan,restore_journal,compact_negative,checked_path,read,sha
from mmsearch.compact_coset43 import mode_slices
from mmsearch.compact_sat import BinaryBasis
from mmsearch.recombine import digest
from scripts.prepare_local_ten43 import freeze


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    start=time.monotonic();b=a.bundle.resolve();out=a.output.resolve();config=read(out/'config.json');cursor=read(out/'cursor.json');summary=read(out/'summary.json')
    for name,expected in read(b/'manifest.json')['files'].items():
        if sha(checked_path(b,name).read_bytes())!=expected:raise ValueError('frozen bundle changed')
    if sha((b/'launch-manifest.json').read_bytes())!=config['launch_manifest_sha256']:raise ValueError('runtime launch pin differs')
    selected=select_plan(b,config['chunk_id']);cases=selected['cases']
    if config['selected_plan_sha256']!=selected['selected_sha256'] or config['catalog_plan_sha256']!=selected['catalog_plan_sha256'] or config['controls_only'] or config['small_control']:raise ValueError('selected query scope differs')
    configsha=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest();records,chain=restore_journal(out,cases,configsha)
    if len(records)!=len(cases) or records!=cursor['results'] or cursor['next_case']!=len(cases) or cursor['config_sha256']!=configsha or not cursor['terminal'] or cursor['status']!='LOCAL_PORTFOLIO_UNSAT':raise ValueError('complete journal/cursor differs')
    if summary['results']!=records or summary['status']!='LOCAL_PORTFOLIO_UNSAT' or not summary['terminal'] or summary['planned_cases']!=len(cases) or summary['result_chain_sha256']!=chain or cursor['result_chain_sha256']!=chain:raise ValueError('summary/journal chain differs')
    if (out/'WINNER.json').exists() or (out/'current').exists() or list(out.glob('*.after-cutoff.raw.json')) or cursor.get('pending_unknown'):raise ValueError('negative batch has positive/open/late artifacts')
    cache=SourceCache(b);controls=[];resultbytes=[];counts=Counter()
    for index,(case,record) in enumerate(zip(cases,records)):
        result=read(checked_path(out,record['result_file']));source,data,full,sourcehash,corehash,inputhash=cache.core(case)
        if result['status']!='LOCAL_UNSAT' or result.get('complete') is not True or result.get('after_cutoff') or result['case']!=case['id'] or result['config_sha256']!=configsha:raise ValueError('non-exact case in completed negatives')
        if result['source_sha256']!=sourcehash or result['core_math_sha256']!=corehash or result['core_input_sha256']!=inputhash or result['core_sha256']!=corehash or result['shape']!=data['shape'] or result['axis']!=case['free_axis']:raise ValueError('result source/mask/core binding differs')
        if result['target_rank']!=case['mode_rank'] or result['budget']!=case['target_local_products'] or result['enumerated_vectors']!=(1<<case['mode_rank'])-1 or result['span_vectors']!=result['enumerated_vectors']:raise ValueError('rank2edge query dimension/scope differs')
        slices,other=mode_slices(data['core'],data['shape'],case['free_axis'])
        if result['target_sha256']!=digest(slices) or result['space_basis']!=BinaryBasis(slices).vectors or result['left_width']!=data['shape'][other[0]] or result['right_width']!=data['shape'][other[1]]:raise ValueError('complete raw slice image binding differs')
        compact_negative(result)
        if result.get('bucket_span_max',result['inside_rank'])>=case['mode_rank'] or result['inside_rank']>=case['mode_rank']:raise ValueError('negative edge ranks not deficient')
        controls.append(dict(index=index,case=case['id'],source_sha256=sourcehash,core_math_sha256=corehash,core_input_sha256=inputhash,result_sha256=record['result_sha256']))
        resultbytes.append((out/record['result_file']).stat().st_size);counts[case['source_id']]+=1
    files=[path for path in out.rglob('*') if path.is_file()];logical=sum(path.stat().st_size for path in files);allocated=sum(path.stat().st_blocks*512 for path in files)
    report=dict(status='AUDITED_EXACT_FIXED_SOURCE_MASK_NEGATIVES',bundle=str(b),output=str(out),bundle_manifest_sha256=sha((b/'manifest.json').read_bytes()),launch_manifest_sha256=config['launch_manifest_sha256'],
        config_sha256=configsha,cursor_sha256=sha((out/'cursor.json').read_bytes()),summary_sha256=sha((out/'summary.json').read_bytes()),completed_journal_sha256=sha((out/'completed.jsonl').read_bytes()),result_chain_sha256=chain,
        cases=len(cases),all_exact_negative=True,unknowns=0,errors=0,late_artifacts=0,new_decoder_calls=0,full_lazy_core_replays=len(controls),source_full_entries_each=15625,source_counts=dict(counts),
        source_mask_core_result_bindings_sha256=digest(controls),case_bindings=controls,
        storage=dict(files=len(files),logical_bytes=logical,allocated_bytes=allocated,result_bytes_min=min(resultbytes),result_bytes_max=max(resultbytes),result_bytes_mean=sum(resultbytes)/len(resultbytes),
            forecast_additional_10000_logical_bytes=logical*20,forecast_additional_10000_allocated_bytes=allocated*20,per_chunk_cap_bytes=128*1024**2),
        observed_production_seconds=summary['elapsed_seconds'],observed_cases_per_second=len(cases)/summary['elapsed_seconds'],audit_seconds=time.monotonic()-start,
        proof_scope='Exact listed fixed-source/mask residual negatives only. Journal/source/rawimage/core/statistics audited without another decoder call; no global rank conclusion.')
    freeze(a.report,report);print(json.dumps({key:report[key] for key in ['status','cases','all_exact_negative','new_decoder_calls','full_lazy_core_replays','result_chain_sha256','storage','audit_seconds']},sort_keys=True))


if __name__=='__main__':main()
