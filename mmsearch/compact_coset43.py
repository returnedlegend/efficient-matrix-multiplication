"""Complete binary CP feasibility when target <= one chosen mode rank + 1.

Enumerates every nonzero rank-one opposite-pair column. This is an exact
finite-algebraic decoder, with no SAT solver or pair dictionary restriction.
"""
import hashlib
import itertools
import json

from .compact_sat import BinaryBasis
from .compact_eight43 import bits,exact_coordinates


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _insert(pivots,value):
    while value:
        p=value.bit_length()-1
        if p not in pivots:pivots[p]=value;return True
        value^=pivots[p]
    return False


def pair_column(left,right,right_width):
    result=0
    for i in bits(left):result^=right<<(i*right_width)
    return result


def mode_slices(core,shape,axis):
    other=[a for a in range(3) if a!=axis];slices=[0]*shape[axis]
    for xyz in itertools.product(*(range(d) for d in shape)):
        if core[(xyz[0]*shape[1]+xyz[1])*shape[2]+xyz[2]]:
            slices[xyz[axis]]^=1<<(xyz[other[0]]*shape[other[1]]+xyz[other[1]])
    return slices,other


def expand_products(products,shape):
    core=[0]*(shape[0]*shape[1]*shape[2])
    for term in products:
        if len(term)!=3 or any(type(v) is not int or v<0 or v>>d for v,d in zip(term,shape)):raise ValueError('invalid factor coordinates')
        for a,b,c in itertools.product(*(bits(v) for v in term)):core[(a*shape[1]+b)*shape[2]+c]^=1
    return core


def solve_core(core,shape,target,axis=None,max_points=1000000,cancelled=None):
    if len(shape)!=3 or any(type(d) is not int or d<0 for d in shape):raise ValueError('invalid shape')
    if len(core)!=shape[0]*shape[1]*shape[2] or any(type(v) is not int or v not in (0,1) for v in core):raise ValueError('invalid binary core')
    if type(target) is not int or target<0:raise ValueError('invalid target')
    if axis is None:
        ranks=[len(BinaryBasis(mode_slices(core,shape,a)[0]).vectors) for a in range(3)]
        axis=max(range(3),key=lambda a:(ranks[a],shape[a],-a))
    if type(axis) is not int or axis not in (0,1,2):raise ValueError('invalid free axis')
    slices,other=mode_slices(core,shape,axis);space=BinaryBasis(slices);d=len(space.vectors)
    count=((1<<shape[other[0]])-1)*((1<<shape[other[1]])-1)
    identity=dict(shape=list(shape),target=target,axis=axis,mode_rank=d,opposite_axes=other,
        all_nonzero_pair_points=count,core_sha256=digest(dict(shape=list(shape),core=core)))
    def finish(status,**kwargs):return dict(identity,status=status,**kwargs)
    if cancelled and cancelled():return finish('UNKNOWN',reason='cancelled before enumeration')
    if target<d:return finish('LOCAL_UNSAT',complete=True,case='mode_rank_exceeds_target')
    if target>d+1:return finish('UNKNOWN',reason='target exceeds supported mode-rank-plus-one scope',complete=False)
    if not d:return finish('SAT',products=[],complete=True,case='zero_tensor',pair_support=[])
    if count>max_points:return finish('UNKNOWN',reason='pair point enumeration cap',complete=False)
    pairs=[];inside=[];buckets={};inside_pivots={};chosen_inside=[]
    for left in range(1,1<<shape[other[0]]):
        for right in range(1,1<<shape[other[1]]):
            if cancelled and cancelled():return finish('UNKNOWN',reason='cancelled during pair enumeration',complete=False)
            q=pair_column(left,right,shape[other[1]]);coordinates=space.coordinates(q);residue=q^space.expand(coordinates)
            index=len(pairs);pairs.append((q,left,right))
            if residue:buckets.setdefault(residue,[]).append(index)
            else:
                inside.append(index)
                if _insert(inside_pivots,coordinates):chosen_inside.append(index)
    def emit(support,case,quotient=0):
        columns=[pairs[i][0] for i in support]
        if len(BinaryBasis(columns).vectors)!=len(columns):raise AssertionError('selected pair support is dependent')
        factors=[0]*len(columns)
        for coordinate,value in enumerate(slices):
            coordinates=exact_coordinates(value,columns)
            for j in bits(coordinates):factors[j]^=1<<coordinate
        products=[]
        for j,index in enumerate(support):
            term=[0,0,0];term[axis]=factors[j];term[other[0]]=pairs[index][1];term[other[1]]=pairs[index][2]
            if all(term):products.append(term)
        if len(products)>target or expand_products(products,shape)!=core:raise AssertionError('pair-basis decode failed full exact core')
        return finish('SAT',complete=True,case=case,products=products,pair_support=[dict(index=i,column=pairs[i][0],left=pairs[i][1],right=pairs[i][2]) for i in support],
            free_coordinate_masks=factors,inside_rank=len(chosen_inside),inside_points=len(inside),nonzero_cosets=len(buckets),quotient_representative=quotient,
            space_basis=space.vectors,core_entries_checked=len(core))
    if len(chosen_inside)==d:return emit(chosen_inside,'inside_points_span_mode_image')
    if target==d:return finish('LOCAL_UNSAT',complete=True,case='inside_points_do_not_span',inside_rank=len(chosen_inside),inside_points=len(inside),nonzero_cosets=len(buckets),space_basis=space.vectors)
    bucket_ranks=[]
    for residue,indices in sorted(buckets.items()):
        if cancelled and cancelled():return finish('UNKNOWN',reason='cancelled during coset scan',complete=False)
        pivots=dict(inside_pivots);anchor=indices[0];chosen=[]
        for index in indices[1:]:
            difference=pairs[index][0]^pairs[anchor][0]
            coordinates=space.coordinates(difference,require_member=True)
            if _insert(pivots,coordinates):chosen.append(index)
            if len(pivots)==d:return emit(chosen_inside+[anchor]+chosen,'single_nonzero_coset_star_differences_span',residue)
        bucket_ranks.append([residue,len(indices),len(pivots)])
    return finish('LOCAL_UNSAT',complete=True,case='no_single_coset_spans',inside_rank=len(chosen_inside),inside_points=len(inside),nonzero_cosets=len(buckets),
        bucket_span_ranks=bucket_ranks,space_basis=space.vectors,pair_catalog_sha256=digest(pairs))
