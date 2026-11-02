"""Prune local replacement patches by exact GF2 flattening-rank bounds.

A patch of m source products replaced by m-1 products can only succeed if
all three tensor unfoldings have matrix rank at most m-1. Passing this test
is necessary, not sufficient. The search is bounded and reproducible by seed.
"""
from __future__ import annotations
import argparse
import itertools
import math
import json
from pathlib import Path
import random
import time


def gf2_rank(rows):
    basis={}
    for value in rows:
        while value:
            pivot=value.bit_length()-1
            if pivot in basis:
                value ^= basis[pivot]
            else:
                basis[pivot]=value
                break
    return len(basis)


def factor_masks(candidate):
    from .sat import _normalize
    candidate = _normalize(candidate)
    return [tuple(sum((v%2)<<j for j,v in enumerate(t[a])) for a in ('u','v','w'))
            for t in candidate['terms']]


def _bits(value):
    while value:
        bit=value & -value
        yield bit.bit_length()-1
        value ^= bit


def precompute_rows(candidate):
    width=candidate['dimension']**2
    result=[]
    for factors in factor_masks(candidate):
        axis_rows=[]
        for axis in range(3):
            b,c=[factors[i] for i in range(3) if i!=axis]
            outer=sum(c << (j*width) for j in _bits(b))
            axis_rows.append(tuple(outer if factors[axis]>>j&1 else 0 for j in range(width)))
        result.append(axis_rows)
    return result


def flattening_bounds(rows,indices):
    return [gf2_rank([_xor(rows[i][axis][j] for i in indices) for j in range(len(rows[0][axis]))])
            for axis in range(3)]


def _xor(values):
    result=0
    for x in values: result ^= x
    return result


def select_patches(candidate, *, seconds=30, attempts=20000, seed=0, max_found=4):
    """Try graph neighborhoods, contiguous windows, and uniform subsets."""
    from .sat import _normalize
    from .verify import verify_candidate
    if (not math.isfinite(seconds) or seconds <= 0 or type(attempts) is not int or attempts < 0
            or type(max_found) is not int or max_found < 1):
        raise ValueError('positive finite seconds, nonnegative integer attempts, positive max_found required')
    candidate = _normalize(candidate)
    if not verify_candidate(candidate, random_trials=0)['valid']:
        raise ValueError('selection requires an exact F2 source decomposition')
    masks=factor_masks(candidate)
    rows=precompute_rows(candidate)
    count=len(masks)
    if count < 2:
        raise ValueError('at least two source terms required')
    sizes=list(range(min(3,count-1),min(8,count-1)+1))
    rng=random.Random(seed)
    neighbors=[]
    for i,factors in enumerate(masks):
        def distance(j):
            other=masks[j]
            shared=sum(x==y for x,y in zip(factors,other))
            overlap=sum((x&y).bit_count() for x,y in zip(factors,other))
            difference=sum((x^y).bit_count() for x,y in zip(factors,other))
            return (-100*shared-overlap,difference,j)
        neighbors.append(sorted((j for j in range(count) if j!=i),key=distance))
    found=[]
    seen=set()
    rejected=checked=0
    started=time.monotonic()
    completed=0
    for attempt in range(attempts):
        if time.monotonic()-started>=seconds or len(found)>=max_found: break
        completed=attempt+1
        k=sizes[attempt%len(sizes)]
        m=k+1
        anchor=rng.randrange(count)
        strategy=(attempt//len(sizes))%4
        if strategy==0:
            selected=tuple(sorted([anchor]+neighbors[anchor][:k]))
        elif strategy==1:
            selected=tuple(sorted([anchor]+rng.sample(neighbors[anchor][:min(count-1,3*k)],k)))
        elif strategy==2:
            start=rng.randrange(count-m+1)
            selected=tuple(range(start,start+m))
        else:
            selected=tuple(sorted(rng.sample(range(count),m)))
        if selected in seen: continue
        seen.add(selected)
        bounds=flattening_bounds(rows,selected)
        checked+=1
        if max(bounds)>k:
            rejected+=1
            continue
        # Delete the sparsest source term; the remaining k terms become mutable.
        drop=min(selected,key=lambda i:__import__('math').prod(x.bit_count() for x in masks[i]))
        found.append({'drop_term':drop,'active_terms':[i for i in selected if i!=drop],
                      'selected_source_terms':list(selected),'flattening_ranks':bounds,'active_count':k})
    return {'seed':seed,'attempt_budget':attempts,'seconds_budget':seconds,
            'attempts_completed':completed,'distinct_patches_checked':checked,
            'flattening_rejections':rejected,'patches':found,
            'elapsed_seconds':time.monotonic()-started,
            'scope':'passing flattening bounds is necessary, not sufficient; bounded local selection only'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',default='artifacts/sat_neighborhood_selection.json')
    parser.add_argument('--seconds',type=float,default=30)
    parser.add_argument('--attempts',type=int,default=20000)
    parser.add_argument('--seed',type=int,default=0)
    args=parser.parse_args()
    report=select_patches(json.loads(Path(args.input).read_text()),seconds=args.seconds,
                          attempts=args.attempts,seed=args.seed)
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__': main()
