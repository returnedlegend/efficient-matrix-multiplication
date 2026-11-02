"""Exact p1/p2 Koszul bounds for all ordered choices of the three modes."""
from __future__ import annotations

import itertools
import time

from .koszul import koszul_bounds
from .koszul_p2 import koszul_p2_bounds


def transpose_tensor(core, shape, permutation):
    if len(shape) != 3 or any(type(x) is not int or x < 0 for x in shape):
        raise ValueError('invalid tensor dimensions')
    if len(core) != shape[0]*shape[1]*shape[2] or any(type(x) is not int or x not in (0, 1) for x in core):
        raise ValueError('invalid binary core')
    if len(permutation) != 3 or any(type(x) is not int for x in permutation) or tuple(sorted(permutation)) != (0, 1, 2):
        raise ValueError('permutation must order all three distinct modes')
    dimensions = [shape[axis] for axis in permutation]
    values = []
    for a, b, c in itertools.product(*(range(size) for size in dimensions)):
        position = [0, 0, 0]
        for axis, value in zip(permutation, (a, b, c)):
            position[axis] = value
        i, j, k = position
        values.append(core[(i*shape[1]+j)*shape[2]+k])
    return values, dimensions


def orientation_bounds(core, shape, target=None, permutations=None,
                       max_dimension=14, max_rows=5000, max_columns=5000):
    started = time.monotonic()
    permutations = list(itertools.permutations(range(3))) if permutations is None else list(permutations)
    evaluations = []
    lower = 0
    decisive = None
    for permutation in permutations:
        transposed, dimensions = transpose_tensor(core, shape, permutation)
        first = koszul_bounds(transposed, dimensions, target=target, modes=(0,))
        entry = dict(first['bounds'][0], status='COMPUTED', orientation=list(permutation),
                     transposed_core_sha256=first['core_sha256'])
        lower = max(lower, entry['tensor_rank_lower_bound'])
        evaluations.append(entry)
        if target is not None and lower > target:
            decisive = entry
            break
        second = koszul_p2_bounds(transposed, dimensions, target=target, modes=(0,),
            max_dimension=max_dimension, max_rows=max_rows, max_columns=max_columns)
        for item in second['bounds']:
            evaluations.append(dict(item, orientation=list(permutation),
                                    transposed_core_sha256=first['core_sha256']))
        lower = max(lower, second['tensor_rank_lower_bound'])
        if target is not None and lower > target:
            decisive = next(item for item in reversed(evaluations)
                            if item.get('tensor_rank_lower_bound', 0) > target)
            break
    return dict(field=2, image_shape=list(shape), bounds=evaluations,
        orientations_requested=[list(p) for p in permutations], target=target,
        tensor_rank_lower_bound=lower, rejected=target is not None and lower > target,
        decisive=decisive, elapsed_seconds=time.monotonic()-started,
        scope='ordered-mode Koszul lower bounds on this local residual only; skipped p2 bounds imply no rejection')
