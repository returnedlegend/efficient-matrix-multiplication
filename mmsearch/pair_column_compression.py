"""Exact compression using only one candidate's active fixed-pair columns.

Full column rank in each orientation is a necessary condition for minimality,
never a sufficient condition or a global lower-bound proof.
"""
from __future__ import annotations

from collections import defaultdict
import math
import time

from .free_factor_sat import ORIENTATIONS, audit, bits, build_system, decode_vectors, satisfies
from .recombine import digest, encode
from .slice_compression import InvalidCertificate, canonical_masks
from .verify import verify_candidate


def validate_rref(system):
    """Check all original-row XOR proofs and full row-space equivalence."""
    rows = system["reduced"]["rows"]
    original, rhs = system["coefficients"], system["right_sides"]
    count, width = len(system["pairs"]), system["metadata"]["width"]
    if system["reduced"]["contradictions"] or len(original) != width**2 or len(rhs) != len(original):
        raise ValueError("consistent complete packed system required")
    pivots = []
    for coefficient, target, proof in rows:
        if (type(coefficient) is not int or not 0 < coefficient < 1 << count or
                type(target) is not int or not 0 <= target < 1 << width or
                type(proof) is not int or not 0 < proof < 1 << len(original)):
            raise ValueError("invalid RREF row or witness")
        actual_coefficient = actual_rhs = 0
        for index in bits(proof):
            actual_coefficient ^= original[index]
            actual_rhs ^= rhs[index]
        if (coefficient, target) != (actual_coefficient, actual_rhs):
            raise ValueError("RREF original-row XOR witness failed")
        pivots.append((coefficient & -coefficient).bit_length()-1)
    if len(set(pivots)) != len(rows) or system["reduced"]["rank"] != len(rows) or system["reduced"]["nullity"] != count-len(rows):
        raise ValueError("RREF rank or pivot metadata is incorrect")
    for i, (coefficient, _target, _proof) in enumerate(rows):
        if any(coefficient >> pivot & 1 for j, pivot in enumerate(pivots) if j != i):
            raise ValueError("rows are not reduced at every pivot")
    for coefficient, target in zip(original, rhs):
        for pivot, row in zip(pivots, rows):
            if coefficient >> pivot & 1:
                coefficient ^= row[0]
                target ^= row[1]
        if coefficient or target:
            raise ValueError("RREF does not reproduce the entire original packed system")
    return True


def pivot_solution(system):
    validate_rref(system)
    vectors = [0]*len(system["pairs"])
    for coefficient, rhs, _proof in system["reduced"]["rows"]:
        pivot = (coefficient & -coefficient).bit_length()-1
        vectors[pivot] = rhs
    if not satisfies(system, vectors):
        raise AssertionError("zero-free-column pivot assignment fails all packed PW=Y equations")
    if sum(bool(v) for v in vectors) > system["reduced"]["rank"]:
        raise AssertionError("pivot solution exceeds the exact pair-column rank")
    return vectors


def pair_merge(terms, dimension, orientation):
    permutation = ORIENTATIONS[orientation]
    groups = defaultdict(list)
    for term in terms:
        a, b, c = (term[axis] for axis in permutation)
        groups[a, b].append(c)
    merged, witnesses = [], []
    for pair, free_values in sorted(groups.items()):
        value = 0
        for free in free_values:
            value ^= free
        witnesses.append(dict(pair=list(pair), source_free_vectors=free_values, merged_free_vector=value))
        if value:
            term = [0, 0, 0]
            for axis, mask in zip(permutation, (*pair, value)):
                term[axis] = mask
            merged.append(tuple(term))
    merged = tuple(sorted(merged))
    return merged, dict(method="same-pair-XOR-merge", orientation=orientation,
        old_count=len(terms), new_count=len(merged), groups=witnesses)


def orientation_proposal(terms, dimension, orientation):
    """Factor the target through a basis of this active column set only."""
    system = build_system(terms, dimension, orientation, baseline=None)
    validate_rref(system)
    count, rank = len(system["pairs"]), system["reduced"]["rank"]
    if count != len(terms):
        raise ValueError("same-pair merges must precede active-column rank factorization")
    summary = dict(orientation=orientation, active_columns=count, pair_column_rank=rank,
        pair_column_nullity=count-rank)
    if rank == count:
        return None, summary
    vectors = pivot_solution(system)
    candidate = decode_vectors(system, vectors, dict(method="exact-F2-active-pair-column-basis-compression",
        field_claim="F2 only; no integer lift or global minimality claim"))
    proof = dict(method="active-pair-column-RREF-basis", orientation=orientation,
        old_count=len(terms), new_count=len(candidate["terms"]), coefficient_rank=rank,
        free_column_policy="all nonpivot free-factor vectors are zero; each pivot vector is its packed RREF RHS",
        output_free_vectors_hex=[hex(value) for value in vectors], system_audit=audit(system),
        lemma="a nonzero kernel direction and a support group's active free vector remove at least one term without activating an outside group")
    if len(candidate["terms"]) >= len(terms):
        raise AssertionError("dependent active columns failed to strictly reduce the number of products")
    return dict(candidate=candidate, proof=proof), summary


def compress_candidate(candidate, seconds=120, stop_at_record=False, max_active=100):
    if not math.isfinite(seconds) or seconds <= 0 or type(max_active) is not int or max_active < 1:
        raise ValueError("positive finite seconds and max-active are required")
    started = time.monotonic()
    deadline = started+seconds
    terms, canonicalization = canonical_masks(candidate)
    if len(terms) > max_active:
        raise ValueError("active source exceeds the explicit per-candidate column cap")
    source_report = verify_candidate(candidate, random_trials=16)
    if not source_report["valid"]:
        raise InvalidCertificate("source failed independent full tensor verification", source_report)
    dimension = candidate["dimension"]
    metadata = dict(method="exact-F2-active-pair-column-compression", source_sha256=digest(candidate),
        field_claim="F2 only; no integer lift, novelty at93, or global minimality claim")
    current = encode(terms, dimension, metadata)
    canonical_report = verify_candidate(current, random_trials=16)
    if not canonical_report["valid"]:
        raise AssertionError("canonicalization failed independent full tensor verification")
    moves, checks, passes = [], [], 0
    stop_reason = "fixed point in these three active-column factorizations"

    def record_reached():
        return stop_at_record and dimension == 5 and len(current["terms"]) <= 92

    first_record = record_reached()
    while not first_record:
        passes += 1
        changed = timed_out = False
        for orientation in ORIENTATIONS:
            if time.monotonic() >= deadline:
                timed_out = True
                break
            merged, merge_proof = pair_merge(terms, dimension, orientation)
            proposals = []
            if len(merged) < len(terms):
                proposals.append(dict(candidate=encode(merged, dimension, metadata), proof=merge_proof))
            # Apply the merge before constructing a matrix of active columns;
            # no ambient dictionary or inactive group can enter this matrix.
            for proposal in proposals:
                updated = proposal["candidate"]
                report = verify_candidate(updated, random_trials=16)
                if not report["valid"]:
                    raise AssertionError("same-pair merge failed independent full verification")
                proposal["proof"].update(before_candidate_sha256=digest(current), after_candidate_sha256=digest(updated), verification=report)
                moves.append(proposal["proof"])
                current, terms = updated, merged
                changed = True
                if record_reached():
                    first_record = True
                    break
            if first_record:
                break
            proposal, summary = orientation_proposal(terms, dimension, orientation)
            checks.append(dict(pass_index=passes, **summary))
            if proposal is None:
                continue
            updated = proposal["candidate"]
            report = verify_candidate(updated, random_trials=16)
            if not report["valid"] or report["rank"] > proposal["proof"]["coefficient_rank"]:
                raise AssertionError("active-column compression failed independent full tensor verification")
            proposal["proof"].update(before_candidate_sha256=digest(current), after_candidate_sha256=digest(updated), verification=report)
            moves.append(proposal["proof"])
            current, terms = updated, canonical_masks(updated)[0]
            changed = True
            if record_reached():
                first_record = True
                break
        if first_record:
            break
        if timed_out:
            stop_reason = "time budget reached; no fixed-point claim"
            break
        if not changed:
            break
    if first_record:
        stop_reason = "first independently verified rank record; stop without further changes"
    final_report = verify_candidate(current, random_trials=16)
    if not final_report["valid"]:
        raise AssertionError("final active-column certificate failed independent verification")
    return dict(candidate=current, source_verification=source_report, canonical_verification=canonical_report,
        final_verification=final_report, canonicalization=canonicalization, moves=moves,
        orientation_checks=checks, passes=passes, source_rank=len(candidate["terms"]),
        canonical_rank=canonicalization["canonical_terms"], final_rank=len(current["terms"]),
        stop_reason=stop_reason, fixed_point=not first_record and "time budget" not in stop_reason,
        winner_eligible=dimension == 5 and len(current["terms"]) <= 92,
        max_active=max_active, elapsed_seconds=time.monotonic()-started,
        scope="only these active pair-column factorizations; no global negative or minimality proof", rank93_policy="research checkpoint only")
