"""Query-free tiny controls for future source-diverse circuit neighborhoods.

N5 generation is deliberately unavailable. These helpers do not call a decoder,
SAT solver, native worker, or candidate-search routine.
"""
from collections import defaultdict
import hashlib
import itertools
import json

from .compact_sat import compress_residual
from .compact_eight43 import canonical_axis_form,expand_core,packed_tensor,transfer_known_products
from .verify import verify_candidate


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def rank(vectors):
    rows={}
    for x in vectors:
        while x:
            p=x.bit_length()-1
            if p not in rows:rows[p]=x;break
            x^=rows[p]
    return len(rows)


def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate JSON key')
        result[key]=value
    return result


def provenance_hold(node_id,nodes,approved_roots,heldout_identities=()):
    """All-parent ancestry closure; source novelty never clears a split hold.

    Node IDs identify frozen provenance events, not canonical tensors: an exact
    walk can revisit a tensor without creating a cycle in the event lineage.
    Approved roots are bound to the digest of the complete root node record.
    """
    if not isinstance(nodes,dict)or len(nodes)>2048:raise ValueError('bounded explicit ancestry graph required')
    forbidden=[];unknown=[];visited=set();active=set();roots=set()
    def visit(key):
        if key in active:unknown.append(dict(node=key,reason='ancestry cycle'));return
        if key in visited:return
        node=nodes.get(key)
        if not isinstance(node,dict):unknown.append(dict(node=key,reason='missing ancestor'));return
        active.add(key);visited.add(key)
        identity=node.get('canonical_source_identity');purpose=node.get('purpose')
        if identity in heldout_identities or purpose in {'evaluation','heldout','validation_recovery'}:
            forbidden.append(dict(node=key,reason='evaluation/heldout provenance or canonical seed identity'))
        elif purpose!='search':unknown.append(dict(node=key,reason='unknown source purpose'))
        for field in ['raw_sha256','canonical_source_identity','provenance_sha256']:
            value=node.get(field)
            if not isinstance(value,str)or len(value)!=64 or any(c not in '0123456789abcdef'for c in value):unknown.append(dict(node=key,reason='missing or invalid '+field))
        parents=node.get('parents')
        if not isinstance(parents,list)or any(not isinstance(p,str)for p in parents)or len(set(parents))!=len(parents):unknown.append(dict(node=key,reason='invalid parent list'));parents=[]
        if not parents:
            if node.get('operation')!='approved_root'or approved_roots.get(key)!=digest(node):unknown.append(dict(node=key,reason='root lacks exact search approval binding'))
            else:roots.add(key)
        else:
            if node.get('operation')not in {'exact_native_walk','exact_bfs','exact_constructive_move','frozen_copy'}:unknown.append(dict(node=key,reason='unreviewed ancestry operation'))
            bindings=node.get('parent_raw_sha256',{})
            for parent in parents:
                if not isinstance(bindings,dict)or not isinstance(nodes.get(parent),dict)or bindings.get(parent)!=nodes[parent].get('raw_sha256'):
                    unknown.append(dict(node=key,reason='parent raw hash binding missing or changed',parent=parent))
                visit(parent)
        active.remove(key)
    visit(node_id)
    status='EXCLUDE_EVALUATION_HELDOUT_ANCESTRY'if forbidden else'DEFER_UNKNOWN_ANCESTRY'if unknown else'ELIGIBLE_BOUND_SEARCH_ANCESTRY'
    return dict(status=status,forbidden=forbidden,unknown=unknown,ancestor_nodes=sorted(visited),approved_root_nodes=sorted(roots),
                mathematical_inequivalence_claim=False,negative_rank_claim=False)


def tiny_source_hold(raw,expected_sha256,expected_products,heldout=(),seen=()):
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('raw source hash changed')
    source=json.loads(raw,object_pairs_hook=unique)
    if type(source.get('dimension'))is not int or source['dimension']!=2:raise ValueError('tiny prototype rejects production n5 dispatch')
    if type(source.get('field'))is not int or source['field']!=2:raise ValueError('exact F2 source required')
    terms=[]
    for t in source.get('terms',[]):
        if set(t)!={'u','v','w'}:raise ValueError('invalid term keys')
        vectors=[t[a]for a in ['u','v','w']]
        if any(not isinstance(v,list)or len(v)!=4 or any(type(x)is not int or x not in (0,1)for x in v)for v in vectors):raise ValueError('strict binary factors required')
        term=tuple(sum(x<<i for i,x in enumerate(v))for v in vectors)
        if not all(term):raise ValueError('zero product forbidden in frozen source')
        terms.append(term)
    if len(terms)!=expected_products or len(set(terms))!=len(terms):raise ValueError('essential source count/duplicate hold')
    identity=digest(sorted(terms))
    if identity in heldout:raise ValueError('heldout source identity')
    if identity in seen:raise ValueError('duplicate canonical source identity')
    proof=verify_candidate(source,random_trials=0)
    if not proof['valid']or proof['exact_entries_checked']!=64:raise ValueError('source full tensor check failed')
    pair_ranks=[]
    for axis in range(3):
        other=[a for a in range(3)if a!=axis]
        pair_ranks.append(rank([sum(t[other[1]]<<(4*i)for i in range(4)if t[other[0]]>>i&1)for t in terms]))
    return dict(source=source,terms=terms,canonical_identity=identity,ordered_terms_sha256=digest(terms),raw_sha256=expected_sha256,
                source_products=len(terms),full_entries_checked=64,opposite_pair_ranks=pair_ranks,
                factor_span_shortcut_allowed=pair_ranks==[len(terms)]*3)


def minimal_circuits(values):
    if not 1<=len(values)<=16 or any(type(v)is not int or not 0<v<16 for v in values):raise ValueError('tiny factor circuit scope only')
    pairgroups=defaultdict(list);lookup=defaultdict(list);found=set()
    for i,v in enumerate(values):lookup[v].append(i)
    for i,j in itertools.combinations(range(len(values)),2):
        pairgroups[values[i]^values[j]].append((i,j))
        if values[i]==values[j]:found.add((i,j))
        for k in lookup[values[i]^values[j]]:
            if j<k:found.add((i,j,k))
    for pairs in pairgroups.values():
        for p,q in itertools.combinations(pairs,2):
            selected=tuple(sorted(set(p+q)))
            if len(selected)==4 and rank([values[i]for i in selected])==3:found.add(selected)
    result=[]
    for selected in sorted(found,key=lambda s:(len(s),s)):
        value=0
        for i in selected:value^=values[i]
        if value or rank([values[i]for i in selected])!=len(selected)-1:raise AssertionError('not a minimal factor circuit')
        result.append(dict(indices=list(selected),size=len(selected),rank=len(selected)-1,xor_value=0))
    return result


def tiny_circuit_unions(source,max_attempts=64,max_masks=16,min_size=3,max_size=8):
    if source.get('dimension')!=2:raise ValueError('N5 neighborhood generation is disabled in prototype')
    if not 1<=max_attempts<=256 or not 1<=max_masks<=32:raise ValueError('unreviewed tiny preparation cap')
    terms=[tuple(sum(v<<j for j,v in enumerate(t[a]))for a in ['u','v','w'])for t in source['terms']]
    circuits=[]
    for axis in range(3):
        circuits.extend(dict(c,axis=axis)for c in minimal_circuits([t[axis]for t in terms]))
    candidates=[];seen=set();attempts=0;exhausted=True
    for number in (2,3):
        for group in itertools.combinations(circuits,number):
            if attempts>=max_attempts or len(candidates)>=max_masks:exhausted=False;break
            attempts+=1
            if len({c['axis']for c in group})<2:continue
            selected=sorted({i for c in group for i in c['indices']});mask=sum(1<<i for i in selected)
            if not min_size<=len(selected)<=max_size or mask in seen:continue
            seen.add(mask);candidates.append(dict(indices=selected,mask=mask,circuit_witnesses=list(group)))
        if not exhausted:break
    return dict(candidates=candidates,attempts=attempts,union_catalog_exhausted=exhausted,
                max_attempts=max_attempts,max_masks=max_masks,source_ordered_terms_sha256=digest(terms),N5_dispatch_enabled=False)


def tiny_mode_route(source,indices):
    if source.get('dimension')!=2:raise ValueError('N5 residual preparation is disabled in prototype')
    if not indices or len(set(indices))!=len(indices)or any(type(i)is not int or not 0<=i<len(source['terms'])for i in indices):raise ValueError('invalid exact local mask')
    bases,core,shape,_=compress_residual(source,indices);k=len(indices);target=k-1;d=max(shape);axis=max(range(3),key=lambda a:(shape[a],-a))
    if d>target:route='EXCLUDED_BY_MODE_RANK'
    elif target==d:route='ZERO_SURPLUS_EXACT'
    elif target==d+1:route='ONE_COSET_EXACT'
    else:route='RETAIN_UNSUPPORTED_SURPLUS_GE2'
    return dict(local_products=k,target=target,shape=shape,free_axis=axis,mode_rank=d,surplus=target-d,
        max_image_less_k=d<k,route=route,core=core,image_bases=[b.vectors for b in bases],indices=list(indices),
        preparation_only=True,decoder_queries=0)


def tiny_constructive_equivalence(old,new,known_products):
    for data in [old,new]:
        shape=data['shape'];bases=data['image_bases'];core=data['core']
        if len(shape)!=3 or any(not 1<=d<=4 for d in shape)or len(core)!=shape[0]*shape[1]*shape[2]:raise ValueError('tiny concise core required')
        if any(len(basis)!=d or rank(basis)!=d or any(type(v)is not int or not 0<v<16 for v in basis)for d,basis in zip(shape,bases)):raise ValueError('independent declared image bases required')
        if any(type(x)is not int or x not in (0,1)for x in core):raise ValueError('binary core required')
    transfer=transfer_known_products(old['core'],old['shape'],old['image_bases'],known_products,
             new['core'],new['shape'],new['image_bases'],width=4)
    if transfer is None:return dict(status='UNKNOWN_NO_EXACT_MAP',negative_transferred=False)
    actual=0
    for t in transfer['products']:actual^=packed_tensor(t,4)
    if actual!=expand_core(new['core'],new['shape'],new['image_bases'],4):raise AssertionError('constructive lift mismatch')
    return dict(status='CONSTRUCTIVE_MAP_VERIFIED',negative_transferred=False,**transfer)
