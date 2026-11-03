#!/usr/bin/env python3
"""Second independent finite-cover oracle, extension census, and late guards."""
import hashlib
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mmsearch import surplus_two7 as decoder
from scripts.marathon7_local_backbone_review import all_spaces,finite_covers,basis,mask,span,outer,rank,witness


def main():
    start=time.monotonic();counts=dict(spaces=0,budget_cases=0,raw_witnesses=0,zero_one_cases=0,extension_census_cases=0,late_cases=0,caps=0)
    with patch.object(decoder.time,'time',return_value=decoder.HARD_DEADLINE-60):
        for a,b,expected in [(2,2,67),(2,3,2825)]:
            spaces=all_spaces(a,b);assert len(spaces)==expected;covers,_=finite_covers(a,b)
            for space in spaces:
                targetmask=mask(space);optimum=next(cost for cost,cover in covers if targetmask&cover==targetmask)
                original=basis(sorted(space));raw=[0]+original+original[::-1]+[0]
                for budget in range(len(original)+3):
                    result=decoder.solve_pair_image(raw,a,b,budget)
                    assert result['complete'] and result['status']==('SAT' if optimum<=budget else 'LOCAL_UNSAT')
                    if result['status']=='SAT':witness(raw,a,b,result);counts['raw_witnesses']+=1
                    counts['budget_cases']+=1
                counts['spaces']+=1
        for raw,a,b,budget,status in [([],0,0,0,'SAT'),([0],0,0,0,'SAT'),([0,1,1],1,1,0,'LOCAL_UNSAT'),([0,1,1],1,1,1,'SAT'),([9],2,2,1,'LOCAL_UNSAT'),([9],2,2,2,'SAT'),([273],3,3,3,'SAT'),([33825],4,4,3,'LOCAL_UNSAT')]:
            result=decoder.solve_pair_image(raw,a,b,budget);assert result['status']==status and result['complete']
            if status=='SAT':witness(raw,a,b,result)
            counts['zero_one_cases']+=1
        # Independent ambient rank-one pair census: every relevant extension once.
        raw=[0,33,33792,33^33792,33,0];s=span(raw);points=[outer(x,y,4,4) for x in range(1,16) for y in range(1,16)]
        inside=span([p for p in points if p in s]);expected=set()
        for i,p in enumerate(points):
            for q in points[i+1:]:
                if p^q in s and p^q not in inside:
                    assert rank(p^q,4,4)==2
                    expected.add(min(p^value for value in s))
        result=decoder.solve_pair_image(raw,4,4,4)
        assert result['case']=='repeated_coset_pair_extension' and set(result['extension_cosets'])==expected
        assert result['extension_cosets']==sorted(expected) and len(expected)==result['total_extensions']
        witness(raw,4,4,result);counts['extension_census_cases']+=1
        for kwargs in [dict(max_vectors=2),dict(max_vectors=3),dict(max_extensions=0),dict(max_mode_rank=1)]:
            result=decoder.solve_pair_image(raw,4,4,4,**kwargs);assert result['status']=='UNKNOWN' and not result['complete'];counts['caps']+=1
        # Delay the initial child and then the new repeated-pair child separately.
        actual=decoder.solve_one
        for trigger in [1,2]:
            calls=[0];flag=[False]
            def late(*a,**k):
                value=actual(*a,**k);calls[0]+=1
                if calls[0]==trigger:flag[0]=True
                return value
            with patch.object(decoder,'solve_one',late):
                value=decoder.solve_pair_image(raw,4,4,4,cancelled=lambda:flag[0]);assert value['status']=='UNKNOWN' and not value['complete'];counts['late_cases']+=1
        actualpair=decoder.solve_pair_image
        for budget in [0,1]:
            flag=[False]
            def latepair(*a,**k):value=actualpair(*a,**k);flag[0]=True;return value
            with patch.object(decoder,'solve_pair_image',latepair):
                value=decoder.solve_core([1],[1,1,1],budget,cancelled=lambda:flag[0]);assert value['status']=='UNKNOWN' and not value['complete'];counts['late_cases']+=1
        with patch.object(decoder.time,'time',return_value=decoder.HARD_DEADLINE):
            value=decoder.solve_pair_image([1],1,1,1,deadline_utc='2099-01-01T00:00:00Z');assert value['status']=='UNKNOWN' and value['case']=='deadline';counts['late_cases']+=1
    result=dict(status='PASS',counts=counts,production_queries=0,elapsed_seconds=time.monotonic()-start,
        module_sha256=hashlib.sha256((ROOT/'mmsearch/surplus_two7.py').read_bytes()).hexdigest(),tests_sha256=hashlib.sha256((ROOT/'tests/test_surplus_two7.py').read_bytes()).hexdigest(),
        proof_sha256=hashlib.sha256((ROOT/'research/marathon7/SURPLUS_TWO_DECODER.md').read_bytes()).hexdigest(),
        scope='Independent complete tiny rank-one-cover oracle, ambient-pair extension dedup census, original raw witnesses, caps and late-child/core barriers. No N5 queries.')
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
