"""Separate bounded pair-span-escape selector proposal; no automatic execution.

Pure bitpacked GF2 mathematics. Production generation requires an authenticated
base receipt and separately approved bounds; this module invokes no solver.
"""
from __future__ import annotations

from functools import lru_cache
from itertools import combinations,permutations

from mmsearch.tensor_code7 import atom_column,digest,supports,validate_prepared
from mmsearch.tensor_code7_extension import (BaseReceipt,WITNESS_SCHEMA,integer,plus_atoms,scalar_zero_check)

SELECTOR_SCHEMA='tensor_code7.extension_selector.v1'
AXIS_ORDERS=tuple(permutations(range(3)))


def pair_column(left,right,width):
    integer(left,'left factor',1,(1<<width)-1)
    integer(right,'right factor',1,(1<<width)-1)
    value=0
    for a in supports(left):
        for b in supports(right):value |= 1 << (a*width+b)
    return value


def span(columns):
    basis={}
    for column in columns:
        add(basis,column)
    return basis


def reduce(basis,value):
    integer(value,"span vector",0)
    while value:
        pivot=value.bit_length()-1
        if pivot not in basis:return value
        value ^= basis[pivot]
    return 0


def remainder(basis,value):
    integer(value,"quotient vector",0)
    # Keep nonpivot coordinates while reducing every pivot, not just the lead.
    for pivot in sorted(basis,reverse=True):
        if value>>pivot&1:value ^= basis[pivot]
    return value


def add(basis,value):
    value=reduce(basis,value)
    if value:basis[value.bit_length()-1]=value
    return bool(value)


@lru_cache(maxsize=256)
def _span_digest(rows):
    return digest([[p,hex(value)] for p,value in rows])


def span_digest(basis):
    return _span_digest(tuple(sorted(basis.items(),reverse=True)))


def projection_diagnostics(atoms,seed,parent_ids,order,n,seed_basis=None,global_basis=None):
    """For one projection, all three new pair remainders equal d tensor b."""
    integer(n,"dimension",1,5)
    integer(seed,"seed state",0)
    if seed.bit_length()>len(atoms):raise ValueError("seed outside base dictionary")
    width=n*n
    if len(parent_ids)!=2 or any(type(i) is not int or not 0<=i<len(atoms) for i in parent_ids):
        raise ValueError('invalid base parent IDs')
    if any(not(seed>>i&1) for i in parent_ids):
        raise ValueError('pair-span seed must contain both selected parents')
    new=plus_atoms(atoms[parent_ids[0]],atoms[parent_ids[1]],list(order),n)
    a,b,free=order
    if seed_basis is None:seed_basis=span(pair_column(atoms[i][a],atoms[i][b],width) for i in supports(seed))
    if global_basis is None:global_basis=span(pair_column(t[a],t[b],width) for t in atoms)
    cross=pair_column(atoms[parent_ids[1]][a],atoms[parent_ids[0]][b],width)
    seed_remainder=remainder(seed_basis,cross)
    global_remainder=remainder(global_basis,cross)
    new_pairs=[pair_column(t[a],t[b],width) for t in new]
    if any(remainder(seed_basis,p)!=seed_remainder for p in new_pairs):
        raise AssertionError('new pair span does not equal old span plus cross')
    if any(remainder(global_basis,p)!=global_remainder for p in new_pairs):
        raise AssertionError('new global pair span does not equal old span plus cross')
    return dict(axis_permutation=list(order),pair_axes=[a,b],free_axis=free,pair_entries=width**2,
        cross_pair_column_hex=hex(cross),seed_pair_span_rank=len(seed_basis),
        global_pair_span_rank=len(global_basis),seed_pair_span_sha256=span_digest(seed_basis),
        global_pair_span_sha256=span_digest(global_basis),seed_cross_remainder_hex=hex(seed_remainder),
        global_cross_remainder_hex=hex(global_remainder),seed_pair_span_escape=bool(seed_remainder),
        global_pair_span_escape=bool(global_remainder),
        seed_pair_rank_gain=int(bool(seed_remainder)),global_pair_rank_gain=int(bool(global_remainder)),
        pair_span_gain_upper_bound=1)


def select_witnesses(base,base_sha256,max_relations=16,max_new_atoms=100,max_attempts=8192,
                     guard=None,production_receipt=None,require_seed_escape=True):
    """Generate only bounded algebraic witnesses/audit, never a target query.

    This is a NEW selector variant, separate from the frozen lex-first proposal.
    Scan a fixed round-robin coactive-pair/axis prefix. Choose seed escapes first,
    then global escapes and independent quotient directions before repeated
    cosets, with deterministic source balancing/ties. No witness gets invented
    when the bounded pool contains fewer than the requested number.
    """
    integer(max_relations,'max_relations',1,16)
    integer(max_new_atoms,'max_new_atoms',1,100)
    integer(max_attempts,'max_attempts',1,8192)
    if require_seed_escape is not True:raise ValueError("initial selector requires literal require_seed_escape=true")
    if base.get('dimension')==5:
        if not isinstance(production_receipt,BaseReceipt) or production_receipt.base_prepared_sha256!=base_sha256 or production_receipt.base_dictionary_sha256!=base.get('dictionary_sha256') or production_receipt.source_manifest_sha256!=base.get('source_manifest_sha256'):
            raise ValueError('n5 witness generation requires independently authenticated base receipt')
    if type(base_sha256) is not str or len(base_sha256)!=64 or any(c not in "0123456789abcdef" for c in base_sha256):
        raise ValueError("independent base raw SHA256 pin required")
    atoms,columns,seeds,cycles=validate_prepared(base,guard)
    n=base['dimension'];width=n*n
    projections={order: [pair_column(t[order[0]],t[order[1]],width) for t in atoms] for order in AXIS_ORDERS}
    global_bases={order:span(values) for order,values in projections.items()}
    seed_bases={(s,order):span(projections[order][i] for i in supports(seed)) for s,seed in enumerate(seeds) for order in AXIS_ORDERS}
    iterators=[iter((pair,order) for pair in combinations(list(supports(seed)),2) for order in AXIS_ORDERS) for seed in seeds]
    base_atoms=set(atoms)
    pool=[];attempted=degenerate=inside_seed=0;exhausted=set()
    while attempted<max_attempts and len(exhausted)<len(seeds):
        for s,iterator in enumerate(iterators):
            if attempted>=max_attempts:break
            if s in exhausted:continue
            if guard:guard()
            try:pair,order=next(iterator)
            except StopIteration:exhausted.add(s);continue
            attempted+=1
            try:new=plus_atoms(atoms[pair[0]],atoms[pair[1]],list(order),n)
            except ValueError:degenerate+=1;continue
            if all(t in base_atoms for t in new):continue
            diag=projection_diagnostics(atoms,seeds[s],pair,order,n,seed_bases[s,order],global_bases[order])
            if require_seed_escape and not diag['seed_pair_span_escape']:
                inside_seed+=1;continue
            five=tuple(sorted([atoms[pair[0]],atoms[pair[1]],*new]))
            pool.append(dict(seed_id=s,parent_atom_ids=list(pair),axis_permutation=list(order),
                new_atoms=new,trial=attempted,diagnostics=diag,relation_key=five))
    selected=[];seen_cycles=set();known=set(atoms);used_global={};used_seed={};used_cosets=set();seed_load={}
    for ordinal in range(max_relations):
        best=None
        for index,item in enumerate(pool):
            if guard and index%128==0:guard()
            if item['relation_key'] in seen_cycles:continue
            additions=set(item['new_atoms'])-known
            if len(known)-len(atoms)+len(additions)>max_new_atoms or len(known)+len(additions)>5000:continue
            d=item['diagnostics'];mode=tuple(d['pair_axes']);s=item['seed_id']
            gr=int(d['global_cross_remainder_hex'],16);sr=int(d['seed_cross_remainder_hex'],16)
            global_independent=bool(reduce(used_global.get(mode,{}),gr))
            seed_independent=bool(reduce(used_seed.get((s,mode),{}),sr))
            coset=(mode,gr) if gr else (s,mode,sr)
            score=(d['seed_pair_span_escape'],d['global_pair_span_escape'],global_independent,
                   seed_independent,coset not in used_cosets,-seed_load.get(s,0),-item['trial'])
            if best is None or score>best[0]:best=(score,item,global_independent,seed_independent,coset)
        if best is None:break
        score,item,gi,si,coset=best
        d=item['diagnostics'];s=item['seed_id'];mode=tuple(d['pair_axes'])
        seen_cycles.add(item['relation_key']);known.update(item['new_atoms']);used_cosets.add(coset)
        seed_load[s]=seed_load.get(s,0)+1
        add(used_global.setdefault(mode,{}),int(d['global_cross_remainder_hex'],16))
        add(used_seed.setdefault((s,mode),{}),int(d['seed_cross_remainder_hex'],16))
        selected.append(dict(item,global_quotient_independent_when_selected=gi,
            seed_quotient_independent_when_selected=si,selection_ordinal=ordinal))
    records=[dict(id=f'escape-plus-{i:03d}',parent_atom_ids=item['parent_atom_ids'],
        axis_permutation=item['axis_permutation'],new_atoms=[list(t) for t in item['new_atoms']]) for i,item in enumerate(selected)]
    manifest=dict(schema=WITNESS_SCHEMA,base_prepared_sha256=base_sha256,
        base_dictionary_sha256=base['dictionary_sha256'],max_new_atoms=max_new_atoms,relations=records)
    audit_items=[]
    for item in selected:
        if guard:guard()
        five=[atoms[i] for i in item['parent_atom_ids']]+item['new_atoms']
        packed=0
        for atom in five:packed ^= atom_column(atom,n)
        independent=scalar_zero_check(five,n,guard)
        if packed or not independent['valid']:
            raise AssertionError('selected full-tensor five-term relation failed independent checks')
        observation={key:value for key,value in item.items() if key not in ('relation_key','new_atoms')}
        observation.update(seed_state_hex=hex(seeds[item['seed_id']]),
            packed_full_tensor_xor_hex=hex(packed),independent_full_zero_check=independent)
        audit_items.append(observation)
    audit=dict(schema=SELECTOR_SCHEMA,status='ALGEBRAIC_WITNESSES_ONLY' if records else 'NO_VALID_WITNESSES_IN_BOUNDED_PREFIX',
        target_query_called=False,base_prepared_sha256=base_sha256,base_dictionary_sha256=base['dictionary_sha256'],
        parameters=dict(max_relations=max_relations,max_new_atoms=max_new_atoms,max_attempts=max_attempts,
            require_seed_escape=require_seed_escape,variant='seed/global pair escape and quotient diversity'),
        attempted_pair_axis_records=attempted,degenerate_records=degenerate,inside_seed_skipped=inside_seed,
        candidate_records=len(pool),accepted_relations=len(records),requested_count_reached=len(records)==max_relations,
        derived_new_atom_count=len(known)-len(atoms),selected=audit_items,
        global_selected_quotient_ranks={str(mode):len(basis) for mode,basis in used_global.items()},
        scope='Only exact pair-span/coset diagnostics for derived full-tensor relations; no global novelty or rank claim')
    return manifest,audit
