"""Exact catalog-span support search through target rank plus two.

This is a general binary column problem. Quotient columns retain original IDs;
no quotient is treated as a tensor-product space or re-tested for rank one.
"""
from .compact_sat import BinaryBasis
from .compact_eight43 import exact_coordinates
from .compact_coset43 import _insert,digest


def remainder(value,basis):return value^basis.expand(basis.coordinates(value))


def quotient_catalog(catalog,basis):
    values={}
    for index,value in catalog:
        q=remainder(value,basis)
        if q and q not in values:values[q]=index
    return [(index,value) for value,index in values.items()]


def one_surplus(catalog,targets,budget,cancelled=None):
    space=BinaryBasis(targets);d=len(space.vectors)
    if budget<d:return dict(status='LOCAL_UNSAT',case='dimension_bound')
    if budget>d+1:return dict(status='UNKNOWN',case='unsupported_one_surplus_bound')
    if not d:return dict(status='SAT',support=[],case='zero_target')
    pivots={};inside=[];buckets={};byid=dict(catalog)
    for index,value in catalog:
        if cancelled and cancelled():return dict(status='UNKNOWN',case='cancelled')
        residue=remainder(value,space)
        if residue:buckets.setdefault(residue,[]).append(index)
        elif _insert(pivots,value):inside.append(index)
    if len(inside)==d:return dict(status='SAT',support=inside,case='inside_span')
    if budget==d:return dict(status='LOCAL_UNSAT',case='inside_rank_bound')
    for residue,indices in sorted(buckets.items()):
        if cancelled and cancelled():return dict(status='UNKNOWN',case='cancelled')
        anchor=indices[0];p=dict(pivots);chosen=[]
        for index in indices[1:]:
            if _insert(p,byid[index]^byid[anchor]):chosen.append(index)
            if len(p)==d:return dict(status='SAT',support=inside+[anchor]+chosen,case='one_nonzero_coset',coset=residue)
    return dict(status='LOCAL_UNSAT',case='no_one_coset')


def scalar_three(catalog,target,max_pairs,cancelled=None):
    byvalue={v:i for i,v in catalog}
    if target in byvalue:return dict(status='SAT',support=[byvalue[target]],pairs=0)
    for index,value in catalog:
        other=byvalue.get(target^value)
        if other is not None and other!=index:return dict(status='SAT',support=[index,other],pairs=0)
    tried=0
    for a,(i,x) in enumerate(catalog):
        for j,y in catalog[a+1:]:
            if (cancelled and cancelled()) or tried>=max_pairs:return dict(status='UNKNOWN',pairs=tried)
            tried+=1;k=byvalue.get(target^x^y)
            if k is not None and k not in (i,j):return dict(status='SAT',support=[i,j,k],pairs=tried)
    return dict(status='LOCAL_UNSAT',pairs=tried)


def solve_span(columns,targets,budget,max_branches=1000000,cancelled=None):
    columns=list(columns);targets=list(targets)
    if any(type(v) is not int or v<0 for v in columns+targets) or type(budget) is not int or budget<0 or type(max_branches) is not int or max_branches<0:raise ValueError('nonnegative integer columns/targets/budget/branch cap required')
    space=BinaryBasis(targets);m=len(space.vectors)
    identity=dict(target_rank=m,budget=budget,catalog_sha256=digest(columns),target_sha256=digest(targets),scope='Exact support spanning this target in this binary catalog only.')
    def finish(status,**kw):return dict(identity,status=status,complete=status!='UNKNOWN',**kw)
    if cancelled and cancelled():return finish('UNKNOWN',case='cancelled')
    if budget<m:return finish('LOCAL_UNSAT',case='dimension_bound')
    if budget>m+2:return finish('UNKNOWN',case='unsupported_surplus_gt_two')
    catalog=[];seen=set();inside_pivots={};forced=[]
    for i,value in enumerate(columns):
        if value and value not in seen:
            seen.add(value);catalog.append((i,value))
            if not remainder(value,space) and _insert(inside_pivots,value):forced.append(i)
    forced_basis=BinaryBasis([columns[i] for i in forced]);h=len(forced)
    reduced_targets=BinaryBasis([remainder(t,forced_basis) for t in space.vectors]).vectors
    reduced=quotient_catalog(catalog,forced_basis);d=len(reduced_targets);remaining=budget-h
    if d!=m-h:raise AssertionError('forcing inside basis changed target dimension incorrectly')
    reduced_space=BinaryBasis(reduced_targets)
    if any(not remainder(v,reduced_space) for _,v in reduced):raise AssertionError('nonzero inside column survived maximal inside basis quotient')
    def emit(support,case,**extra):
        chosen=forced+support
        if len(chosen)!=len(set(chosen)) or len(chosen)>budget:raise AssertionError('duplicate/overbudget lifted support')
        values=[columns[i] for i in chosen]
        if len(BinaryBasis(values).vectors)!=len(values):raise AssertionError('lifted support is dependent')
        coords=[exact_coordinates(t,values) for t in targets]
        return finish('SAT',case=case,support=chosen,target_coordinates=coords,forced_inside_basis=forced,
            forced_rank=h,reduced_target_rank=d,reduced_budget=remaining,**extra)
    if not d:return emit([],'forced_inside_span')
    easy=one_surplus(reduced,reduced_targets,min(remaining,d+1),cancelled)
    if easy['status']=='SAT':return emit(easy['support'],'forced_then_'+easy['case'])
    if easy['status']=='UNKNOWN':return finish('UNKNOWN',case='cancelled_easy_phase',forced_rank=h)
    if remaining<=d+1:return finish('LOCAL_UNSAT',case='complete_one_surplus_negative',forced_rank=h,reduced_target_rank=d)
    if remaining!=d+2:raise AssertionError('unexpected reduced surplus')
    if d==1:
        result=scalar_three(reduced,reduced_targets[0],max_branches,cancelled)
        if result['status']=='SAT':return emit(result['support'],'forced_scalar_weight_three',pairs_tried=result['pairs'])
        return finish(result['status'],case='scalar_weight_three',forced_rank=h,pairs_tried=result['pairs'])
    buckets={};byid=dict(reduced)
    for index,value in reduced:buckets.setdefault(remainder(value,reduced_space),[]).append(index)
    branches=0
    for residue,indices in sorted(buckets.items()):
        if not residue:raise AssertionError('inside projected column survived')
        for a,i in enumerate(indices):
            for j in indices[a+1:]:
                if (cancelled and cancelled()) or branches>=max_branches:return finish('UNKNOWN',case='pair_contraction_budget',branches=branches,forced_rank=h)
                branches+=1;pair=BinaryBasis([byid[i],byid[j]])
                if len(pair.vectors)!=2:raise AssertionError('contracted pair is dependent')
                new_targets=BinaryBasis([remainder(t,pair) for t in reduced_targets]).vectors
                if len(new_targets)!=d-1:raise AssertionError('same coset contraction missed exactly one target dimension')
                contracted=quotient_catalog(reduced,pair)
                result=one_surplus(contracted,new_targets,d,cancelled)
                if result['status']=='SAT':return emit([i,j]+result['support'],'forced_same_coset_pair_then_one_surplus',branches=branches,contracted_pair=[i,j],contracted_case=result['case'])
                if result['status']=='UNKNOWN':return finish('UNKNOWN',case='cancelled_contraction',branches=branches)
    return finish('LOCAL_UNSAT',case='all_same_coset_contractions_negative',branches=branches,forced_rank=h,reduced_target_rank=d)
