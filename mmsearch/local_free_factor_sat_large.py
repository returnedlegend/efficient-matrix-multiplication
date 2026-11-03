"""Larger nested local neighborhoods; reuse the reviewed exact SAT helpers.

Circuit unions select free groups only. Their vectors remain arbitrary in the
unchanged complete tensor formula. More local degrees of freedom do not show
that a lower-rank solution exists.
"""
from __future__ import annotations

import random

from .local_free_factor_sat import checked_circuits, local_assumptions, local_bound
from .recombine import digest
from .recombine_sat import bits


def neighborhoods(system, supports, *, seed=0, families=8, max_groups=256):
    """Nested, overlap-connected unions of 8,16,32,64 distinct circuits.

    Packed support and frontier sets keep the larger selection inexpensive.
    Prefer newly included baseline-active groups, then smaller support growth;
    seeded tie priorities diversify the roots and growth paths reproducibly.
    Every selected circuit adds at least one previously fixed group.
    """
    if not supports or not 1 <= families <= 64 or not 1 <= max_groups <= 256:
        raise ValueError('invalid large neighborhood limits')
    count = len(system['baseline_vectors'])
    if any(not support or any(type(g) is not int or not 0 <= g < count for g in support)
           for support in supports):
        raise ValueError('invalid circuit support')
    active = sum(1 << g for g,v in enumerate(system['baseline_vectors']) if v)
    masks = [sum(1 << g for g in support) for support in supports]
    adjacency = [0]*count
    for i, support in enumerate(supports):
        for g in support:
            adjacency[g] |= 1 << i
    rng = random.Random(seed)
    order = list(range(len(supports)))
    rng.shuffle(order)
    priorities = [0]*len(order)
    for priority,i in enumerate(order):
        priorities[i] = priority
    roots = [i for i in order if masks[i] & active]
    roots.sort(key=lambda i: -(masks[i] & active).bit_count())
    seen = set()
    for family,root in enumerate(roots[:families]):
        # Distinct family priorities avoid converging to the same growth path
        # when different roots belong to the same short-kernel component.
        family_order = list(range(len(supports)))
        rng.shuffle(family_order)
        family_priorities = [0]*len(family_order)
        for priority,i in enumerate(family_order):
            family_priorities[i] = priority
        selected = [root]
        selected_mask = 1 << root
        free = masks[root]
        if free.bit_count() > max_groups:
            continue
        frontier = 0
        for g in supports[root]:
            frontier |= adjacency[g]
        for size in (8,16,32,64):
            while len(selected) < size:
                best = None
                free_count = free.bit_count()
                for i in bits(frontier & ~selected_mask):
                    added = masks[i] & ~free
                    added_count = added.bit_count()
                    if not added_count or free_count+added_count > max_groups:
                        continue
                    score = (-(added & active).bit_count(), added_count, family_priorities[i])
                    if best is None or score < best[0]:
                        best = score,i,added
                if best is None:
                    break
                _,chosen,added = best
                selected.append(chosen)
                selected_mask |= 1 << chosen
                free |= added
                for g in bits(added):
                    frontier |= adjacency[g]
            if len(selected) != size:
                break
            groups = list(bits(free))
            key = tuple(groups)
            if key in seen:
                continue
            seen.add(key)
            yield dict(family=family,circuit_count=size,circuit_indices=list(selected),
                free_groups=groups,free_group_count=len(groups),
                baseline_active_in_free=(free & active).bit_count(),
                neighborhood_sha256=digest(groups),
                selection='nested overlap-connected 8/16/32/64 circuit unions; arbitrary free vectors on union')
