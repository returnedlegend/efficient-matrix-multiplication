"""Exact CP(d+1) from rank-two matrices inside the actual slice image.

This separate prototype never enumerates the ambient rank-one variety.
"""
from .compact_sat import BinaryBasis
from .compact_eight43 import bits,exact_coordinates
from .compact_coset43 import _insert,digest,mode_slices,pair_column,expand_products


def matrix_rank_at_most_two(value,a,b):
    """Return0/1/2 or3 meaning at least3, plus up to two independent raw rows."""
    if type(a) is not int or type(b) is not int or min(a,b)<0 or type(value) is not int or value<0 or value>>(a*b):raise ValueError('matrix bits outside ambient shape')
    mask=(1<<b)-1;r0=r1=0
    for i in range(a):
        row=value>>(i*b)&mask
        if not row:continue
        if not r0:r0=row
        elif row!=r0 and not r1:r1=row
        elif row not in (r0,r1,r0^r1):return 3,(r0,r1)
    return (2 if r1 else 1 if r0 else 0),(r0,r1)


def rankone_factors(value,a,b):
    rank,rows=matrix_rank_at_most_two(value,a,b)
    if rank!=1:return None
    right=rows[0];left=sum(1<<i for i in range(a) if value>>(i*b)&((1<<b)-1))
    if pair_column(left,right,b)!=value:raise AssertionError('rank-one row factorization failed')
    return left,right


def rank_two_splits(value,a,b):
    """All exactly three unordered rank-one pairs summing to a rank-two matrix."""
    rank,(r0,r1)=matrix_rank_at_most_two(value,a,b)
    if rank!=2:raise ValueError('rank-two matrix required')
    c0=c1=0;mask=(1<<b)-1
    for i in range(a):
        row=value>>(i*b)&mask
        if row in (r0,r0^r1):c0|=1<<i
        if row in (r1,r0^r1):c1|=1<<i
    splits={}
    def dot(x,y):return (x&y).bit_count()&1
    for u in (1,2,3):
        for v in (1,2,3):
            if u==v:continue
            alpha=next(x for x in (1,2,3) if dot(x,u)==1 and dot(x,v)==0)
            beta=next(x for x in (1,2,3) if dot(x,u)==0 and dot(x,v)==1)
            left=(c0 if u&1 else 0)^(c1 if u&2 else 0);right=(r0 if alpha&1 else 0)^(r1 if alpha&2 else 0)
            left2=(c0 if v&1 else 0)^(c1 if v&2 else 0);right2=(r0 if beta&1 else 0)^(r1 if beta&2 else 0)
            p=pair_column(left,right,b);q=pair_column(left2,right2,b)
            if not p or not q or p^q!=value:raise AssertionError('GL2 split failed')
            if p>q:p,q,left,right,left2,right2=q,p,left2,right2,left,right
            splits[(p,q)]=dict(p=p,q=q,p_left=left,p_right=right,q_left=left2,q_right=right2)
    if len(splits)!=3:raise AssertionError('rank-two matrix must have three unordered splits')
    return [splits[key] for key in sorted(splits)]


def solve_pair_image(targets,a,b,budget=None,max_vectors=65535,cancelled=None):
    targets=list(targets)
    if type(a) is not int or type(b) is not int or min(a,b)<0 or type(max_vectors) is not int or max_vectors<0 or any(type(v) is not int or v<0 or v>>(a*b) for v in targets):raise ValueError('invalid matrix image')
    space=BinaryBasis(targets);d=len(space.vectors);budget=d+1 if budget is None else budget
    if type(budget) is not int or budget<0:raise ValueError('invalid budget')
    identity=dict(target_rank=d,budget=budget,left_width=a,right_width=b,target_sha256=digest(targets),algorithm='rank2_in_S_edges_without_ambient_rankone_catalog')
    def finish(status,**kw):return dict(identity,status=status,complete=status!='UNKNOWN',**kw)
    if cancelled and cancelled():return finish('UNKNOWN',case='cancelled')
    if budget<d:return finish('LOCAL_UNSAT',case='dimension_bound')
    if budget>d+1:return finish('UNKNOWN',case='unsupported_surplus_gt_one')
    if not d:return finish('SAT',case='zero_target',support=[],target_coordinates=[0]*len(targets),inside_rank=0)
    count=(1<<d)-1
    if count>max_vectors:return finish('UNKNOWN',case='subspace_enumeration_cap',span_vectors=count)
    pivots={};inside=[];inside_basis=[];buckets={};rank_counts={1:0,2:0,3:0};split_count=0;zero_coset_splits=0
    def point(value,left,right):return dict(column=value,left=left,right=right,id=(left-1)*((1<<b)-1)+right-1)
    for coordinates in range(1,count+1):
        if cancelled and cancelled():return finish('UNKNOWN',case='cancelled_enumeration',enumerated_vectors=coordinates-1)
        value=space.expand(coordinates);rank,_=matrix_rank_at_most_two(value,a,b);rank_counts[rank]+=1
        if rank==1:
            left,right=rankone_factors(value,a,b);entry=dict(point(value,left,right),span_coordinates=coordinates);inside.append(entry)
            if _insert(pivots,coordinates):inside_basis.append(entry)
        elif rank==2 and budget==d+1:
            for split in rank_two_splits(value,a,b):
                split_count+=1;residue=split['p']^space.expand(space.coordinates(split['p']))
                if residue!=(split['q']^space.expand(space.coordinates(split['q']))):raise AssertionError('split endpoints differ modulo S')
                if not residue:zero_coset_splits+=1;continue
                # One original endpoint pair per difference/coset suffices.
                buckets.setdefault(residue,{}).setdefault(coordinates,dict(split,span_coordinates=coordinates,difference=value))
    stats=dict(span_vectors=count,enumerated_vectors=count,matrix_rank_classes=dict(rank1=rank_counts[1],rank2=rank_counts[2],rank_at_least3=rank_counts[3]),inside_points=len(inside),inside_rank=len(inside_basis),nonzero_edge_cosets=len(buckets),unordered_rank2_splits=split_count,zero_coset_splits=zero_coset_splits,space_basis=space.vectors)
    def emit(pool,case,edges=None,coset=0):
        selected=[];basis={}
        for entry in pool:
            if _insert(basis,entry['column']):selected.append(entry)
        if len(selected)>budget or any(rankone_factors(e['column'],a,b)!=(e['left'],e['right']) for e in selected):raise AssertionError('selected support is not original rank-one points')
        coefficients=[exact_coordinates(t,[e['column'] for e in selected]) for t in targets]
        for target,mask in zip(targets,coefficients):
            value=0
            for j in bits(mask):value^=selected[j]['column']
            if value!=target:raise AssertionError('original raw target lift failed')
        return finish('SAT',case=case,support=selected,target_coordinates=coefficients,chosen_edges=edges or [],chosen_coset=coset,**stats)
    if len(inside_basis)==d:return emit(inside_basis,'inside_rankone_span')
    if budget==d:return finish('LOCAL_UNSAT',case='inside_rankone_deficiency',**stats)
    bucket_ranks=[]
    for residue,edges in sorted(buckets.items()):
        if cancelled and cancelled():return finish('UNKNOWN',case='cancelled_coset_scan',**stats)
        basis=dict(pivots);chosen=[]
        for coordinates,edge in sorted(edges.items()):
            if _insert(basis,coordinates):chosen.append(edge)
            if len(basis)==d:
                pool=list(inside_basis)
                for entry in chosen:pool.extend([point(entry['p'],entry['p_left'],entry['p_right']),point(entry['q'],entry['q_left'],entry['q_right'])])
                return emit(pool,'single_coset_rank2_edges_span',chosen,residue)
        bucket_ranks.append([residue,len(edges),len(basis)])
    return finish('LOCAL_UNSAT',case='no_single_rank2_edge_coset_spans',bucket_span_ranks=bucket_ranks,**stats)


def solve_core(core,shape,target,axis=None,max_vectors=65535,cancelled=None):
    if len(shape)!=3 or any(type(v) is not int or v<0 for v in shape) or len(core)!=shape[0]*shape[1]*shape[2] or any(type(v) is not int or v not in (0,1) for v in core):raise ValueError('invalid core')
    if axis is None:
        ranks=[len(BinaryBasis(mode_slices(core,shape,j)[0]).vectors) for j in range(3)];axis=max(range(3),key=lambda j:(ranks[j],shape[j],-j))
    if type(axis) is not int or axis not in (0,1,2):raise ValueError('invalid free axis')
    slices,other=mode_slices(core,shape,axis);result=solve_pair_image(slices,shape[other[0]],shape[other[1]],target,max_vectors,cancelled)
    result.update(shape=list(shape),axis=axis,core_sha256=digest(dict(shape=list(shape),core=core)))
    if result['status']=='SAT':
        free=[0]*len(result['support'])
        for coordinate,mask in enumerate(result['target_coordinates']):
            for j in bits(mask):free[j]^=1<<coordinate
        products=[]
        for j,entry in enumerate(result['support']):
            term=[0,0,0];term[axis]=free[j];term[other[0]]=entry['left'];term[other[1]]=entry['right']
            if all(term):products.append(term)
        if len(products)>target or expand_products(products,shape)!=core:raise AssertionError('all raw free-slice CP reconstruction failed')
        result['products']=products
    return result
