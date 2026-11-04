"""Exact CP(d+3) under the proved rank-one-backbone bound b<=d-5.

No N5 loading or publication. Incomplete priors, children, caps and late results
are UNKNOWN. Original rank-one points and every original raw slice are retained.
"""
from datetime import datetime,timezone
import math

from .backbone7 import DEADLINE,_matrix
from .compact_sat import BinaryBasis
from .compact_eight43 import bits,exact_coordinates
from .compact_coset43 import _insert,digest,expand_products,mode_slices,pair_column
from .compact_rank2_edges43 import matrix_rank_at_most_two,rank_two_splits,rankone_factors
from .surplus_two_large7 import _Guard,solve_pair_image as solve_two

MAX_MODE_RANK=11


def solve_pair_image(targets,rows,columns,budget=None,*,max_vectors=2047,
                     max_extensions=6141,max_child_vectors=8191,max_child_extensions=24573,
                     max_mode_rank=MAX_MODE_RANK,cancelled=None,timeout_seconds=None,
                     deadline_utc=DEADLINE):
    targets=list(targets);_matrix(0,rows,columns)
    for value in targets:_matrix(value,rows,columns)
    if budget is not None and (type(budget) is not int or budget<0):raise ValueError('literal nonnegative budget required')
    caps=(max_vectors,max_extensions,max_child_vectors,max_child_extensions,max_mode_rank)
    if any(type(x) is not int or x<0 for x in caps) or max_mode_rank>MAX_MODE_RANK:
        raise ValueError('literal nonnegative caps; parent mode cap at most11')
    guard=_Guard(cancelled,timeout_seconds,deadline_utc)
    identity=dict(algorithm='conditional_surplus_three7',target_sha256=digest(targets),
        raw_target_count=len(targets),left_width=rows,right_width=columns,
        effective_deadline_utc=datetime.fromtimestamp(guard.deadline,timezone.utc).isoformat(),
        publication_eligible=False,requires_ambient_verification=True)
    def finish(status,case,**kwargs):
        reason=guard.reason()
        if reason:status,case='UNKNOWN',reason
        return dict(identity,status=status,complete=status!='UNKNOWN',case=case,**kwargs)
    reason=guard.reason()
    if reason:return finish('UNKNOWN',reason)
    space=BinaryBasis(targets);d=len(space.vectors);budget=d+3 if budget is None else budget
    identity.update(target_rank=d,space_basis=list(space.vectors),budget=budget)
    if budget<d:return finish('LOCAL_UNSAT','dimension_bound')
    if budget>d+3:return finish('UNKNOWN','unsupported_surplus_gt_three')
    if d>max_mode_rank:return finish('UNKNOWN','parent_mode_rank_cap')
    count=(1<<d)-1
    if count>max_vectors:return finish('UNKNOWN','parent_subspace_enumeration_cap',span_vectors=count)

    def emit(pool,case,**stats):
        selected=[];pivots={}
        for original in pool:
            reason=guard.reason()
            if reason:return finish('UNKNOWN',reason,raw_cover_factor_points=[dict(p) for p in pool],**stats)
            point=dict(original)
            if (not point['left'] or not point['right'] or point['left']>>rows or point['right']>>columns
                    or pair_column(point['left'],point['right'],columns)!=point['column']):
                raise AssertionError('child returned invalid original rank-one factor point')
            if _insert(pivots,point['column']):selected.append(point)
        basis=[p['column'] for p in selected];coordinates=[]
        for target in targets:
            reason=guard.reason()
            if reason:return finish('UNKNOWN',reason,raw_cover_factor_points=[dict(p) for p in pool],**stats)
            mask=exact_coordinates(target,basis);rebuilt=0
            for i in bits(mask):rebuilt^=basis[i]
            if rebuilt!=target:raise AssertionError('original raw slice reconstruction differs')
            coordinates.append(mask)
        if len(selected)>budget:raise AssertionError('cover exceeds requested budget')
        return finish('SAT',case,support=selected,factor_point_pool=[dict(p) for p in pool],
            target_coordinates=coordinates,**stats)

    prior=solve_two(targets,rows,columns,min(budget,d+2),max_vectors=max_child_vectors,
        max_extensions=max_child_extensions,max_mode_rank=12,cancelled=guard.stopped,
        timeout_seconds=guard.remaining(),deadline_utc=deadline_utc)
    reason=guard.reason()
    if reason:return finish('UNKNOWN',reason,last_prior_result=prior)
    prior_stats=dict(prior_result_sha256=digest(prior),prior_case=prior.get('case'))
    if prior['status']=='SAT':return emit(prior['support'],'surplus_two_cover',**prior_stats)
    if prior['status']!='LOCAL_UNSAT' or prior.get('complete') is not True:
        return finish('UNKNOWN','surplus_two_prior_incomplete',last_prior_result=prior,**prior_stats)
    if budget<=d+2:return finish('LOCAL_UNSAT','surplus_two_complete_negative',**prior_stats)

    inside=[];inside_pivots={};rank_two=[]
    for coordinates in range(1,count+1):
        reason=guard.reason()
        if reason:return finish('UNKNOWN',reason,enumerated_vectors=coordinates-1,**prior_stats)
        value=space.expand(coordinates);rank,_=matrix_rank_at_most_two(value,rows,columns)
        if rank==1 and _insert(inside_pivots,coordinates):
            left,right=rankone_factors(value,rows,columns)
            inside.append(dict(column=value,left=left,right=right,span_coordinates=coordinates))
        elif rank==2:rank_two.append((coordinates,value))
    b=len(inside)
    stats=dict(prior_stats,span_vectors=count,enumerated_vectors=count,inside_rank=b,
        backbone_codimension=d-b,rank_two_matrices=len(rank_two),required_backbone_bound=d-5)
    if b>d-5:return finish('UNKNOWN','conditional_backbone_bound_not_met',**stats)
    backbone=BinaryBasis([p['span_coordinates'] for p in inside]);candidates={};splits=0;relevant=0
    for coordinates,value in rank_two:
        reason=guard.reason()
        if reason:return finish('UNKNOWN',reason,**stats)
        if not coordinates^backbone.expand(backbone.coordinates(coordinates)):continue
        relevant+=1
        for split in rank_two_splits(value,rows,columns):
            reason=guard.reason()
            if reason:return finish('UNKNOWN',reason,**stats)
            splits+=1;coset=split['p']^space.expand(space.coordinates(split['p']))
            if not coset or coset!=split['q']^space.expand(space.coordinates(split['q'])):
                raise AssertionError('rank-two split quotient identity differs')
            candidates.setdefault(coset,dict(split,coset=coset,difference=value,difference_coordinates=coordinates))
    ordered=sorted(candidates)
    stats.update(relevant_rank_two_differences=relevant,unordered_rank_two_splits=splits,
        total_extensions=len(ordered),extension_cosets=ordered,tested_extensions=[],
        conditional_pair_theorem_applies=True)
    for cursor,coset in enumerate(ordered):
        reason=guard.reason()
        if reason:return finish('UNKNOWN',reason,extension_cursor=cursor,**stats)
        if cursor>=max_extensions:return finish('UNKNOWN','parent_extension_cap',extension_cursor=cursor,**stats)
        seed=candidates[coset];extended=BinaryBasis(list(space.vectors)+[seed['p']])
        if len(extended.vectors)!=d+1:raise AssertionError('parent split extension dimension differs')
        child=solve_two(extended.vectors,rows,columns,d+3,max_vectors=max_child_vectors,
            max_extensions=max_child_extensions,max_mode_rank=12,cancelled=guard.stopped,
            timeout_seconds=guard.remaining(),deadline_utc=deadline_utc)
        reason=guard.reason()
        if reason:return finish('UNKNOWN',reason,extension_cursor=cursor,last_child_result=child,**stats)
        if child['status']=='SAT':return emit(child['support'],'conditional_repeated_pair_extension',
            extension_cursor=cursor,extension_certificate=seed,child_result_sha256=digest(child),**stats)
        if child['status']!='LOCAL_UNSAT' or child.get('complete') is not True:
            return finish('UNKNOWN','extension_child_incomplete',extension_cursor=cursor,
                child_case=child.get('case'),last_child_result=child,**stats)
        stats['tested_extensions'].append(dict(coset=coset,status='LOCAL_UNSAT',child_result_sha256=digest(child)))
    return finish('LOCAL_UNSAT','all_conditional_repeated_pair_extensions_negative',
        extension_cursor=len(ordered),**stats)


def solve_core(core,shape,target=None,axis=None,**kwargs):
    guard=_Guard(kwargs.get('cancelled'),kwargs.get('timeout_seconds'),kwargs.get('deadline_utc',DEADLINE))
    if (len(shape)!=3 or any(type(d) is not int or d<0 for d in shape) or len(core)!=math.prod(shape)
            or any(type(v) is not int or v not in (0,1) for v in core)):
        raise ValueError('literal binary core and shape required')
    if axis is None:
        ranks=[len(BinaryBasis(mode_slices(core,shape,j)[0]).vectors) for j in range(3)]
        axis=max(range(3),key=lambda j:(ranks[j],shape[j],-j))
    if type(axis) is not int or axis not in (0,1,2):raise ValueError('literal axis0..2 required')
    slices,other=mode_slices(core,shape,axis);kwargs['timeout_seconds']=guard.remaining()
    result=solve_pair_image(slices,shape[other[0]],shape[other[1]],target,**kwargs)
    result.update(shape=list(shape),axis=axis,core_sha256=digest(dict(shape=list(shape),core=core)))
    def finish():
        reason=guard.reason()
        if reason:result.update(status='UNKNOWN',complete=False,case=reason)
        return result
    if finish()['status']!='SAT':return result
    free=[0]*len(result['support'])
    for i,mask in enumerate(result['target_coordinates']):
        for j in bits(mask):free[j]|=1<<i
    products=[]
    for j,point in enumerate(result['support']):
        term=[0,0,0];term[axis]=free[j];term[other[0]]=point['left'];term[other[1]]=point['right']
        if all(term):products.append(term)
    if len(products)>result['budget'] or expand_products(products,shape)!=list(core):
        raise AssertionError('every original compact coefficient reconstruction differs')
    result.update(products=products,core_entries_checked=len(core))
    return finish()
