"""Finite6+2-to8 preparation and genuine fulln3 local8-to7 positive control."""
from .compact_sat import compress_residual
from .sat_neighborhoods import factor_masks
from .recombine import encode
from .search import naive_terms
from .verify import verify_candidate


def planted_eight_to_seven_n3():
    forms=[(1<<(i+1))^1 for i in range(6)]
    products=[(forms[0],forms[0],forms[1]),(forms[0],forms[1],forms[0]),(forms[1],forms[0],forms[0])]
    products += [(x,x,x) for x in forms[2:]]
    outside=[]
    for a,b,c in products:outside.extend([(a^256,b,c),(256,b,c)])
    a,b,c=products[0];local=[(a^128,b,c),(128,b,c)]+products[1:]
    source=encode(naive_terms(3)+outside+local,3,dict(method='planted W-plus-four-diagonals local8to7 fulln3 control'))
    checked=verify_candidate(source,random_trials=0)
    if not checked['valid'] or checked['rank']!=49 or checked['exact_entries_checked']!=729:raise AssertionError('n3 planted source invalid')
    masks=factor_masks(source);indices=sorted(masks.index(term) for term in local)
    if len(indices)!=8 or len(set(indices))!=8:raise AssertionError('planted8support not unique')
    bases,core,shape,_=compress_residual(source,indices)
    if shape!=[6,6,6]:raise AssertionError('planted core is not concise6x6x6')
    data=dict(shape=shape,core=core,image_bases=[b.vectors for b in bases],source_indices=indices,outside_indices=[i for i in range(49) if i not in indices])
    return source,data,checked
