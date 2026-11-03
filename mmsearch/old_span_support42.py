"""Exact dictionary-support search C*Y=W inside one old active-pair span."""
import types

from . import free_factor_sat as ff
from . import hyperplane_rankone42 as hp
from . import rankone_census42 as rc

ORIENTATION={0:'vw',1:'wu',2:'uv'}


def coefficient_system(source,points):
    rc.validate_points(source,points)
    return dict(C_rows=[sum(1<<j for j,p in enumerate(points)if p['c']>>i&1)for i in range(source['R'])],
                W_rows=list(source['W_rows']),columns=[p['c']for p in points],
                rank=len(hp.linear_basis([p['c']for p in points])),
                point_order_sha256=hp.digest(points),source_identity=rc.source_identity(source))


def build_problem(candidate,source,points,target=92,max_formula_mb=640):
    coefficients=coefficient_system(source,points);others=source['other_axes'];axis=source['free_axis']
    dictionary=[]
    for point in points:
        term=[0,0,0];term[others[0]]=point['a'];term[others[1]]=point['b'];dictionary.append(tuple(term))
    system=ff.build_system(dictionary,source['dimension'],ORIENTATION[axis],baseline=candidate,
              provenance=dict(method='old-span-census-coefficient-support',point_catalog_sha256=hp.digest(points)))
    if system['metadata']['linear_rank']!=source['R']or coefficients['rank']!=source['R']:
        raise ValueError('dictionary lost full source coefficient span')
    # The existing encoder chooses cyclic pair order. Map every physical pair
    # back to the source's sorted other-axis convention before using its c label.
    bypair={(p['a'],p['b']):p['c']for p in points};labels=[]
    for pair in system['pairs']:
        labels.append(bypair[tuple(reversed(pair))if axis==1 else tuple(pair)])
    width=source['width'];A=source['A_columns']
    physical_columns=[hp.combine(A,c)for c in labels]
    # Check every one of the625 original fixed-pair coefficient rows and RHS.
    for i in range(width):
        for j in range(width):
            physical_bit=(j*width+i)if axis==1 else(i*width+j)
            expected=sum(1<<p for p,column in enumerate(physical_columns)if column>>physical_bit&1)
            if system['coefficients'][i*width+j]!=expected:raise AssertionError('physical coefficient row differs from A*C')
            expected_rhs=0
            for r,column in enumerate(A):
                if column>>physical_bit&1:expected_rhs^=source['W_rows'][r]
            if system['right_sides'][i*width+j]!=expected_rhs:raise AssertionError('physical target row differs from A*W')
    problem=ff.build_problem(system,rank=target,max_formula_mb=max_formula_mb)
    problem['coefficient_system']=dict(C_rows=[sum(1<<j for j,c in enumerate(labels)if c>>r&1)for r in range(source['R'])],
            W_rows=source['W_rows'],point_labels=labels,source_identity=rc.source_identity(source))
    problem['source_model']=source
    problem['metadata'].update(old_span_scope=True,coefficient_equivalence='A injective: A*C*Y=A*W iff C*Y=W',
            original_fixed_pair_cells_checked=width*width,source_A_rank=source['R'],
            point_catalog_sha256=hp.digest(points),source_free_axis=axis,
            scope='Only this verified rank-one point catalog in the chosen old active-pair span S; partial-catalog UNSAT is not a complete-S or global negative.')
    return problem


def validate_decode(problem,assignment,assumptions=()):
    if any(assignment[abs(lit)]!=(lit>0)for lit in assumptions):raise AssertionError('support assumption mismatch')
    candidate,report=ff.validate_decode(problem,assignment);coefficient=problem['coefficient_system'];width=problem['system']['metadata']['width']
    vectors=[sum(int(assignment[g*width+j+1])<<j for j in range(width))for g in range(len(coefficient['point_labels']))]
    for row,expected in zip(coefficient['C_rows'],coefficient['W_rows']):
        observed=0
        for g in hp.bits(row):observed^=vectors[g]
        if observed!=expected:raise AssertionError('support witness failed explicit C*Y=W')
    if not report['valid']or report['exact_entries_checked']!=problem['source_model']['dimension']**6:
        raise AssertionError('support witness failed full tensor verification')
    return candidate,report


def solve(problem,**kwargs):
    original=hp.solve_oracle
    private=types.FunctionType(original.__code__,dict(original.__globals__,validate_decode=validate_decode),
                               original.__name__,original.__defaults__,original.__closure__)
    result=private(problem,**kwargs)
    if result['status']=='HYPERPLANE_SPAN_UNSAT':result['status']='SUPPORT_CATALOG_UNSAT'
    if result['status']=='SAT':result['candidate']=result.pop('point')
    return result
