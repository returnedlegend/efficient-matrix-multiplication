"""Explicitly authorized, bounded n5 C3 dictionary/rank audit; no optimization.

The tiny module's n5 constructor remains disabled. This wrapper alone builds
n5 orbit columns after immutable preparation and complete source replay gates.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from mmsearch import cyclic_tensor_code7 as c
from scripts import tensor_code7 as base
from scripts.verify_record42_independent import verify_bytes
from mmsearch.verify import verify_candidate

PREPARED_SHA='cf4644cab66d697f05d6724d919973b9884f17def9586c0e1220b9ea67554e2b'
ANCHOR_SHA='26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8'
SEED_SHA='56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b'
OUTPUT_CAP=32*1024**2
DEADLINE='2026-11-03T19:24:17Z'


def sha(raw):return hashlib.sha256(raw).hexdigest()
def raw(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def read(path):return base.strict_load(Path(path).read_bytes())


def independent_orbit_tensor(members,width):
    """Evaluate every input basis pair's complete trace-output bit row."""
    full=0
    for first in range(width):
        for second in range(width):
            row=0
            for u,v,w in members:
                if ((u>>first)&1) and ((v>>second)&1):row^=w
            full|=row<<(width*(width*first+second))
    return full


def kernel_rank(columns,guard=lambda *_:None):
    basis={};kernel=[]
    for index,column in enumerate(columns):
        guard('column_elimination');witness=1<<index
        while column:
            pivot=column.bit_length()-1
            if pivot not in basis:
                basis[pivot]=(column,witness);break
            previous,mask=basis[pivot];column^=previous;witness^=mask
        if not column:kernel.append(witness)
    for witness in kernel:
        guard('kernel_witness_check')
        if c.xor_columns(columns,witness):raise ValueError('nonzero kernel witness syndrome')
    return len(basis),tuple(kernel)


def audit_columns(atoms,seed_terms,n,guard=lambda *_:None,max_orbits=2000,progress=None):
    progress={} if progress is None else progress
    progress.update(stage='orbit_columns',independently_checked_columns=0)
    representatives=c.orbit_representatives(atoms,n,max_orbits=max_orbits);width=n*n
    full=[];compressed=[];weights=[];members=[]
    for representative in representatives:
        guard('pre_orbit_column');expanded=c.orbit(representative,n);column=c.orbit_tensor(representative,n)
        independent=independent_orbit_tensor(expanded,width)
        if column!=independent:raise ValueError('independent full orbit tensor differs')
        selected=c.compress_invariant(column,width)
        if c.expand_invariant(selected,width)!=column:raise ValueError('orbit projection/inverse differs')
        full.append(column);compressed.append(selected);weights.append(len(expanded));members.append(expanded);progress['independently_checked_columns']=len(full);guard('post_orbit_column')
    if len({term for group in members for term in group})!=sum(weights):raise ValueError('distinct whole orbits overlap')
    target=c.target_tensor(n);compressed_target=c.compress_invariant(target,width)
    if c.expand_invariant(compressed_target,width)!=target:raise ValueError('target projection/inverse differs')
    normalized=[c.validate_atom(term,n) for term in seed_terms]
    if len(set(normalized))!=len(normalized):raise ValueError('seed has duplicate products')
    lookup={representative:index for index,representative in enumerate(representatives)}
    selected={c.orbit_representative(term,n) for term in normalized}
    if not selected<=lookup.keys():raise ValueError('exact seed orbit missing from approved dictionary')
    seed=sum(1<<lookup[term] for term in selected);expanded_seed=sorted(term for index in c._bits(seed) for term in members[index])
    if expanded_seed!=sorted(normalized):raise ValueError('seed orbit closure/expansion differs')
    cost=sum(weights[index] for index in c._bits(seed))
    if cost!=len(normalized) or c.xor_columns(full,seed)!=target or c.xor_columns(compressed,seed)!=compressed_target:raise ValueError('seed exactness/cost differs')
    progress['stage']='full_column_elimination'
    full_rank,full_kernel=kernel_rank(full,guard);progress['full_rank']=full_rank;progress['stage']='compressed_column_elimination'
    compressed_rank,kernel=kernel_rank(compressed,guard)
    if full_rank!=compressed_rank or len(full_kernel)!=len(kernel) or full_rank+len(kernel)!=len(full):raise ValueError('full/compressed rank-nullity differs')
    for witness in kernel:
        if c.xor_columns(full,witness):raise ValueError('compressed kernel fails full tensor')
    for witness in full_kernel:
        if c.xor_columns(compressed,witness):raise ValueError('full kernel fails compressed tensor')
    # Every generated relation has its unique newest dependent-column bit, hence
    # is independent; confirm explicitly with a second elimination on masks.
    witness_rank,_=kernel_rank(kernel,guard)
    if witness_rank!=len(kernel):raise ValueError('dependent kernel basis')
    movable=0
    for witness in kernel:movable|=witness
    cubes=[{'column':index,'factor_mask':representative[0],'seed_selected':bool((seed>>index)&1),'forced':not bool((movable>>index)&1),'forced_value':((seed>>index)&1) if not ((movable>>index)&1) else None} for index,representative in enumerate(representatives) if weights[index]==1]
    odd=[index for index,witness in enumerate(kernel) if witness.bit_count()%2]
    report={'dictionary_orbits':len(representatives),'cube_orbits':len(cubes),'nonfixed_orbits':len(representatives)-len(cubes),'expanded_distinct_products':sum(weights),'full_tensor_entries':width**3,'invariant_coordinates':len(c.coordinate_orbits(width)),
            'full_rank':full_rank,'compressed_rank':compressed_rank,'nullity':len(kernel),'independent_kernel_rank':witness_rank,'dictionary_independent_entries_checked':len(full)*width**3,'dictionary_projection_inverse_entries_checked':len(full)*width**3,
            'seed_orbits':seed.bit_count(),'seed_cubes':sum(weights[index]==1 for index in c._bits(seed)),'seed_nonfixed_orbits':sum(weights[index]==3 for index in c._bits(seed)),'seed_product_cost':cost,'seed_full_syndrome_mismatches':(c.xor_columns(full,seed)^target).bit_count(),
            'kernel_parity':{'all_weights_odd':all(weight%2 for weight in weights),'seed_cost_parity':cost%2,'odd_basis_vectors':len(odd),'odd_basis_indices':odd,'can_change_cost_parity':bool(odd),'interpretation':'Odd kernel vector is necessary to reach exactly even cost92 from odd cost93. If all kernel vectors are even, <=92 may still mean odd cost<=91; this is not an impossibility proof for <=92.'},
            'cube_variables':cubes,'forced_cube_variables':sum(item['forced'] for item in cubes),'forced_cube_ones':sum(item['forced_value']==1 for item in cubes),'forced_cube_zeros':sum(item['forced_value']==0 for item in cubes),
            'forced_all_variables':len(full)-movable.bit_count(),'packed_full_columns_bytes':sum((x.bit_length()+7)//8 for x in full),'packed_compressed_columns_bytes':sum((x.bit_length()+7)//8 for x in compressed),'packed_kernel_bytes':sum((x.bit_length()+7)//8 for x in kernel)}
    dictionary={'format':'cyclic-orbit-code7-audit-dictionary-v1','dimension':n,'field':2,'representatives':[list(term) for term in representatives],'weights':weights,'full_columns_hex':[hex(x) for x in full],'compressed_columns_hex':[hex(x) for x in compressed],'compressed_target_hex':hex(compressed_target),'target_hex':hex(target),'seed_state_hex':hex(seed),'kernel_hex':[hex(x) for x in kernel],'rank':full_rank,'nullity':len(kernel),'scope':'Finite approved whole-orbit dictionary only; no optimization performed.'}
    return dictionary,report


def inner_phase_guard(guard):
    # Keep the canonical guard's normal <=0.1s polling and every-call time/signal
    # checks. Stage boundaries and publications still request forced freshness.
    return lambda _name='loop':guard('loop')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['prepared','manifest','approved-root','root-eligibility','campaign-dir','guard-state','output-dir']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--root-eligibility-sha256',required=True);parser.add_argument('--authorize-n5-audit',action='store_true');parser.add_argument('--preview',action='store_true');args=parser.parse_args(argv)
    if not args.authorize_n5_audit:parser.error('explicit --authorize-n5-audit required; no optimization authorization exists')
    started=time.monotonic();cpu_started=time.process_time();out=args.output_dir.resolve();campaign=args.campaign_dir.resolve()
    if out.exists() or not out.is_relative_to(campaign):raise ValueError('new campaign-contained output directory required')
    if sha(args.prepared.read_bytes())!=PREPARED_SHA or sha(args.manifest.read_bytes())!=ANCHOR_SHA or sha(args.root_eligibility.read_bytes())!=args.root_eligibility_sha256:raise ValueError('root-approved immutable input pin differs')
    document=read(args.prepared);approval=read(args.root_eligibility)
    if approval.get('owner')!='root' or approval.get('approved_manifest_sha256')!=ANCHOR_SHA or approval.get('approved_source_count')!=32 or set(approval.get('approved_groups',[]))!={'anchors','known_input_train_states'} or approval.get('heldout_evaluation_excluded') is not True:raise ValueError('root source eligibility differs')
    if document['dictionary_size']!=406 or len(document['sources'])!=32 or document['source_manifest_sha256']!=ANCHOR_SHA:raise ValueError('approved base dictionary/source count differs')
    if args.prepared.stat().st_mode&0o222:raise ValueError('base prepared bytes must be immutable')
    lifecycle=document['lifecycle_config'];config_raw=(campaign/'campaign.json').read_bytes()
    if str(campaign)!=lifecycle['campaign_dir'] or sha(config_raw)!=lifecycle['campaign_sha256'] or str(args.guard_state.resolve())!=lifecycle['guard_state']:raise ValueError('base campaign/guard binding differs')
    guard=base.Guard(DEADLINE,30,campaign,args.guard_state,lifecycle['campaign_sha256'])
    guard('pre_audit')
    code_names=['scripts/audit_cyclic_tensor_code7.py','mmsearch/cyclic_tensor_code7.py','tests/test_cyclic_tensor_code7.py','tests/test_audit_cyclic_tensor_code7.py','scripts/verify_record42_independent.py']
    code={name:sha((ROOT/name).read_bytes()) for name in code_names}
    for name,digest in document['code_sha256'].items():
        if sha((ROOT/name).read_bytes())!=digest:raise ValueError('base replay code changed: '+name)
    if args.preview:
        print(json.dumps({'status':'PREVIEW_ONLY','zero_mutations':True,'matrix_builds':0,'solver_calls':0,'seconds':30,'cpu':1,'nice':10,'memory_mib':1024,'output_mib':32,'hard_deadline':DEADLINE,'prepared_sha256':PREPARED_SHA,'source_manifest_sha256':ANCHOR_SHA,'root_eligibility_sha256':args.root_eligibility_sha256},sort_keys=True));return 0
    os.sched_setaffinity(0,{1});os.setpriority(os.PRIO_PROCESS,0,10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(OUTPUT_CAP,OUTPUT_CAP))
    out.mkdir(parents=True);writes=0
    def barrier(name='loop'):
        guard(name)
        if sum(path.stat().st_size for path in out.rglob('*') if path.is_file())>OUTPUT_CAP:raise base.Stop('32MiB aggregate output cap')
    def save(name,value):
        nonlocal writes
        payload=value if isinstance(value,bytes) else raw(value);barrier('pre_write')
        used=sum(path.stat().st_size for path in out.rglob('*') if path.is_file())
        if used+len(payload)>OUTPUT_CAP:raise base.Stop('32MiB aggregate output cap')
        path=out/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(payload)
        writes+=len(payload);barrier('post_write')
    def alarm(_signal,_frame):raise base.Stop('30s hard audit alarm')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,max(.001,30-(time.monotonic()-started)))
    status='UNKNOWN_AUDIT_NOT_COMPLETED';report={};progress={'stage':'source_replay_not_started'};inner_guard=inner_phase_guard(guard)
    try:
        for name in code:save('code/'+name,(ROOT/name).read_bytes())
        replay_args=SimpleNamespace(manifest=args.manifest,manifest_sha256=ANCHOR_SHA,approved_root=args.approved_root,prepared=args.prepared,outdir=out)
        # Base replay's temporary bytes are a deterministic copy of its immutable
        # inputs tree; preflight the peak instead of rescanning it per inner step.
        replay_bytes=sum(p.stat().st_size for p in (args.prepared.parent/'inputs').rglob('*') if p.is_file())
        existing_bytes=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
        if replay_bytes+existing_bytes+65536>OUTPUT_CAP:raise base.Stop('preflight replay output cap')
        progress['stage']='source_replay';barrier('pre_complete_32_source_replay')
        base.verify_source_binding(replay_args,document,inner_guard);barrier('post_complete_32_source_replay')
        progress.update(stage='seed_verification',replayed_sources=32,replay_input_bytes=replay_bytes)
        # The root group supplies seed56e2dc; never look through other directories.
        source=next(item for item in document['sources'] if item['sha256']==SEED_SHA)
        if source['source_group']!='native_initial_train' or source['ancestor_ids']!=[source['root_id']]:raise ValueError('C3 seed is not the approved native train root')
        seed_raw=(args.prepared.parent/source['snapshot']).read_bytes()
        if sha(seed_raw)!=SEED_SHA:raise ValueError('seed source byte pin differs')
        save('seed-source.json',seed_raw);persisted=(out/'seed-source.json').read_bytes();seed_candidate=base.strict_load(persisted)
        first=verify_candidate(seed_candidate,random_trials=0);barrier('post_seed_primary_full15625')
        second=verify_bytes(persisted);barrier('post_seed_independent_full15625')
        if not first['valid'] or not second['valid'] or first['exact_entries_checked']!=15625 or second['exact_entries_checked']!=15625 or second['essential_rank']!=93:raise ValueError('known source exactness/rank differs')
        seed_terms=[tuple(sum(bit<<i for i,bit in enumerate(term[axis])) for axis in ('u','v','w')) for term in seed_candidate['terms']]
        dictionary,report=audit_columns([tuple(term) for term in document['atoms']],seed_terms,5,inner_guard,max_orbits=2000,progress=progress)
        barrier('post_orbit_rank_audit')
        if report['seed_orbits']!=33 or report['seed_cubes']!=3 or report['seed_nonfixed_orbits']!=30 or report['seed_product_cost']!=93:raise ValueError('known seed orbit inventory differs')
        dictionary.update(base_prepared_sha256=PREPARED_SHA,source_manifest_sha256=ANCHOR_SHA,root_eligibility_sha256=args.root_eligibility_sha256,seed_source_sha256=SEED_SHA)
        save('dictionary.json',dictionary);save('seed-verification.json',{'primary':first,'independent':second})
        for name,digest in {**document['code_sha256'],**code}.items():
            if sha((ROOT/name).read_bytes())!=digest:raise ValueError('runtime code changed during audit')
        if sha(args.prepared.read_bytes())!=PREPARED_SHA or sha(args.manifest.read_bytes())!=ANCHOR_SHA or sha(args.root_eligibility.read_bytes())!=args.root_eligibility_sha256:raise ValueError('source configuration changed during audit')
        barrier('post_persisted_dictionary_and_pins');status='PREPARED_DICTIONARY_AUDIT_ONLY'
        report.update(wrapper_version=2,format='cyclic-orbit-code7-production-audit-v1',status=status,optimization_calls=0,solver_calls=0,decoding_search_calls=0,private_eval_payloads_read=0,replayed_sources=32,
            base_prepared_sha256=PREPARED_SHA,source_manifest_sha256=ANCHOR_SHA,root_eligibility_sha256=args.root_eligibility_sha256,seed_source_sha256=SEED_SHA,
            dictionary_sha256=sha((out/'dictionary.json').read_bytes()),code_sha256=code,base_replay_code_sha256=document['code_sha256'],
            runtime=base.runtime(),elapsed_seconds=time.monotonic()-started,process_cpu_seconds=time.process_time()-cpu_started,guard=guard.observation(),output_bytes_before_manifest=sum(p.stat().st_size for p in out.rglob('*') if p.is_file()),
            seed_inventory_correction='Known seed is33 orbits=30 nonfixed*3+3 cubes*1=93 products, not31 orbits.',scope='Finite approved cyclic whole-orbit dictionary. No minimum-weight calculation, optimization or negative bound established.')
        save('manifest.json',report);barrier('post_manifest');save('checksums.json',{str(p.relative_to(out)):sha(p.read_bytes()) for p in out.rglob('*') if p.is_file()});barrier('final_audit_barrier')
        save('COMPLETE.json',{'status':'PREPARED_DICTIONARY_AUDIT_ONLY','manifest_sha256':sha((out/'manifest.json').read_bytes()),'checksums_sha256':sha((out/'checksums.json').read_bytes()),'acceptance':'Require this seal and absence of UNKNOWN.json; no optimization authorization.'})
        for path in out.rglob('*'):
            if path.is_file():path.chmod(0o444)
        print(json.dumps({key:report[key] for key in ['status','dictionary_orbits','cube_orbits','full_rank','compressed_rank','nullity','seed_orbits','seed_product_cost','kernel_parity','forced_cube_variables','elapsed_seconds','process_cpu_seconds']},sort_keys=True));return 0
    except base.Stop as error:
        # Retain partial bytes without claiming completed preparation after a stop.
        failure={'status':'UNKNOWN_STOPPED_AUDIT','reason':str(error),'optimization_calls':0,'solver_calls':0,'decoding_search_calls':0,'elapsed_seconds':time.monotonic()-started,'partial_counts':report or progress}
        payload=raw(failure)
        if sum(p.stat().st_size for p in out.rglob('*') if p.is_file())+len(payload)<=OUTPUT_CAP:
            with (out/'UNKNOWN.json').open('xb') as stream:stream.write(payload)
        print(json.dumps(failure,sort_keys=True));return 2
    finally:signal.setitimer(signal.ITIMER_REAL,0)

if __name__=='__main__':raise SystemExit(main())
