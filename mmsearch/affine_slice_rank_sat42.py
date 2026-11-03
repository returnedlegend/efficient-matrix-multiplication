"""Exact unrestricted-factor affine-slice matrix rank SAT over F2.

Only the chosen source/free-axis/delta family is constrained. New rank factors
are arbitrary width-bit forms, with zero columns permitted. No dictionary,
factor independence, full-rank or term-ordering restriction is imposed.
"""
import math
from pathlib import Path
import types

from .free_factor_kernel import pair_column
from .free_factor_sat import packed_rref
from . import local_eliminated42sat as lifecycle
from .recombine import digest
from .search import encode_candidate
from .slice_compression import canonical_masks
from .verify import verify_candidate


def matrix_rank(matrix,width):
    pivots={}
    for i in range(width):
        row=(matrix>>(i*width))&((1<<width)-1)
        while row:
            pivot=row.bit_length()-1
            if pivot not in pivots:pivots[pivot]=row;break
            row^=pivots[pivot]
    return len(pivots)


def build_matrix_problem(matrix,neutral_columns,width,rank_bound):
    if (type(width) is not int or not 1<=width<=25 or type(rank_bound) is not int or
            not 0<=rank_bound<=width or type(matrix) is not int or not 0<=matrix<1<<(width*width) or
            any(type(column) is not int or not 0<=column<1<<(width*width) for column in neutral_columns)):
        raise ValueError('invalid exact affine matrix parameters')
    count=len(neutral_columns);nv=count;z=list(range(1,count+1));a=[];b=[];c=[];clauses=[];xors=[]
    def allocate(size):
        nonlocal nv
        result=list(range(nv+1,nv+size+1));nv+=size;return result
    for _ in range(rank_bound):
        av=allocate(width);bv=allocate(width);cv=allocate(width*width);a.append(av);b.append(bv);c.append(cv)
        for i in range(width):
            for j in range(width):
                gate=cv[i*width+j]
                clauses.extend(([-av[i],-bv[j],gate],[av[i],-gate],[bv[j],-gate]))
    for bit in range(width*width):
        variables=[cv[bit] for cv in c]+[z[g] for g,column in enumerate(neutral_columns) if column>>bit&1]
        rhs=bool(matrix>>bit&1)
        if variables:xors.append((variables,rhs))
        elif rhs:clauses.append([])
    metadata=dict(encoding='unrestricted-affine-slice-min-rank-native-xor-42-v1',kind='matrix-control',width=width,
        rank_bound=rank_bound,neutral_variables=count,variables=nv,cnf_clauses=len(clauses),native_xors=len(xors),
        complete_matrix_equations=width*width,allow_zero_factor_columns=True,full_rank_constraints=False,
        term_permutation_constraints=False,solver_threads=1,
        scope='This frozen affine matrix family only; no global tensor-rank nonexistence claim.',
        checkpoint_policy='Formula/assumptions/seeds are reproducible; solver internal learned-clause resume is not provided.')
    metadata['formula_sha256']=digest(dict(nv=nv,clauses=clauses,xors=xors))
    return dict(nv=nv,clauses=clauses,xors=xors,z_variables=z,a_variables=a,b_variables=b,c_variables=c,
                matrix=matrix,neutral_columns=list(neutral_columns),metadata=metadata)


def build_problem(candidate,free_axis,delta,rank_bound=None):
    if type(free_axis) is not int or free_axis not in (0,1,2):raise ValueError('invalid free axis')
    terms,canonicalization=canonical_masks(candidate);n=candidate['dimension'];width=n*n
    report=verify_candidate(candidate,random_trials=0)
    if not report['valid'] or report['exact_entries_checked']!=n**6:raise ValueError('invalid source certificate')
    if type(delta) is not int or not 0<delta<1<<width:raise ValueError('invalid free-factor delta')
    selected=[term for term in terms if term[free_axis]==delta]
    neutral=[term for term in terms if term[free_axis]!=delta]
    if not selected:raise ValueError('delta has no source terms')
    rank_bound=len(selected)-1 if rank_bound is None else rank_bound
    others=[axis for axis in range(3) if axis!=free_axis];matrix=0
    for term in selected:matrix^=pair_column([term[axis] for axis in others],width)
    columns=[pair_column([term[axis] for axis in others],width) for term in neutral]
    problem=build_matrix_problem(matrix,columns,width,rank_bound)
    problem.update(source_terms=[list(t) for t in terms],selected_terms=[list(t) for t in selected],
                   neutral_terms=[list(t) for t in neutral],source_dimension=n,free_axis=free_axis,other_axes=others,delta=delta)
    problem['metadata'].update(kind='full-matrix-multiplication',free_axis=free_axis,other_axes=others,delta=delta,
        selected_count=len(selected),source_rank=len(terms),candidate_rank_bound=len(neutral)+rank_bound,
        source_canonical_sha256=digest(encode_candidate(terms,n)),source_verification=report,
        source_canonicalization=canonicalization,unmixed_matrix_rank=matrix_rank(matrix,width),
        scope=f'Only source {digest(encode_candidate(terms,n))}, free axis {free_axis}, delta {delta}: '
              'neutral factors change by z*delta and selected slice is replaced by arbitrary binary rank factors. '
              'UNSAT excludes only this affine family, never global rank92.')
    problem['metadata']['family_sha256']=digest({key:problem[key] for key in
        ('source_terms','free_axis','delta','matrix','neutral_columns')}|dict(rank_bound=rank_bound))
    return problem


def validate_lift(problem,z_values,factors):
    width=problem['metadata']['width'];rank_bound=problem['metadata']['rank_bound']
    if len(z_values)!=len(problem['z_variables']) or any(type(z) is not bool for z in z_values):raise ValueError('invalid neutral bits')
    if len(factors)!=rank_bound or any(len(pair)!=2 or any(type(v) is not int or not 0<=v<1<<width for v in pair) for pair in factors):
        raise ValueError('invalid unrestricted rank factors')
    matrix=problem['matrix']
    for selected,column in zip(z_values,problem['neutral_columns']):
        if selected:matrix^=column
    observed=0
    for pair in factors:observed^=pair_column(pair,width)
    if matrix!=observed or matrix_rank(matrix,width)>rank_bound:raise ValueError('rank factorization does not lift affine matrix')
    return matrix


def witness_assignment(problem,z_values,factors):
    validate_lift(problem,z_values,factors);assignment=[None]+[False]*problem['nv'];width=problem['metadata']['width']
    for variable,value in zip(problem['z_variables'],z_values):assignment[variable]=value
    for av,bv,cv,(a,b) in zip(problem['a_variables'],problem['b_variables'],problem['c_variables'],factors):
        for i,v in enumerate(av):assignment[v]=bool(a>>i&1)
        for j,v in enumerate(bv):assignment[v]=bool(b>>j&1)
        for i in range(width):
            for j in range(width):assignment[cv[i*width+j]]=bool((a>>i&1) and (b>>j&1))
    return assignment


def control_assumptions(problem):
    if problem['metadata']['kind']!='full-matrix-multiplication' or len(problem['selected_terms'])!=problem['metadata']['rank_bound']:
        raise ValueError('original-factor control requires rank bound k')
    factors=[[term[axis] for axis in problem['other_axes']] for term in problem['selected_terms']]
    assignment=witness_assignment(problem,[False]*len(problem['z_variables']),factors)
    return [variable if value else -variable for variable,value in enumerate(assignment[1:],1)]


def validate_decode(problem,assignment,assumptions=()):
    if (not isinstance(assignment,(list,tuple)) or len(assignment)!=problem['nv']+1 or
            any(type(value) is not bool for value in assignment[1:])):raise AssertionError('incomplete or non-Boolean model')
    if any(assignment[abs(lit)]!=(lit>0) for lit in assumptions):raise AssertionError('assumption violation')
    if any(not any(assignment[abs(lit)]==(lit>0) for lit in row) for row in problem['clauses']):raise AssertionError('AND/CNF violation')
    if any(bool(sum(assignment[v] for v in row)%2)!=rhs for row,rhs in problem['xors']):raise AssertionError('native XOR violation')
    width=problem['metadata']['width'];z=[assignment[v] for v in problem['z_variables']]
    factors=[(sum(int(assignment[v])<<i for i,v in enumerate(av)),sum(int(assignment[v])<<j for j,v in enumerate(bv)))
             for av,bv in zip(problem['a_variables'],problem['b_variables'])]
    matrix=validate_lift(problem,z,factors)
    if problem['metadata']['kind']=='matrix-control':
        return dict(z=z,factors=factors,matrix=matrix),dict(valid=True,matrix_entries_checked=width*width,
            matrix_rank=matrix_rank(matrix,width),full_MM_certificate=False)
    axis=problem['free_axis'];others=problem['other_axes'];delta=problem['delta'];terms=[]
    for term,selected in zip(problem['neutral_terms'],z):
        new=list(term);new[axis]^=delta if selected else 0
        if not new[axis]:raise AssertionError('neutral free factor unexpectedly vanished')
        terms.append(tuple(new))
    for a,b in factors:
        if not a or not b:continue
        term=[0]*3;term[axis]=delta;term[others[0]]=a;term[others[1]]=b;terms.append(tuple(term))
    canonical=set()
    for term in terms:
        if term in canonical:canonical.remove(term)
        else:canonical.add(term)
    candidate=encode_candidate(canonical,problem['source_dimension'],method='unrestricted-affine-slice-rank-replacement',
        family_sha256=problem['metadata']['family_sha256'],formula_sha256=problem['metadata']['formula_sha256'],
        free_axis=axis,delta=delta,neutral_bits=z,new_rank_factors=factors,field_claim='F2 only; arbitrary new other-axis forms')
    report=verify_candidate(candidate,random_trials=0)
    if (not report['valid'] or report['exact_entries_checked']!=problem['source_dimension']**6 or
            report['rank']>problem['metadata']['candidate_rank_bound']):raise AssertionError('decoded full tensor/rank check failed')
    return candidate,report


def solve(problem,seconds=30,conflicts=10000000,memory_mb=1536,assumptions=(),options=None,log_path=None,cancelled=None):
    # Reuse the reviewed resource-limited child lifecycle in a private namespace;
    # the shared helper module is never monkey-patched or altered.
    original=lifecycle.solve;namespace=dict(original.__globals__,validate_decode=validate_decode)
    bounded=types.FunctionType(original.__code__,namespace,original.__name__,original.__defaults__,original.__closure__)
    result=bounded(problem,seconds=seconds,conflicts=conflicts,memory_mb=memory_mb,assumptions=assumptions,
                   options=options,log_path=log_path,cancelled=cancelled)
    if result['status']=='LOCAL_UNSAT':result['status']='AFFINE_FAMILY_UNSAT'
    if result['status']=='SAT' and problem['metadata']['kind']=='matrix-control':result['witness']=result.pop('candidate')
    return result


def solve_rank_zero(problem):
    if problem['metadata']['rank_bound']!=0:raise ValueError('rank-zero linear solve required')
    width=problem['metadata']['width'];columns=problem['neutral_columns'];coefficients=[];rhs=[]
    for bit in range(width*width):
        coefficients.append(sum(1<<g for g,column in enumerate(columns) if column>>bit&1));rhs.append((problem['matrix']>>bit)&1)
    reduced=packed_rref(coefficients,rhs,len(columns),1)
    if reduced['contradictions']:return dict(status='AFFINE_FAMILY_UNSAT',linear_proof=reduced,scope=problem['metadata']['scope'])
    z=[False]*len(columns)
    for row,value,_ in reduced['rows']:z[(row&-row).bit_length()-1]=bool(value)
    assignment=witness_assignment(problem,z,[]);candidate,report=validate_decode(problem,assignment)
    return dict(status='SAT',candidate=candidate,verification=report,complete_assignment=assignment,linear_proof=reduced)


def write_problem(problem,prefix):
    prefix=Path(prefix);prefix.parent.mkdir(parents=True,exist_ok=True)
    lifecycle.write_problem(problem,prefix)
