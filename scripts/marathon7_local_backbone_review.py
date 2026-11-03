#!/usr/bin/env python3
"""Independent finite-cover oracle and post-cutoff controls for backbone7."""
from collections import deque
from datetime import datetime,timezone
import hashlib
import itertools
import json
from pathlib import Path
import random
import sys
import time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mmsearch import backbone7 as decoder


def span(values):
    answer={0}
    for value in values:answer|={v^value for v in tuple(answer)}
    return answer


def basis(values):
    selected=[];points={0}
    for value in values:
        if value not in points:selected.append(value);points|={p^value for p in tuple(points)}
    return selected


def outer(x,y,a,b):return sum(((x>>i&1)&(y>>j&1))<<(i*b+j) for i in range(a) for j in range(b))
def rank(value,a,b):return len(span([(value>>(i*b))&((1<<b)-1) for i in range(a)])).bit_length()-1
def mask(points):return sum(1<<point for point in points)


def witness(raw,a,b,result):
    assert len(result['support'])<=result['budget']
    assert len(result['target_coordinates'])==len(raw)
    for point in result['support']:
        assert point in result['factor_point_pool']
        assert point['left'] and point['right']
        assert point['column']==outer(point['left'],point['right'],a,b)
    for value,coordinate in zip(raw,result['target_coordinates']):
        rebuilt=0
        for i,point in enumerate(result['support']):
            if coordinate>>i&1:rebuilt^=point['column']
        assert rebuilt==value


def all_spaces(a,b):
    initial=frozenset({0});spaces={initial};queue=deque([initial])
    while queue:
        old=queue.popleft()
        for value in range(1,1<<(a*b)):
            new=frozenset(set(old)|{p^value for p in old})
            if new not in spaces:spaces.add(new);queue.append(new)
    return spaces


def finite_covers(a,b):
    rankones=[outer(x,y,a,b) for x in range(1,1<<a) for y in range(1,1<<b)]
    initial=frozenset({0});spaces={initial};queue=deque([initial]);covers=[]
    while queue:
        old=queue.popleft();covers.append((len(old).bit_length()-1,mask(old)))
        for point in rankones:
            if point in old:continue
            new=frozenset(set(old)|{p^point for p in old})
            if new not in spaces:spaces.add(new);queue.append(new)
    return sorted(covers),rankones


def main():
    started=time.monotonic();counts=dict(spaces=0,budget_cases=0,exact_corank_le_one=0,positive_raw_witnesses=0,stronger_3x3_corank_one=0,late_primitive_and_core=0)
    with patch.object(decoder.time,'time',return_value=decoder.HARD_DEADLINE-60):
        for a,b,expected in [(2,2,67),(2,3,2825)]:
            spaces=all_spaces(a,b);assert len(spaces)==expected;covers,rankones=finite_covers(a,b)
            for space in spaces:
                targetmask=mask(space);optimum=next(cost for cost,cover in covers if targetmask&cover==targetmask)
                original=basis(sorted(space));backbone=basis([point for point in rankones if point in space]);q=len(original)-len(backbone)
                raw=[0]+original+original[::-1]+[0]
                for budget in range(a*b+1):
                    result=decoder.solve_pair_image(raw,a,b,budget);counts['budget_cases']+=1
                    if result['status']=='SAT':assert optimum<=budget;witness(raw,a,b,result);counts['positive_raw_witnesses']+=1
                    elif result['status']=='LOCAL_UNSAT':assert optimum>budget
                    else:assert q>1 and optimum<=budget or q>1 and result['case']=='restricted_upper_bound_exceeds_budget'
                    if q<=1:
                        assert result['status']==('SAT' if optimum<=budget else 'LOCAL_UNSAT')
                        if result.get('exact_cp_rank') is not None:assert result['exact_cp_rank']==optimum
                        counts['exact_corank_le_one']+=1
                counts['spaces']+=1
        # Independent covers with <=3 rank-one points certify no cheaper 3x3 cover.
        points=[outer(x,y,3,3) for x in range(1,8) for y in range(1,8)]
        covers3=sorted({(r,mask(span(subset))) for r in range(4) for subset in itertools.combinations(points,r)})
        rng=random.Random(70711)
        while counts['stronger_3x3_corank_one']<80:
            p=rng.choice(points);d=rng.randrange(1,512)
            if rank(d,3,3)<2 or rank(d^p,3,3)<2:continue
            expected=1+min(rank(d,3,3),rank(d^p,3,3));targetmask=mask({0,p,d,p^d})
            assert not any(cost<expected and cover&targetmask==targetmask for cost,cover in covers3)
            raw=[0,d,p,d^p,d,0]
            for budget in range(6):
                result=decoder.solve_pair_image(raw,3,3,budget)
                assert result['status']==('SAT' if budget>=expected else 'LOCAL_UNSAT')
                if result['status']=='SAT':assert result['exact_cp_rank']==expected;witness(raw,3,3,result)
            counts['stronger_3x3_corank_one']+=1
        # A primitive that crosses cancellation after precheck must not close negative.
        original=decoder.BinaryBasis;flag=[False]
        class LateBasis(original):
            def __init__(self,*a,**k):super().__init__(*a,**k);flag[0]=True
        with patch.object(decoder,'BinaryBasis',LateBasis):
            result=decoder.solve_pair_image([1],1,1,0,cancelled=lambda:flag[0]);assert result['status']=='UNKNOWN' and not result['complete'];counts['late_primitive_and_core']+=1
        actual=decoder.solve_pair_image
        for budget in [0,1]:
            flag[0]=False
            def late(*a,**k):
                result=actual(*a,**k);flag[0]=True;return result
            with patch.object(decoder,'solve_pair_image',late):
                result=decoder.solve_core([1],[1,1,1],budget,cancelled=lambda:flag[0]);assert result['status']=='UNKNOWN' and not result['complete'];counts['late_primitive_and_core']+=1
    result=dict(status='PASS',production_queries=0,counts=counts,module_sha256=hashlib.sha256((ROOT/'mmsearch/backbone7.py').read_bytes()).hexdigest(),
        tests_sha256=hashlib.sha256((ROOT/'tests/test_backbone7.py').read_bytes()).hexdigest(),proof_sha256=hashlib.sha256((ROOT/'research/marathon7/BACKBONE_DECODER.md').read_bytes()).hexdigest(),
        elapsed_seconds=time.monotonic()-started,scope='Complete tiny-space external rank-one-cover oracle; 80 independent3x3corank1 controls; lateprimitive/core barriers. No N5 query.')
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
