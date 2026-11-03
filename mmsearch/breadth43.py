"""Exact fixed-family mapping and deterministic diversity selection for pilots."""
from __future__ import annotations

from collections import Counter

from .free_factor_sat import satisfies
from .recombine import canonical_terms,digest


def binary_rank(values):
    basis={}
    for value in values:
        if type(value) is not int or value<0:raise ValueError('nonnegative strict integer vectors required')
        while value:
            pivot=(value&-value).bit_length()-1
            if pivot not in basis:basis[pivot]=value;break
            value^=basis[pivot]
    return len(basis)


def difference_rank(first,second):
    if len(first)!=len(second):raise ValueError('models must share the same ordered fixed pairs')
    return binary_rank(a^b for a,b in zip(first,second))


def matrix_rank(mask,dimension):
    if type(mask) is not int or type(dimension) is not int or dimension<1 or not 0<=mask<1<<(dimension*dimension):
        raise ValueError('invalid packed square matrix')
    return binary_rank((mask>>(r*dimension))&((1<<dimension)-1) for r in range(dimension))


def factor_histogram(terms,dimension):
    counts=Counter(tuple(matrix_rank(mask,dimension) for mask in term) for term in terms)
    return {'/'.join(map(str,key)):value for key,value in sorted(counts.items())}


def histogram_distance(first,second):
    return sum(abs(first.get(key,0)-second.get(key,0)) for key in set(first)|set(second))


def map_source(system,candidate,heldout_hashes=(),tested_term_hashes=(),tested_model_hashes=()):
    terms=canonical_terms(candidate);term_hash=digest(terms)
    basic=dict(term_hash=term_hash,canonical_rank=len(terms))
    if term_hash in heldout_hashes:return dict(basic,status='EXCLUDED_V43_HELDOUT')
    if term_hash in tested_term_hashes:return dict(basic,status='EXCLUDED_ALREADY_TESTED_MODEL')
    pair_map={tuple(pair):g for g,pair in enumerate(system['pairs'])}
    orientation=system['metadata']['mode_permutation']
    missing=set();vectors=[0]*len(pair_map)
    for term in terms:
        a,b,c=(term[axis] for axis in orientation)
        if (a,b) not in pair_map:missing.add((a,b))
        else:vectors[pair_map[a,b]]^=c
    if missing:return dict(basic,status='SKIPPED_NOT_IN_FAMILY',missing_fixed_pairs=[list(p) for p in sorted(missing)])
    model_hash=digest(vectors)
    if model_hash in tested_model_hashes:return dict(basic,status='EXCLUDED_ALREADY_TESTED_MODEL',model_sha256=model_hash)
    merged=sum(bool(v) for v in vectors)
    if len(terms)!=93 or merged!=93:return dict(basic,status='SKIPPED_NOT_RANK93',merged_rank=merged,model_sha256=model_hash)
    if not satisfies(system,vectors):raise AssertionError('source violates original full fixed-pair equations')
    return dict(basic,status='ELIGIBLE',vectors=vectors,model_sha256=model_hash,merged_rank=merged,
        factor_rank_histogram=factor_histogram(terms,candidate['dimension']))


def select_farthest(candidates,tested,count=4):
    if type(count) is not int or count<1 or len(candidates)<count or not tested:
        raise ValueError('enough candidates and a nonempty tested reference set required')
    remaining=list(candidates);references=list(tested);selected=[];trace=[]
    for step in range(count):
        scored=[]
        for candidate in remaining:
            ranks=[difference_rank(candidate['vectors'],other['vectors']) for other in references]
            hist=[histogram_distance(candidate['factor_rank_histogram'],other['factor_rank_histogram']) for other in references]
            score=(min(ranks),min(hist),sum(ranks),candidate['term_hash'])
            scored.append((score,candidate,ranks,hist))
        score,best,ranks,hist=max(scored,key=lambda item:item[0])
        selected.append(best);references.append(best);remaining.remove(best)
        trace.append(dict(step=step,term_hash=best['term_hash'],model_sha256=best['model_sha256'],
            minimum_difference_rank=score[0],minimum_histogram_l1=score[1],sum_difference_ranks=score[2],
            reference_difference_ranks=ranks,reference_histogram_l1=hist,
            ranking='maximize min rank_F2(Wcandidate-Wreference), then min joint factor-rank histogram L1, then rank sum, then lexical term hash',
            scored_candidates=[dict(term_hash=c['term_hash'],score=list(s),difference_ranks=r,histogram_l1=h)
                for s,c,r,h in sorted(scored,key=lambda item:item[0],reverse=True)]))
    return selected,trace
