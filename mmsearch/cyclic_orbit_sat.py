"""Exact C3 orbit-local repair in one shared GF2 factor subspace.

Local UNSAT freezes the chosen outside terms. It is never a global rank bound.
Zero orbits and fixed cubes are allowed in every mutable slot.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import multiprocessing as mp
import random
import time

from .compact_sat import BinaryBasis,lex_nondecreasing
from .native_bridge import canonical_terms,term_set_sha256
from .sat import CNF
from .sat_neighborhoods import gf2_rank
from .search import _outer,_rotations,_toggle,encode_candidate,is_cyclic,orbit_counts
from .verify import verify_candidate
from .xor_sat import XorCNF,validate_model as validate_formula_model


def tensor_mask(terms,width):
    result=0
    for term in terms:
        result^=_outer(term,width)
    return result


def core_flattening_ranks(core,d):
    rows=[[0]*d for _ in range(3)]
    for i,j,k in itertools.product(range(d),repeat=3):
        if core>>((i*d+j)*d+k)&1:
            rows[0][i]|=1<<(j*d+k)
            rows[1][j]|=1<<(i*d+k)
            rows[2][k]|=1<<(i*d+j)
    return [gf2_rank(values) for values in rows]


def build_patch_problem(patch_terms,slots,*,n=5,symmetry=True,use_bounds=True,koszul=False):
    """Encode an arbitrary cyclic patch; full source exactness is checked above.

    A single retraction onto span(all patch factors) applied in all three modes
    fixes the target and commutes with C3. Thus permitting zeros and cubes
    loses no ambient C3-slot solution under this compression.
    """
    if type(slots) is not int or slots<0 or type(n) is not int or not 1<=n<=5:
        raise ValueError('invalid slots or matrix dimension')
    patch=set()
    for term in patch_terms:
        if len(term)!=3 or any(type(x) is not int or not 0<=x<1<<(n*n) for x in term):
            raise ValueError('patch factors must be integer masks within dimension')
        _toggle(patch,tuple(term))
    if not is_cyclic(patch):
        raise ValueError('patch must contain complete cyclic orbits')
    basis=BinaryBasis(sorted({factor for term in patch for factor in term}))
    d=len(basis.vectors)
    projected=[]
    for term in sorted(patch):
        coords=tuple(basis.coordinates(factor,require_member=True) for factor in term)
        if tuple(basis.expand(value) for value in coords)!=term:
            raise AssertionError('shared basis did not exactly lift a source factor')
        projected.append(coords)
    core=tensor_mask(projected,d)
    flattening=core_flattening_ranks(core,d)
    lower=max(flattening,default=0)
    koszul_report=None
    if koszul:
        from .koszul import koszul_bounds
        koszul_report=koszul_bounds([(core>>i)&1 for i in range(d**3)],[d]*3,target=3*slots)
        lower=max(lower,koszul_report['tensor_rank_lower_bound'])
    bound_rejected=use_bounds and lower>3*slots
    cnf=XorCNF();variables=[]
    if bound_rejected:
        cnf.clauses.append([])
    else:
        for _ in range(slots):
            factors=[[cnf.variable() for _ in range(d)] for _ in range(3)]
            variables.append(factors)
            if symmetry:
                # Choose a cyclic rotation whose first factor is least. Do not
                # order V against W: a reflection is not a C3 symmetry.
                lex_nondecreasing(cnf,factors[0],factors[1])
                lex_nondecreasing(cnf,factors[0],factors[2])
        for i,j,k in itertools.product(range(d),repeat=3):
            if (i,j,k)!=min((i,j,k),(k,i,j),(j,k,i)):
                continue
            monomials=[]
            for factors in variables:
                for a,b,c in ((i,j,k),(k,i,j),(j,k,i)):
                    monomials.append(cnf.conjunction([factors[0][a],factors[1][b],factors[2][c]]))
            # XorCNF cancels duplicate monomials, including three equal cube
            # monomials, which leave one copy in characteristic two.
            cnf.parity(monomials,bool(core>>((i*d+j)*d+k)&1))
    formula=dict(nv=cnf.nv,clauses=cnf.clauses,xors=cnf.xors)
    metadata=dict(dimension=n,field=2,shared_basis=basis.vectors,shared_dimension=d,
                  slots=slots,nominal_product_cap=3*slots,patch_terms=sorted(patch),
                  patch_term_set_sha256=term_set_sha256(patch),core_hex=hex(core),
                  flattening_ranks=flattening,tensor_rank_lower_bound=lower,
                  lower_bound_rejected=bound_rejected,koszul=koszul_report,
                  symmetry='U<=lexV and U<=lexW' if symmetry else 'none',
                  zero_orbits_allowed=True,fixed_cubes_allowed=True,
                  formula_sha256=hashlib.sha256(json.dumps(formula,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                  scope='Only this chosen patch with its outside terms frozen; no global rank statement.')
    return dict(**formula,metadata=metadata,variables=variables,
                and_gate_variables=sorted(set(cnf.and_cache.values())))


def validate_decode_patch(problem,model):
    nv=problem['nv']
    if (not isinstance(model,(list,tuple)) or len(model)!=nv
            or any(type(lit) is not int or not 1<=abs(lit)<=nv for lit in model)
            or {abs(lit) for lit in model}!=set(range(1,nv+1))):
        raise AssertionError('incomplete or malformed C3 SAT model')
    validate_formula_model(problem,model)
    true={lit for lit in model if lit>0};basis=problem['metadata']['shared_basis']
    def lift(variables):
        value=0
        for index,var in enumerate(variables):
            if var in true:
                value^=basis[index]
        return value
    replacement=set()
    for factors in problem['variables']:
        term=tuple(lift(values) for values in factors)
        for item in _rotations(term):
            _toggle(replacement,item)
    metadata=problem['metadata'];n=metadata['dimension']
    if (len(replacement)>metadata['nominal_product_cap'] or not is_cyclic(replacement)
            or tensor_mask(replacement,n*n)!=tensor_mask(metadata['patch_terms'],n*n)):
        raise AssertionError('lifted C3 replacement failed exact patch identity or term cap')
    return replacement


def _worker(problem,seconds,conflicts,memory_mb,backend,sender):
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(memory_mb*1024**2,memory_mb*1024**2))
        resource.setrlimit(resource.RLIMIT_CPU,(math.ceil(seconds)+1,math.ceil(seconds)+2))
        if backend in ('auto','cryptominisat'):
            try:
                import pycryptosat
            except ImportError:
                if backend=='cryptominisat':
                    raise
            else:
                solver=pycryptosat.Solver(threads=1,verbose=0,time_limit=seconds,confl_limit=conflicts)
                if problem['nv']:
                    solver.add_clause([problem['nv'],-problem['nv']])
                for clause in problem['clauses']:
                    solver.add_clause(clause)
                for variables,rhs in problem['xors']:
                    solver.add_xor_clause(variables,rhs)
                status,assignment=solver.solve(time_limit=seconds,confl_limit=conflicts)
                model=[i if assignment[i] else -i for i in range(1,problem['nv']+1)] if status is True else None
                sender.send(dict(status='SAT' if status is True else 'UNSAT' if status is False else 'UNKNOWN',
                                 model=model,solver='CryptoMiniSat',version=pycryptosat.__version__))
                return
        from pysat.solvers import Cadical195
        # Translate only native parities; reuse the same exact shared AND gates.
        expanded=CNF();expanded.nv=problem['nv'];expanded.clauses=list(problem['clauses'])
        for variables,rhs in problem['xors']:
            expanded.parity(variables,rhs)
        with Cadical195() as solver:
            # This python-sat build indexes clause[0] in bootstrap_with and
            # cannot bootstrap an empty contradiction clause; add it directly.
            for clause in expanded.clauses:
                solver.add_clause(clause)
            if expanded.nv:
                solver.add_clause([expanded.nv,-expanded.nv])
            solver.conf_budget(conflicts)
            status=solver.solve_limited()
            model=[lit for lit in solver.get_model() if abs(lit)<=problem['nv']] if status is True else None
        sender.send(dict(status='SAT' if status is True else 'UNSAT' if status is False else 'UNKNOWN',
                         model=model,solver='CaDiCaL195'))
    except Exception as exc:
        sender.send(dict(status='ERROR',error=f'{type(exc).__name__}: {exc}'))
    finally:
        sender.close()


def solve_patch(problem,*,seconds=10,conflicts=100000,memory_mb=1536,backend='auto'):
    if (not math.isfinite(seconds) or seconds<=0 or type(conflicts) is not int or conflicts<1
            or type(memory_mb) is not int or memory_mb<128 or backend not in ('auto','cryptominisat','cadical')):
        raise ValueError('invalid solver budget/backend')
    if problem['metadata']['lower_bound_rejected']:
        return dict(status='LOWER_BOUND_REJECTED',tensor_rank_lower_bound=problem['metadata']['tensor_rank_lower_bound'],
                    nominal_product_cap=problem['metadata']['nominal_product_cap'],scope=problem['metadata']['scope'])
    context=mp.get_context('fork');receiver,sender=context.Pipe(duplex=False)
    process=context.Process(target=_worker,args=(problem,seconds,conflicts,memory_mb,backend,sender))
    started=time.monotonic();process.start();sender.close()
    try:
        if receiver.poll(max(0,seconds-(time.monotonic()-started))):
            try:
                result=receiver.recv()
            except EOFError:
                result=dict(status='ERROR',reason='solver exited without a result')
        else:
            result=dict(status='UNKNOWN',reason='wall-clock budget reached')
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=.5)
        if process.is_alive():
            process.kill();process.join()
        receiver.close()
    result.update(elapsed_seconds=time.monotonic()-started,scope=problem['metadata']['scope'])
    if result['status']=='SAT':
        replacement=validate_decode_patch(problem,result['model'])
        result['replacement_terms']=sorted(replacement)
        result['essential_replacement_terms']=len(replacement)
    return result


def nonfixed_orbits(terms):
    terms=set(terms)
    if not is_cyclic(terms):
        raise ValueError('complete cyclic closure required')
    return [term for term in sorted(terms) if not term[0]==term[1]==term[2] and term==min(_rotations(term))]


def choose_neighbor_orbits(terms,k,*,seed=0,anchor=None):
    reps=nonfixed_orbits(terms)
    if type(k) is not int or not 2<=k<=7 or k>len(reps):
        raise ValueError('choose 2..7 existing nonfixed orbits')
    rng=random.Random(seed)
    anchor=rng.randrange(len(reps)) if anchor is None else anchor
    if type(anchor) is not int or not 0<=anchor<len(reps):
        raise ValueError('invalid anchor orbit')
    selected=[anchor]
    while len(selected)<k:
        def score(index):
            a=set(reps[index]);shared=max(len(a&set(reps[j])) for j in selected)
            overlap=max(sum((x&y).bit_count() for x in reps[index] for y in reps[j]) for j in selected)
            return (-shared,-overlap,index)
        selected.append(min((i for i in range(len(reps)) if i not in selected),key=score))
    return sorted(selected)


def build_repair(candidate,orbit_indices,*,slots=None,symmetry=True,koszul=False,strict95=True):
    terms=set(canonical_terms(candidate));n=candidate['dimension']
    report=verify_candidate(encode_candidate(terms,n),random_trials=0)
    if not report['valid'] or not is_cyclic(terms):
        raise ValueError('source must be independently exact and cyclic')
    if strict95 and (n!=5 or len(terms)!=95 or orbit_counts(terms)['fixed_cubes']!=2):
        raise ValueError('repair branch requires an exact cyclic rank95 source with two fixed cubes')
    reps=nonfixed_orbits(terms);indices=list(orbit_indices)
    if (not 2<=len(indices)<=7 or len(set(indices))!=len(indices)
            or any(type(i) is not int or not 0<=i<len(reps) for i in indices)):
        raise ValueError('select 2..7 distinct valid orbit indices')
    slots=len(indices)-1 if slots is None else slots
    if type(slots) is not int or not 0<=slots<len(indices):
        raise ValueError('replacement slots must save at least one complete orbit')
    patch={term for index in indices for term in _rotations(reps[index])}
    outside=terms-patch
    problem=build_patch_problem(patch,slots,n=n,symmetry=symmetry,koszul=koszul)
    problem['outside_terms']=sorted(outside)
    problem['metadata'].update(source_term_set_sha256=term_set_sha256(terms),source_rank=len(terms),
                               orbit_indices=indices,source_profile=orbit_counts(terms),
                               outside_term_set_sha256=term_set_sha256(outside),
                               global_nominal_rank_cap=len(outside)+3*slots,
                               initial_verification=report)
    return problem


def validate_decode_global(problem,model):
    replacement=validate_decode_patch(problem,model)
    terms=set(problem['outside_terms'])
    for term in replacement:
        _toggle(terms,term)
    n=problem['metadata']['dimension']
    candidate=encode_candidate(terms,n,method='exact-C3-orbit-local-SAT',problem=problem['metadata'])
    report=verify_candidate(candidate,random_trials=0)
    if (not report['valid'] or not is_cyclic(terms)
            or len(terms)>problem['metadata']['global_nominal_rank_cap']):
        raise AssertionError('decoded C3 model failed independent global exact verification or rank cap')
    return candidate,report
