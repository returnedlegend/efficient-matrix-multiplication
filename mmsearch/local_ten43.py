"""Exact local10 preparation helpers; no production feasibility queries."""
import math
from .compact_sat import BinaryBasis,compress_residual
from .compact_eight43 import factor_core,expand_core,packed_tensor,replace_and_verify
from .sat_neighborhoods import factor_masks,gf2_rank
from .recombine import encode
from .search import naive_terms
from .verify import verify_candidate


def mask_indices(lo,hi):
    if lo<0 or lo>>64 or hi<0 or hi>>29:raise ValueError('mask outside93 indices')
    return [i for i in range(93) if (lo>>i&1 if i<64 else hi>>(i-64)&1)]


def extension_shapes(terms,selected,x,y):
    result=[]
    for axis in range(3):
        basis=BinaryBasis([terms[i][axis] for i in selected]);old=len(basis.vectors)
        a=terms[x][axis]^basis.expand(basis.coordinates(terms[x][axis]));b=terms[y][axis]^basis.expand(basis.coordinates(terms[y][axis]))
        result.append(old+gf2_rank([a,b]))
    return result


def native_row(line):
    row=list(map(int,line.split()))
    if len(row)!=16:raise ValueError('bad native bound row')
    return dict(source=row[0],lo=row[1],hi=row[2],shape=row[3:6],p1_ranks=row[6:9],p1_lower=row[9],p1_passed=bool(row[10]),
        p2_ranks=row[11:14],p2_lower=row[14],p2_passed=bool(row[15]))


def point_domain(shape):
    axis=max(range(3),key=lambda a:(shape[a],-a));other=[a for a in range(3) if a!=axis]
    return axis,((1<<shape[other[0]])-1)*((1<<shape[other[1]])-1)


def source_core(source,indices):
    terms=factor_masks(source);bases,core,shape=factor_core(terms,indices);ambient=0
    for i in indices:ambient^=packed_tensor(terms[i],source['dimension']**2)
    if expand_core(core,shape,bases,source['dimension']**2)!=ambient:raise AssertionError('exact full ambient core expansion failed')
    return dict(shape=shape,core=core,image_bases=bases,source_indices=indices,outside_indices=[i for i in range(len(terms)) if i not in indices],
        expanded_entries_checked=source['dimension']**6),ambient


def planted_small():
    local=[(11,5,9),(8,5,9),(3,10,6),(12,5,6)]
    outside=[(2,5,9),(1,5,9),(7,10,6),(4,10,6),(8,5,6),(4,5,6)]
    source=encode(naive_terms(2)+outside+local,2,dict(method='planted W-tensor one-coset full-MM control'))
    checked=verify_candidate(source,random_trials=0)
    if not checked['valid'] or checked['rank']!=18 or checked['exact_entries_checked']!=64:raise AssertionError('planted full source invalid')
    masks=factor_masks(source);indices=sorted(masks.index(term) for term in local);bases,core,shape,_=compress_residual(source,indices)
    if shape!=[2,2,2]:raise AssertionError('planted concise W-tensor changed')
    data=dict(shape=shape,core=core,image_bases=[b.vectors for b in bases],source_indices=indices,outside_indices=[i for i in range(18) if i not in indices])
    return source,data,checked
