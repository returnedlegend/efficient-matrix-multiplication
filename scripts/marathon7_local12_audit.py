#!/usr/bin/env python3
"""Query-free replay audit of the completed local12 preparation prefix."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,read,sha
from mmsearch.marathon7_local import SourceCache
from mmsearch.compact_sat import BinaryBasis
from mmsearch.compact_coset43 import mode_slices
from mmsearch.koszul_p2 import koszul_p2_rows
from mmsearch.sat_neighborhoods import gf2_rank
from mmsearch.recombine import digest
from mmsearch.observed_rank3_lazy42 import chain_read


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prep',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();start=time.monotonic();prep=a.prep.resolve();bundle=a.bundle.resolve()
    for root,manifest in [(prep,'PARTIAL-MANIFEST.json' if (prep/'PARTIAL-MANIFEST.json').exists() else 'manifest.json'),(bundle,'manifest.json')]:
        for name,expected in read(root/manifest)['files'].items():
            path=(root/name).resolve()
            if not path.is_relative_to(root) or sha(path)!=expected:raise ValueError('release checksum mismatch')
    inputplan=read(prep/'INPUT-PLAN.json');summary=read(prep/'REPORT.json');state=read(prep/'cursor.json');records,chain=chain_read(prep/'candidates.jsonl',digest(inputplan))
    assert summary['config_sha256']==digest(inputplan)==state['config_sha256'];assert summary['result_chain_sha256']==chain
    assert len(records)==summary['committed']==state['committed'];assert state['unique_masks']==len(records)+(1 if state['pending'] else 0)<=500
    assert sum(state['positions'])==state['raw_pairs']<=217792 and len(state['positions'])==64 and max(state['positions'])<=3403
    assert len(inputplan['selected_parents'])==64 and Counter(r[0] for r in inputplan['selected_parents'])=={s:16 for s in range(4)}
    cache=SourceCache(prep);seen=set();counts=Counter();p2count=rank3negative=rank3witnesses=0;bindings=[]
    for index,record in enumerate(records):
        case=record['case'];sourceid=case['source_id'];key=(sourceid,case['mask_lo'],case['mask_hi']);assert key not in seen;seen.add(key)
        parent=inputplan['selected_parents'][record['parent_ordinal']];mask=parent[1]|(parent[2]<<64);parentids=[i for i in range(93) if mask>>i&1]
        assert sourceid==parent[0] and record['parent_mask_lo']==parent[1] and record['parent_mask_hi']==parent[2]
        assert len(parentids)==10 and len(set(record['added_indices']))==2 and not set(parentids)&set(record['added_indices'])
        assert sorted(parentids+record['added_indices'])==case['source_indices'] and len(case['source_indices'])==12
        assert case['source_products']==93 and case['source_local_products']==12 and case['target_local_products']==11 and max(case['shape'])==9 and case['shape'][case['free_axis']]==9
        source,data,full,sourcehash,corehash,inputhash=cache.core(case)
        assert record['source_sha256']==sourcehash==inputplan['source_sha256'][str(sourceid)] and record['core_math_sha256']==corehash and record['core_input_sha256']==inputhash
        assert record['full_ambient_entries_checked']==full['exact_entries_checked']==15625 and record['decoder_queries']==0
        assert len(record['p2'])==3
        for mode,answer in enumerate(record['p2']):
            matrix,columns,rows=koszul_p2_rows(data['core'],data['shape'],mode);rank=gf2_rank(matrix);contribution=math.comb(data['shape'][mode]-1,2)
            assert answer==dict(mode=mode,status='COMPUTED',rows=rows,columns=columns,matrix_rank=rank,rank_one_contribution=contribution,lower_bound=(rank+contribution-1)//contribution,matrix_sha256=digest(matrix));p2count+=1
        p2excluded=any(item['lower_bound']>11 for item in record['p2']);lowexcluded=False
        for answer in record['rank3']:
            axis=answer['axis'];slices,other=mode_slices(data['core'],data['shape'],axis);space=BinaryBasis(slices);assert len(space.vectors)==9 and space.vectors==answer['space_basis']
            witnesses=answer['lowrank_coordinate_basis'];assert gf2_rank(witnesses)==answer['lowrank_span_rank']
            def scalar_rank(coordinate):
                matrix=space.expand(coordinate);width=data['shape'][other[1]]
                return gf2_rank([(matrix>>(i*width))&((1<<width)-1) for i in range(data['shape'][other[0]])])
            assert all(0<coordinate<512 and scalar_rank(coordinate)<=3 for coordinate in witnesses)
            if answer['status']=='BOUND_PASSED_NOT_EXISTENCE':assert answer['complete'] and answer['lowrank_span_rank']==9;rank3witnesses+=1
            else:
                assert answer['status']=='LOWRANK_SPAN_EXCLUDES' and answer['complete'] and answer['points_tested']==511 and answer['enumeration_complete']
                accepted=[coordinate for coordinate in range(1,512) if scalar_rank(coordinate)<=3];assert gf2_rank(accepted)==answer['lowrank_span_rank']<9;rank3negative+=1;lowexcluded=True
        expected='P2_EXCLUDED' if p2excluded else 'RANK3_SPAN_EXCLUDED' if lowexcluded else 'RETAINED';assert record['disposition']==expected
        if expected=='RETAINED' and inputplan['rank3_filter']:assert {answer['axis'] for answer in record['rank3']}=={axis for axis,d in enumerate(case['shape']) if d==9}
        counts[expected]+=1;bindings.append(dict(id=case['id'],source_sha256=sourcehash,core_math_sha256=corehash,core_input_sha256=inputhash))
    assert dict(counts)==summary['dispositions'];assert [r['case'] for r in records if r['disposition']=='RETAINED']==summary['retained_cases']
    pilot=read(bundle/'plan.json');selected=read(bundle/'SELECTED-PREP-RECORDS.json');assert 0<len(selected)<=25 and pilot['cases']==[r['case'] for r in selected]
    assert all(record in records and record['disposition']=='RETAINED' for record in selected);assert len({r['case']['id'] for r in selected})==len(selected)
    result=dict(status='PASS',prep_census_status=summary['status'],completed_filter_records=len(records),partial_cursor_preserved=summary['status']=='UNKNOWN',dispositions=dict(counts),lazy_core_replays=len(records),p2_matrices_replayed=p2count,
        rank3_negative_full511_replays=rank3negative,rank3_positive_witness_checks=rank3witnesses,selected_pilot_cases=len(selected),source_mask_core_bindings_sha256=digest(bindings),chain_sha256=chain,new_decoder_calls=0,
        prep_snapshot_manifest_sha256=sha(prep/('PARTIAL-MANIFEST.json' if (prep/'PARTIAL-MANIFEST.json').exists() else 'manifest.json')),bundle_manifest_sha256=sha(bundle/'manifest.json'),elapsed_seconds=time.monotonic()-start,
        scope='All completed filter records replayed; unvisited masks remain unqueried/open. Necessary filters only; no decomposition evidence.')
    freeze(a.report,result);print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
