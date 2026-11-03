"""Necessary binary CP bound from the span of low-rank slice matrices.

This module does not decide CP existence. It never constructs a CP candidate,
uses a solver, or dispatches a campaign query.
"""
import hashlib
import json
import math
import time

from .compact_sat import BinaryBasis
from .compact_rank2_edges43 import matrix_rank_at_most_two


SCOPE = ('Necessary condition for this exact F2 matrix slice image only; '
         'NOT_EXCLUDED is not an existence certificate or global rank claim.')


def required_rank2_span(image_rank, surplus):
    """If CP <= d+c, rank(span{M in S: rank(M)<=2}) >= max(0,d+c+1-2**c)."""
    if (type(image_rank) is not int or image_rank < 0
            or type(surplus) is not int or surplus < 0):
        raise ValueError('literal nonnegative image rank and surplus required')
    total = image_rank + surplus + 1
    # Avoid constructing a huge 2**c when the bound is already vacuous.
    if surplus >= total.bit_length():
        return 0
    return max(0, total - (1 << surplus))


def classify_pair_image(targets, left_width, right_width, budget, *,
                        max_vectors=65535, seconds=None, cancelled=None,
                        clock=time.monotonic):
    """Test only the necessary rank<=2-span condition for the actual slice image.

    A low-rank witness basis can establish NOT_EXCLUDED before enumeration ends.
    EXCLUDED by span deficiency requires every nonzero matrix of S. Caps and
    cooperative wall/cancellation stops return UNKNOWN unless the condition has
    already been decided before the stop. Time is checked again after each rank
    calculation and at return; it does not preempt one matrix rank calculation.
    """
    started = clock()
    targets = list(targets)
    if (type(left_width) is not int or type(right_width) is not int
            or min(left_width, right_width) < 0
            or type(budget) is not int or budget < 0
            or type(max_vectors) is not int or max_vectors < 0
            or any(type(value) is not int or value < 0
                   or value.bit_length() > left_width*right_width for value in targets)):
        raise ValueError('invalid literal binary matrix image or resource bound')
    if (seconds is not None and (type(seconds) not in (int, float)
            or not math.isfinite(seconds) or seconds < 0)):
        raise ValueError('seconds must be None or finite and nonnegative')
    space = BinaryBasis(targets)
    d = len(space.vectors)
    surplus = budget - d
    required = required_rank2_span(d, surplus) if surplus >= 0 else None
    fingerprint = hashlib.sha256(json.dumps(
        {'shape': [left_width, right_width], 'raw_targets_hex': [hex(v) for v in targets]},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    identity = dict(image_rank=d, budget=budget, surplus=surplus,
                    required_rank2_span=required, shape=[left_width, right_width],
                    raw_target_sha256=fingerprint, space_basis_hex=[hex(v) for v in space.vectors],
                    algorithm='necessary_rank_at_most_two_span_bound', scope=SCOPE,
                    existence_claim=False)
    scanned = 0
    pivots, witness = {}, []
    rank_classes = {'rank1': 0, 'rank2': 0, 'rank_at_least3': 0}

    def stop_reason():
        if cancelled is not None and cancelled():
            return 'cancelled'
        if seconds is not None and clock()-started >= seconds:
            return 'wall_budget'
        return None

    def finish(status, case, enumeration_complete=False):
        reason = stop_reason()
        if reason:
            status, case = 'UNKNOWN', reason
        elapsed = clock()-started
        if seconds is not None and elapsed >= seconds:
            status, case = 'UNKNOWN', 'wall_budget'
        exact_rank = (len(witness) if enumeration_complete
                      and sum(rank_classes.values()) == scanned else None)
        return dict(identity, status=status, case=case, complete=status != 'UNKNOWN',
                    enumeration_complete=enumeration_complete,
                    excludes_budget=True if status == 'EXCLUDED' else
                                    False if status == 'NOT_EXCLUDED' else None,
                    enumerated_vectors=scanned, rank2_span_rank=exact_rank,
                    observed_rank2_span_rank=len(witness),
                    rank_classes=rank_classes, low_rank_witness=witness,
                    elapsed_seconds=elapsed)

    reason = stop_reason()
    if reason:
        return finish('UNKNOWN', reason)
    if budget < d:
        return finish('EXCLUDED', 'flattening_rank_exceeds_budget')
    if required == 0:
        return finish('NOT_EXCLUDED', 'vacuous_necessary_bound', not d)

    count = (1 << d)-1
    value = coordinates = 0
    for step in range(1, min(count, max_vectors)+1):
        reason = stop_reason()
        if reason:
            return finish('UNKNOWN', reason)
        toggle = (step & -step).bit_length()-1
        value ^= space.vectors[toggle]
        coordinates ^= 1 << toggle
        rank, _ = matrix_rank_at_most_two(value, left_width, right_width)
        if rank not in (1, 2, 3):
            raise AssertionError('nonzero independent-space vector classified as zero')
        scanned += 1
        reason = stop_reason()
        if reason:
            return finish('UNKNOWN', reason, scanned == count)
        rank_classes['rank1' if rank == 1 else 'rank2' if rank == 2
                     else 'rank_at_least3'] += 1
        if rank in (1, 2):
            reduced = coordinates
            while reduced:
                pivot = reduced.bit_length()-1
                if pivot not in pivots:
                    pivots[pivot] = reduced
                    witness.append(dict(matrix_hex=hex(value), matrix_rank=rank,
                                        space_coordinates_hex=hex(coordinates)))
                    break
                reduced ^= pivots[pivot]
            if len(witness) >= required:
                return finish('NOT_EXCLUDED', 'necessary_span_witness', scanned == count)
    if scanned < count:
        return finish('UNKNOWN', 'vector_cap')
    return finish('EXCLUDED', 'complete_rank2_span_deficiency', True)
