"""Exact GF2 multilinear-image compression for local tensor SAT.

Projecting each factor onto the three mode images of the residual tensor
preserves that tensor. Therefore a K-slot decomposition exists in the ambient
space iff one exists in these image bases. This is exact preprocessing, not a
support-conditioning assumption. Decoding expands to the original coordinates.
"""
from __future__ import annotations

import itertools

from .sat import CNF, _normalize, choose_active_terms
from .sat_neighborhoods import factor_masks
from .verify import verify_candidate


def bits(value):
    while value:
        bit = value & -value
        yield bit.bit_length()-1
        value ^= bit


class BinaryBasis:
    """Echelon basis and a linear coordinate projection defined on all vectors."""
    def __init__(self, vectors=()):
        self.vectors = []
        self.pivots = {}
        for vector in vectors:
            reduced = vector
            for pivot in sorted(self.pivots, reverse=True):
                if reduced >> pivot & 1:
                    reduced ^= self.vectors[self.pivots[pivot]]
            if reduced:
                pivot = reduced.bit_length()-1
                self.pivots[pivot] = len(self.vectors)
                self.vectors.append(reduced)

    def coordinates(self, vector, require_member=False):
        result = 0
        reduced = vector
        for pivot in sorted(self.pivots, reverse=True):
            if reduced >> pivot & 1:
                index = self.pivots[pivot]
                reduced ^= self.vectors[index]
                result ^= 1 << index
        if require_member and reduced:
            raise ValueError('vector is outside basis span')
        return result

    def expand(self, coordinates):
        result = 0
        for index in bits(coordinates):
            result ^= self.vectors[index]
        return result


def local_residual(source, selected):
    width = source['dimension']**2
    values = [0]*(width**3)
    masks = factor_masks(source)
    for index in selected:
        for a, b, c in itertools.product(*(bits(value) for value in masks[index])):
            values[(a*width+b)*width+c] ^= 1
    return values, masks


def image_bases(values, width):
    bases = []
    for axis in range(3):
        vectors = []
        other = [i for i in range(3) if i != axis]
        for b, c in itertools.product(range(width), repeat=2):
            vector = 0
            position = [0, 0, 0]
            position[other[0]], position[other[1]] = b, c
            for a in range(width):
                position[axis] = a
                i, j, k = position
                vector |= values[(i*width+j)*width+k] << a
            if vector:
                vectors.append(vector)
        bases.append(BinaryBasis(vectors))
    return bases


def compress_residual(source, selected):
    """Return exact image bases and compressed coefficients, checking expansion."""
    width = source['dimension']**2
    residual, masks = local_residual(source, selected)
    bases = image_bases(residual, width)
    shape = [len(basis.vectors) for basis in bases]
    core = [0]*(shape[0]*shape[1]*shape[2])
    for index in selected:
        coordinates = [basis.coordinates(vector) for basis, vector in zip(bases, masks[index])]
        for a, b, c in itertools.product(*(bits(value) for value in coordinates)):
            core[(a*shape[1]+b)*shape[2]+c] ^= 1
    # Explicitly check every original entry, including expected zeros, before
    # trusting the transformed constraints. This also tests projection/indexing.
    expanded = [0]*(width**3)
    for a, b, c in itertools.product(*(range(size) for size in shape)):
        if core[(a*shape[1]+b)*shape[2]+c]:
            for i, j, k in itertools.product(bits(bases[0].vectors[a]),
                    bits(bases[1].vectors[b]), bits(bases[2].vectors[c])):
                expanded[(i*width+j)*width+k] ^= 1
    if expanded != residual:
        raise AssertionError('multilinear image compression failed exact expansion')
    return bases, core, shape, masks


def lex_nondecreasing(cnf, left, right):
    """Constrain left <= right lexicographically, allowing ties and zero."""
    if len(left) != len(right):
        raise ValueError('lex vectors must have equal length')
    prefix_equal = None
    for a, b in zip(left, right):
        cnf.clauses.append(([-prefix_equal] if prefix_equal is not None else []) + [-a, b])
        equal = cnf.variable()
        cnf.parity([a, b, equal], 1)
        prefix_equal = equal if prefix_equal is None else cnf.conjunction([prefix_equal, equal])


def build_compact_cnf(candidate, rank=92, active_terms=None, drop_term=None,
                      support_mode='image', active_count=5, symmetry='none'):
    source = _normalize(candidate)
    if not verify_candidate(source, random_trials=0)['valid']:
        raise ValueError('compact encoding requires an exact source')
    if type(rank) is not int or rank < 1 or len(source['terms']) != rank+1:
        raise ValueError('source must have exactly rank+1 terms')
    if drop_term is None:
        drop_term = 0
    if type(drop_term) is not int or not 0 <= drop_term <= rank:
        raise ValueError('invalid deleted source index')
    if active_terms is None:
        active_terms = choose_active_terms(source, drop_term, active_count)
    active_terms = list(active_terms)
    if (not active_terms or len(set(active_terms)) != len(active_terms) or
            any(type(i) is not int or not 0 <= i <= rank or i == drop_term for i in active_terms)):
        raise ValueError('invalid active terms')
    if support_mode not in ('image', 'union', 'full'):
        raise ValueError('invalid support mode')
    if symmetry not in ('none', 'u-lex'):
        raise ValueError('invalid symmetry mode')
    n = source['dimension']
    width = n*n
    selected = active_terms+[drop_term]
    bases, core, shape, masks = compress_residual(source, selected)
    cnf = CNF()
    variables = {}
    phases = []
    variable_map = []
    for index in active_terms:
        variables[index] = []
        for axis, basis in enumerate(bases):
            coefficients = [cnf.variable() for _ in basis.vectors]
            variables[index].append(coefficients)
            initial = basis.coordinates(masks[index][axis])
            phases.extend(var if initial >> j & 1 else -var for j, var in enumerate(coefficients))
            for coordinate in range(width):
                inputs = [coefficients[j] for j, vector in enumerate(basis.vectors) if vector >> coordinate & 1]
                if not inputs:
                    continue
                if len(inputs) == 1:
                    original = inputs[0]
                else:
                    original = cnf.variable()
                    cnf.parity(inputs+[original], 0)
                variable_map.append(dict(variable=original, source_term=index,
                                         axis=('u', 'v', 'w')[axis], coordinate=coordinate))
    if symmetry == 'u-lex':
        # Mutable slots have identical domains. Every decomposition admits a
        # permutation sorting these columns; ties and zero factors stay allowed.
        for left, right in zip(active_terms, active_terms[1:]):
            lex_nondecreasing(cnf, variables[left][0], variables[right][0])
    for a, b, c in itertools.product(*(range(size) for size in shape)):
        monomials = [cnf.conjunction([variables[index][0][a], variables[index][1][b],
                                      variables[index][2][c]]) for index in active_terms]
        cnf.parity(monomials, core[(a*shape[1]+b)*shape[2]+c])
    retained = [i for i in range(rank+1) if i != drop_term]
    metadata = dict(dimension=n, field=2, rank=rank, source_term_count=rank+1,
        coefficient_domain=[-1, 0, 1], canonical_field_representatives=[0, 1],
        sign_identification='-1 = 1 in characteristic 2', drop_term=drop_term,
        active_terms=active_terms, frozen_terms=[i for i in retained if i not in active_terms],
        support_mode='multilinear-image', requested_support_mode=support_mode,
        image_shape=shape, image_bases=[basis.vectors for basis in bases],
        symmetry=symmetry,
        coordinate_projection=[[basis.coordinates(1 << j) for j in range(width)] for basis in bases],
        support={axis: [j for j in range(width) if any(vector >> j & 1 for vector in basis.vectors)]
                 for axis, basis in zip(('u', 'v', 'w'), bases)},
        tensor_equations=width**3, compressed_tensor_equations=len(core),
        original_equations_enforced_by='exact image projection and verified expansion of every original residual entry',
        preprocessing_exact_entries_checked=width**3, variables=cnf.nv,
        factor_variables=len(variable_map), compact_factor_variables=len(active_terms)*sum(shape),
        clauses=len(cnf.clauses), factor_variable_map=variable_map,
        scope='local frozen neighborhood only; UNSAT is not a global rank lower bound',
        rank_preservation='mode projections are identity on the residual images; projecting each product preserves a K-slot decomposition')
    return dict(clauses=cnf.clauses, nv=cnf.nv, metadata=metadata,
                source=source, retained=retained, phases=phases)
