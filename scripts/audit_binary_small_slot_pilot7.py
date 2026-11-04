#!/usr/bin/env python3
"""Read-only result/proof-ledger audit; never calls a tensor decoder."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(payload):return hashlib.sha256(payload).hexdigest()
def raw(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()


def audit(path):
    path=Path(path);summary=json.loads((path/'summary.json').read_bytes())
    checksums=json.loads((path/'checksums.json').read_bytes())
    for name,expected in checksums.items():
        if digest((path/name).read_bytes())!=expected:raise ValueError('result checksum changed: '+name)
    selection=json.loads((path/'selection.json').read_bytes())
    if summary['selection_sha256']!=digest(raw(selection)):raise ValueError('selection digest differs')
    rows={r['id']:r for r in selection['cases']};totals={k:0 for k in (
        'subsets_considered','mode_rank_exclusions','supported_decoder_calls','repair_calls',
        'exact_decoder_exclusions','decoder_unknowns','negative_cache_hits')}
    proof_hashes=set();case_stats=[]
    for result in summary['results']:
        if result['status']!='UNKNOWN' or result['complete']:raise ValueError('expected completed diagnostic UNKNOWN run')
        decoder=result['raw_decoder'];entry=rows[result['case']]
        if decoder['status']!='UNKNOWN' or decoder['complete'] or decoder['best_loss']!=1:
            raise ValueError('overall repair-family scope differs')
        observed=decoder['subset_results']
        if [r['slots'] for r in observed]!=entry['slots']:raise ValueError('executed subsets differ from bound selection')
        if decoder['subsets_considered']!=len(observed) or len(observed)!=600:raise ValueError('missing selected subsets')
        if any(r['status']!='REPAIR_EXCLUDED' or r['complete'] is not True for r in observed):
            raise ValueError('a selected repair lacks a complete individual exclusion')
        for key,proof in decoder['negative_proofs'].items():
            actual=digest(raw({k:proof[k] for k in ('shape','core','budget')}))
            observation=proof['observation']
            if (key!=actual or proof['key']!=key or proof['budget']!=6
                    or observation['status']!='REPAIR_EXCLUDED' or observation['complete'] is not True
                    or observation['case']!='exact_selected_residual_negative'
                    or observation['actual_mode_shape']!=proof['shape']
                    or observation['compact_core_sha256']!=digest(bytes(proof['core']))):
                raise ValueError('negative proof/input binding differs')
            proof_hashes.add(digest(raw(proof)))
        for row in observed:
            if row.get('proof_sha256') and row['proof_sha256'] not in proof_hashes:
                raise ValueError('negative reference has no bound complete proof')
        for key in totals:totals[key]+=decoder[key]
        case_stats.append(dict(case=result['case'],**{k:decoder[k] for k in totals},best_loss=decoder['best_loss']))
    if totals['subsets_considered']!=5400 or totals['mode_rank_exclusions']+totals['exact_decoder_exclusions']+totals['negative_cache_hits']!=5400:
        raise ValueError('selected-family accounting differs')
    records=list((path/'records').glob('*.json'))
    if records:raise ValueError('unexpected canonical candidate')
    return dict(status='PASS',input_summary_sha256=digest((path/'summary.json').read_bytes()),
        checksums_sha256=digest((path/'checksums.json').read_bytes()),checked_files=len(checksums),
        selected_cases=len(case_stats),totals=totals,case_stats=case_stats,unique_exact_negative_proofs=len(proof_hashes),
        elapsed_seconds=summary['elapsed_seconds'],stop_reason=summary['stop_reason'],canonical_candidates=0,
        no_additional_decoder_calls=True,all_nine_CP14_cases_remain_unknown=True,
        scope='Only600selectedS6 repairs percase excluded;2403unvisited subsets/case and other factor states remain open',
        audit_script_sha256=digest(Path(__file__).read_bytes()))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pilot',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=audit(a.pilot)
    with a.output.open('xb') as stream:stream.write(json.dumps(result,sort_keys=True,indent=2).encode()+b'\n')
    print(json.dumps(result['totals'],sort_keys=True))
