"""Exact constructive BFS helpers; current-parent span differences, no SAT."""
from mmsearch.constructive_affine43 import (pair_column,reduce_span,apply_move)
from mmsearch.kernel_quartet_frontier import compress_export
from mmsearch.native_bridge import canonical_terms,term_set_sha256
from mmsearch.search import encode_candidate
from mmsearch.verify import verify_candidate


def extend_with_parent(full_columns,full_basis,parent_pairs,*,width=25):
    columns=list(full_columns)+[pair_column(a,b,width) for a,b in parent_pairs]
    basis=dict(full_basis);added=[]
    for index,column in enumerate(columns[len(full_columns):],len(full_columns)):
        remainder,proof=reduce_span(column,basis)
        if not remainder:continue
        witness=(1<<index)^proof;pivot=remainder.bit_length()-1
        reconstructed=0;bits=witness
        while bits:
            bit=bits&-bits;reconstructed^=columns[bit.bit_length()-1];bits^=bit
        if reconstructed!=remainder:raise AssertionError('parent augmentation witness failed')
        basis[pivot]=(remainder,witness)
        added.append({'pivot':pivot,'vector_hex':hex(remainder),'original_column_xor_hex':hex(witness)})
    return columns,basis,added


def difference_witnesses(child,parent,orientation,columns,basis,*,width=25):
    a,b,_=orientation;old={(term[a],term[b]) for term in parent};new={(term[a],term[b]) for term in child}-old;outside=[]
    for pair in sorted(new):
        column=pair_column(*pair,width);remainder,proof=reduce_span(column,basis)
        if not remainder:continue
        reconstructed=0;bits=proof
        while bits:
            bit=bits&-bits;reconstructed^=columns[bit.bit_length()-1];bits^=bit
        if column^reconstructed!=remainder:raise AssertionError('fresh-difference nonmembership proof failed')
        outside.append({'pair':list(pair),'column_hex':hex(column),'remainder_hex':hex(remainder),'full_plus_parent_column_xor_hex':hex(proof)})
    return outside,len(new)


def composed_control(previous_control):
    source=set(canonical_terms(previous_control['before']))
    first,first_proof=apply_move(source,(0,1,2),1,(3,3,2),3,n=2)
    first_report=verify_candidate(encode_candidate(first,2),random_trials=0)
    if term_set_sha256(first)!=term_set_sha256(canonical_terms(previous_control['after'])):raise AssertionError('reused first control differs')
    second,second_proof=apply_move(first,(0,1,2),2,(3,3,3),3,n=2)
    second_report=verify_candidate(encode_candidate(second,2),random_trials=0)
    compressed,report,trace=compress_export(encode_candidate(second,2))
    if (not all(value['valid'] and value['exact_entries_checked']==64 for value in (first_report,second_report,report))
        or not trace['fixed_point'] or trace['winner'] or len(compressed['terms'])>len(second)):
        raise AssertionError('composed move/compression exactness control failed')
    return {'source':previous_control['before'],'first':encode_candidate(first,2),'second':encode_candidate(second,2),
            'compressed':compressed,'proofs':[first_proof,second_proof],
            'reports':{'first':first_report,'second':second_report,'compressed':report},'compression':trace,
            'ranks':[len(source),len(first),len(second),len(compressed['terms'])],
            'claim':'planted n2 composition and compression control only, no n5 record'}
