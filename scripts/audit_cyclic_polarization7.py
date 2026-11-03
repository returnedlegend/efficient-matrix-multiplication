"""One explicitly authorized, bounded C3 polarization dictionary audit only."""
from __future__ import annotations
import argparse
import hashlib
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
from mmsearch import cyclic_tensor_code7 as c
from mmsearch.cube_polarization import polarize_cubes
from mmsearch.cyclic_tensor_polarization7 import projected_diagnostics,gf2_rank
from scripts.audit_cyclic_tensor_code7 import audit_columns,raw
from scripts import tensor_code7 as lifecycle
from scripts.verify_record42_independent import verify_bytes
from mmsearch.verify import verify_candidate

DICT_SHA='23ff2b7ef344b79277712731cdc80ecc4b030a82026ca77d9fec32a02ebd047b'
MANIFEST_SHA='eb6337722adaf26ecc3e11795cc94865c2a556db7af70d4efd83b917bb0a392b'
HELPER_SHA='988488ad2992143b872495fde672538c6d03a99b6767e96040e16a5201140d79'
ANCHOR_SHA='26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8'
ELIGIBILITY_SHA='7354183ab6e9c89f76110e1c916738ced4856499632a2f317508b1d6bea7bb55'
CAP=32*1024**2
DEADLINE='2026-11-03T19:24:17Z'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return lifecycle.strict_load(Path(path).read_bytes())
def as_candidate(terms,n):
    return {'field':2,'dimension':n,'terms':[{axis:[(value>>i)&1 for i in range(n*n)] for axis,value in zip(('u','v','w'),term)} for term in sorted(terms)]}


def materialize(old_representatives,seed_terms,pair,n,guard=lambda *_:None,*,authorize_n5=False,progress=None):
    if n==5 and not authorize_n5:raise ValueError('n5 extension requires explicit audit authorization')
    a,b=pair
    if type(a) is not int or type(b) is not int or not a or not b or a==b:raise ValueError('distinct nonzero cube masks required')
    c.validate_atom((a,a,a),n);c.validate_atom((b,b,b),n)
    old=tuple(tuple(term) for term in old_representatives);oldset=set(old)
    added=tuple(c.orbit_representative(term,n) for term in [(a^b,a^b,a^b),(a,a,b),(a,b,b)])
    if len(set(added))!=3 or oldset&set(added):raise ValueError('exactly three absent orbit columns required')
    if (a,a,a) not in seed_terms or (b,b,b) not in seed_terms:raise ValueError('selected seed cubes absent')
    dictionary,report=audit_columns(old+added,seed_terms,n,guard,max_orbits=278,progress=progress)
    representatives=[tuple(term) for term in dictionary['representatives']];lookup={term:i for i,term in enumerate(representatives)}
    relation_terms=((a,a,a),(b,b,b),*added);relation=sum(1<<lookup[term] for term in relation_terms)
    full=[int(value,16) for value in dictionary['full_columns_hex']];compressed=[int(value,16) for value in dictionary['compressed_columns_hex']]
    if relation.bit_count()!=5 or c.xor_columns(full,relation) or c.xor_columns(compressed,relation):raise ValueError('odd5 polarization witness is not exact zero')
    seed=int(dictionary['seed_state_hex'],16);polarized=seed^relation;expanded=tuple(sorted(term for i in c._bits(polarized) for term in c.orbit(representatives[i],n)))
    reused=tuple(sorted(polarize_cubes(seed_terms,a,b)))
    if expanded!=reused:raise ValueError('unchanged cube_polarization helper disagrees with orbit witness')
    weights=dictionary['weights'];cost=sum(weights[i] for i in c._bits(polarized));cubes=[i for i,w in enumerate(weights) if w==1];kernel=[int(value,16) for value in dictionary['kernel_hex']]
    generators=[(sum(((value>>index)&1)<<p for p,index in enumerate(cubes)),value.bit_count()%2) for value in kernel]
    cube_seed=sum(((seed>>index)&1)<<p for p,index in enumerate(cubes));diagnostic=projected_diagnostics(len(cubes),cube_seed,seed.bit_count()%2,generators)
    report.update(added_columns=3,added_representatives=[list(term) for term in added],new_column_indices=[lookup[term] for term in added],old_to_new_column_map=[lookup[term] for term in old],pair=list(pair),sum_cube=a^b,
        known_zero_relation_hex=hex(relation),known_zero_relation_orbits=relation.bit_count(),known_zero_relation_expanded_products=sum(weights[i] for i in c._bits(relation)),polarized_cost=cost,polarized_selected_orbits=polarized.bit_count(),polarized_cubes=sum((polarized>>i)&1 for i in cubes),
        polarized_nonfixed_orbits=sum((polarized>>i)&1 for i,w in enumerate(weights) if w==3),new_column_independent_entries_checked=3*(n**6),cube_factor_rank=gf2_rank(representatives[i][0] for i in cubes),joint_complete_kernel_projection=diagnostic)
    dictionary.update(polarization_pair=list(pair),polarization_relation_hex=hex(relation),polarized_state_hex=hex(polarized))
    return dictionary,report,expanded


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['config','output-dir']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--expected-config-sha256',required=True);p.add_argument('--authorize-n5-audit',action='store_true');p.add_argument('--preview',action='store_true');a=p.parse_args(argv)
    if not a.authorize_n5_audit:p.error('explicit authorization required; this grants no solver/optimization permission')
    start=time.monotonic();cpu_start=time.process_time()
    if sha(a.config)!=a.expected_config_sha256:raise ValueError('frozen audit configuration differs')
    config=read(a.config);campaign=Path(config['campaign']);base=Path(config['base_audit']);out=a.output_dir.resolve()
    if out.exists() or not out.is_relative_to(campaign) or config['pair']!=[4096,262208] or config['sum_cube']!=266304:raise ValueError('new output/exact pair required')
    if (config['cpu'],config['nice'],config['memory_mib'],config['seconds'],config['output_bytes'],config['max_columns'],config['max_expanded_products'])!=(3,10,1024,30,CAP,278,826):raise ValueError('authorized envelope differs')
    os.sched_setaffinity(0,{3});os.setpriority(os.PRIO_PROCESS,0,10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    guard=lifecycle.Guard(DEADLINE,30,campaign,campaign/'operations-v3/state.json',config['campaign_sha256']);guard('pre_extension_input')
    if sha(base/'dictionary.json')!=DICT_SHA or sha(base/'manifest.json')!=MANIFEST_SHA or (base/'UNKNOWN.json').exists():raise ValueError('approved sealed dictionary differs')
    seal=read(base/'COMPLETE.json')
    if seal['manifest_sha256']!=MANIFEST_SHA or sha(base/'checksums.json')!=seal['checksums_sha256']:raise ValueError('base completion seal differs')
    for name,digest in read(base/'checksums.json').items():
        if sha(base/name)!=digest:raise ValueError('base package hash differs')
    if sha(ROOT/'mmsearch/cube_polarization.py')!=HELPER_SHA:raise ValueError('unchanged polarization helper differs')
    if sha(campaign/'tensor-code-source-anchors-v1/manifest.json')!=ANCHOR_SHA or sha(campaign/'root-review-decisions/tensor-code-source-anchors-approved.json')!=ELIGIBILITY_SHA:raise ValueError('root source eligibility pin differs')
    for name,digest in config['runtime_code_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('frozen runtime differs: '+name)
    if a.preview:print(json.dumps({'status':'PREVIEW_ONLY','zero_mutations':True,'n5_columns_generated':0,'solver_calls':0,'config_sha256':a.expected_config_sha256},sort_keys=True));return 0
    out.mkdir(parents=True);progress={'stage':'initialized','new_columns_checked':0}
    def strict(name):
        guard(name)
        if sum(q.stat().st_size for q in out.rglob('*') if q.is_file())>CAP:raise lifecycle.Stop('aggregate output cap')
    def save(name,value):
        payload=value if isinstance(value,bytes) else raw(value);strict('pre_publication')
        if sum(q.stat().st_size for q in out.rglob('*') if q.is_file())+len(payload)>CAP:raise lifecycle.Stop('aggregate output cap')
        path=out/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        strict('post_publication')
    def alarm(*_):raise lifecycle.Stop('30s hard audit alarm')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,max(.001,30-(time.monotonic()-start)))
    try:
        save('config.json',a.config.read_bytes())
        strict('pre_runtime_snapshot')
        runtime_bytes=sum((ROOT/name).stat().st_size for name in config['runtime_code_sha256'])
        if runtime_bytes+sum(q.stat().st_size for q in out.rglob('*') if q.is_file())>CAP:raise lifecycle.Stop('runtime snapshot output cap')
        for name in config['runtime_code_sha256']:
            guard('loop');path=out/'code'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/name).read_bytes())
        strict('post_runtime_snapshot')
        old=read(base/'dictionary.json');source=read(base/'seed-source.json');seed_terms=tuple(sorted(tuple(sum(bit<<i for i,bit in enumerate(term[axis])) for axis in ('u','v','w')) for term in source['terms']))
        strict('pre_new_column_and_rank_stage');progress['stage']='columns_and_rank'
        dictionary,report,polarized=materialize(old['representatives'],seed_terms,config['pair'],5,lambda _='loop':guard('loop'),authorize_n5=True,progress=progress)
        strict('post_new_column_and_rank_stage')
        if report['dictionary_orbits']!=278 or report['expanded_distinct_products']!=826 or report['seed_product_cost']!=93 or report['polarized_cost']!=98 or report['polarized_cubes']!=2 or report['polarized_nonfixed_orbits']!=32:raise ValueError('authorized extension inventory differs')
        for old_index,new_index in enumerate(report['old_to_new_column_map']):
            if dictionary['full_columns_hex'][new_index]!=old['full_columns_hex'][old_index] or dictionary['compressed_columns_hex'][new_index]!=old['compressed_columns_hex'][old_index]:raise ValueError('old column changed')
        checks={}
        for label,terms in [('seed93',seed_terms),('polarized98',polarized)]:
            progress['stage']='verifying_'+label;save('states/'+label+'.json',as_candidate(terms,5));persisted=(out/'states'/f'{label}.json').read_bytes()
            strict('pre_'+label+'_primary');first=verify_candidate(json.loads(persisted),random_trials=0);strict('post_'+label+'_primary_full15625')
            second=verify_bytes(persisted);strict('post_'+label+'_strict_independent_full15625')
            if not first['valid'] or not second['valid'] or first['exact_entries_checked']!=15625 or second['exact_entries_checked']!=15625 or second['essential_rank']!=len(terms):raise ValueError('persisted audit state failed full verifier')
            checks[label]={'primary':first,'independent':second,'persisted_sha256':sha(out/'states'/f'{label}.json')}
        save('state-verifications.json',checks);save('dictionary.json',dictionary);save('pair-witness.json',{'pair':config['pair'],'sum':266304,'relation_hex':report['known_zero_relation_hex'],'relation_indices':list(c._bits(int(report['known_zero_relation_hex'],16))),'expanded_products':9,'scope':'Exact whole-orbit zero relation; no target92 solution claimed.'})
        for name,digest in config['runtime_code_sha256'].items():
            if sha(ROOT/name)!=digest:raise ValueError('runtime changed during audit')
        if sha(base/'dictionary.json')!=DICT_SHA or sha(base/'manifest.json')!=MANIFEST_SHA or sha(a.config)!=a.expected_config_sha256:raise ValueError('base/config changed during audit')
        strict('post_all_checks_pre_manifest');report.update(format='cyclic-polarization7-extension-audit-v1',status='PREPARED_EXTENSION_AUDIT_ONLY',base_dictionary_sha256=DICT_SHA,base_manifest_sha256=MANIFEST_SHA,source_manifest_sha256=ANCHOR_SHA,root_eligibility_sha256=ELIGIBILITY_SHA,unchanged_helper_sha256=HELPER_SHA,config_sha256=a.expected_config_sha256,dictionary_sha256=sha(out/'dictionary.json'),runtime_code_sha256=config['runtime_code_sha256'],runtime=lifecycle.runtime(),process_cpu_seconds=time.process_time()-cpu_start,elapsed_seconds=time.monotonic()-start,guard=guard.observation(),solver_calls=0,optimization_calls=0,decoder_search_calls=0,private_eval_payloads_read=0,scope='One derived dictionary/rank audit; modulo permission is not a feasible92 proof.')
        save('manifest.json',report);save('checksums.json',{str(q.relative_to(out)):sha(q) for q in out.rglob('*') if q.is_file()});strict('final_pre_seal');save('COMPLETE.json',{'status':report['status'],'manifest_sha256':sha(out/'manifest.json'),'checksums_sha256':sha(out/'checksums.json'),'acceptance':'Require matching hashes and absence of UNKNOWN.json; no optimization permission.'})
        for path in out.rglob('*'):
            if path.is_file():path.chmod(0o444)
        print(json.dumps({k:report[k] for k in ['status','dictionary_orbits','expanded_distinct_products','full_rank','compressed_rank','nullity','seed_product_cost','polarized_cost','joint_complete_kernel_projection','process_cpu_seconds','elapsed_seconds']},sort_keys=True));return 0
    except Exception as error:
        failure={'status':'UNKNOWN_STOPPED_EXTENSION_AUDIT','reason':type(error).__name__+': '+str(error),'progress':progress,'elapsed_seconds':time.monotonic()-start,'solver_calls':0,'optimization_calls':0};payload=raw(failure)
        if sum(q.stat().st_size for q in out.rglob('*') if q.is_file())+len(payload)<=CAP:
            with (out/'UNKNOWN.json').open('xb') as stream:stream.write(payload)
        print(json.dumps(failure,sort_keys=True));return 2
    finally:signal.setitimer(signal.ITIMER_REAL,0)

if __name__=='__main__':raise SystemExit(main())
