"""Exact three-direction blocks over GF(2), with an independent Python oracle.

For an optimum x, take a basis of the nonzero parity classes whose observed
values match s*x. Enumerating those at most three observed-value constraints
preserves every matched contribution. A solution with free parameters zero
therefore has score at least that optimum. Zero is an observed value too.
"""
from collections import Counter
from itertools import combinations, product

from .free_factor_kernel import decode_checked, pair_column
from .free_factor_kernel_wide import validate_circuit
from .kernel_pair_block import optimize_pair, single_optimum


def partition(s1, s2, s3):
    groups = [[] for _ in range(8)]
    supports = [set(s) for s in (s1, s2, s3)]
    for g in sorted(set.union(*supports)):
        groups[sum(1 << i for i, s in enumerate(supports) if g in s)].append(g)
    return groups


def constraint_solution(classes, values):
    """Solve at most three independent scalar-mask rows; free variables zero."""
    rows = list(zip(classes, values))
    pivot = 0
    for bit in range(3):
        found = next((j for j in range(pivot, len(rows)) if rows[j][0] >> bit & 1), None)
        if found is None:
            continue
        rows[pivot], rows[found] = rows[found], rows[pivot]
        mask, value = rows[pivot]
        for j, (m, v) in enumerate(rows):
            if j != pivot and m >> bit & 1:
                rows[j] = (m ^ mask, v ^ value)
        pivot += 1
    if pivot != len(classes):
        return None
    result = [0, 0, 0]
    for mask, value in rows:
        result[(mask & -mask).bit_length() - 1] = value
    return tuple(result)


def optimize_triple(vectors, s1, s2, s3):
    groups = partition(s1, s2, s3)
    counts = [Counter(vectors[g] for g in group) for group in groups]
    zeros = sum(c[0] for c in counts)
    best, move, considered = zeros, (0, 0, 0), 1
    present = [s for s in range(1, 8) if counts[s]]
    for size in range(1, 4):
        for classes in combinations(present, size):
            if constraint_solution(classes, (0,) * size) is None:
                continue
            for values in product(*(sorted(counts[s]) for s in classes)):
                x = constraint_solution(classes, values)
                score = sum(counts[s][(x[0] if s & 1 else 0) ^
                                      (x[1] if s & 2 else 0) ^
                                      (x[2] if s & 4 else 0)] for s in present)
                considered += 1
                if score > best or (score == best and x < move):
                    best, move = score, x
    return dict(d=move[0], e=move[1], f=move[2], score=best,
                initial_zeros=zeros, delta=zeros-best, candidate_count=considered,
                upper_bound=sum(max(c.values(), default=0) for c in counts),
                partition=groups)


def apply_triple(vectors, s1, s2, s3, d, e, f):
    moved = list(vectors)
    for support, direction in zip((s1, s2, s3), (d, e, f)):
        for g in support:
            moved[g] ^= direction
    return moved


def component_lower_bound(vectors, supports):
    """Exact delta if disconnected; otherwise safe class-frequency lower bound."""
    neighbors = [set(s) for s in supports]
    isolated = [i for i in range(3) if all(not (neighbors[i] & neighbors[j])
                                         for j in range(3) if i != j)]
    if isolated:
        i = isolated[0]
        j, k = [x for x in range(3) if x != i]
        return (single_optimum(vectors, supports[i])['delta'] +
                optimize_pair(vectors, supports[j], supports[k])['delta'])
    counts = [Counter(vectors[g] for g in group) for group in partition(*supports)]
    return sum(c[0] - max(c.values(), default=0) for c in counts)


def validate_triple_solution(system, circuits, record):
    indices = [record[key] for key in ('circuit_i', 'circuit_j', 'circuit_k')]
    if any(type(i) is not int for i in indices) or not 0 <= indices[0] < indices[1] < indices[2] < len(circuits):
        raise ValueError('invalid native triple indices')
    width = system['metadata']['width']
    move = [record[key] for key in ('d', 'e', 'f')]
    if any(type(x) is not int or not 0 <= x < 1 << width for x in move):
        raise ValueError('invalid native triple masks')
    columns = [pair_column(pair, width) for pair in system['pairs']]
    supports = [circuits[i]['support'] for i in indices]
    for support in supports:
        validate_circuit(columns, support)
    optimum = optimize_triple(system['baseline_vectors'], *supports)
    moved = apply_triple(system['baseline_vectors'], *supports, *move)
    rank = sum(bool(w) for w in moved)
    if rank != sum(bool(w) for w in system['baseline_vectors']) + optimum['delta'] or rank != record['after_rank']:
        raise ValueError('native triple disagrees with independent exact optimum')
    candidate, report = decode_checked(system, moved, dict(
        method='exact-wide-three-kernel-direction-block', indices=indices,
        directions=move, exact_block_optimum=optimum))
    return moved, candidate, report
