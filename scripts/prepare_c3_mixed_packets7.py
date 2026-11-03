"""Metadata-only exact nine-product C3 packet preparation; no decoder calls.

One approved source; all three cubes plus every pair of nonfixed orbits. The
full source pair-column independence certifies the factor/unfolding-rank match.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from mmsearch.compact_sat import BinaryBasis
from mmsearch.compact_eight43 import packed_tensor,expand_core
from mmsearch.compact_coset43 import mode_slices
from mmsearch.sat_neighborhoods import gf2_rank
from scripts import tensor_code7 as lifecycle
from scripts.verify_record42_independent import verify_bytes
from mmsearch.verify import verify_candidate

SOURCE_SHA='56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b'
ANCHOR_SHA='26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8'
ELIGIBILITY_SHA='7354183ab6e9c89f76110e1c916738ced4856499632a2f317508b1d6bea7bb55'
CAP=32*1024**2
DEADLINE='2026-11-03T19:24:17Z'


def sha_bytes(raw):return hashlib.sha256(raw).hexdigest()
def sha(path):return sha_bytes(Path(path).read_bytes())
def raw(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def read(path):return lifecycle.strict_load(Path(path).read_bytes())
def bits(value):
    while value:
        bit=value&-value;yield bit.bit_length()-1;value^=bit


def rank_witness(columns):
    basis={};pivots=[];selected=[]
    for index,value in enumerate(columns):
        while value:
            pivot=value.bit_length()-1
            if pivot not in basis:basis[pivot]=value;pivots.append(pivot);selected.append(index);break
            value^=basis[pivot]
    return {'rank':len(basis),'pivot_rows':pivots,'independent_column_positions':selected}


def source_pair_witnesses(terms,width):
    witnesses=[]
    for axis in range(3):
        other=[j for j in range(3) if j!=axis];columns=[]
        for term in terms:
            value=0
            for i in bits(term[other[0]]):value^=term[other[1]]<<(i*width)
            columns.append(value)
        witness=rank_witness(columns)
        if witness['rank']!=len(terms):raise ValueError('source opposite-pair columns are not all independent')
        # The selected coordinate rows form an independently rechecked square
        # full-rank minor; source columns are regenerated from the source hash.
        restricted=[sum(((value>>row)&1)<<i for i,row in enumerate(witness['pivot_rows'])) for value in columns]
        if gf2_rank(restricted)!=len(terms):raise ValueError('pair-column minor witness differs')
        witnesses.append({'free_axis':axis,'opposite_axes':other,'column_count':len(terms),'pair_width':[width,width],**witness})
    return witnesses


def literal_terms(source):
    n=source['dimension'];terms=[]
    for term in source['terms']:
        if set(term)!=set(('u','v','w')):raise ValueError('literal term schema differs')
        values=[]
        for axis in ('u','v','w'):
            vector=term[axis]
            if len(vector)!=n*n or any(type(bit) is not int or bit not in (0,1) for bit in vector):raise ValueError('literal binary factors required')
            value=sum(bit<<i for i,bit in enumerate(vector))
            if not value:raise ValueError('zero factor in essential source')
            values.append(value)
        terms.append(tuple(values))
    if len(terms)!=len(set(terms)):raise ValueError('duplicate essential source products')
    return terms


def packet_family(terms,n,guard=lambda *_:None):
    width=n*n;lookup={term:i for i,term in enumerate(terms)};cubes=[];orbits={}
    for i,term in enumerate(terms):
        u,v,w=term;rotations={(u,v,w),(v,w,u),(w,u,v)}
        if not rotations<=lookup.keys():raise ValueError('source is not closed under full C3 orbits')
        if len(rotations)==1:cubes.append(i)
        else:orbits[min(rotations)]=sorted(lookup[member] for member in rotations)
    if len(cubes)!=3:raise ValueError('packet family requires exactly three source cubes')
    orbit_indices=[orbits[key] for key in sorted(orbits)];pair_witnesses=source_pair_witnesses(terms,width)
    tensors=[packed_tensor(term,width) for term in terms];records=[];counts=collections.Counter();retained_checks=0
    for ordinal,(left,right) in enumerate(combinations(range(len(orbit_indices)),2)):
        guard('loop');indices=sorted(cubes+orbit_indices[left]+orbit_indices[right])
        if len(indices)!=9 or len(set(indices))!=9:raise ValueError('packet must be exactly nine distinct source products')
        factors_by_axis=[{terms[i][axis] for i in indices} for axis in range(3)]
        if factors_by_axis[0]!=factors_by_axis[1] or factors_by_axis[1]!=factors_by_axis[2]:raise ValueError('C3 packet factor sets differ between modes')
        basis=BinaryBasis(sorted(factors_by_axis[0]));d=len(basis.vectors);factor_witness=rank_witness([terms[i][0] for i in indices])
        if factor_witness['rank']!=d:raise ValueError('shared factor-rank witness differs')
        target=8
        branch='FLATTENING_EXCLUDED' if d>target else 'CP(d)' if d==8 else 'CP(d+1)' if d==7 else 'CP(d+2)' if d==6 else 'DEFER_REVIEWED_BACKBONE_REQUIRED'
        mask=sum(1<<i for i in indices);record={'id':f'c3-mixed9-p{left:02}-{right:02}','ordinal':ordinal,'source_indices':indices,'term_mask_lo':mask&((1<<64)-1),'term_mask_hi':mask>>64,'orbit_mask_hex':hex((1<<left)|(1<<right)),'nonfixed_orbit_pair':[left,right],'shared_mode_basis':basis.vectors,
            'branch_metadata':{'local_products':9,'target_local_products':8,'outside_products':len(terms)-9,'target_global_products':len(terms)-1,'mode_shape':[d,d,d],'d':d,'branch':branch,'free_axis':0,'same_factor_span_all_modes':True,'source_pair_independence_reused':True,
            'factor_rank_witness':factor_witness,'actual_unfolding_ranks_by_independent_pair_columns':[d,d,d],'pilot_eligible_reviewed_route':d in (7,8),'unreviewed_rank2_span_lower_bound_called':False}}
        if d>8:
            record['branch_metadata'].update(status='FLATTENING_EXCLUDED',reason='Exact unfolding rank exceeds target8; this chosen residual cannot have rank<=8.')
        else:
            core_mask=0
            for i in indices:
                coords=tuple(basis.coordinates(value,require_member=True) for value in terms[i])
                if tuple(basis.expand(value) for value in coords)!=terms[i]:raise ValueError('mode-coordinate lift changed source factor')
                core_mask^=packed_tensor(coords,d)
            core=[(core_mask>>i)&1 for i in range(d**3)];ambient=0
            for i in indices:ambient^=tensors[i]
            if expand_core(core,[d,d,d],[basis.vectors]*3,width)!=ambient:raise ValueError('retained actual core fails full ambient expansion')
            actual=[gf2_rank(mode_slices(core,[d,d,d],axis)[0]) for axis in range(3)]
            if actual!=[d,d,d]:raise ValueError('retained actual core mode ranks differ from factor ranks')
            record['branch_metadata'].update(status='RETAINED_METADATA_ONLY',actual_core_mode_ranks=actual,ambient_entries_checked=width**3,core_entries_checked=d**3,
                ambient_sha256=sha_bytes(ambient.to_bytes((width**3+7)//8,'little')),actual_core_sha256=sha_bytes(bytes(core)),core_storage='Not stored; reconstruct from pinned source, indices and common mode basis.')
            retained_checks+=1
        counts[str(d)]+=1;records.append(record)
    return {'source_order':'0-based original JSON term order, not sorted term order','cube_source_indices':sorted(cubes),'nonfixed_orbit_source_indices':orbit_indices,'nonfixed_orbit_order':'Lexicographic minimum literal triple under the three cyclic rotations','pair_column_witnesses':pair_witnesses,'packets':records,'dimension_counts':dict(sorted(counts.items())),'packet_count':len(records),'retained_actual_core_checks':retained_checks}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--expected-config-sha256',required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--authorize-preparation',action='store_true');p.add_argument('--preview',action='store_true');a=p.parse_args(argv)
    if not a.authorize_preparation:p.error('explicit metadata-only packet preparation authorization required')
    started=time.monotonic();cpu_started=time.process_time()
    if sha(a.config)!=a.expected_config_sha256:raise ValueError('configuration pin differs')
    config=read(a.config);campaign=Path(config['campaign']);out=a.output_dir.resolve();source_path=Path(config['source'])
    if out.exists() or not out.is_relative_to(campaign) or (config['cpu'],config['nice'],config['memory_mib'],config['seconds'],config['output_bytes'])!=(0,10,512,60,CAP):raise ValueError('new output/exact authorized envelope required')
    if sha(source_path)!=SOURCE_SHA or sha(campaign/'tensor-code-source-anchors-v1/manifest.json')!=ANCHOR_SHA or sha(campaign/'root-review-decisions/tensor-code-source-anchors-approved.json')!=ELIGIBILITY_SHA:raise ValueError('approved source/root input pin differs')
    source_meta=read(campaign/'tensor-code-source-anchors-v1/manifest.json');approved=next(item for item in source_meta['known_input_train_states'] if item['sha256']==SOURCE_SHA)
    if not all(approved.get(key) is True for key in ['root_approved_train','heldout_excluded','evaluation_excluded']):raise ValueError('source is not the explicit train root')
    os.sched_setaffinity(0,{0});os.setpriority(os.PRIO_PROCESS,0,10);resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP));resource.setrlimit(resource.RLIMIT_CORE,(0,0));guard=lifecycle.Guard(DEADLINE,60,campaign,campaign/'operations-v3/state.json',config['campaign_sha256']);guard('pre_preparation')
    for name,digest in config['runtime_code_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('frozen runtime changed: '+name)
    if a.preview:print(json.dumps({'status':'PREVIEW_ONLY','zero_mutations':True,'packets_generated':0,'decoder_calls':0,'source_sha256':SOURCE_SHA},sort_keys=True));return 0
    out.mkdir();progress={'stage':'source_validation'}
    def strict(name):
        guard(name)
        if sum(path.stat().st_size for path in out.rglob('*') if path.is_file())>CAP:raise lifecycle.Stop('aggregate32MiB output cap')
    def save(name,value):
        payload=raw(value);strict('pre_publication')
        if sum(path.stat().st_size for path in out.rglob('*') if path.is_file())+len(payload)>CAP:raise lifecycle.Stop('aggregate32MiB output cap')
        with (out/name).open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        strict('post_publication')
    def alarm(*_):raise lifecycle.Stop('60s hard metadata preparation alarm')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,max(.001,60-(time.monotonic()-started)))
    try:
        source_raw=source_path.read_bytes();source=lifecycle.strict_load(source_raw);first=verify_candidate(source,random_trials=0);strict('post_source_primary_full15625');second=verify_bytes(source_raw);strict('post_source_strict_independent_full15625')
        if not first['valid'] or not second['valid'] or first['exact_entries_checked']!=15625 or second['exact_entries_checked']!=15625 or second['essential_rank']!=93:raise ValueError('source full tensor/exact93 differs')
        terms=literal_terms(source)
        if len(terms)!=93 or source['dimension']!=5 or source['field']!=2:raise ValueError('only approved literal n5F2 rank93 source')
        strict('pre_packet_census');progress['stage']='packet_census_and_core_checks';catalog=packet_family(terms,5,lambda _='loop':guard('loop'));strict('post_packet_census_and_core_checks')
        if catalog['packet_count']!=435 or len(catalog['nonfixed_orbit_source_indices'])!=30 or len(catalog['cube_source_indices'])!=3:raise ValueError('literal435 packet family differs')
        for record in catalog['packets']:record['source_sha256']=SOURCE_SHA
        catalog.update(format='c3-mixed9-packet-catalog-v1',source={'path':str(source_path),'raw_sha256':SOURCE_SHA,'source_manifest_sha256':ANCHOR_SHA,'root_eligibility_sha256':ELIGIBILITY_SHA,'essential_products':93,'primary_full_entries_checked':15625,'independent_full_entries_checked':15625},family={'all_cubes':3,'nonfixed_orbits_selected':2,'nonfixed_orbit_count':30,'combinations':435,'local_products':9,'target_products':8,'outside_products':84,'index_order':catalog['source_order'],'no_decoder_called':True})
        eligible=[item for item in catalog['packets'] if item['branch_metadata']['pilot_eligible_reviewed_route']]
        eligible.sort(key=lambda item:(item['branch_metadata']['d'],item['ordinal']));selected=eligible[:25]
        pilot={'format':'c3-mixed9-first25-pilot-proposal-v1','status':'DISABLED_PROPOSAL_ONLY_REQUIRES_ROOT_REVIEW','enabled':False,'decoder_launch_authorized':False,'source_sha256':SOURCE_SHA,'case_ids':[item['id'] for item in selected],'cases':[{'id':item['id'],'source_indices':item['source_indices'],'orbit_mask_hex':item['orbit_mask_hex'],'mode_shape':item['branch_metadata']['mode_shape'],'route':item['branch_metadata']['branch'],'shared_mode_basis':item['shared_mode_basis'],'free_axis':0,'local_products':9,'target_local_products':8,'outside_products':84} for item in selected],
            'case_count':len(selected),'selection_rule':'Reviewed-route d7 first then d8; source-orbit lexicographic pair order within dimension; no outcomes used. d6 awaits separately reviewed CP(d+2) machinery; d<=5 defers.','proposed_limits':{'cpu':0,'nice':10,'memory_mib':512,'total_wall_seconds':60,'per_case_wall_seconds':2,'max_pair_vectors':65535,'hard_deadline':DEADLINE},'gates':['Regenerate and recheck source, exact selected residual, ambient/core equality and all mode ranks from metadata.','Use reviewed CP(d) or CP(d+1) backend only. No unreviewed rank2-span lower bound is wired.','Late/capped returns remain UNKNOWN. Exact full15625 primary+strict-independent checks on persisted global candidates and fresh post-call guard checks precede any global-guard record handoff.','Any finite negative applies only to this literal9-to8 packet with outside84 frozen; no global rank lower bound.']}
        save('catalog.json',catalog);save('pilot-proposal.json',pilot)
        for name,digest in config['runtime_code_sha256'].items():
            if sha(ROOT/name)!=digest:raise ValueError('runtime changed during preparation')
        if sha(source_path)!=SOURCE_SHA or sha(a.config)!=a.expected_config_sha256:raise ValueError('source/config changed during preparation')
        strict('pre_manifest');branches=collections.Counter(record['branch_metadata']['branch'] for record in catalog['packets']);manifest={'format':'c3-mixed9-packet-preparation-v1','status':'PREPARED_METADATA_NO_DECODER','source':catalog['source'],'family':catalog['family'],'packet_count':435,'dimension_counts':catalog['dimension_counts'],'branch_counts':dict(branches),'retained_actual_core_checks':catalog['retained_actual_core_checks'],'retained_ambient_entries_checked':15625*catalog['retained_actual_core_checks'],'pair_column_ranks':[item['rank'] for item in catalog['pair_column_witnesses']],'pilot_case_count':len(selected),'catalog_sha256':sha(out/'catalog.json'),'pilot_proposal_sha256':sha(out/'pilot-proposal.json'),'runtime_code_sha256':config['runtime_code_sha256'],'config_sha256':a.expected_config_sha256,'runtime':lifecycle.runtime(),'guard':guard.observation(),'elapsed_seconds':time.monotonic()-started,'process_cpu_seconds':time.process_time()-cpu_started,'decoder_calls':0,'solver_calls':0,'unreviewed_helper_calls':0,'koszul_calls':0,'private_eval_payloads_read':0}
        save('manifest.json',manifest);save('checksums.json',{str(path.relative_to(out)):sha(path) for path in out.rglob('*') if path.is_file()});save('COMPLETE.json',{'manifest_sha256':sha(out/'manifest.json'),'checksums_sha256':sha(out/'checksums.json'),'acceptance':'Require matching pins and no UNKNOWN.json; metadata preparation does not authorize decoders.'})
        for path in out.rglob('*'):
            if path.is_file():path.chmod(0o444)
        print(json.dumps({key:manifest[key] for key in ['status','packet_count','dimension_counts','branch_counts','retained_actual_core_checks','pilot_case_count','elapsed_seconds','process_cpu_seconds']},sort_keys=True));return 0
    except Exception as error:
        failure={'status':'UNKNOWN_PACKET_PREPARATION','reason':type(error).__name__+': '+str(error),'progress':progress,'decoder_calls':0,'solver_calls':0}
        with (out/'UNKNOWN.json').open('xb') as stream:stream.write(raw(failure))
        print(json.dumps(failure,sort_keys=True));return 2
    finally:signal.setitimer(signal.ITIMER_REAL,0)

if __name__=='__main__':raise SystemExit(main())
