"""Versioned derived-source contract; the original initial16 gate is unchanged."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from mmsearch.compact_xor3_seed7 import reduce_shared_two,xor_three
from mmsearch.tensor_code7 import term_from_atom
from scripts import campaign_native_baseline7 as safe
from scripts import tensor_code7 as identities

SCHEMA='native_xor3_source7.v1'
PREPARED_SHA='2302ae5e82fe7afd1845dd50ffd5c12f17e1efb56b8f4adf1ed09bd31a71e886'
SOURCES_SHA='9cdc5193b3fc9be8ff111bf46efd3e7990f7f82d8251fd1914ead556b33c5c51'
ANCHORS_SHA='26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def native_bytes(terms):return''.join(f'{a} {b} {c}\n'for a,b,c in sorted(terms)).encode()
def identity(terms):return dict(term_set_sha256=sha(native_bytes(terms)),rl_source_sha256=identities.digest(sorted(terms)))
def parent_candidate(terms,n=5):return dict(dimension=n,field=2,terms=[term_from_atom(atom,n)for atom in sorted(terms)])

def derive(parents,claimed_moves=None,poll=None):
    if len(parents)!=3:raise ValueError('exactly three authenticated tensor parents required')
    initial=xor_three(parents);terms,moves=reduce_shared_two(initial,poll)
    if claimed_moves is not None and encoded(moves)!=encoded(claimed_moves):raise ValueError('exact deterministic reduction replay differs')
    return initial,terms,moves

def schema_check(document):
    required={'schema','dimension','field','authority','sources','scope'}
    if (set(document)!=required or document['schema']!=SCHEMA or type(document['dimension'])is not int
            or document['dimension']!=5 or type(document['field'])is not int or document['field']!=2
            or not isinstance(document['sources'],list) or not 1<=len(document['sources'])<=8):
        raise ValueError('strict versioned F2 dimension5 derived-source contract required')
    if any(type(row.get('index'))is not int for row in document['sources'])or [row.get('index')for row in document['sources']]!=list(range(len(document['sources']))):raise ValueError('consecutive literal source indices required')
    for row in document['sources']:
        parents=row.get('parent_indices')
        if (not isinstance(parents,list) or len(parents)!=3 or any(type(i)is not int or not 0<=i<36 for i in parents)
                or parents!=sorted(set(parents)) or type(row.get('reduced_rank'))is not int or not 93<=row['reduced_rank']<=125):
            raise ValueError('three distinct approved parent indices and source rank93..125 required')
    return document

def pinned_file(bundle,record,expected=None):
    if set(record)!={'file','sha256'}:raise ValueError('exact file/SHA record required')
    declared=bundle/record['file']
    if declared.is_symlink():raise ValueError('symlink authority rejected')
    path=declared.resolve(strict=True)
    if not path.is_relative_to(bundle):raise ValueError('authority outside frozen bundle')
    raw=path.read_bytes()
    if sha(raw)!=record['sha256'] or expected is not None and sha(raw)!=expected:raise ValueError('root-pinned authority/source bytes differ')
    return raw

def candidate_schema(candidate):
    if (not isinstance(candidate,dict)or set(candidate)-{'dimension','field','terms','metadata'}
            or type(candidate.get('dimension'))is not int or candidate['dimension']!=5
            or type(candidate.get('field'))is not int or candidate['field']!=2
            or not isinstance(candidate.get('terms'),list)or not 93<=len(candidate['terms'])<=125):
        raise ValueError('literal dimension5/F2 derived candidate terms schema required')
    return candidate

def load_source(bundle,contract_sha,index,fresh):
    """Authenticate root-pinned catalogue/lineage and replay one exact derived source."""
    bundle=Path(bundle).resolve();raw=(bundle/'sources.json').read_bytes()
    if sha(raw)!=contract_sha:raise ValueError('externally root-pinned derived contract differs')
    document=schema_check(json.loads(raw));authority=document['authority']
    if set(authority)!={'prepared','native_sources','anchors','authentication_receipt'}:raise ValueError('complete authority closure required')
    prepared=json.loads(pinned_file(bundle,authority['prepared'],PREPARED_SHA))
    native_manifest=json.loads(pinned_file(bundle,authority['native_sources'],SOURCES_SHA))
    anchors=json.loads(pinned_file(bundle,authority['anchors'],ANCHORS_SHA))
    receipt=json.loads(pinned_file(bundle,authority['authentication_receipt']))
    if (receipt.get('status')!='AUTHENTICATED_FULL_NATIVE_CORPUS_REPLAY' or receipt.get('source_prepared_sha256')!=PREPARED_SHA
            or receipt.get('source_manifest_sha256')!=SOURCES_SHA or receipt.get('authority_anchors_sha256')!=ANCHORS_SHA):
        raise ValueError('complete authenticated parent corpus receipt required')
    if native_manifest.get('schema')!='tensor_code7.native_corpus_sources.v1' or prepared.get('schema')!='tensor_code7.native_corpus_prepared.v1':raise ValueError('wrong parent authority schemas')
    roots={entry['id']:entry for entry in anchors['known_input_train_states']}
    prohibited=set(anchors['prohibited_identities']['heldout'])|set(anchors['prohibited_identities']['evaluation'])
    if type(index)is not int or not 0<=index<len(document['sources']):raise ValueError('source index differs')
    row=document['sources'][index];atoms=list(map(tuple,prepared['atoms']));states=prepared['seed_states_hex']
    if len(atoms)!=522 or len(states)!=36 or len(prepared['source_records'])!=36:raise ValueError('exact522-column/36-parent authority required')
    parents=[];lineage=[]
    for parent_index,claimed in zip(row['parent_indices'],row['parent_records'],strict=True):
        record=prepared['source_records'][parent_index]
        if record!=claimed or record['index']!=parent_index:raise ValueError('parent lineage record differs from frozen authority')
        root=roots.get(record['native_root_id'])
        if root is None or root['root_approved_train']is not True or root['heldout_excluded']is not True or root['evaluation_excluded']is not True or root['split']!='train':raise ValueError('unknown/heldout/evaluation training ancestor')
        node=anchors['nodes'][root['id']]
        if node['parent_ids'] or node['parent_files'] or node['node_type']!='native_initial_train' or node['root_id']!=node['id']:raise ValueError('initial root ancestor closure differs')
        state=int(states[parent_index],16)
        if state<0 or state.bit_length()>522:raise ValueError('parent state outside fixed authority')
        terms=tuple(atoms[i]for i in range(522)if state>>i&1);candidate=parent_candidate(terms);parent_raw=encoded(candidate)
        if (len(terms)!=record['rank'] or record['rank']not in(93,94) or identity(terms)!=record['identity']
                or sha(parent_raw)!=record['canonical_certificate_sha256'] or set(record['identity'].values())&prohibited):
            raise ValueError('parent identity/rank/canonical source bytes differ')
        if not fresh('pre_parent_full_checks'):raise ValueError('parent check stopped')
        primary=safe.verify_candidate(candidate,random_trials=0)
        if not fresh('post_parent_primary'):raise ValueError('parent primary late')
        independent=safe.independent(candidate,parent_raw)
        if not fresh('post_parent_independent'):raise ValueError('parent independent late')
        if not primary['valid']or not independent['valid']or primary['exact_entries_checked']!=15625 or independent['exact_entries_checked']!=15625 or independent['essential_rank']!=len(terms):raise ValueError('parent full tensor check failed')
        parents.append(terms);lineage.append(record)
    def replay_poll():
        if not fresh('xor3_reduction_replay'):raise ValueError('derived reduction replay stopped')
    initial,terms,moves=derive(parents,row['reduction_moves'],poll=replay_poll)
    candidate_raw=pinned_file(bundle,{'file':row['file'],'sha256':row['sha256']});candidate=json.loads(candidate_raw)
    candidate_schema(candidate)
    identities.reject_ineligible_metadata(candidate.get('metadata',{}))
    if (len(initial)!=row['initial_rank']or len(terms)!=row['reduced_rank']or identity(terms)!=row['identity']
            or tuple(safe.base.canonical_terms(candidate))!=terms or set(row['identity'].values())&prohibited):
        raise ValueError('derived XOR3/fixpoint source binding differs or is prohibited')
    if not fresh('pre_derived_full_checks'):raise ValueError('derived source stopped')
    primary=safe.verify_candidate(candidate,random_trials=0)
    if not fresh('post_derived_primary'):raise ValueError('derived primary late')
    independent=safe.independent(candidate,candidate_raw)
    if not fresh('post_derived_independent'):raise ValueError('derived independent late')
    if not primary['valid']or not independent['valid']or primary['exact_entries_checked']!=15625 or independent['exact_entries_checked']!=15625 or independent['essential_rank']!=len(terms):raise ValueError('derived full double tensor check failed')
    return terms,dict(schema=SCHEMA,source_sha256=sha(candidate_raw),contract_sha256=contract_sha,
        source_index=index,parent_indices=row['parent_indices'],parent_records=lineage,initial_rank=len(initial),
        reduced_rank=len(terms),reduction_count=len(moves),identity=row['identity'],primary=primary,independent=independent,
        ancestry='Three authenticated native train descendants; exact GF2 odd XOR plus exact shared-two-factor reductions; no unknown edges.')
