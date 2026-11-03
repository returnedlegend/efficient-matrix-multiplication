"""Exact rank-nonincreasing affine multi-flip and pair-span witnesses over F2."""
from itertools import permutations
from mmsearch.native_bridge import canonical_terms
from mmsearch.search import encode_candidate,naive_terms,residual
from mmsearch.verify import verify_candidate

ORIENTATIONS=tuple(permutations(range(3)))  # fixed a, fixed b, free factor


def pair_column(a,b,width):
    value=0
    while a:
        bit=a&-a;value^=b<<((bit.bit_length()-1)*width);a^=bit
    return value


def span_basis(columns):
    rows={}
    for index,column in enumerate(columns):
        value=column;proof=1<<index
        while value:
            pivot=value.bit_length()-1
            if pivot not in rows:rows[pivot]=(value,proof);break
            row,witness=rows[pivot];value^=row;proof^=witness
    # Every basis row has an exact witness in the original full pair list.
    for row,proof in rows.values():
        reconstructed=0;bits=proof
        while bits:
            bit=bits&-bits;reconstructed^=columns[bit.bit_length()-1];bits^=bit
        if reconstructed!=row:raise AssertionError('pair-span original-column witness failed')
    return rows


def reduce_span(value,basis):
    witness=0
    for pivot in sorted(basis,reverse=True):
        if value>>pivot&1:
            row,proof=basis[pivot];value^=row;witness^=proof
    return value,witness


def projected_span(dictionary,orientation,*,n=5):
    a,b,free=orientation;width=n*n;bound=1<<width
    if sorted(orientation)!=[0,1,2]:raise ValueError('three distinct axes required')
    pairs=set()
    for term in dictionary:
        if len(term)!=3 or any(type(value) is not int or not 0<=value<bound for value in term):raise ValueError('strict binary-mask dictionary required')
        if term[a] and term[b]:pairs.add((term[a],term[b]))
    pairs=sorted(pairs);columns=[pair_column(x,y,width) for x,y in pairs]
    return pairs,columns,span_basis(columns)


def coordinate_solutions(vectors,target):
    """All exact coefficient witnesses, including dependent-fiber solutions."""
    rows={};null=[]
    for index,original in enumerate(vectors):
        value=original;proof=1<<index
        while value:
            pivot=value.bit_length()-1
            if pivot not in rows:rows[pivot]=(value,proof);break
            row,witness=rows[pivot];value^=row;proof^=witness
        else:null.append(proof)
    value=target;particular=0
    for pivot in sorted(rows,reverse=True):
        if value>>pivot&1:
            row,proof=rows[pivot];value^=row;particular^=proof
    if value:return
    current=particular
    for index in range(1<<len(null)):
        if index:
            bit=index&-index;current^=null[bit.bit_length()-1]
        if current.bit_count()>=2:yield current


def apply_move(terms,orientation,delta,neutral,coordinates,*,n):
    ordered=sorted(terms);a,b,free=orientation
    selected=[term for term in ordered if term[free]==delta]
    if len(selected)<2 or neutral not in terms or neutral[free]==delta:raise ValueError('invalid repeated slice/neutral term')
    if type(coordinates) is not int or coordinates<0 or coordinates>>len(selected) or coordinates.bit_count()<2:raise ValueError('nontrivial in-range coordinates required')
    represented=0
    for index,term in enumerate(selected):
        if coordinates>>index&1:represented^=term[a]
    if represented!=neutral[a]:raise ValueError('coordinate witness does not equal neutral factor')
    selected_map={term:index for index,term in enumerate(selected)};proposed=set()
    for original in ordered:
        term=list(original)
        if original in selected_map and coordinates>>selected_map[original]&1:term[b]^=neutral[b]
        if original==neutral:term[free]^=delta
        term=tuple(term)
        if not all(term):continue
        if term in proposed:proposed.remove(term)
        else:proposed.add(term)
    if len(proposed)>len(terms):raise AssertionError('affine move increased canonical product count')
    if residual(proposed,n):raise AssertionError('affine identity changed exact tensor')
    return proposed,{'orientation':list(orientation),'delta':delta,'selected_terms':[list(term) for term in selected],
                    'neutral_term':list(neutral),'coordinate_mask':coordinates,'coordinate_weight':coordinates.bit_count(),
                    'identity':'sum_i a_i*(b_i+x_i*b_j)*delta + a_j*b_j*(c_j+delta) equals original because a_j=XOR_i x_i*a_i; canonical zeros/duplicates cancel overF2'}


def planted_control():
    # Add the exact zero tensor (a1+a2+a3)*b*c with a3=a1+a2 to naiveMM2.
    terms=set(naive_terms(2))|{(1,3,2),(2,3,2),(3,3,2)}
    before=verify_candidate(encode_candidate(terms,2),random_trials=0)
    changed,proof=apply_move(terms,(0,1,2),1,(3,3,2),3,n=2)
    after=verify_candidate(encode_candidate(changed,2),random_trials=0)
    if not before['valid'] or not after['valid'] or before['exact_entries_checked']!=64 or after['exact_entries_checked']!=64 or len(terms)!=len(changed) or changed==terms:
        raise AssertionError('planted exact n2 control failed')
    try:apply_move(terms,(0,1,2),1,(3,3,2),1,n=2)
    except ValueError:bad_coordinates_rejected=True
    else:raise AssertionError('invalid coordinates accepted')
    return {'before':encode_candidate(terms,2),'after':encode_candidate(changed,2),'before_verification':before,
            'after_verification':after,'proof':proof,'bad_coordinates_rejected':bad_coordinates_rejected,
            'claim':'exact rank-preserving11-product n2 control, not an improved n2 algorithm or span-escape claim'}
