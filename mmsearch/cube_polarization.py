"""Exact cyclic cube polarization and simultaneous GL conjugation over F2.

Distinct from a longer flip walk: explicitly changes the fixed-cube profile.
"""
from __future__ import annotations

from itertools import combinations
import random

from .search import _rotations, _toggle, is_cyclic


def orbit_inventory(terms):
    terms = set(terms)
    if not is_cyclic(terms):
        raise ValueError("orbit inventory requires cyclic closure")
    return dict(fixed_cube_masks=sorted(a for a,b,c in terms if a == b == c),
                three_cycle_representatives=[list(t) for t in sorted(terms)
                    if not t[0] == t[1] == t[2] and t == min(_rotations(t))])


def polarize_cubes(terms, a, b):
    """Replace a^3+b^3 by (a+b)^3+C3(a,a,b)+C3(a,b,b).

    All tensor factors are exact integer masks, with F2 cancellation. Input
    cubes must exist and be distinct. The identity adds at most five terms.
    """
    result = set(terms)
    if type(a) is not int or type(b) is not int or not a or not b or a == b:
        raise ValueError("two distinct nonzero integer cube factors are required")
    if (a,a,a) not in result or (b,b,b) not in result:
        raise ValueError("requested fixed cubes are absent")
    for term in ((a,a,a),(b,b,b),(a^b,a^b,a^b),*_rotations((a,a,b)),*_rotations((a,b,b))):
        _toggle(result,term)
    return result


def conjugate_terms(terms, n, i, j):
    """Simultaneous involutory conjugation of all factors by I+E[j,i].

    This is a trace-tensor automorphism preserving cyclic closure, rank, and
    fixed-cube count. It changes coordinates of the polarized search seed.
    """
    if not 0 <= i < n or not 0 <= j < n or i == j:
        raise ValueError("distinct valid conjugation indices required")
    def transform(mask):
        value = mask ^ (((mask >> (i*n)) & ((1<<n)-1)) << (j*n))
        return value ^ sum(((value >> (r*n+j)) & 1) << (r*n+i) for r in range(n))
    return {tuple(transform(mask) for mask in term) for term in terms}


def polarized_seeds(terms, n, *, conjugates=0, seed=0):
    """Yield all fixed-cube pairs, plus bounded randomized conjugate variants."""
    terms = set(terms)
    if not is_cyclic(terms):
        raise ValueError("cube-polarization portfolio requires a cyclic seed")
    if type(conjugates) is not int or not 0 <= conjugates <= 64:
        raise ValueError("conjugates must be an integer in 0..64")
    cubes = sorted(a for a,b,c in terms if a == b == c)
    rng = random.Random(seed)
    seen = set()
    for a,b in combinations(cubes,2):
        current = polarize_cubes(terms,a,b)
        sequence = []
        for variant in range(conjugates+1):
            if variant:
                i,j = rng.sample(range(n),2)
                current = conjugate_terms(current,n,i,j)
                sequence.append([i,j])
            key = tuple(sorted(current))
            if key not in seen:
                seen.add(key)
                yield current.copy(), dict(cube_pair=[a,b], conjugations=list(sequence),
                                           initial_rank=len(terms), polarized_rank=len(current))
