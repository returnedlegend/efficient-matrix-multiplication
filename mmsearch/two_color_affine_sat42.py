"""Coupled two-color affine replacement with arbitrary new F2 rank-one pairs."""
import types

from . import local_eliminated42sat as lifecycle
from .affine_slice_rank_sat42 import build_matrix_problem,matrix_rank
from .free_factor_kernel import pair_column
from .recombine import digest
from .search import encode_candidate
from .slice_compression import canonical_masks
from .verify import verify_candidate

COORDINATES=((1,0),(0,1),(1,1))


def independent_basis(columns):
    pivots={}
    for column in columns:
        value=column
        while value:
            bit=value.bit_length()-1
            if bit in pivots:value^=pivots[bit]
            else:pivots[bit]=value;break
    return pivots


def quotient_certificate(matrices,neutral_columns):
    pivots=independent_basis(neutral_columns);residuals=[]
    for matrix in matrices:
        value=matrix
        for bit in sorted(pivots,reverse=True):
            if value>>bit&1:value^=pivots[bit]
        residuals.append(value)
    rank=len(independent_basis(residuals))
    return dict(neutral_span_rank=len(pivots),augmented_span_rank=len(pivots)+rank,quotient_syndrome_rank=rank,
        syndrome_residuals_hex=[hex(value) for value in residuals],
        neutral_basis_hex={str(bit):hex(value) for bit,value in sorted(pivots.items())},
        monochrome_profiles_excluded=rank==2,
        lemma='All new monochrome contributions have one coordinate color direction. Modulo the neutral outer-product span, '
              'two independent matrix syndromes cannot lie on that one-dimensional color line.')


def build_coupled_problem(matrices,neutral_columns,width,profile):
    if (type(width) is not int or not 1<=width<=25 or len(matrices)!=2 or any(type(m) is not int or not 0<=m<1<<(width*width) for m in matrices) or
            any(type(column) is not int or not 0<=column<1<<(width*width) for column in neutral_columns) or
            len(profile)!=3 or any(type(count) is not int or count<0 for count in profile)):
        raise ValueError('invalid two-color matrices/profile')
    q=sum(profile);count=len(neutral_columns)
    if q>93:raise ValueError('explicit product-count resource cap93 exceeded')
    nv=2*count;z=list(range(1,nv+1));avars=[];bvars=[];cvars=[];clauses=[]
    def allocate(size):
        nonlocal nv
        values=list(range(nv+1,nv+size+1));nv+=size;return values
    for _ in range(q):
        av=allocate(width);bv=allocate(width);cv=allocate(width*width)
        avars.append(av);bvars.append(bv);cvars.append(cv)
        for i in range(width):
            for j in range(width):
                gate=cv[i*width+j]
                clauses.extend(([-av[i],-bv[j],gate],[av[i],-gate],[bv[j],-gate]))
    result=dict(nv=nv,z_variables=z,a_variables=avars,b_variables=bvars,c_variables=cvars,clauses=clauses,
                metadata=dict(width=width,allow_zero_factor_columns=True,full_rank_constraints=False,
                    term_permutation_constraints=False,solver_threads=1,checkpoint_policy='Frozen formulas and assumptions; solver rebuilt per attempt.'))
    z=result['z_variables'];z1=z[:count];z2=z[count:];colors=[color for color,n in enumerate(profile) for _ in range(n)]
    xors=[];clauses=list(result['clauses'])
    for channel in range(2):
        for bit in range(width*width):
            variables=[result['c_variables'][s][bit] for s,color in enumerate(colors) if COORDINATES[color][channel]]
            variables += [(z1 if channel==0 else z2)[g] for g,column in enumerate(neutral_columns) if column>>bit&1]
            rhs=bool(matrices[channel]>>bit&1)
            if variables:xors.append((variables,rhs))
            elif rhs:clauses.append([])
    result.update(clauses=clauses,xors=xors,matrices=list(matrices),neutral_columns=list(neutral_columns),
                  z1_variables=z1,z2_variables=z2,profile=list(profile),factor_colors=colors)
    result.pop('matrix',None)
    result['metadata'].update(encoding='coupled-two-color-unrestricted-affine-native-xor-42-v1',
        kind='two-matrix-control',new_products=q,color_profile=list(profile),neutral_terms=count,
        neutral_selector_bits=2*count,complete_matrix_equations=2*width*width,
        cnf_clauses=len(clauses),native_xors=len(xors),shared_product_gates=True,
        coupled_channel_equations=True,scope='Only this fixed two-color affine profile; no global rank bound.')
    result['metadata']['formula_sha256']=digest(dict(nv=result['nv'],clauses=clauses,xors=xors))
    result['quotient_certificate']=quotient_certificate(matrices,neutral_columns)
    return result


def build_problem(candidate,free_axis,d,e,profile):
    if type(free_axis) is not int or free_axis not in (0,1,2):raise ValueError('invalid free axis')
    terms,canonicalization=canonical_masks(candidate);n=candidate['dimension'];width=n*n
    if any(type(value) is not int or not 0<value<1<<width for value in (d,e)) or d==e:raise ValueError('dependent/invalid color basis')
    report=verify_candidate(candidate,random_trials=0)
    if not report['valid'] or report['exact_entries_checked']!=n**6:raise ValueError('invalid source certificate')
    palette=[d,e,d^e];selected=[term for term in terms if term[free_axis] in palette]
    neutral=[term for term in terms if term[free_axis] not in palette]
    if not selected or sum(profile)>len(selected):raise ValueError('invalid replacement count')
    others=[axis for axis in range(3) if axis!=free_axis];matrices=[0,0]
    for term in selected:
        color=palette.index(term[free_axis]);column=pair_column([term[axis] for axis in others],width)
        for channel,enabled in enumerate(COORDINATES[color]):
            if enabled:matrices[channel]^=column
    columns=[pair_column([term[axis] for axis in others],width) for term in neutral]
    result=build_coupled_problem(matrices,columns,width,profile)
    result.update(source_terms=[list(term) for term in terms],selected_terms=[list(term) for term in selected],
        neutral_terms=[list(term) for term in neutral],source_dimension=n,free_axis=free_axis,other_axes=others,palette=palette)
    result['metadata'].update(kind='full-matrix-multiplication',source_rank=len(terms),selected_count=len(selected),
        selected_color_counts=[sum(term[free_axis]==value for term in selected) for value in palette],
        free_axis=free_axis,other_axes=others,color_basis=[d,e],palette=palette,candidate_rank_bound=len(neutral)+sum(profile),
        source_canonical_sha256=digest(encode_candidate(terms,n)),source_verification=report,source_canonicalization=canonicalization,
        scope=f'Source {digest(encode_candidate(terms,n))}, axis {free_axis}, color span {palette}, profile {list(profile)} only. '
              'Neutral terms shift within the color span; new other-axis forms are unrestricted. No global rank92 UNSAT claim.')
    result['metadata']['family_sha256']=digest(dict(source_terms=result['source_terms'],free_axis=free_axis,
        palette=palette,profile=list(profile),matrices=matrices,neutral_columns=columns))
    return result


def validate_lift(problem,z1,z2,factors):
    count=len(problem['neutral_columns']);width=problem['metadata']['width']
    if len(z1)!=count or len(z2)!=count or any(type(value) is not bool for value in [*z1,*z2]):raise ValueError('invalid neutral color bits')
    if len(factors)!=sum(problem['profile']) or any(len(pair)!=2 or any(type(value) is not int or not 0<=value<1<<width for value in pair) for pair in factors):
        raise ValueError('invalid arbitrary factor columns')
    expected=list(problem['matrices']);actual=[0,0]
    for channel,z in enumerate((z1,z2)):
        for enabled,column in zip(z,problem['neutral_columns']):
            if enabled:expected[channel]^=column
    for color,pair in zip(problem['factor_colors'],factors):
        column=pair_column(pair,width)
        for channel,enabled in enumerate(COORDINATES[color]):
            if enabled:actual[channel]^=column
    if actual!=expected:raise ValueError('coupled matrix lift failed')
    return expected


def witness_assignment(problem,z1,z2,factors):
    validate_lift(problem,z1,z2,factors);assignment=[None]+[False]*problem['nv'];width=problem['metadata']['width']
    for variables,values in ((problem['z1_variables'],z1),(problem['z2_variables'],z2)):
        for variable,value in zip(variables,values):assignment[variable]=value
    for av,bv,cv,(a,b) in zip(problem['a_variables'],problem['b_variables'],problem['c_variables'],factors):
        for i,v in enumerate(av):assignment[v]=bool(a>>i&1)
        for j,v in enumerate(bv):assignment[v]=bool(b>>j&1)
        for i in range(width):
            for j in range(width):assignment[cv[i*width+j]]=bool((a>>i&1) and (b>>j&1))
    return assignment


def control_assumptions(problem):
    expected=problem['metadata']['selected_color_counts']
    if list(problem['profile'])!=expected:raise ValueError('source color/factor control requires original profile')
    factors=[]
    for color in range(3):
        factors += [[term[axis] for axis in problem['other_axes']] for term in problem['selected_terms']
                    if term[problem['free_axis']]==problem['palette'][color]]
    assignment=witness_assignment(problem,[False]*len(problem['neutral_columns']),[False]*len(problem['neutral_columns']),factors)
    return [v if value else -v for v,value in enumerate(assignment[1:],1)]


def validate_decode(problem,assignment,assumptions=()):
    if not isinstance(assignment,(list,tuple)) or len(assignment)!=problem['nv']+1 or any(type(v) is not bool for v in assignment[1:]):
        raise AssertionError('incomplete/non-Boolean model')
    if any(assignment[abs(lit)]!=(lit>0) for lit in assumptions):raise AssertionError('assumption violation')
    if any(not any(assignment[abs(lit)]==(lit>0) for lit in row) for row in problem['clauses']):raise AssertionError('AND/CNF violation')
    if any(bool(sum(assignment[v] for v in row)%2)!=rhs for row,rhs in problem['xors']):raise AssertionError('coupled XOR violation')
    z1=[assignment[v] for v in problem['z1_variables']];z2=[assignment[v] for v in problem['z2_variables']]
    factors=[(sum(int(assignment[v])<<i for i,v in enumerate(av)),sum(int(assignment[v])<<j for j,v in enumerate(bv)))
             for av,bv in zip(problem['a_variables'],problem['b_variables'])]
    matrices=validate_lift(problem,z1,z2,factors);width=problem['metadata']['width']
    if problem['metadata']['kind']=='two-matrix-control':return dict(z1=z1,z2=z2,factors=factors),dict(valid=True,matrix_entries_checked=2*width*width,
        channel_ranks=[matrix_rank(matrix,width) for matrix in matrices],full_MM_certificate=False)
    axis=problem['free_axis'];others=problem['other_axes'];palette=problem['palette'];terms=[]
    for term,s1,s2 in zip(problem['neutral_terms'],z1,z2):
        new=list(term);new[axis]^=(palette[0] if s1 else 0)^(palette[1] if s2 else 0)
        if not new[axis]:raise AssertionError('neutral factor vanished outside color span')
        terms.append(tuple(new))
    for pair,color in zip(factors,problem['factor_colors']):
        a,b=pair
        if not a or not b:continue
        term=[0]*3;term[axis]=palette[color];term[others[0]]=a;term[others[1]]=b;terms.append(tuple(term))
    canonical=set()
    for term in terms:
        if term in canonical:canonical.remove(term)
        else:canonical.add(term)
    candidate=encode_candidate(canonical,problem['source_dimension'],method='coupled-two-color-affine-replacement',
        family_sha256=problem['metadata']['family_sha256'],formula_sha256=problem['metadata']['formula_sha256'],
        free_axis=axis,palette=palette,color_profile=problem['profile'],new_rank_factors=factors,neutral_bits=[z1,z2],field_claim='F2 only')
    report=verify_candidate(candidate,random_trials=0)
    if not report['valid'] or report['exact_entries_checked']!=problem['source_dimension']**6 or report['rank']>problem['metadata']['candidate_rank_bound']:
        raise AssertionError('full tensor/product bound failed')
    return candidate,report


def solve(problem,seconds=30,conflicts=10000000,memory_mb=1536,assumptions=(),options=None,log_path=None,cancelled=None):
    original=lifecycle.solve;namespace=dict(original.__globals__,validate_decode=validate_decode)
    bounded=types.FunctionType(original.__code__,namespace,original.__name__,original.__defaults__,original.__closure__)
    result=bounded(problem,seconds=seconds,conflicts=conflicts,memory_mb=memory_mb,assumptions=assumptions,
        options=options,log_path=log_path,cancelled=cancelled)
    if result['status']=='LOCAL_UNSAT':result['status']='TWO_COLOR_PROFILE_UNSAT'
    if result['status']=='SAT' and problem['metadata']['kind']=='two-matrix-control':result['witness']=result.pop('candidate')
    return result
