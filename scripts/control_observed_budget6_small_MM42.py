"""Full n2 distinct-pair9to8 control requiring exact groupweight6 (not production)."""
import argparse
import itertools
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.search import naive_terms,encode_candidate
from mmsearch.free_factor_sat import build_system
from mmsearch.observed_budget6_runtime42 import SourceRuntime
from mmsearch.observed_budget642 import decode_budget6
from mmsearch.observed_rank342 import rank


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=False)
    terms=naive_terms(2);u,v,w=terms[0];source=terms[1:]+[(u^2,v,w),(2,v,w)]
    if len(set((a,b) for a,b,c in source))!=9:raise AssertionError('control activepairs notdistinct')
    system=build_system(source+[(u,v,0)],2,'uv',encode_candidate(source,2));runtime=SourceRuntime(system);q=runtime.prepare(system,[1,2,4])
    h=[int(x,16) for x in q['column_syndromes_hex']];t=[int(x,16) for x in q['targets_hex']];minimum=None;supports=0
    for size in range(len(h)+1):
        for indices in itertools.combinations(range(len(h)),size):
            supports+=1;chosen=[h[i] for i in indices]
            if rank(chosen+t)==rank(chosen):minimum=size;break
        if minimum is not None:break
    if (q['k'],q['target_rank'],q['weight_bound'],minimum)!=(7,3,6,6):raise AssertionError('minimum6 control changed')
    result=decode_budget6(h,t,6,1)
    if result['status']!='HIT' or result['weight']!=6:raise AssertionError('prototype failed minimum6 control')
    answer=runtime.decode_hit(system,q,result['entries'])
    if answer['verification']['rank']!=8 or answer['verification']['exact_entries_checked']!=64:raise AssertionError('full64controlfailed')
    values=dict(system=system,quotient=q,decoder_result=result,candidate=answer['candidate'],lift=answer['lift'],verification=answer['verification'],
        oracle=dict(minimum=minimum,subsets_tested=supports,old_rank=9,new_rank=8,active_fixed_pairs_unique=True,production_queries=0))
    for name,value in values.items():(a.output_dir/(name+'.json')).write_text(json.dumps(value,sort_keys=True)+'\n')
    print(json.dumps(dict(status='SMALL_FULL_MM_PASSED',minimum=minimum,rank_before=9,rank_after=8,full_entries=64,production_queries=0)))


if __name__=='__main__':main()
