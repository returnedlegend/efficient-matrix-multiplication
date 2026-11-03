"""Rank-one span discovery inside one fixed-pair coefficient hyperplane over F2.

Oracle UNSAT excludes only this physical hyperplane. It is not a tensor-rank
lower bound. Each oracle is fresh; checkpoints retain points, not learned clauses.
"""
import hashlib
import json
import types

from . import local_eliminated42sat as lifecycle
from .sat import CNF
from .search import decode_candidate,encode_candidate
from .verify import verify_candidate


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def bits(value):
    while value:
        bit=value&-value;yield bit.bit_length()-1;value^=bit


def linear_basis(vectors):
    basis={}
    for index,value in enumerate(vectors):
        witness=1<<index
        while value:
            pivot=value.bit_length()-1
            if pivot not in basis:basis[pivot]=(value,witness);break
            row,old=basis[pivot];value^=row;witness^=old
    return basis


def coordinates(vectors,value):
    result=0
    for pivot,(row,witness) in sorted(linear_basis(vectors).items(),reverse=True):
        if value>>pivot&1:value^=row;result^=witness
    return None if value else result


def canonical_span(vectors):
    rows={p:r for p,(r,_) in linear_basis(vectors).items()}
    for pivot in sorted(rows):
        for other in rows:
            if other!=pivot and rows[other]>>pivot&1:rows[other]^=rows[pivot]
    return [rows[p] for p in sorted(rows)]


def nullspace(rows,width):
    if any(type(r) is not int or r<0 or r>>width for r in rows):raise ValueError('invalid GF2 row')
    reduced=canonical_span(rows);pivots={r.bit_length()-1:r for r in reduced};answer=[]
    for free in range(width):
        if free in pivots:continue
        value=1<<free
        for pivot,row in pivots.items():
            if row>>free&1:value|=1<<pivot
        if any((row&value).bit_count()%2 for row in rows):raise AssertionError('annihilator construction failed')
        answer.append(value)
    return answer


def combine(columns,coefficient):
    value=0
    for index in bits(coefficient):value^=columns[index]
    return value


def pair_column(a,b,width):return sum(b<<(i*width) for i in bits(a))


def prepare_source(candidate,free_axis):
    if type(free_axis) is not int or free_axis not in (0,1,2):raise ValueError('invalid free axis')
    n=candidate.get('dimension')
    if type(n) is not int or not 2<=n<=5 or type(candidate.get('field')) is not int or candidate['field']!=2:
        raise ValueError('exact n2..5 field2 source required')
    terms=decode_candidate(candidate,n)
    if any(not all(t) for t in terms) or len(set(terms))!=len(terms):
        raise ValueError('source terms must be distinct and nonzero; order is preserved')
    report=verify_candidate(candidate,random_trials=0)
    if not report['valid'] or report['exact_entries_checked']!=n**6:raise ValueError('source failed full tensor verification')
    other=[axis for axis in range(3) if axis!=free_axis];width=n*n
    pairs=[(t[other[0]],t[other[1]]) for t in terms]
    result=prepare_linear(pairs,[t[free_axis] for t in terms],width,free_axis=free_axis)
    result.update(kind='full-matrix-multiplication',dimension=n,source_terms=[list(t)for t in terms],
                  source_sha256=digest(candidate),source_verification=report,other_axes=other)
    result['source_data_sha256']=digest({k:v for k,v in result.items() if k!='source_data_sha256'})
    return result


def prepare_linear(pairs,free_values,width,free_axis=2):
    if type(width) is not int or not 1<=width<=25 or len(pairs)!=len(free_values) or not pairs:
        raise ValueError('invalid linear family dimensions')
    bound=1<<width
    if any(len(p)!=2 or any(type(x) is not int or not 0<x<bound for x in p)for p in pairs):
        raise ValueError('invalid rank-one fixed pair')
    if any(type(w) is not int or not 0<=w<bound for w in free_values):raise ValueError('invalid free vector')
    columns=[pair_column(a,b,width)for a,b in pairs];rank=len(linear_basis(columns))
    if rank!=len(columns):raise ValueError('active fixed-pair matrix A must have full column rank R')
    target_coefficients=[sum(1<<r for r,w in enumerate(free_values)if w>>j&1)for j in range(width)]
    target=[combine(columns,c)for c in target_coefficients]
    return dict(kind='linear-control',width=width,R=len(columns),pairs=[list(p)for p in pairs],
                A_columns=columns,A_rank=rank,W_rows=list(free_values),W_columns=target_coefficients,
                target_columns=target,target_sha256=digest(dict(width=width,target=target)),free_axis=free_axis)


def build_family(source,lam):
    R=source['R']
    if type(lam) is not int or not 0<lam<1<<R:raise ValueError('lambda must be a nonzero R-bit vector')
    if any((lam&w).bit_count()%2 for w in source['W_columns']):raise ValueError('lambda^T W is not zero')
    if len(linear_basis(source['A_columns']))!=R:raise ValueError('A lost full column rank')
    kernel=nullspace([lam],R);physical=canonical_span([combine(source['A_columns'],c)for c in kernel])
    if len(physical)!=R-1:raise AssertionError('H does not have dimension R-1')
    initial=[1<<i for i in range(R)if not lam>>i&1]
    family=dict(source=source,lambda_mask=lam,lambda_weight=lam.bit_count(),H_dimension=R-1,
                initial_coefficients=initial,physical_H_basis=physical,
                physical_H_sha256=digest(dict(axis=source['free_axis'],target=source['target_sha256'],span=physical)),
                scope='Only the rank-one points in this exact fixed-pair-span hyperplane H; not unrestricted tensor rank.')
    family['family_sha256']=digest(family)
    return family


def validate_point(family,coefficients,point):
    source=family['source'];R=source['R'];width=source['width']
    if not isinstance(point,dict) or set(point)!={'a','b','c'}:raise ValueError('point must contain exactly a,b,c')
    a,b,c=(point[k]for k in ['a','b','c'])
    if (any(type(x) is not int for x in [a,b,c]) or not 0<a<1<<width or not 0<b<1<<width
            or not 0<c<1<<R):raise ValueError('invalid rank-one point masks')
    if (c&family['lambda_mask']).bit_count()%2:raise ValueError('point is outside lambda hyperplane')
    if combine(source['A_columns'],c)!=pair_column(a,b,width):raise ValueError('point fails all A*c=a outer b equations')
    if coordinates(coefficients,c) is not None:raise ValueError('point does not strictly increase U rank')
    if len(linear_basis([*coefficients,c]))!=len(coefficients)+1:raise AssertionError('point rank increase failed')
    return True


def state_vectors(family,points):
    coefficients=list(family['initial_coefficients'])
    pairs=[tuple(family['source']['pairs'][c.bit_length()-1])for c in coefficients]
    for point in points:
        validate_point(family,coefficients,point);coefficients.append(point['c']);pairs.append((point['a'],point['b']))
    if len(coefficients)>family['H_dimension']:raise ValueError('point basis exceeds H dimension')
    return coefficients,pairs


def contained(family,coefficients):
    return all(coordinates(coefficients,w)is not None for w in family['source']['W_columns'])


def build_oracle(family,points=()):
    coefficients,_=state_vectors(family,points);source=family['source'];R=source['R'];width=source['width']
    cnf=CNF();a=[cnf.variable()for _ in range(width)];b=[cnf.variable()for _ in range(width)]
    c=[cnf.variable()for _ in range(R)];gates=[cnf.conjunction([a[i],b[j]])for i in range(width)for j in range(width)]
    xors=[]
    for bit,gate in enumerate(gates):xors.append(([gate]+[c[r]for r,col in enumerate(source['A_columns'])if col>>bit&1],False))
    xors.append(([c[r]for r in bits(family['lambda_mask'])],False))
    annihilator=nullspace(coefficients,R);aux=[cnf.variable()for _ in annihilator]
    for value,var in zip(annihilator,aux):xors.append(([var]+[c[r]for r in bits(value)],False))
    cnf.clauses.extend([a,b,aux])
    formula=dict(nv=cnf.nv,clauses=cnf.clauses,xors=xors)
    metadata=dict(encoding='rank-one-point-in-coefficient-hyperplane42-v1',scope=family['scope'],
                  width=width,R=R,U_dimension=len(coefficients),H_dimension=family['H_dimension'],
                  factor_bits=2*width,AND_gates=width*width,coefficient_bits=R,
                  annihilator_auxiliaries=len(aux),matrix_equations=width*width,
                  variables=cnf.nv,CNF_clauses=len(cnf.clauses),native_XOR_equations=len(xors),
                  formula_sha256=digest(formula),family_sha256=family['family_sha256'],
                  checkpoint_policy='Fresh solver per point; points/formulas retained, no learned-clause serialization.')
    return dict(**formula,a_variables=a,b_variables=b,c_variables=c,gates=gates,
                annihilator=annihilator,aux_variables=aux,coefficients=coefficients,
                family=family,metadata=metadata)


def witness_assignment(problem,point):
    values=[None]+[False]*problem['nv'];a,b,c=(point[k]for k in ['a','b','c']);width=problem['metadata']['width']
    for variables,mask in [(problem['a_variables'],a),(problem['b_variables'],b),(problem['c_variables'],c)]:
        for index,var in enumerate(variables):values[var]=bool(mask>>index&1)
    matrix=pair_column(a,b,width)
    for bit,var in enumerate(problem['gates']):values[var]=bool(matrix>>bit&1)
    for ell,var in zip(problem['annihilator'],problem['aux_variables']):values[var]=bool((ell&c).bit_count()%2)
    return values


def validate_decode(problem,assignment,assumptions=()):
    if (not isinstance(assignment,(list,tuple)) or len(assignment)!=problem['nv']+1
            or any(type(x)is not bool for x in assignment[1:])):raise AssertionError('incomplete/nonboolean point assignment')
    if any(assignment[abs(lit)]!=(lit>0)for lit in assumptions):raise AssertionError('point assumption violation')
    if any(not any(assignment[abs(lit)]==(lit>0)for lit in row)for row in problem['clauses']):raise AssertionError('point CNF violation')
    if any(bool(sum(assignment[v]for v in row)%2)!=rhs for row,rhs in problem['xors']):raise AssertionError('point XOR violation')
    point={key:sum(int(assignment[v])<<i for i,v in enumerate(problem[key+'_variables']))for key in ['a','b','c']}
    validate_point(problem['family'],problem['coefficients'],point)
    return point,dict(valid=True,matrix_entries_checked=problem['metadata']['matrix_equations'],
                      strict_rank_increase=True,lambda_parity_zero=True,full_MM_certificate=False)


def solve_oracle(problem,seconds=20,conflicts=10000000,memory_mb=1536,options=None,log_path=None,cancelled=None):
    options={}if options is None else dict(options)
    requested=options.get('seed','0')
    if (type(requested)not in (int,str) or isinstance(requested,str)and not requested.isdecimal()
            or int(requested)<0):raise ValueError('solver seed must be a nonnegative integer')
    requested_seed=int(requested);modulus=2147483647;solver_seed=requested_seed%modulus
    options['seed']=str(solver_seed)
    original=lifecycle.solve
    private=types.FunctionType(original.__code__,dict(original.__globals__,validate_decode=validate_decode),
                               original.__name__,original.__defaults__,original.__closure__)
    result=private(problem,seconds=seconds,conflicts=conflicts,memory_mb=memory_mb,
                   options=options,log_path=log_path,cancelled=cancelled)
    result.update(requested_seed=requested_seed,solver_seed=solver_seed,solver_seed_modulus=modulus)
    if result['status']=='LOCAL_UNSAT':result['status']='HYPERPLANE_SPAN_UNSAT'
    if result['status']=='SAT':result['point']=result.pop('candidate')
    return result


def decode_containment(family,points):
    coefficients,pairs=state_vectors(family,points);source=family['source'];width=source['width']
    if not contained(family,coefficients):raise ValueError('target W is outside U')
    rows=[0]*len(coefficients)
    for bit,w in enumerate(source['W_columns']):
        representation=coordinates(coefficients,w)
        if combine(coefficients,representation)!=w:raise AssertionError('C*D=W verification failed')
        for r in bits(representation):rows[r]|=1<<bit
    if source['kind']=='linear-control':
        return dict(pairs=[list(p)for p in pairs],free_rows=rows),dict(valid=True,full_MM_certificate=False,rank=sum(bool(w)for w in rows))
    terms=[];axis=source['free_axis'];other=source['other_axes']
    for pair,w in zip(pairs,rows):
        if not w:continue
        term=[0]*3;term[axis]=w;term[other[0]]=pair[0];term[other[1]]=pair[1];terms.append(tuple(term))
    candidate=encode_candidate(terms,source['dimension'],method='rank-one-hyperplane-span42',
                  family_sha256=family['family_sha256'],physical_H_sha256=family['physical_H_sha256'],
                  free_axis=axis,coefficient_basis=coefficients,free_rows=rows,scope=family['scope'])
    report=verify_candidate(candidate,random_trials=0)
    if not report['valid'] or report['rank']>len(coefficients) or len(coefficients)>source['R']-1:
        raise AssertionError('full tensor decode or product bound failed')
    return candidate,report


def weight_four_lambdas(source,limit=16):
    values=source['W_rows'];groups={};seen=set();result=[]
    for i in range(len(values)):
        for j in range(i+1,len(values)):
            key=values[i]^values[j]
            if key:groups.setdefault(key,[]).append((i,j))
    for key in sorted(groups):
        pairs=groups[key]
        for x,(i,j)in enumerate(pairs):
            for k,l in pairs[x+1:]:
                support=tuple(sorted([i,j,k,l]))
                if len(set(support))!=4 or support in seen:continue
                seen.add(support)
                if len(linear_basis([values[t]for t in support]))!=3:continue
                lam=sum(1<<t for t in support)
                if any((lam&w).bit_count()%2 for w in source['W_columns']):raise AssertionError('pair collision lambda failed')
                result.append(lam)
                if len(result)>=limit:return result
    return result
