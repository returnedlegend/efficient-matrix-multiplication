#!/usr/bin/env python3
"""Read-only conditional-C3 proof-ledger audit, including partial UNKNOWN work."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(payload):return hashlib.sha256(payload).hexdigest()
def raw(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()


def audit(directory):
    directory=Path(directory);summary=json.loads((directory/'summary.json').read_bytes())
    plan=json.loads((directory/'plan.json').read_bytes());checksums=json.loads((directory/'checksums.json').read_bytes())
    for name,digest in checksums.items():
        if sha((directory/name).read_bytes())!=digest:raise ValueError('bundle checksum changed: '+name)
    if summary['selected_cases_sha256']!=sha(raw(plan['cases'])):raise ValueError('qualified source case digest differs')
    expected={row['id']:row for row in plan['cases']};seen=set();closed=[];unknown=[];observations=[]
    completed_children=0;attempted_children=0;prior_negative_receipts=0
    for result in summary['results']:
        case=result.get('case')
        if case not in expected or case in seen:raise ValueError('unexpected or duplicate parent')
        seen.add(case);row=expected[case];meta=row['conditional_metadata']
        decoder=result.get('raw_decoder');late=directory/'.raw-returns'/(case+'.late-result.raw')
        if decoder is None and late.exists():decoder=json.loads(late.read_bytes()).get('raw_decoder')
        decoder=decoder or {};tested=decoder.get('tested_extensions',[])
        cosets=sorted(int(v['coset_hex'],16) for v in meta['distinct_child_cosets'])
        if (len(tested)>len(cosets) or len({v['coset'] for v in tested})!=len(tested)
                or any(v['coset'] not in cosets or v['status']!='LOCAL_UNSAT'
                       or len(v['child_result_sha256'])!=64 for v in tested)):
            raise ValueError('partial child negative prefix is invalid')
        if [v['coset'] for v in tested]!=cosets[:len(tested)]:raise ValueError('completed child prefix skips work')
        count=len(tested);attempt=count
        if ('last_child_result' in decoder or 'child_result_sha256' in decoder):
            attempt=max(attempt,decoder.get('extension_cursor',count)+1)
        if attempt>len(cosets):raise ValueError('child attempt count exceeds authorized parent')
        completed_children+=count;attempted_children+=attempt
        prior_negative=bool(decoder.get('prior_result_sha256')) and decoder.get('case')!='surplus_two_cover'
        prior_negative_receipts+=prior_negative
        if result['status']=='LOCAL_UNSAT':
            if (result.get('complete') is not True or decoder.get('status')!='LOCAL_UNSAT'
                    or decoder.get('complete') is not True or decoder.get('case')!='all_conditional_repeated_pair_extensions_negative'
                    or not prior_negative or decoder.get('target_rank')!=11 or decoder.get('budget')!=14
                    or decoder.get('inside_rank')!=meta['backbone_rank'] or meta['backbone_rank']>6
                    or decoder.get('conditional_pair_theorem_applies') is not True
                    or decoder.get('extension_cosets')!=cosets or decoder.get('total_extensions')!=len(cosets)
                    or decoder.get('extension_cursor')!=len(cosets) or count!=len(cosets)):
                raise ValueError('complete parent misses prior or required child decision')
            closed.append(case)
        elif result['status']=='UNKNOWN':
            if result.get('complete'):raise ValueError('UNKNOWN cannot be complete')
            unknown.append(case)
        elif result['status'] not in ('TARGET_EMITTED_TO_GLOBAL_GUARD','ERROR'):
            raise ValueError('unrecognized parent status')
        observations.append(dict(case=case,status=result['status'],decoder_status=decoder.get('status'),
            decoder_case=decoder.get('case'),expected_children=len(cosets),completed_negative_children=count,
            returned_or_completed_child_queries=attempt,prior_negative_receipt=prior_negative,
            raw_late_diagnostic=late.exists(),last_child_raw_retained='last_child_result' in decoder))
    if sorted(closed)!=sorted(summary['closed_parent_cases']):raise ValueError('summary closure differs from individual proof ledger')
    if len(plan['excluded_b7_cases'])!=2 or any(case in seen for case in plan['excluded_b7_cases']):
        raise ValueError('b7 complement incorrectly queried or closed')
    remaining=[case for case in expected if case not in closed]
    return dict(status='PASS',summary_sha256=sha((directory/'summary.json').read_bytes()),
        checksums_sha256=sha((directory/'checksums.json').read_bytes()),checked_files=len(checksums),
        source_cases_planned=7,source_cases_attempted=len(seen),closed_parent_cases=closed,
        unresolved_qualified_cases=remaining,excluded_b7_cases=plan['excluded_b7_cases'],
        complete_child_negatives=completed_children,returned_or_completed_child_queries=attempted_children,
        prior_negative_parent_receipts=prior_negative_receipts,observations=observations,
        internal_CP13_redundancy_accepted=True,
        minimum_recomputed_CP13_child_priors=completed_children,
        internal_redundancy_scope='ReviewedLargeS2 reruns eachchildCP13prior before itsnewCP14decision; no cacheoverlay. Count is a lowerbound ifa currentchildtimedout.',
        elapsed_seconds=summary['elapsed_seconds'],process_cpu_seconds=summary['process_cpu_seconds'],
        stop_reason=summary['stop_reason'],canonical_candidates=len(list((directory/'records').glob('*.json'))),
        whole_nine_remaining_without_record=len(remaining)+2,
        no_additional_decoder_calls=True,no_global_rank_lower_bound=True,
        audit_script_sha256=sha(Path(__file__).read_bytes()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('pilot',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=audit(args.pilot)
    with args.output.open('xb') as stream:stream.write(raw(result))
    print(json.dumps({k:result[k] for k in ('status','source_cases_attempted','complete_child_negatives','whole_nine_remaining_without_record')},sort_keys=True))
