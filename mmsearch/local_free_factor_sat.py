"""Local assumptions and exact necessary bounds for an unchanged full tensor SAT.

The circuits choose neighborhoods only. Every free vector in a selected group
remains arbitrary, and all original global tensor equations remain in the SAT.
"""
from __future__ import annotations

import random

from .free_factor_sat import packed_rref, satisfies
from .recombine import digest
from .recombine_sat import bits


def checked_circuits(system, records):
    count = len(system['pairs'])
    supports = []
    for record in records:
        support = record['support']
        if (not isinstance(support, list) or not support or len(set(support)) != len(support)
                or any(type(g) is not int or not 0 <= g < count for g in support)):
            raise ValueError('invalid circuit support')
        mask = sum(1 << g for g in support)
        if any((row & mask).bit_count() % 2 for row in system['coefficients']):
            raise ValueError('supplied circuit is not in the full coefficient kernel')
        supports.append(frozenset(support))
    return supports


def local_assumptions(system, free_groups, *, fix_indicators=True):
    vectors = system['baseline_vectors']
    width, count = system['metadata']['width'], len(vectors)
    free = set(free_groups)
    if any(type(g) is not int or not 0 <= g < count for g in free):
        raise ValueError('free group outside pair dictionary')
    assumptions = []
    for g, vector in enumerate(vectors):
        if g in free:
            continue
        assumptions.extend(g*width+c+1 if vector >> c & 1 else -(g*width+c+1)
                           for c in range(width))
        if fix_indicators:
            y = count*width+g+1
            assumptions.append(y if vector else -y)
    return assumptions


def local_bound(system, free_groups, target):
    """Witnessed RREF lower bound, conditional on fixing every outside vector.

    Baseline feasibility makes the restricted RHS exactly the baseline's free
    contribution. Singleton RREF rows force complete vectors independently of
    all remaining free vectors, so their nonzero groups must stay active.
    """
    vectors = system['baseline_vectors']
    if not satisfies(system, vectors):
        raise ValueError('local bound requires a globally feasible baseline')
    groups = sorted(set(free_groups))
    if any(type(g) is not int or not 0 <= g < len(vectors) for g in groups):
        raise ValueError('free group outside pair dictionary')
    selected = sum(1 << g for g in groups)
    positions = {g: i for i, g in enumerate(groups)}
    coefficients, rhs = [], []
    for row in system['coefficients']:
        restricted = row & selected
        coefficient = value = 0
        for g in bits(restricted):
            coefficient |= 1 << positions[g]
            value ^= vectors[g]
        coefficients.append(coefficient)
        rhs.append(value)
    reduced = packed_rref(coefficients, rhs, len(groups), system['metadata']['width'])
    if reduced['contradictions']:
        raise AssertionError('feasible baseline produced contradictory local equations')
    fixed_active = sum(bool(v) for g, v in enumerate(vectors) if not (selected >> g & 1))
    forced = {groups[g]: vector for g, vector in reduced['forced'].items()}
    forced_nonzero = sum(bool(v) for v in forced.values())
    lower = fixed_active + forced_nonzero
    return dict(status='LOCAL_UNSAT_BOUND' if lower > target else 'BOUND_INCONCLUSIVE',
        classification='LOCAL_UNSAT' if lower > target else 'INCONCLUSIVE', target=target,
        free_groups=groups, free_group_count=len(groups), fixed_active=fixed_active,
        forced_nonzero=forced_nonzero, forced_zero=sum(not v for v in forced.values()),
        forced_vectors_hex={str(g): hex(v) for g, v in forced.items()}, lower_bound=lower,
        local_linear_rank=reduced['rank'], local_nullity=reduced['nullity'],
        restricted_rows_hex=[[hex(c),hex(r)] for c,r in zip(coefficients,rhs)],
        rref_rows_hex=[[hex(x) for x in row] for row in reduced['rows']],
        rref_layout='[local coefficients, packed free-vector RHS, XOR witness of original full row indices]',
        fixed_outside_vectors_sha256=digest([[g,v] for g,v in enumerate(vectors) if g not in positions]),
        scope='Only solutions on these full fixed pairs with every group outside free_groups fixed to its baseline vector; passing this bound is not existence evidence.')


def neighborhoods(system, supports, *, seed=0, families=32, max_groups=128):
    """Deterministic overlap-connected unions of 1,2,4,8,16 circuits."""
    if not supports or not 1 <= families <= 256 or not 1 <= max_groups <= 128:
        raise ValueError('invalid neighborhood limits')
    rng = random.Random(seed)
    active = {g for g,v in enumerate(system['baseline_vectors']) if v}
    adjacency = {}
    for i, support in enumerate(supports):
        for g in support:
            adjacency.setdefault(g, set()).add(i)
    roots = [i for i,s in enumerate(supports) if s & active]
    rng.shuffle(roots)
    # Favor roots touching several baseline terms, while retaining diverse ties.
    roots.sort(key=lambda i: -len(supports[i] & active))
    seen = set()
    for family, root in enumerate(roots[:families]):
        selected, free = [root], set(supports[root])
        frontier = set().union(*(adjacency[g] for g in free))
        for size in (1,2,4,8,16):
            while len(selected) < size:
                candidates = [i for i in frontier if i not in selected
                              and len(free | supports[i]) <= max_groups
                              and supports[i] - free]
                if not candidates:
                    break
                rng.shuffle(candidates)
                candidates.sort(key=lambda i: (-len((supports[i]-free) & active),
                                                len(supports[i]-free)))
                chosen = candidates[0]
                selected.append(chosen)
                added = supports[chosen]-free
                free.update(added)
                frontier.update(set().union(*(adjacency[g] for g in added)))
            if len(selected) != size:
                break
            key = tuple(sorted(free))
            if key in seen:
                continue
            seen.add(key)
            yield dict(family=family, circuit_count=size, circuit_indices=list(selected),
                free_groups=list(key), free_group_count=len(key),
                baseline_active_in_free=len(free & active),
                neighborhood_sha256=digest(list(key)),
                selection='overlap-connected circuit unions; arbitrary free vectors on union')
