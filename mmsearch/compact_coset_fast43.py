"""Exact rank-d shortcut; unchanged complete one-coset fallback for rank d+1."""
from .compact_sat import BinaryBasis
from .compact_eight43 import bits,exact_coordinates
from .compact_coset43 import (_insert,digest,expand_products,mode_slices,
    solve_core as solve_one_coset)


def rankone_matrix_factors(value,left_width,right_width):
    if not value or value>>(left_width*right_width):return None
    right=0;left=0;mask=(1<<right_width)-1
    for i in range(left_width):
        row=value>>(i*right_width)&mask
        if row:
            if right and right!=row:return None
            right=row;left|=1<<i
    return (left,right) if right else None


def solve_core(core,shape,target,axis=None,max_points=1000000,cancelled=None):
    if len(shape)!=3 or any(type(d) is not int or d<0 for d in shape):raise ValueError('invalid shape')
    if len(core)!=shape[0]*shape[1]*shape[2] or any(type(v) is not int or v not in (0,1) for v in core):raise ValueError('invalid core')
    if type(target) is not int or target<0:raise ValueError('invalid target')
    if axis is None:
        ranks=[len(BinaryBasis(mode_slices(core,shape,a)[0]).vectors) for a in range(3)]
        axis=max(range(3),key=lambda a:(ranks[a],shape[a],-a))
    if type(axis) is not int or axis not in (0,1,2):raise ValueError('invalid free axis')
    slices,other=mode_slices(core,shape,axis);space=BinaryBasis(slices);d=len(space.vectors)
    if target!=d or not d:
        result=solve_one_coset(core,shape,target,axis,max_points,cancelled)
        result['algorithm']='complete_one_coset' if target<=d+1 else 'unsupported_surplus'
        return result
    count=(1<<d)-1;a,b=[shape[j] for j in other]
    identity=dict(shape=list(shape),target=target,axis=axis,mode_rank=d,opposite_axes=other,
        all_nonzero_pair_points=((1<<a)-1)*((1<<b)-1),span_vectors=count,
        core_sha256=digest(dict(shape=list(shape),core=core)),algorithm='enumerate_mode_subspace_rankone_test')
    def finish(status,**kwargs):return dict(identity,status=status,**kwargs)
    if count>max_points:return finish('UNKNOWN',reason='mode subspace enumeration cap',complete=False)
    pivots={};chosen=[];inside=[]
    for mask in range(1,count+1):
        if cancelled and cancelled():return finish('UNKNOWN',reason='cancelled during mode subspace enumeration',complete=False)
        q=space.expand(mask);factors=rankone_matrix_factors(q,a,b)
        if factors:
            left,right=factors;point=dict(span_mask=mask,column=q,left=left,right=right,index=(left-1)*((1<<b)-1)+right-1)
            inside.append(point)
            if _insert(pivots,mask):chosen.append(point)
    if len(chosen)<d:return finish('LOCAL_UNSAT',complete=True,case='inside_points_do_not_span',inside_rank=len(chosen),inside_points=len(inside),
        inside_pair_points=inside,space_basis=space.vectors,tested_span_vectors=count)
    columns=[p['column'] for p in chosen];free=[0]*len(columns)
    for coordinate,value in enumerate(slices):
        coefficients=exact_coordinates(value,columns)
        for j in bits(coefficients):free[j]^=1<<coordinate
    products=[]
    for point,coefficient in zip(chosen,free):
        term=[0,0,0];term[axis]=coefficient;term[other[0]]=point['left'];term[other[1]]=point['right']
        if all(term):products.append(term)
    if len(products)>target or expand_products(products,shape)!=core:raise AssertionError('fast exact decode failed core expansion')
    return finish('SAT',complete=True,case='inside_points_span_mode_image',products=products,pair_support=chosen,
        free_coordinate_masks=free,inside_rank=d,inside_points=len(inside),space_basis=space.vectors,tested_span_vectors=count,core_entries_checked=len(core))
