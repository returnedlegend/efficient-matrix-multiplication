"""Tiny whole-orbit polarization extension and projected invariant diagnostics.

No n5 dictionary constructor, optimizer or solver. Production-source metadata
may be inspected separately; actual extension generation is restricted to n<=3.
"""
from __future__ import annotations
from itertools import combinations
from . import cyclic_tensor_code7 as c
from .cube_polarization import polarize_cubes


def gf2_rank(values):
    basis={}
    for value in values:
        if type(value) is not int or value<0:raise ValueError('nonnegative integer vectors required')
        while value:
            pivot=value.bit_length()-1
            if pivot not in basis:basis[pivot]=value;break
            value^=basis[pivot]
    return len(basis)


def polarization_orbits(a,b,n):
    if type(n) is not int or not 1<=n<=3:raise ValueError('tiny extension only; n5 generation is disabled')
    c.validate_atom((a,a,a),n);c.validate_atom((b,b,b),n)
    if a==b:raise ValueError('distinct nonzero cube factors required')
    representatives=c.orbit_representatives([(a,a,a),(b,b,b),(a^b,a^b,a^b),(a,a,b),(a,b,b)],n)
    if len(representatives)!=5:raise AssertionError('polarization must have five distinct whole orbits')
    tensor=0
    for representative in representatives:tensor^=c.orbit_tensor(representative,n)
    if tensor:raise AssertionError('polarization relation is not tensor zero')
    return representatives


def extend_tiny(terms,pairs,n):
    if type(n) is not int or not 1<=n<=3:raise ValueError('tiny extension only; n5 generation is disabled')
    old=[c.validate_atom(term,n) for term in terms]
    additions=[representative for a,b in pairs for representative in polarization_orbits(a,b,n)]
    code=c.TinyOrbitCode.build(old+additions,n)
    index={term:i for i,term in enumerate(code.representatives)};relations=[]
    for a,b in pairs:
        relation=sum(1<<index[representative] for representative in polarization_orbits(a,b,n))
        if relation.bit_count()!=5 or c.xor_columns(code.columns,relation):raise AssertionError('bad odd five-orbit relation')
        relations.append(relation)
    return code,tuple(relations)


def polarize_tiny_seed(terms,a,b,n):
    if type(n) is not int or not 1<=n<=3:raise ValueError('tiny seed prototype only; n5 generation is disabled')
    source={c.validate_atom(term,n) for term in terms};polarization_orbits(a,b,n)
    result=polarize_cubes(source,a,b);error=0
    for term in source^result:error^=c.atom_tensor(term,n)
    if error:raise AssertionError('reused cube polarization changed the tensor')
    return tuple(sorted(result))


def projected_diagnostics(cube_count,seed_cube_mask,seed_selection_parity,generators,*,max_rank=16):
    """Enumerate only a <=16-dimensional cube/parity projection, not code states.

    Generator entries are (cube-toggle mask, whole-orbit-selection parity).
    This yields necessary cost residues for the specified relation span only.
    Without a complete extended-kernel audit, absent residues are not exclusions
    for any larger dictionary. Present residues never prove a feasible weight.
    """
    if type(cube_count) is not int or not 0<=cube_count<=15:raise ValueError('cube projection cap is15 variables')
    if type(seed_cube_mask) is not int or not 0<=seed_cube_mask<1<<cube_count or type(seed_selection_parity) is not int or seed_selection_parity not in (0,1):raise ValueError('bad projected seed')
    basis={}
    for mask,parity in generators:
        if type(mask) is not int or not 0<=mask<1<<cube_count or type(parity) is not int or parity not in (0,1):raise ValueError('bad projected generator')
        value=mask|(parity<<cube_count)
        while value:
            pivot=value.bit_length()-1
            if pivot not in basis:basis[pivot]=value;break
            value^=basis[pivot]
    if len(basis)>max_rank:raise ValueError('projected rank cap exceeded')
    image=[seed_cube_mask|(seed_selection_parity<<cube_count)]
    for value in basis.values():image += [state^value for state in image]
    residues=set();counts=set();parities=set()
    for state in image:
        count=(state&((1<<cube_count)-1)).bit_count();parity=state>>cube_count
        # Nonfixed whole-orbit products contribute0 mod3. All weights are odd.
        residue=next(r for r in range(6) if r%3==count%3 and r%2==parity)
        residues.add(residue);counts.add(count);parities.add(parity)
    return {'projected_rank':len(basis),'projected_states_checked':len(image),'possible_cube_counts':sorted(counts),'possible_selection_parities':sorted(parities),'necessary_cost_residues_mod6':sorted(residues),'exact92_residue_permitted':2 in residues,
            'scope':'Only the specified known-relation cube/parity image; no tensor-state search or weight feasibility claim.'}


def polarization_projection_generators(forms):
    """Abstract zero-XOR cube triples, each lifted by the known odd5 relation."""
    if len(set(forms))!=len(forms) or any(type(value) is not int or value<=0 for value in forms):raise ValueError('distinct positive cube forms required')
    lookup={value:i for i,value in enumerate(forms)};result=[]
    for a,b in combinations(forms,2):
        if a^b in lookup:result.append(((1<<lookup[a])|(1<<lookup[b])|(1<<lookup[a^b]),1))
    return tuple(result)
