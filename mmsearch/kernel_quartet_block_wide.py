"""Independent exact four-direction oracle using full-rank present-class bases.

An optimum's positively matched classes span all present classes: otherwise
an independent unmatched class can gain an observed value while preserving
every positive contribution. Thus only full-rank bases need be enumerated.
"""
from collections import Counter
from itertools import combinations, product
from math import prod

from .free_factor_kernel import decode_checked, pair_column
from .free_factor_kernel_wide import validate_circuit


def partition(supports):
    if len(supports) != 4:
        raise ValueError('requires four supports')
    sets = [set(s) for s in supports]
    result = [[] for _ in range(16)]
    for group in sorted(set.union(*sets)):
        result[sum(1 << i for i, support in enumerate(sets) if group in support)].append(group)
    return result


def binary_rank(rows):
    basis = {}
    for row in rows:
        while row:
            bit = row.bit_length()-1
            if bit not in basis:
                basis[bit] = row
                break
            row ^= basis[bit]
    return len(basis)


def constraint_solution(classes, values):
    rows = list(zip(classes, values))
    pivot = 0
    for bit in range(4):
        found = next((j for j in range(pivot, len(rows)) if rows[j][0] >> bit & 1), None)
        if found is None:
            continue
        rows[pivot], rows[found] = rows[found], rows[pivot]
        mask, value = rows[pivot]
        for j, (m, v) in enumerate(rows):
            if j != pivot and m >> bit & 1:
                rows[j] = m ^ mask, v ^ value
        pivot += 1
    if pivot != len(classes):
        raise ValueError('dependent quartet constraints')
    result = [0]*4
    for mask, value in rows:
        result[(mask & -mask).bit_length()-1] = value
    return tuple(result)


def frequencies(vectors, supports):
    return [Counter(vectors[g] for g in group) for group in partition(supports)]


def basis_workload(vectors, supports):
    counts = frequencies(vectors, supports)
    present = [s for s in range(1, 16) if counts[s]]
    rank = binary_rank(present)
    bases = [basis for basis in combinations(present, rank) if binary_rank(basis) == rank]
    return dict(present_rank=rank, present_classes=present, basis_count=len(bases),
                exact_rhs_assignments=sum(prod(len(counts[s]) for s in basis) for basis in bases),
                distinct_values=sum(len(c) for c in counts))


def optimize_quartet(vectors, s1, s2, s3, s4):
    counts = frequencies(vectors, (s1, s2, s3, s4))
    present = [s for s in range(1, 16) if counts[s]]
    rank = binary_rank(present)
    zeros = sum(c[0] for c in counts)
    best, move, candidates, basis_count, workload = zeros, (0, 0, 0, 0), 1, 0, 0
    for classes in combinations(present, rank):
        if binary_rank(classes) != rank:
            continue
        basis_count += 1
        workload += prod(len(counts[s]) for s in classes)
        for values in product(*(sorted(counts[s]) for s in classes)):
            x = constraint_solution(classes, values)
            score = 0
            for s in present:
                shifted = 0
                for bit in range(4):
                    if s >> bit & 1:
                        shifted ^= x[bit]
                score += counts[s][shifted]
            candidates += 1
            if score > best or (score == best and x < move):
                best, move = score, x
    return dict(d=move[0], e=move[1], f=move[2], g=move[3], score=best,
                initial_zeros=zeros, delta=zeros-best, candidate_count=candidates,
                present_rank=rank, basis_count=basis_count, exact_rhs_assignments=workload,
                upper_bound=sum(max(c.values(), default=0) for c in counts))


def apply_quartet(vectors, s1, s2, s3, s4, d, e, f, g):
    moved = list(vectors)
    for support, direction in zip((s1, s2, s3, s4), (d, e, f, g)):
        for index in support:
            moved[index] ^= direction
    return moved


def validate_quartet_solution(system, circuits, record):
    indices = [record[key] for key in ('circuit_i', 'circuit_j', 'circuit_k', 'circuit_l')]
    if any(type(i) is not int for i in indices) or not 0 <= indices[0] < indices[1] < indices[2] < indices[3] < len(circuits):
        raise ValueError('invalid native quartet indices')
    width = system['metadata']['width']
    move = [record[key] for key in ('d', 'e', 'f', 'g')]
    if any(type(x) is not int or not 0 <= x < 1 << width for x in move):
        raise ValueError('invalid native quartet masks')
    columns = [pair_column(pair, width) for pair in system['pairs']]
    supports = [circuits[i]['support'] for i in indices]
    for support in supports:
        validate_circuit(columns, support)
    optimum = optimize_quartet(system['baseline_vectors'], *supports)
    moved = apply_quartet(system['baseline_vectors'], *supports, *move)
    rank = sum(bool(w) for w in moved)
    if rank != sum(bool(w) for w in system['baseline_vectors'])+optimum['delta'] or rank != record['after_rank']:
        raise ValueError('native quartet disagrees with independent exact optimum')
    candidate, report = decode_checked(system, moved, dict(method='exact-wide-four-kernel-direction-block',
        indices=indices, directions=move, exact_block_optimum=optimum))
    return moved, candidate, report
