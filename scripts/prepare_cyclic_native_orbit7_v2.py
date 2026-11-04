"""Authorized metadata-only C3 native-corpus dictionary audit; no solver/search."""
import argparse,gzip,hashlib,json,os,resource,signal,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT))
from mmsearch.cyclic_native_corpus7 import authenticate_portfolio,choose_diverse,candidate_from_atoms,parse_json_candidate,sha,PORTFOLIO_SHA
from mmsearch.cyclic_native_orbit7 import build_metadata
from mmsearch.marathon7_cached_guard import CampaignGuard,CampaignHold
from mmsearch.marathon7_cancel_poller import CancelPoller
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import verify_bytes
BASE_DICT='23ff2b7ef344b79277712731cdc80ecc4b030a82026ca77d9fec32a02ebd047b'
BASE_MANIFEST='eb6337722adaf26ecc3e11795cc94865c2a556db7af70d4efd83b917bb0a392b'
SEED_SHA='56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b'
DEADLINE='2026-11-03T19:24:17Z';CAP=32*1024**2

def read(p):return json.loads(Path(p).read_bytes())
def raw(v):return (json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
def file_sha(p):return sha(Path(p).read_bytes())

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--expected-config-sha256',required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--authorize-production-preparation',action='store_true');p.add_argument('--preview',action='store_true');a=p.parse_args();start=time.monotonic();cpu_start=time.process_time()
    if not a.authorize_production_preparation:p.error('explicit production metadata preparation authorization required')
    if file_sha(a.config)!=a.expected_config_sha256:raise ValueError('config pin differs')
    config=read(a.config);campaign=Path(config['campaign']);out=a.output_dir.resolve();qa_path=Path(config['source_qa']);base_path=Path(config['base_dictionary']);portfolio=Path(config['portfolio'])
    if out!=campaign/'cyclic-native-orbit7-prep-001' or out.exists() or (config['cpu'],config['nice'],config['memory_mib'],config['seconds'],config['max_orbits'],config['max_sources'])!=(3,10,1024,120,2000,24):raise ValueError('exact authorized new output/envelope required')
    if file_sha(qa_path)!=config['source_qa_sha256'] or file_sha(base_path)!=BASE_DICT or file_sha(base_path.parent/'manifest.json')!=BASE_MANIFEST or file_sha(portfolio/'manifest.json')!=PORTFOLIO_SHA or file_sha(config['seed_source'])!=SEED_SHA:raise ValueError('approved source/metadata/base pin differs')
    for name,pin in config['runtime_code_sha256'].items():
        if file_sha(ROOT/name)!=pin:raise ValueError('runtime drift: '+name)
    if file_sha(campaign/'campaign.json')!=config['campaign_sha256']:raise ValueError('campaign policy differs')
    guard=CampaignGuard(120,DEADLINE,guard_state=campaign/'operations-v3/state.json',campaign_dir=campaign);poller=CancelPoller(guard,lambda:start+120)
    def check(name='loop'):
        if name=='loop':
            if poller.cancelled():poller.force_check(name)
        else:poller.force_check(name)
    check('pre_native_orbit_audit')
    if time.time()+150>guard.deadline:raise ValueError('outer envelope cannot fit UTC')
    if a.preview:print(json.dumps(dict(status='PREVIEW_ONLY',zero_mutations=True,dictionary_builds=0,solver_calls=0,source_schemas=24)));return 0
    os.sched_setaffinity(0,{3});os.setpriority(os.PRIO_PROCESS,0,10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP));resource.setrlimit(resource.RLIMIT_CORE,(0,0));out.mkdir();progress=dict(stage='source_authority',selected_sources_checked=0)
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    def save(name,value):
        check('pre_publication');payload=value if isinstance(value,bytes) else raw(value)
        if sum(f.stat().st_size for f in out.rglob('*') if f.is_file())+len(payload)>CAP:raise ValueError('32MiB aggregate output cap')
        dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        check('post_publication')
    def alarm(*_):raise TimeoutError('120second metadata audit cap')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,max(.001,120-(time.monotonic()-start)))
    try:
        save('config.json',config);qa=read(qa_path);records,authority=authenticate_portfolio(campaign,portfolio,config['cpp_path'],qa['producer_pins'],check);selected,selection=choose_diverse(records,24)
        expected=[{k:r[k] for k in ('run','path','raw_sha256','identity','rl_identity','rank')} for r in qa['selected']]
        if [{k:r[k] for k in ('run','path','raw_sha256','identity','rl_identity','rank')} for r in selected]!=expected:raise ValueError('qualified selected source list differs')
        schemas=[];proofs=[]
        for index,row in enumerate(selected):
            check('pre_selected_source');candidate=candidate_from_atoms(row['atoms']);payload=raw(candidate);first=verify_candidate(candidate,random_trials=0);check('post_selected_primary');second=verify_bytes(payload);check('post_selected_independent')
            if not first['valid'] or not second['valid'] or first['rank']!=row['rank'] or second['essential_rank']!=row['rank'] or first['exact_entries_checked']!=15625 or second['exact_entries_checked']!=15625:raise ValueError('selected source full double check failed')
            save(f'sources/source-{index:02}.candidate.raw',payload);proof=dict(id=f'source-{index:02}',run=row['run'],raw_sha256=row['raw_sha256'],native_path=row['path'],rank=row['rank'],identity=row['identity'],rl_identity=row['rl_identity'],primary=first,independent=second);save(f'sources/source-{index:02}.proof.raw',proof);proofs.append(proof);schemas.append(dict(id=f'source-{index:02}',atoms=row['atoms'],raw_sha256=row['raw_sha256']));progress['selected_sources_checked']+=1
        seed_raw=Path(config['seed_source']).read_bytes();seed_atoms,seed_candidate=parse_json_candidate(seed_raw);check('pre_seed_primary');seed_primary=verify_candidate(seed_candidate,random_trials=0);check('post_seed_primary');seed_independent=verify_bytes(seed_raw);check('post_seed_independent')
        if not seed_primary['valid'] or not seed_independent['valid'] or seed_independent['essential_rank']!=93:raise ValueError('preserved seed is not exact93')
        base=read(base_path);old_forms=[base['representatives'][i][0] for i,w in enumerate(base['weights']) if w==1]
        if old_forms!=[4096,262208,16777217]:raise ValueError('oldcubeK differs')
        progress['stage']='dictionary_columns_and_exterior_metadata';check('pre_all_dictionary_columns')
        dictionary,diagnostics,projections=build_metadata(schemas,seed_atoms,base['representatives'],old_forms,5,allow_n5=True,guard=lambda *_:check('loop'),progress=progress);check('post_all_dictionary_columns')
        mapping=dictionary['old_to_new_column_indices']
        for i,j in enumerate(mapping):
            if any(dictionary[k][j]!=base[k][i] for k in ('representatives','weights','full_columns_hex','compressed_columns_hex')):raise ValueError('old dictionary embedding mutated')
        if diagnostics['old_full_rank']!=201 or diagnostics['old_F_rank']!=195 or diagnostics['seed_product_cost']!=93:raise ValueError('oldrank/exterior/seed93 certificate differs')
        if not diagnostics['new_nonzero_F_orbits']:raise ValueError('new corpus does not escape wedge-zero extension hypothesis')
        dictionary.update(source_authority=authority,source_qa_sha256=config['source_qa_sha256'],base_dictionary_sha256=BASE_DICT,base_manifest_sha256=BASE_MANIFEST)
        save('dictionary.json',dictionary);save('diagnostics.json',diagnostics);save('column-exterior-projections.json',projections);save('source-provenance.json',dict(authority=authority,selection=selection,selected=proofs,seed_primary=seed_primary,seed_independent=seed_independent,seed_sha256=SEED_SHA))
        check('pre_final_input_recheck')
        if file_sha(qa_path)!=config['source_qa_sha256'] or file_sha(base_path)!=BASE_DICT or file_sha(a.config)!=a.expected_config_sha256:raise ValueError('source/base/config changed')
        for name,pin in config['runtime_code_sha256'].items():
            if file_sha(ROOT/name)!=pin:raise ValueError('runtime changed: '+name)
        manifest=dict(format='cyclic-native-orbit7-prepared-v1',status='SEALED_METADATA_NO_SEARCH',dictionary_sha256=file_sha(out/'dictionary.json'),diagnostics_sha256=file_sha(out/'diagnostics.json'),projection_sha256=file_sha(out/'column-exterior-projections.json'),source_provenance_sha256=file_sha(out/'source-provenance.json'),source_qa_sha256=config['source_qa_sha256'],base_dictionary_sha256=BASE_DICT,selected_sources=24,seed_product_cost=93,dictionary_orbits=diagnostics['dictionary_orbits'],cube_orbits=diagnostics['cube_orbits'],full_rank=diagnostics['full_rank'],nullity=diagnostics['nullity'],F_rank=diagnostics['F_rank'],F_rank_added=diagnostics['F_rank_added'],new_nonzero_F_orbits=diagnostics['new_nonzero_F_orbits'],kernel_parity=diagnostics['kernel_parity'],cube_factor_rank=diagnostics['cube_factor_rank'],kernel_cube_coordinate_projection_rank=diagnostics['kernel_cube_coordinate_projection_rank'],elapsed_seconds=time.monotonic()-start,cpu_seconds=time.process_time()-cpu_start,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,config_sha256=a.expected_config_sha256,runtime_code_sha256=config['runtime_code_sha256'],guard=guard.observation(),poller=poller.metrics(),solver_calls=0,decoder_calls=0,optimization_calls=0,private_eval_payloads_read=0,claim='New finite approvedC3 dictionary metadata only; nonzeroFescapesdegenerateextensionhypothesis butisnotimprovementorexistenceproof.')
        save('manifest.json',manifest);save('COMPLETE.json',dict(manifest_sha256=file_sha(out/'manifest.json'),dictionary_sha256=file_sha(out/'dictionary.json')))
        for f in out.rglob('*'):
            if f.is_file():f.chmod(0o444)
        print(json.dumps({k:manifest[k] for k in ('status','dictionary_orbits','cube_orbits','full_rank','nullity','F_rank','F_rank_added','new_nonzero_F_orbits','cube_factor_rank','elapsed_seconds','cpu_seconds','max_rss_kib')}));return 0
    except Exception as error:
        failure=dict(status='UNKNOWN_METADATA_AUDIT',reason=type(error).__name__+': '+str(error),progress=progress,solver_calls=0,decoder_calls=0,optimization_calls=0)
        with (out/'UNKNOWN.json').open('xb') as stream:stream.write(raw(failure))
        print(json.dumps(failure));return 1
    finally:signal.setitimer(signal.ITIMER_REAL,0)
if __name__=='__main__':raise SystemExit(main())
