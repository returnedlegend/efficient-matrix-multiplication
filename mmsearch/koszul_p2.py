"""Optional exact p=2 Koszul bounds, with explicit cost-based skipping.

The map exterior^2(A) tensor B* -> exterior^3(A) tensor C has rank
binomial(dim(A)-1,2) on each nonzero rank-one tensor. Characteristic-two
exterior multiplication omits repeated indices and uses plus for all signs.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import time

from .sat_neighborhoods import gf2_rank


def koszul_p2_rows(core, shape, mode=0):
    if len(shape) != 3 or any(type(x) is not int or x < 0 for x in shape):
        raise ValueError('shape must have three nonnegative integer dimensions')
    if len(core) != math.prod(shape) or any(type(x) is not int or x not in (0, 1) for x in core):
        raise ValueError('core must have exactly the stated number of binary integer entries')
    if type(mode) is not int or mode not in (0, 1, 2):
        raise ValueError('invalid mode')
    other = [i for i in range(3) if i != mode]
    a, b, c = shape[mode], shape[other[0]], shape[other[1]]
    fibers = [[0]*c for _ in range(a)]
    position = [0, 0, 0]
    for i, j, k in itertools.product(range(a), range(b), range(c)):
        position[mode], position[other[0]], position[other[1]] = i, j, k
        x, y, z = position
        fibers[i][k] |= core[(x*shape[1]+y)*shape[2]+z] << j
    pairs = {pair: i for i, pair in enumerate(itertools.combinations(range(a), 2))}
    rows = []
    for triple in itertools.combinations(range(a), 3):
        blocks = [(i, pairs[tuple(j for j in triple if j != i)]) for i in triple]
        for k in range(c):
            row = 0
            for i, pair_index in blocks:
                row ^= fibers[i][k] << (pair_index*b)
            rows.append(row)
    return rows, math.comb(a, 2)*b, math.comb(a, 3)*c


def koszul_p2_bounds(core, shape, target=None, modes=(0, 1, 2),
                     max_dimension=14, max_rows=5000, max_columns=5000):
    started = time.monotonic()
    if len(shape) != 3 or any(type(x) is not int or x < 0 for x in shape):
        raise ValueError('invalid shape')
    if len(core) != math.prod(shape) or any(type(x) is not int or x not in (0, 1) for x in core):
        raise ValueError('invalid binary core')
    if any(type(x) is not int or x < 0 for x in (max_dimension, max_rows, max_columns)):
        raise ValueError('cost caps must be nonnegative integers')
    if any(type(mode) is not int or mode not in (0, 1, 2) for mode in modes):
        raise ValueError('invalid modes')
    def estimate(mode):
        other = [i for i in range(3) if i != mode]
        a, b, c = shape[mode], shape[other[0]], shape[other[1]]
        rows, columns = math.comb(a, 3)*c, math.comb(a, 2)*b
        return rows*columns, rows, columns, mode
    results = []
    lower = 0
    for _, row_count, column_count, mode in sorted(estimate(mode) for mode in modes):
        a = shape[mode]
        base = dict(mode=mode, exterior_degree=2, rows=row_count, columns=column_count,
                    rank_one_contribution=math.comb(max(0, a-1), 2))
        if a < 3 or a > max_dimension or row_count > max_rows or column_count > max_columns:
            reason = ('dimension below nontrivial p2 range' if a < 3 else
                      'dimension cap' if a > max_dimension else
                      'row cap' if row_count > max_rows else 'column cap')
            results.append(dict(base, status='SKIPPED', reason=reason))
            continue
        rows, columns, _ = koszul_p2_rows(core, shape, mode)
        rank = gf2_rank(rows)
        contribution = base['rank_one_contribution']
        bound = (rank+contribution-1)//contribution
        lower = max(lower, bound)
        results.append(dict(base, status='COMPUTED', matrix_rank=rank,
            tensor_rank_lower_bound=bound,
            matrix_sha256=hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()))
        if target is not None and lower > target:
            break
    return dict(field=2, exterior_degree=2, image_shape=list(shape), bounds=results,
        tensor_rank_lower_bound=lower, target=target, rejected=target is not None and lower > target,
        computed_modes=sum(x['status'] == 'COMPUTED' for x in results),
        skipped_modes=sum(x['status'] == 'SKIPPED' for x in results),
        cost_caps=dict(max_dimension=max_dimension, max_rows=max_rows, max_columns=max_columns),
        elapsed_seconds=time.monotonic()-started,
        scope='p2 lower bound on this selected residual only; skipped modes imply no rejection')
