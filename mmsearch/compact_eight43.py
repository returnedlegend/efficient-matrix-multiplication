"""Exact residual/core identities and constructive transfer of known products."""
import hashlib
import itertools
import json

from .compact_sat import BinaryBasis
from .recombine import canonical_terms,encode
from .sat_neighborhoods import factor_masks,gf2_rank
from .verify import verify_candidate


def bits(value):
    while value:
        bit=value&-value;yield bit.bit_length()-1;value^=bit


def packed_tensor(term,width=25):
    a,b,c=term;value=0
    for i in bits(a):
        for j in bits(b):value^=c<<((i*width+j)*width)
    return value


def factor_core(terms,indices):
    bases=[BinaryBasis([terms[i][axis] for i in indices]) for axis in range(3)]
    shape=[len(b.vectors) for b in bases];core=[0]*(shape[0]*shape[1]*shape[2])
    for i in indices:
        coords=[basis.coordinates(value,require_member=True) for basis,value in zip(bases,terms[i])]
        for a,b,c in itertools.product(*(bits(v) for v in coords)):core[(a*shape[1]+b)*shape[2]+c]^=1
    return [b.vectors for b in bases],core,shape


def expand_core(core,shape,bases,width=25):
    value=0
    for a,b,c in itertools.product(*(range(d) for d in shape)):
        if core[(a*shape[1]+b)*shape[2]+c]:value^=packed_tensor([bases[0][a],bases[1][b],bases[2][c]],width)
    return value


def permute_core(core,shape,permutation):
    dims=[shape[axis] for axis in permutation];values=[]
    for coordinates in itertools.product(*(range(d) for d in dims)):
        original=[0,0,0]
        for new,old in enumerate(permutation):original[old]=coordinates[new]
        values.append(core[(original[0]*shape[1]+original[1])*shape[2]+original[2]])
    return dims,values


def canonical_axis_form(core,shape):
    candidates=[]
    for p in itertools.permutations(range(3)):
        dims,values=permute_core(core,shape,p)
        candidates.append(((tuple(dims),bytes(values)),p))
    key,p=min(candidates,key=lambda item:item[0])
    fingerprint=hashlib.sha256(json.dumps([list(key[0]),list(key[1])],separators=(',',':')).encode()).hexdigest()
    return key,list(p),fingerprint


def exact_coordinates(value,vectors):
    basis={}
    for i,vector in enumerate(vectors):
        witness=1<<i
        while vector:
            p=vector.bit_length()-1
            if p not in basis:basis[p]=(vector,witness);break
            vector^=basis[p][0];witness^=basis[p][1]
    if len(basis)!=len(vectors):raise ValueError('coordinate basis is not independent')
    witness=0
    for p in sorted(basis,reverse=True):
        if value>>p&1:value^=basis[p][0];witness^=basis[p][1]
    if value:raise ValueError('known factor is outside its declared image basis')
    return witness


def transfer_known_products(old_core,old_shape,old_bases,old_products,new_core,new_shape,new_bases,width=25):
    old_key,old_perm,_=canonical_axis_form(old_core,old_shape)
    new_key,new_perm,_=canonical_axis_form(new_core,new_shape)
    if old_key!=new_key:return None
    old_actual=0
    for product in old_products:old_actual^=packed_tensor(product,width)
    if old_actual!=expand_core(old_core,old_shape,old_bases,width):
        raise AssertionError('known products do not equal their declared old tensor')
    replacement=[];coordinate_witnesses=[]
    for product in old_products:
        old_coords=[exact_coordinates(value,basis) for value,basis in zip(product,old_bases)]
        new_coords=[0,0,0]
        for canonical_axis in range(3):new_coords[new_perm[canonical_axis]]=old_coords[old_perm[canonical_axis]]
        factors=[]
        for value,basis in zip(new_coords,new_bases):
            expanded=0
            for i in bits(value):expanded^=basis[i]
            factors.append(expanded)
        replacement.append(tuple(factors));coordinate_witnesses.append(dict(old=old_coords,new=new_coords))
    actual=0
    for product in replacement:actual^=packed_tensor(product,width)
    target=expand_core(new_core,new_shape,new_bases,width)
    if actual!=target:raise AssertionError('explicit axis/basis transfer failed exact ambient expansion')
    return dict(products=replacement,old_axis_permutation=old_perm,new_axis_permutation=new_perm,
        coordinate_witnesses=coordinate_witnesses,exact_ambient_entries_checked=width**3,
        known_product_count=len(old_products))


def replace_and_verify(source,indices,products,metadata=None):
    old=factor_masks(source);selected=set(indices)
    replacement=[tuple(t) for t in products if all(t)]
    candidate=encode(canonical_terms(encode([term for i,term in enumerate(old) if i not in selected]+replacement,
        source['dimension'])),source['dimension'],metadata or {})
    verification=verify_candidate(candidate,random_trials=0)
    if not verification['valid'] or verification['exact_entries_checked']!=source['dimension']**6:
        raise AssertionError('constructive residual replacement failed full tensor verification')
    return candidate,verification


def opposite_pair_ranks(terms,width=25):
    ranks=[]
    for axis in range(3):
        other=[a for a in range(3) if a!=axis];columns=[]
        for term in terms:
            a,b=term[other[0]],term[other[1]];column=0
            for i in bits(a):column^=b<<(i*width)
            columns.append(column)
        ranks.append(gf2_rank(columns))
    return ranks
