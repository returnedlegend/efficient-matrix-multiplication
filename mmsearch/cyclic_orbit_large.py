"""Size-guarded k=8..10 adapters reusing the frozen exact C3 encoder unchanged."""
from __future__ import annotations

import random

from .cyclic_orbit_sat import build_patch_problem,nonfixed_orbits
from .native_bridge import canonical_terms,term_set_sha256
from .search import _rotations,encode_candidate,is_cyclic,orbit_counts
from .verify import verify_candidate

DEFAULT_MAX_VARIABLES=150000
DEFAULT_MAX_CLAUSES=600000
DEFAULT_MAX_ESTIMATED_MEMORY_MB=1024


def encoding_estimate(d,slots,*,symmetry=True):
    """Conservative Python-build + serialization + solver RAM planning estimate.

    Native-XOR is assumed. Full d^3 monomials per slot upper-bound shared gates.
    Bytes are a planning estimate, not a measured or guaranteed memory bound.
    """
    if type(d) is not int or not 0<=d<=25 or type(slots) is not int or not 0<=slots<=9:
        raise ValueError('dimension must be 0..25 and slots 0..9')
    q=slots*d**3;factor_variables=3*slots*d
    symmetry_variables=(2*slots*d+2*slots*max(0,d-1)) if symmetry else 0
    symmetry_clauses=(2*slots*d+6*slots*max(0,d-1)) if symmetry else 0
    variables=factor_variables+q+symmetry_variables
    clauses=4*q+symmetry_clauses
    xors=(d**3+2*d)//3+(2*slots*d if symmetry else 0)
    # Conservative working allowance includes simultaneous Python clauses,
    # AND cache, JSON strings/bytes, fork/CMS overhead and parity literals.
    estimated_bytes=(256*1024**2+768*clauses+384*variables+128*xors
                     +32*slots*(d**3+2*d))
    return dict(variables=variables,cnf_clauses=clauses,native_xors=xors,
                estimated_memory_bytes=estimated_bytes,
                estimated_memory_mb=(estimated_bytes+1024**2-1)//1024**2,
                estimate_policy='Conservative planning estimate; not measured RAM. Native-XOR backend assumed.')


def guarded_patch_problem(patch,slots,*,n=5,symmetry=True,koszul=False,
                          max_variables=DEFAULT_MAX_VARIABLES,max_clauses=DEFAULT_MAX_CLAUSES,
                          max_estimated_memory_mb=DEFAULT_MAX_ESTIMATED_MEMORY_MB):
    if (type(max_variables) is not int or max_variables<1 or type(max_clauses) is not int or max_clauses<1
            or type(max_estimated_memory_mb) is not int or max_estimated_memory_mb<128):
        raise ValueError('positive variable/clause caps and memory estimate cap >=128 MB required')
    # Zero-slot probe computes the SAME shared basis/core and exact bounds,
    # but constructs no nonlinear gates for a nonzero patch.
    probe=build_patch_problem(patch,0,n=n,symmetry=symmetry,koszul=koszul)
    metadata=probe['metadata'];lower=metadata['tensor_rank_lower_bound']
    estimate=encoding_estimate(metadata['shared_dimension'],slots,symmetry=symmetry)
    limits=dict(max_variables=max_variables,max_clauses=max_clauses,
                max_estimated_memory_mb=max_estimated_memory_mb)
    reasons=[]
    if estimate['variables']>max_variables:
        reasons.append('estimated variables exceed cap')
    if estimate['cnf_clauses']>max_clauses:
        reasons.append('estimated clauses exceed cap')
    if estimate['estimated_memory_mb']>max_estimated_memory_mb:
        reasons.append('estimated working memory exceeds cap')
    if lower>3*slots or reasons:
        if lower<=3*slots:
            # No formula was encoded. Do not leave the zero-slot probe's
            # contradiction behind where it could be mistaken for local UNSAT.
            probe['clauses']=[];probe['xors']=[]
            metadata['formula_sha256']=None
        metadata.update(slots=slots,nominal_product_cap=3*slots,lower_bound_rejected=lower>3*slots,
                        skipped_too_large=bool(reasons) and lower<=3*slots,
                        encoding_status='BOUND_REJECTED' if lower>3*slots else 'NOT_ENCODED_SIZE_GUARD',
                        size_guard_reasons=reasons,encoding_estimate=estimate,size_guard_limits=limits)
        return probe
    problem=build_patch_problem(patch,slots,n=n,symmetry=symmetry,koszul=koszul)
    actual_reasons=[]
    if problem['nv']>max_variables or len(problem['clauses'])>max_clauses:
        actual_reasons.append('actual formula exceeds configured variable/clause cap')
    problem['metadata'].update(skipped_too_large=bool(actual_reasons),encoding_status='ENCODED',
                                size_guard_reasons=actual_reasons,encoding_estimate=estimate,size_guard_limits=limits)
    return problem


def choose_large_neighbor_orbits(terms,k,*,seed=0,anchor=None):
    reps=nonfixed_orbits(terms)
    if type(k) is not int or not 8<=k<=10 or k>len(reps):
        raise ValueError('large branch requires 8..10 existing nonfixed orbits')
    rng=random.Random(seed)
    anchor=rng.randrange(len(reps)) if anchor is None else anchor
    if type(anchor) is not int or not 0<=anchor<len(reps):
        raise ValueError('invalid anchor orbit')
    selected=[anchor]
    while len(selected)<k:
        def score(index):
            factors=set(reps[index]);shared=max(len(factors&set(reps[j])) for j in selected)
            overlap=max(sum((x&y).bit_count() for x in reps[index] for y in reps[j]) for j in selected)
            return (-shared,-overlap,index)
        selected.append(min((i for i in range(len(reps)) if i not in selected),key=score))
    return sorted(selected)


def build_large_repair(candidate,orbit_indices,*,koszul=False,symmetry=True,
                       max_variables=DEFAULT_MAX_VARIABLES,max_clauses=DEFAULT_MAX_CLAUSES,
                       max_estimated_memory_mb=DEFAULT_MAX_ESTIMATED_MEMORY_MB):
    terms=set(canonical_terms(candidate));n=candidate['dimension']
    report=verify_candidate(encode_candidate(terms,n),random_trials=0)
    if (n!=5 or len(terms)!=95 or not is_cyclic(terms) or orbit_counts(terms)['fixed_cubes']!=2
            or not report['valid'] or report['exact_entries_checked']!=15625):
        raise ValueError('large repair requires exact cyclic5x5 rank95 source with two fixed cubes')
    reps=nonfixed_orbits(terms);indices=list(orbit_indices)
    if (not 8<=len(indices)<=10 or len(set(indices))!=len(indices)
            or any(type(index) is not int or not 0<=index<len(reps) for index in indices)):
        raise ValueError('large repair requires 8..10 distinct valid orbit indices')
    slots=len(indices)-1
    patch={term for index in indices for term in _rotations(reps[index])}
    outside=terms-patch
    problem=guarded_patch_problem(patch,slots,n=n,koszul=koszul,symmetry=symmetry,
                                 max_variables=max_variables,max_clauses=max_clauses,
                                 max_estimated_memory_mb=max_estimated_memory_mb)
    problem['outside_terms']=sorted(outside)
    problem['metadata'].update(source_term_set_sha256=term_set_sha256(terms),source_rank=len(terms),
                               orbit_indices=indices,source_profile=orbit_counts(terms),
                               outside_term_set_sha256=term_set_sha256(outside),
                               global_nominal_rank_cap=len(outside)+3*slots,initial_verification=report)
    return problem
