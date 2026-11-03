"""Enumerate rank-one points in S=span(old active fixed-pair columns), over F2.

Distinct coefficients are blocked individually, not by their linear span.
UNSAT proves completeness only in S. Point caps/UNKNOWN never prove completeness.
"""
import types
from collections import defaultdict

from . import hyperplane_rankone42 as hp
from .sat import CNF


def source_identity(source):
    return hp.digest(dict(width=source['width'],A_columns=source['A_columns'],W_rows=source['W_rows'],
                          free_axis=source['free_axis'],target_sha256=source['target_sha256']))


def initial_points(source):
    if source['A_rank']!=source['R'] or len(hp.linear_basis(source['A_columns']))!=source['R']:
        raise ValueError('census requires A column rank R')
    return [dict(a=pair[0],b=pair[1],c=1<<i)for i,pair in enumerate(source['pairs'])]


def validate_point(source,point,known_coefficients=()):
    if not isinstance(point,dict)or set(point)!={'a','b','c'}:raise ValueError('point requires exactly a,b,c')
    a,b,c=(point[k]for k in ['a','b','c']);width=source['width'];R=source['R']
    if any(type(x)is not int for x in [a,b,c])or not 0<a<1<<width or not 0<b<1<<width or not 0<c<1<<R:
        raise ValueError('invalid census factor/coefficient masks')
    if c in known_coefficients:raise ValueError('repeated known coefficient point')
    if hp.combine(source['A_columns'],c)!=hp.pair_column(a,b,width):raise ValueError('rank-one point violates A*c=Q')
    return True


def validate_points(source,points,cap=4096):
    if not source['R']<=len(points)<=cap:raise ValueError('invalid known census size/cap')
    if points[:source['R']]!=initial_points(source):raise ValueError('old unit points must be preserved')
    known=set()
    for point in points:validate_point(source,point,known);known.add(point['c'])
    return known


def build_oracle(source,points,cap=4096):
    known=validate_points(source,points,cap);width=source['width'];R=source['R'];cnf=CNF()
    a=[cnf.variable()for _ in range(width)];b=[cnf.variable()for _ in range(width)];c=[cnf.variable()for _ in range(R)]
    gates=[cnf.conjunction([a[i],b[j]])for i in range(width)for j in range(width)]
    xors=[([gate]+[c[r]for r,col in enumerate(source['A_columns'])if col>>bit&1],False)
          for bit,gate in enumerate(gates)]
    cnf.clauses.extend([a,b])
    for point in points:cnf.clauses.append([-var if point['c']>>i&1 else var for i,var in enumerate(c)])
    formula=dict(nv=cnf.nv,clauses=cnf.clauses,xors=xors)
    return dict(**formula,source=source,known_coefficients=sorted(known),a_variables=a,b_variables=b,c_variables=c,gates=gates,
        metadata=dict(encoding='old-active-span-rankone-point-census42-v1',formula_sha256=hp.digest(formula),
          source_identity=source_identity(source),width=width,R=R,known_points=len(points),
          factor_bits=2*width,AND_gates=width*width,coefficient_bits=R,matrix_equations=width*width,
          block_clauses=len(points),block_clause_literals=len(points)*R,variables=cnf.nv,
          CNF_clauses=len(cnf.clauses),native_XOR_equations=len(xors),point_cap=cap,
          lambda_constraint=False,outside_span_constraint=False,individual_point_blocks=True,
          scope='All nonzero rank-one matrices in this fixed old active-pair span S only; never all matrix-multiplication algorithms.'))


def witness_assignment(problem,point):
    a,b,c=(point[k]for k in ['a','b','c']);values=[None]+[False]*problem['nv']
    for key,mask in [('a',a),('b',b),('c',c)]:
        for i,var in enumerate(problem[key+'_variables']):values[var]=bool(mask>>i&1)
    matrix=hp.pair_column(a,b,problem['source']['width'])
    for i,var in enumerate(problem['gates']):values[var]=bool(matrix>>i&1)
    return values


def validate_decode(problem,assignment,assumptions=()):
    if (not isinstance(assignment,(list,tuple))or len(assignment)!=problem['nv']+1
            or any(type(v)is not bool for v in assignment[1:])):raise AssertionError('incomplete/nonboolean census model')
    if any(assignment[abs(lit)]!=(lit>0)for lit in assumptions):raise AssertionError('census assumption violation')
    if any(not any(assignment[abs(lit)]==(lit>0)for lit in row)for row in problem['clauses']):raise AssertionError('census CNF violation')
    if any(bool(sum(assignment[v]for v in row)%2)!=rhs for row,rhs in problem['xors']):raise AssertionError('census XOR violation')
    point={key:sum(int(assignment[v])<<i for i,v in enumerate(problem[key+'_variables']))for key in ['a','b','c']}
    validate_point(problem['source'],point,set(problem['known_coefficients']))
    return point,dict(valid=True,matrix_entries_checked=problem['source']['width']**2,
                      new_coefficient_point=True,full_MM_certificate=False,census_complete=False)


def solve_oracle(problem,**kwargs):
    # Reuse v3's unchanged seed normalization and bounded worker lifecycle in a
    # private function namespace. No module-level monkey patch is performed.
    original=hp.solve_oracle
    private=types.FunctionType(original.__code__,dict(original.__globals__,validate_decode=validate_decode),
                               original.__name__,original.__defaults__,original.__closure__)
    result=private(problem,**kwargs)
    if result['status']=='HYPERPLANE_SPAN_UNSAT':result['status']='CENSUS_COMPLETE_UNSAT'
    return result


def common_factor_closure(source,points,cap=4096,max_rounds=4):
    points=[dict(point)for point in points];known=validate_points(source,points,cap);rounds=0;changed=True
    while changed and rounds<max_rounds and len(points)<cap:
        rounds+=1;changed=False;groups=defaultdict(list)
        for point in points:
            groups[0,point['a']].append((point['b'],point['c']))
            groups[1,point['b']].append((point['a'],point['c']))
        for (axis,fixed),vectors in sorted(groups.items()):
            basis={}
            for factor,coefficient in vectors:
                value=factor;witness=coefficient
                while value:
                    pivot=value.bit_length()-1
                    if pivot not in basis:basis[pivot]=(value,witness);break
                    old,c=basis[pivot];value^=old;witness^=c
                if not value and witness:raise AssertionError('same-factor dependence violates injective A')
            independent=[basis[p]for p in sorted(basis)]
            for mask in range(1,1<<len(independent)):
                value=c=0
                for index in hp.bits(mask):value^=independent[index][0];c^=independent[index][1]
                if c in known:continue
                point=dict(a=fixed if axis==0 else value,b=value if axis==0 else fixed,c=c)
                validate_point(source,point,known);points.append(point);known.add(c);changed=True
                if len(points)>=cap:break
            if len(points)>=cap:break
    return points,dict(rounds=rounds,known_points=len(points),new_points=len(points)-source['R'],
        closure_saturated=not changed,point_cap_reached=len(points)>=cap,census_complete=False,
        scope='Common-factor linear closure is only a verified point lower bound; saturation is not a complete rank-one census.')
