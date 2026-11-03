"""Exact factor-image closure metadata; no tensor decomposition query."""
from .compact_sat import BinaryBasis
from .compact_eight43 import exact_coordinates
from .compact_coset43 import _insert,digest


def factor_image_closure(terms,parent,cancelled=None):
    """Find original products whose three factors lie in the fixed parent images.

    Actual tensor mode images equal these factor spans only with the separately
    verified global opposite-pair column-independence precondition.
    """
    if len(set(parent))!=len(parent) or any(type(i) is not int or not 0<=i<len(terms) for i in parent) or any(len(term)!=3 or any(type(v) is not int or not 0<v<1<<25 for v in term) for term in terms):raise ValueError('invalid source products or parent support')
    bases=[BinaryBasis([terms[i][axis] for i in parent]) for axis in range(3)];witness=[]
    for axis,basis in enumerate(bases):
        pivots={};original=[]
        for i in parent:
            if _insert(pivots,terms[i][axis]):original.append(i)
        vectors=[terms[i][axis] for i in original]
        witness.append(dict(axis=axis,basis=list(basis.vectors),original_independent_indices=original,basis_from_original_coordinates=[exact_coordinates(v,vectors) for v in basis.vectors]))
    closure=[];outside=[];tested=0
    def finish(status):
        if cancelled and cancelled():status='UNKNOWN'
        return dict(status=status,complete=status=='COMPLETE',parent_indices=list(parent),shape=[len(b.vectors) for b in bases],basis_witnesses=witness,closure=closure,other_products=outside,
            raw_other_products_tested=tested,closure_size=len(closure),parent_terms=len(parent),source_factor_sha256=digest(terms),actual_image_requires_pair_independence=True)
    if cancelled and cancelled():return finish('UNKNOWN')
    for i,term in enumerate(terms):
        if cancelled and cancelled():return finish('UNKNOWN')
        if i not in parent:tested+=1
        coordinates=[basis.coordinates(value) for basis,value in zip(bases,term)]
        if all(basis.expand(mask)==value for basis,mask,value in zip(bases,coordinates,term)):
            entry=dict(source_index=i,factor_coordinates=coordinates);closure.append(entry)
            if i not in parent:outside.append(entry)
    if not set(parent)<={entry['source_index'] for entry in closure}:raise AssertionError('parent not contained in own factor image')
    return finish('COMPLETE')
