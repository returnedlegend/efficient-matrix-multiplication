"""Exact characteristic-two p=1 Koszul flattening bounds for local tensors.

For T in A tensor B tensor C, the map A tensor B* -> exterior^2(A)
tensor C sends x tensor beta to sum_i (a_i wedge x) tensor beta(b_i)c_i.
For one nonzero product its rank is dim(A)-1. Rank subadditivity gives
rank(T) >= ceil(rank(Koszul(T))/(dim(A)-1)). In characteristic two wedge
signs coincide, but x wedge x remains zero: repeated indices are omitted.
All calculations below are exact GF2 bit operations; bounds concern T only.
"""
from __future__ import annotations

import itertools
import hashlib
import json
import time

from .sat_neighborhoods import gf2_rank


def koszul_p1_rows(core, shape, mode=0):
    """Bitset rows, columns indexed by (A-coordinate, B-coordinate)."""
    if len(shape) != 3 or any(type(x) is not int or x < 0 for x in shape):
        raise ValueError('shape must have three nonnegative integer dimensions')
    if len(core) != shape[0]*shape[1]*shape[2] or any(type(x) is not int or x not in (0, 1) for x in core):
        raise ValueError('core must have exactly the stated number of binary integer entries')
    if type(mode) is not int or mode not in (0, 1, 2):
        raise ValueError('mode must be 0, 1, or 2')
    other = [i for i in range(3) if i != mode]
    a, b, c = shape[mode], shape[other[0]], shape[other[1]]
    fibers = [[0]*c for _ in range(a)]
    position = [0, 0, 0]
    for i, j, k in itertools.product(range(a), range(b), range(c)):
        position[mode], position[other[0]], position[other[1]] = i, j, k
        x, y, z = position
        fibers[i][k] |= core[(x*shape[1]+y)*shape[2]+z] << j
    # The coefficient for output {i,j} is T_j on input i plus T_i on
    # input j; exterior diagonal terms are zero, including in characteristic 2.
    rows = [(fibers[j][k] << (i*b)) ^ (fibers[i][k] << (j*b))
            for i, j in itertools.combinations(range(a), 2) for k in range(c)]
    return rows, a*b, (a*(a-1)//2)*c


def koszul_bounds(core, shape, target=None, modes=(0, 1, 2)):
    started = time.monotonic()
    bounds = []
    for mode in modes:
        rows, columns, row_count = koszul_p1_rows(core, shape, mode)
        matrix_rank = gf2_rank(rows)
        contribution = max(0, shape[mode]-1)
        lower = (matrix_rank+contribution-1)//contribution if contribution else 0
        bounds.append(dict(mode=mode, exterior_degree=1, rows=row_count, columns=columns,
            matrix_rank=matrix_rank, rank_one_contribution=contribution, tensor_rank_lower_bound=lower,
            matrix_sha256=hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()))
    # Use actual unfolding ranks rather than ambient dimensions: this helper
    # also accepts non-concise tensors, including cancelling rank-one sums.
    unfoldings = [[0]*size for size in shape]
    for a, b, c in itertools.product(*(range(size) for size in shape)):
        if core[(a*shape[1]+b)*shape[2]+c]:
            unfoldings[0][a] |= 1 << (b*shape[2]+c)
            unfoldings[1][b] |= 1 << (a*shape[2]+c)
            unfoldings[2][c] |= 1 << (a*shape[1]+b)
    flattening_ranks = [gf2_rank(rows) for rows in unfoldings]
    lower = max([0]+flattening_ranks+[entry['tensor_rank_lower_bound'] for entry in bounds])
    return dict(field=2, arithmetic='exact GF2', image_shape=list(shape), bounds=bounds,
        flattening_ranks=flattening_ranks,
        core_sha256=hashlib.sha256(json.dumps(dict(shape=list(shape), core=core), separators=(',', ':')).encode()).hexdigest(),
        tensor_rank_lower_bound=lower, target=target,
        rejected=target is not None and lower > target,
        elapsed_seconds=time.monotonic()-started,
        scope='lower bound only for this selected residual tensor; no global matrix-multiplication rank bound')
