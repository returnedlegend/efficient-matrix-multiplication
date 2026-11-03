"""Exact F2 compression of all terms sharing one factor by matrix rank.

Only a strict decrease in the number of rank-one terms is applied. Every
input, applied move, and final candidate receives independent full tensor
verification; no integer lift or novelty is asserted.
"""
from __future__ import annotations

from collections import defaultdict
import math
import time

from .recombine import digest, encode
from .verify import verify_candidate

AXES = ("u", "v", "w")


class InvalidCertificate(ValueError):
    def __init__(self, message, report=None):
        super().__init__(message)
        self.report = report


def canonical_masks(candidate):
    """Strict integer bits; zero products vanish and equal triples XOR-cancel."""
    if (not isinstance(candidate, dict) or type(candidate.get("dimension")) is not int or
            candidate["dimension"] < 1 or type(candidate.get("field")) is not int or candidate["field"] != 2 or
            not isinstance(candidate.get("terms"), list)):
        raise InvalidCertificate("positive dimension, field=2 and a terms array are required")
    width = candidate["dimension"]**2
    terms, zeros, duplicates = set(), 0, 0
    for term in candidate["terms"]:
        if not isinstance(term, dict) or set(term) != set(AXES):
            raise InvalidCertificate("each term must have exactly u, v, w")
        masks = []
        for axis in AXES:
            vector = term[axis]
            if (not isinstance(vector, list) or len(vector) != width or
                    any(type(x) is not int or x not in (0, 1) for x in vector)):
                raise InvalidCertificate("factor coordinates must be strict integer bits of dimension-squared length")
            masks.append(sum(x << i for i, x in enumerate(vector)))
        triple = tuple(masks)
        if not all(triple):
            zeros += 1
        elif triple in terms:
            terms.remove(triple)
            duplicates += 1
        else:
            terms.add(triple)
    return tuple(sorted(terms)), dict(input_terms=len(candidate["terms"]), zero_products_removed=zeros,
        duplicate_pairs_cancelled=duplicates, canonical_terms=len(terms))


def _validate_matrix(rows, width):
    if (type(width) is not int or width < 1 or not isinstance(rows, (list, tuple)) or
            any(type(row) is not int or row < 0 or row >> width for row in rows)):
        raise ValueError("matrix rows must be in-range integer bitmasks")


def _basis(rows):
    basis, pivots = [], {}
    for row in rows:
        residual = row
        while residual:
            pivot = residual.bit_length()-1
            if pivot in pivots:
                residual ^= basis[pivots[pivot]]
            else:
                pivots[pivot] = len(basis)
                basis.append(residual)
                break
    return basis, pivots


def factor_matrix(rows, width):
    """Return M=sum_j columns[j] outer row_basis[j], over exact GF2."""
    _validate_matrix(rows, width)
    basis, pivots = _basis(rows)
    coordinates = []
    for row in rows:
        residual = row
        coordinate = 0
        for pivot in sorted(pivots, reverse=True):
            if residual >> pivot & 1:
                index = pivots[pivot]
                coordinate ^= 1 << index
                residual ^= basis[index]
        if residual:
            raise AssertionError("row-basis coordinate expansion failed")
        coordinates.append(coordinate)
    columns = [sum(((coordinate >> j) & 1) << i for i, coordinate in enumerate(coordinates))
               for j in range(len(basis))]
    witness = dict(width=width, height=len(rows), rank=len(basis), row_basis=basis,
                   row_coordinates=coordinates, columns=columns)
    verify_factorization(rows, width, witness)
    return witness


def verify_factorization(rows, width, witness):
    """Reject incomplete/corrupt factor witnesses, including nonminimal ones."""
    _validate_matrix(rows, width)
    if not isinstance(witness, dict):
        raise AssertionError("factorization witness must be an object")
    rank = witness.get("rank")
    if (type(rank) is not int or rank < 0 or witness.get("width") != width or witness.get("height") != len(rows) or
            any(type(witness.get(key)) is not int for key in ("width", "height"))):
        raise AssertionError("factorization dimensions/rank are invalid")
    basis, coordinates, columns = (witness.get(key) for key in ("row_basis", "row_coordinates", "columns"))
    if (not all(isinstance(values, list) for values in (basis, coordinates, columns)) or
            len(basis) != rank or len(columns) != rank or len(coordinates) != len(rows) or
            any(type(row) is not int or not 0 < row < 1 << width for row in basis) or
            any(type(c) is not int or c < 0 or c >> rank for c in coordinates) or
            any(type(c) is not int or not 0 < c < 1 << len(rows) for c in columns)):
        raise AssertionError("factorization arrays are invalid")
    if len(_basis(rows)[0]) != rank or len(_basis(basis)[0]) != rank:
        raise AssertionError("factorization rank is not the exact matrix rank")
    for i, (row, coordinate) in enumerate(zip(rows, coordinates)):
        reconstructed = 0
        for j, basis_row in enumerate(basis):
            if coordinate >> j & 1:
                reconstructed ^= basis_row
            if bool(columns[j] >> i & 1) != bool(coordinate >> j & 1):
                raise AssertionError("factorization column/coordinate disagreement")
        if row != reconstructed:
            raise AssertionError("factorization does not reproduce every matrix entry")
    return True


def group_matrix(terms, axis, width):
    if type(axis) is not int or axis not in (0, 1, 2) or type(width) is not int or width < 1:
        raise ValueError("invalid axis or width")
    rows = [0]*width
    other = [a for a in range(3) if a != axis]
    for triple in terms:
        if (not isinstance(triple, (list, tuple)) or len(triple) != 3 or
                any(type(v) is not int or not 0 <= v < 1 << width for v in triple)):
            raise ValueError("terms must be exact in-range mask triples")
        left, right = (triple[a] for a in other)
        while left:
            bit = left & -left
            rows[bit.bit_length()-1] ^= right
            left ^= bit
    return rows


def propose_group(terms, axis, factor, width):
    """One-axis basis refactoring is exported only when product count drops."""
    rows = group_matrix(terms, axis, width)
    if type(factor) is not int or not 0 < factor < 1 << width or any(t[axis] != factor for t in terms):
        raise ValueError("all group terms must share the declared nonzero factor")
    witness = factor_matrix(rows, width)
    if witness["rank"] >= len(terms):
        return None
    other = [a for a in range(3) if a != axis]
    new_terms = []
    for column, row in zip(witness["columns"], witness["row_basis"]):
        term = [0, 0, 0]
        term[axis] = factor
        term[other[0]], term[other[1]] = column, row
        new_terms.append(tuple(term))
    proposal = dict(axis=axis, axis_name=AXES[axis], factor=factor,
        other_axes=other, matrix_rows=rows, factorization=witness,
        old_terms=[list(t) for t in sorted(terms)], new_terms=[list(t) for t in sorted(new_terms)],
        old_count=len(terms), new_count=len(new_terms))
    verify_proposal(proposal, width)
    return proposal


def verify_proposal(proposal, width):
    axis, factor = proposal["axis"], proposal["factor"]
    old, new = proposal["old_terms"], proposal["new_terms"]
    rows = group_matrix(old, axis, width)
    if (type(factor) is not int or not 0 < factor < 1 << width or
            any(t[axis] != factor for t in old+new) or proposal["matrix_rows"] != rows or
            proposal["old_count"] != len(old) or proposal["new_count"] != len(new) or len(new) >= len(old) or
            proposal["axis_name"] != AXES[axis] or proposal["other_axes"] != [a for a in range(3) if a != axis]):
        raise AssertionError("invalid compression proposal")
    witness = proposal["factorization"]
    verify_factorization(rows, width, witness)
    other = [a for a in range(3) if a != axis]
    expected = []
    for column, row in zip(witness["columns"], witness["row_basis"]):
        term = [0, 0, 0]
        term[axis] = factor
        term[other[0]], term[other[1]] = column, row
        expected.append(term)
    if sorted(new) != sorted(expected) or group_matrix(new, axis, width) != rows:
        raise AssertionError("replacement terms disagree with exact factorization")
    return True


def compress_candidate(candidate, seconds=120, stop_at_record=False):
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("positive finite time budget required")
    started = time.monotonic()
    deadline = started+seconds
    terms, canonicalization = canonical_masks(candidate)
    source_report = verify_candidate(candidate, random_trials=16)
    if not source_report["valid"]:
        raise InvalidCertificate("input failed independent exact tensor verification", source_report)
    dimension, width = candidate["dimension"], candidate["dimension"]**2
    metadata = dict(method="exact-F2-shared-factor-matrix-rank-compression",
        source_sha256=digest(candidate), field_claim="F2 only; no integer lift or novelty claim")
    current = encode(terms, dimension, metadata)
    canonical_report = verify_candidate(current, random_trials=16)
    if not canonical_report["valid"]:
        raise AssertionError("XOR canonicalization failed independent verification")
    moves, passes = [], 0
    stop_reason = "fixed point"
    first_record = bool(stop_at_record and dimension == 5 and len(terms) <= 92)
    while not first_record:
        passes += 1
        changed = False
        timed_out = False
        for axis in range(3):
            groups = defaultdict(list)
            for term in terms:
                groups[term[axis]].append(term)
            for factor, group in sorted(groups.items()):
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                if len(group) < 2:
                    continue
                proposal = propose_group(group, axis, factor, width)
                if proposal is None:
                    continue
                replacement = tuple(sorted([term for term in terms if term[axis] != factor]+
                                           [tuple(term) for term in proposal["new_terms"]]))
                updated = encode(replacement, dimension, metadata)
                report = verify_candidate(updated, random_trials=16)
                if not report["valid"]:
                    raise AssertionError("applied compression failed independent exact tensor verification")
                proposal.update(global_rank_before=len(terms), global_rank_after=len(replacement),
                    before_candidate_sha256=digest(current), after_candidate_sha256=digest(updated),
                    verification=report, pass_index=passes)
                moves.append(proposal)
                terms, current = replacement, updated
                changed = True
                if stop_at_record and dimension == 5 and len(terms) <= 92:
                    first_record = True
                    break
            if timed_out or first_record:
                break
        if first_record:
            break
        if timed_out:
            stop_reason = "time budget reached; no fixed-point claim"
            break
        if not changed:
            break
    if first_record:
        stop_reason = "first independently verified rank record; stop without further refactoring"
    final_report = verify_candidate(current, random_trials=16)
    if not final_report["valid"]:
        raise AssertionError("final compressed candidate failed independent verification")
    return dict(candidate=current, source_verification=source_report,
        canonical_verification=canonical_report, final_verification=final_report,
        canonicalization=canonicalization, moves=moves, passes=passes,
        source_rank=len(candidate["terms"]), canonical_rank=canonicalization["canonical_terms"],
        final_rank=len(terms), stop_reason=stop_reason, fixed_point=stop_reason == "fixed point",
        elapsed_seconds=time.monotonic()-started,
        winner_eligible=dimension == 5 and candidate["field"] == 2 and len(terms) <= 92,
        rank93_policy="research checkpoint only; no novelty claim")
