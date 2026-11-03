"""Exact embedding and new-kernel witnesses for a versioned pair dictionary."""
from .breadth43 import binary_rank
from .common_delta42 import columns_from_rows,multiply
from .recombine import digest
from .recombine_sat import bits


def _embedding(old,new):
    if (old['metadata']['orientation']!=new['metadata']['orientation']
            or old['metadata']['mode_permutation']!=new['metadata']['mode_permutation']
            or old['metadata']['width']!=new['metadata']['width']):
        raise ValueError('dictionary orientations or coordinate widths do not match')
    if old['right_sides']!=new['right_sides'] or len(old['coefficients'])!=len(new['coefficients']):
        raise ValueError('dictionary original tensor rows do not match')
    old_pairs=[tuple(p) for p in old['pairs']];new_pairs=[tuple(p) for p in new['pairs']]
    if old_pairs!=sorted(set(old_pairs)) or new_pairs!=sorted(set(new_pairs)):
        raise ValueError('distinct lexicographically ordered fixed pairs required')
    positions={pair:g for g,pair in enumerate(new_pairs)}
    if any(pair not in positions for pair in old_pairs):raise ValueError('old fixed pair missing from expansion')
    mapping=[positions[p] for p in old_pairs]
    old_columns=columns_from_rows(old);new_columns=columns_from_rows(new)
    if any(old_columns[g]!=new_columns[h] for g,h in enumerate(mapping)):
        raise AssertionError('old original coefficient column changed under embedding')
    added=[g for g in range(len(new_pairs)) if g not in set(mapping)]
    return mapping,added,old_columns,new_columns


def additional_kernel_evidence(old,new):
    mapping,added,old_columns,new_columns=_embedding(old,new)
    old_rank=binary_rank(old_columns);new_rank=binary_rank(new_columns)
    old_null=len(old_columns)-old_rank;new_null=len(new_columns)-new_rank;difference=new_null-old_null
    if difference<0:raise AssertionError('adding columns decreased kernel dimension')
    pivots={(row&-row).bit_length()-1 for row,_,_ in new['reduced']['rows']}
    restricted_basis={};directions=[]
    for free in range(len(new_columns)):
        if free in pivots:continue
        vector=1<<free
        for row,_,_ in new['reduced']['rows']:
            if row>>free&1:vector^=row&-row
        restricted=sum(((vector>>g)&1)<<i for i,g in enumerate(added))
        residual=restricted
        while residual:
            pivot=(residual&-residual).bit_length()-1
            if pivot not in restricted_basis:
                if multiply(new_columns,vector):raise AssertionError('new direction fails original full coefficient kernel')
                restricted_basis[pivot]=residual
                directions.append(dict(full_kernel_mask_hex=hex(vector),support_groups=list(bits(vector)),
                    added_coordinate_mask_hex=hex(restricted),free_group=free,
                    original_rows_checked=len(new['coefficients'])))
                break
            residual^=restricted_basis[pivot]
        if len(directions)==difference:break
    if len(directions)!=difference:raise AssertionError('could not witness all added kernel dimensions')
    evidence=dict(orientation=new['metadata']['orientation'],mode_permutation=new['metadata']['mode_permutation'],
        old_pair_count=len(old_columns),new_pair_count=len(new_columns),old_to_new_group_indices=mapping,
        added_group_indices=added,added_fixed_pairs=[list(new['pairs'][g]) for g in added],
        old_rank=old_rank,new_rank=new_rank,rank_change=new_rank-old_rank,
        old_nullity=old_null,new_nullity=new_null,added_kernel_dimensions=difference,
        old_coefficients_sha256=digest([hex(c) for c in old['coefficients']]),
        new_coefficients_sha256=digest([hex(c) for c in new['coefficients']]),
        directions=directions,scope='Exact linear coefficient-rank/kernel embedding only; no product-count or tensor-rank lower bound.')
    validate_kernel_evidence(old,new,evidence)
    return evidence


def validate_kernel_evidence(old,new,evidence):
    mapping,added,old_columns,new_columns=_embedding(old,new)
    old_rank,new_rank=binary_rank(old_columns),binary_rank(new_columns)
    difference=(len(new_columns)-new_rank)-(len(old_columns)-old_rank)
    if (evidence['old_to_new_group_indices']!=mapping or evidence['added_group_indices']!=added
            or evidence['old_rank']!=old_rank or evidence['new_rank']!=new_rank
            or evidence['added_kernel_dimensions']!=difference or len(evidence['directions'])!=difference
            or evidence['old_coefficients_sha256']!=digest([hex(c) for c in old['coefficients']])
            or evidence['new_coefficients_sha256']!=digest([hex(c) for c in new['coefficients']])):
        raise AssertionError('kernel expansion metadata mismatch')
    restrictions=[]
    for item in evidence['directions']:
        vector=int(item['full_kernel_mask_hex'],16)
        if vector<0 or vector>>len(new_columns) or multiply(new_columns,vector):
            raise AssertionError('kernel expansion direction fails original equations')
        restricted=sum(((vector>>g)&1)<<i for i,g in enumerate(added))
        if restricted!=int(item['added_coordinate_mask_hex'],16) or list(bits(vector))!=item['support_groups']:
            raise AssertionError('kernel expansion support/restriction mismatch')
        restrictions.append(restricted)
    if binary_rank(restrictions)!=difference:raise AssertionError('new kernel directions are not independent modulo old kernel')
    return True
