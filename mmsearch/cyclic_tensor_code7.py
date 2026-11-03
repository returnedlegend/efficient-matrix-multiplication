"""Tiny prototype of weighted whole-C3-orbit tensor codes over F2.

Independent of tensor_code7's unrestricted whole-atom code. There is no CLI,
production dictionary builder, solver, search loop, or record publication here.
The code constructor is deliberately restricted to matrix dimensions <=3.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

Atom = tuple[int, int, int]


def _dimension(n):
    if type(n) is not int or not 1 <= n <= 5:
        raise ValueError('matrix dimension must be an integer in1..5')
    return n*n


def validate_atom(atom, n) -> Atom:
    width = _dimension(n)
    if not isinstance(atom, (tuple, list)) or len(atom) != 3 or any(type(value) is not int or not 0 < value < 1 << width for value in atom):
        raise ValueError('whole atom needs three nonzero integer factor masks')
    return tuple(atom)


def orbit(atom, n) -> tuple[Atom, ...]:
    """Distinct C3 rotations only. Reflection is not identified."""
    u, v, w = validate_atom(atom, n)
    return tuple(sorted({(u,v,w), (v,w,u), (w,u,v)}))


def orbit_representative(atom, n) -> Atom:
    return orbit(atom, n)[0]


def orbit_representatives(atoms: Iterable[Atom], n, *, max_orbits=2000):
    """Close a finite whole-atom corpus under C3, then deduplicate whole orbits.

    This neither mixes factors nor takes a Cartesian product of factor palettes.
    Corpus atoms need not already form complete orbits. Source eligibility is a
    separate mandatory production input gate, not inferred by this function.
    """
    if type(max_orbits) is not int or not 1 <= max_orbits <= 2000:
        raise ValueError('orbit-column cap must be in1..2000')
    representatives = set()
    for atom in atoms:
        representatives.add(orbit_representative(atom, n))
        if len(representatives) > max_orbits:
            raise ValueError('orbit-column cap exceeded; never silently truncate')
    return tuple(sorted(representatives))


def _bits(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length()-1
        mask ^= bit


def atom_tensor(atom, n):
    width = _dimension(n)
    atom = validate_atom(atom, n)
    result = 0
    for i in _bits(atom[0]):
        for j in _bits(atom[1]):
            for k in _bits(atom[2]):
                result |= 1 << ((i*width+j)*width+k)
    return result


def orbit_tensor(atom, n):
    result = 0
    for member in orbit(atom, n):
        result ^= atom_tensor(member, n)
    return result


def target_tensor(n):
    """Trace convention: A[i,j] B[j,k] W[k,i], row-major factor masks."""
    width = _dimension(n)
    result = 0
    for i in range(n):
        for j in range(n):
            for k in range(n):
                result ^= 1 << (((i*n+j)*width+j*n+k)*width+k*n+i)
    return result


@lru_cache(maxsize=5)
def coordinate_orbits(width):
    """Flat coefficient coordinates under (i,j,k)->(j,k,i)."""
    if type(width) is not int or not 1 <= width <= 25:
        raise ValueError('coordinate width must be an integer in1..25')
    result = []
    for i in range(width):
        for j in range(width):
            for k in range(width):
                triples = {(i,j,k), (j,k,i), (k,i,j)}
                if (i,j,k) == min(triples):
                    result.append(tuple(sorted((a*width+b)*width+c for a,b,c in triples)))
    return tuple(result)


def compress_invariant(full_tensor, width):
    """Select one coefficient per coordinate orbit, rejecting noninvariance.

    On the C3-fixed subspace this is an invertible linear map. It is not a
    free/fixed factor projection, and does not discard any invariant equation.
    """
    if type(full_tensor) is not int or full_tensor < 0 or full_tensor.bit_length() > width**3:
        raise ValueError('invalid full tensor mask')
    result = 0
    for index, coordinates in enumerate(coordinate_orbits(width)):
        bit = (full_tensor >> coordinates[0]) & 1
        if any(((full_tensor >> coordinate) & 1) != bit for coordinate in coordinates):
            raise ValueError('tensor is not C3 invariant')
        result |= bit << index
    return result


def expand_invariant(compressed, width):
    coordinates = coordinate_orbits(width)
    if type(compressed) is not int or compressed < 0 or compressed.bit_length() > len(coordinates):
        raise ValueError('invalid compressed invariant tensor')
    result = 0
    for index in _bits(compressed):
        for coordinate in coordinates[index]:
            result |= 1 << coordinate
    return result


def repeated_weight_literals(variables, weights):
    """Future SAT cardinality input: keep one/three repeated positive literals.

    These are integer multiplicities, never F2 parities. The actual production
    encoder/backend remains a separately reviewed future component.
    """
    if len(variables) != len(weights) or len(set(variables)) != len(variables):
        raise ValueError('one distinct variable per orbit required')
    if any(type(v) is not int or v <= 0 for v in variables) or any(type(w) is not int or w not in (1,3) for w in weights):
        raise ValueError('positive integer variables and literal weights1/3 required')
    return [variable for variable, weight in zip(variables, weights) for _ in range(weight)]


def xor_columns(columns, state):
    if type(state) is not int or state < 0 or state.bit_length() > len(columns):
        raise ValueError('invalid orbit selection mask')
    result = 0
    for index in _bits(state):
        result ^= columns[index]
    return result


@dataclass(frozen=True)
class TinyOrbitCode:
    n: int
    representatives: tuple[Atom, ...]
    columns: tuple[int, ...]
    weights: tuple[int, ...]
    compressed: bool

    @classmethod
    def build(cls, atoms, n, *, compressed=True, max_orbits=2000):
        if type(n) is not int or not 1 <= n <= 3:
            raise ValueError('tiny prototype only; n5 dictionary construction is not implemented')
        if type(compressed) is not bool:
            raise ValueError('compression flag must be boolean')
        representatives = orbit_representatives(atoms, n, max_orbits=max_orbits)
        full = tuple(orbit_tensor(atom, n) for atom in representatives)
        columns = tuple(compress_invariant(column,n*n) for column in full) if compressed else full
        return cls(n, representatives, columns, tuple(len(orbit(atom,n)) for atom in representatives), compressed)

    def target(self):
        target = target_tensor(self.n)
        return compress_invariant(target,self.n*self.n) if self.compressed else target

    def expand_state(self, state):
        xor_columns(self.columns,state)  # Validate the entire state mask first.
        terms = {term for index in _bits(state) for term in orbit(self.representatives[index],self.n)}
        if len(terms) != self.weight(state):
            raise AssertionError('whole orbit supports overlap')
        return tuple(sorted(terms))

    def weight(self, state):
        xor_columns(self.columns,state)
        return sum(self.weights[index] for index in _bits(state))

    def state_from_terms(self, terms):
        normalized = [validate_atom(term,self.n) for term in terms]
        if len(set(normalized)) != len(normalized):
            raise ValueError('source must have distinct canonical essential products')
        selected = {orbit_representative(term,self.n) for term in normalized}
        lookup = {atom:index for index,atom in enumerate(self.representatives)}
        if not selected <= lookup.keys():
            raise ValueError('source orbit absent from finite dictionary')
        state = sum(1 << lookup[atom] for atom in selected)
        if set(self.expand_state(state)) != set(normalized):
            raise ValueError('source omits C3 orbit members')
        return state

    def linear_system(self):
        """Column elimination with complete kernel witnesses; no decoder search."""
        basis = {}
        kernel = []
        for index,column in enumerate(self.columns):
            witness = 1 << index
            while column:
                pivot = column.bit_length()-1
                if pivot not in basis:
                    basis[pivot] = (column,witness)
                    break
                row,mask = basis[pivot]
                column ^= row
                witness ^= mask
            if not column:
                if xor_columns(self.columns,witness):
                    raise AssertionError('kernel witness is not exact')
                kernel.append(witness)
        target = self.target()
        particular = 0
        while target:
            pivot = target.bit_length()-1
            if pivot not in basis:
                return {'consistent':False,'rank':len(basis),'nullity':len(kernel),'particular':None,'kernel':tuple(kernel)}
            row,mask = basis[pivot]
            target ^= row
            particular ^= mask
        return {'consistent':True,'rank':len(basis),'nullity':len(kernel),'particular':particular,'kernel':tuple(kernel)}

    def candidate(self, state):
        """Expand first and check every literal tensor coefficient; no WINNER API."""
        terms = self.expand_state(state)
        full = 0
        for term in terms:
            full ^= atom_tensor(term,self.n)
        if full != target_tensor(self.n):
            raise ValueError('orbit state fails full target tensor')
        width = self.n*self.n
        return {'field':2,'dimension':self.n,'terms':[{axis:[(value>>i)&1 for i in range(width)] for axis,value in zip(('u','v','w'),term)} for term in terms]}
