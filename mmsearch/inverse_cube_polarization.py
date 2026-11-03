"""Exact inverse binary cubic polarization, outside fixed-cube constraints."""
from __future__ import annotations

import math
import time

from .recombine import digest,encode
from .slice_compression import InvalidCertificate,canonical_masks
from .verify import verify_candidate


def rotations(term):
    a,b,c=term
    return ((a,b,c),(b,c,a),(c,a,b))


def identity(a,b,width):
    if (type(width) is not int or width<1 or type(a) is not int or type(b) is not int or
            not 0<a<1<<width or not 0<b<1<<width or a==b):
        raise ValueError('two distinct nonzero in-range exact integer masks required')
    c=a^b
    terms=tuple(sorted(((a,a,a),(b,b,b),(c,c,c),*rotations((a,a,b)),*rotations((a,b,b)))))
    if len(set(terms))!=9:raise AssertionError('polarization identity terms are not distinct')
    rows=[0]*(width*width)
    for u,v,w in terms:
        for i in range(width):
            if u>>i&1:
                for j in range(width):
                    if v>>j&1:rows[i*width+j]^=w
    if any(rows):raise AssertionError('cubic polarization fails exact coefficient identity')
    return terms


def patterns(terms,width):
    terms=set(terms);pairs=set()
    for term in terms:
        values=set(term)
        if len(values)==2:pairs.add(tuple(sorted(values)))
    for a,b in sorted(pairs):
        nine=identity(a,b,width);required={(a^b,a^b,a^b),*rotations((a,a,b)),*rotations((a,b,b))}
        if required<=terms:
            new=terms^set(nine)
            yield dict(a=a,b=b,c=a^b,identity_terms=[list(t) for t in nine],
                required_terms=[list(t) for t in sorted(required)],
                removed_terms=[list(t) for t in sorted(terms&set(nine))],
                added_terms=[list(t) for t in sorted(set(nine)-terms)],
                old_count=len(terms),new_count=len(new),rank_drop=len(terms)-len(new),
                coefficient_identity='all width^3 binary coefficients of the nine-term XOR are zero',
                scope='requires the complete cube plus both repeated-factor cyclic orbits; changes fixed-cube inventory')


def verify_move(terms,move,width):
    original=set(terms);a,b=move['a'],move['b'];nine=set(identity(a,b,width))
    required={(a^b,a^b,a^b),*rotations((a,a,b)),*rotations((a,b,b))}
    if (move['c']!=a^b or sorted(move['identity_terms'])!=sorted([list(t) for t in nine]) or
            sorted(move['required_terms'])!=sorted([list(t) for t in required]) or not required<=original):
        raise ValueError('incomplete or corrupt inverse-polarization pattern')
    new=original^nine
    if (move['old_count']!=len(original) or move['new_count']!=len(new) or
            move['rank_drop']!=len(original)-len(new) or move['rank_drop']<5 or
            sorted(move['removed_terms'])!=sorted([list(t) for t in original&nine]) or
            sorted(move['added_terms'])!=sorted([list(t) for t in nine-original])):
        raise ValueError('inverse-polarization toggle/count witness is corrupt')
    return tuple(sorted(new))


def compress_candidate(candidate,seconds=120,stop_at_record=True):
    if not math.isfinite(seconds) or seconds<=0:raise ValueError('positive finite budget required')
    started=time.monotonic();deadline=started+seconds
    terms,normalization=canonical_masks(candidate)
    source_report=verify_candidate(candidate,random_trials=16)
    if not source_report['valid']:raise InvalidCertificate('source failed independent exact tensor verification',source_report)
    n=candidate['dimension'];width=n*n
    metadata=dict(method='exact inverse F2 cubic polarization',source_sha256=digest(candidate),
        claim='rank93 checkpoint is not novel; no integer lift or rank lower-bound claim')
    current=encode(terms,n,metadata);canonical_report=verify_candidate(current,random_trials=16)
    if not canonical_report['valid']:raise AssertionError('canonicalization failed exact tensor verification')
    moves=[];stop_reason='no complete inverse pattern'
    while not(stop_at_record and n==5 and len(terms)<=92):
        if time.monotonic()>=deadline:stop_reason='budget reached; not exhaustive';break
        move=next(patterns(terms,width),None)
        if move is None:break
        updated_terms=verify_move(terms,move,width)
        updated=encode(updated_terms,n,metadata);report=verify_candidate(updated,random_trials=16)
        if not report['valid']:raise AssertionError('inverse polarization failed independent full tensor verification')
        move.update(before_candidate_sha256=digest(current),after_candidate_sha256=digest(updated),verification=report)
        moves.append(move);current,terms=updated,updated_terms
    if stop_at_record and n==5 and len(terms)<=92:stop_reason='first verified rank record; stop further changes'
    report=verify_candidate(current,random_trials=16)
    if not report['valid']:raise AssertionError('final inverse certificate failed independent verification')
    return dict(candidate=current,moves=moves,canonicalization=normalization,source_verification=source_report,
        canonical_verification=canonical_report,final_verification=report,source_rank=len(candidate['terms']),
        final_rank=len(terms),winner_eligible=n==5 and len(terms)<=92,stop_reason=stop_reason,
        elapsed_seconds=time.monotonic()-started,
        scope='explicit inverse-polarization pattern scan only; failure is not a rank lower bound or UNSAT')
