"""Exactly one authorized bounded SAT query on the sealed366-orbit C3 code."""
import argparse,hashlib,json,os,resource,signal,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'.xor-deps')]
from mmsearch.cyclic_code_sat7 import build_problem,solve,validate_code
from mmsearch import cyclic_tensor_code7 as c
from mmsearch.sat_neighborhoods import gf2_rank
from mmsearch.marathon7_cached_guard import CampaignGuard,CampaignHold
from mmsearch.marathon7_cancel_poller import CancelPoller
from scripts import campaign_native_baseline7 as safe
DICT_SHA='12ceaae3e96013a56fb960383f7f34531793977661ce65a47f94f88c838481f5'
MANIFEST_SHA='de288ca0881dc283df3a15567d3a1ea28b605800ebeca10f4500f091452045fb'
DEADLINE='2026-11-03T19:24:17Z';CAP=32*1024**2

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def raw(v):return (json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
def freeze(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(v if isinstance(v,bytes) else raw(v));f.flush();os.fsync(f.fileno())
    p.chmod(0o444)

def verified_formula_payload(payload,expected):
    if payload!=raw(expected):raise ValueError('persisted formula bytes differ')
    return json.loads(payload)

def configure_background_priority():
    """Keep an inherited queue priority; never request privileged promotion."""
    if os.getpriority(os.PRIO_PROCESS,0)<10:
        os.setpriority(os.PRIO_PROCESS,0,10)


def checked_input(dictionary,check=lambda *_:None):
    if dictionary['dimension']!=5 or dictionary['field']!=2 or len(dictionary['representatives'])!=366 or dictionary['rank']!=243 or dictionary['nullity']!=123 or dictionary['weights'].count(1)!=5 or dictionary['weights'].count(3)!=361:raise ValueError('one sealed366-orbit code required')
    full=[int(v,16) for v in dictionary['full_columns_hex']];compressed=[int(v,16) for v in dictionary['compressed_columns_hex']];kernel=[int(v,16) for v in dictionary['kernel_hex']];seed=int(dictionary['seed_state_hex'],16);target=int(dictionary['compressed_target_hex'],16);fulltarget=int(dictionary['target_hex'],16)
    if len(full)!=366 or len(compressed)!=366 or fulltarget!=c.target_tensor(5) or c.compress_invariant(fulltarget,25)!=target or gf2_rank(full)!=243:raise ValueError('full tensor/rank differs')
    for i,rep in enumerate(dictionary['representatives']):
        check('loop')
        if tuple(rep)!=c.orbit_representative(rep,5) or len(c.orbit(rep,5))!=dictionary['weights'][i] or c.orbit_tensor(rep,5)!=full[i] or c.expand_invariant(compressed[i],25)!=full[i]:raise ValueError('literal orbit/column/projection differs')
    validate_code(compressed,target,seed,kernel,dictionary['weights'],243)
    if len(kernel)!=123 or any(c.xor_columns(full,v) for v in kernel) or c.xor_columns(full,seed)!=fulltarget or sum(dictionary['weights'][i] for i in c._bits(seed))!=93:raise ValueError('complete fullkernel/seed93 audit differs')
    return compressed,target,seed,kernel,dictionary['weights'],243

def expand_model(dictionary,result):
    state=int(result['state_hex'],16);terms=sorted(t for i in c._bits(state) for t in c.orbit(dictionary['representatives'][i],5))
    if len(terms)!=len(set(terms)) or len(terms)!=result['product_cost'] or not 0<len(terms)<=92:raise ValueError('integer expanded orbit cost differs')
    full=[int(v,16) for v in dictionary['full_columns_hex']]
    if c.xor_columns(full,state)!=int(dictionary['target_hex'],16):raise ValueError('model fulltensor syndrome differs')
    return safe.base.encode_candidate(terms,5,method='cyclic-native-orbit7-kernel-SAT',dictionary_sha256=DICT_SHA,state_hex=hex(state),formula_sha256=result['formula_sha256'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--expected-config-sha256',required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--preview',action='store_true');a=p.parse_args();start=time.monotonic();cpu_start=time.process_time()
    if sha(a.config)!=a.expected_config_sha256:raise ValueError('configuration differs')
    config=read(a.config);campaign=Path(config['campaign']);directory=Path(config['dictionary']).parent;out=a.output_dir.resolve()
    if out!=campaign/'cyclic-native-orbit7-sat001-001' or out.exists() or (config['cpu'],config['memory_mib'],config['solver_seconds'],config['inner_seconds'],config['outer_seconds'])!=(3,1024,60,80,110):raise ValueError('one exact authorized newquery/envelope required')
    if sha(config['dictionary'])!=DICT_SHA or sha(directory/'manifest.json')!=MANIFEST_SHA:raise ValueError('sealed dictionary/manifest differs')
    for name,pin in config['runtime_code_sha256'].items():
        if sha(ROOT/name)!=pin:raise ValueError('runtime differs: '+name)
    for path,pin in config['external_dependency_sha256'].items():
        if sha(path)!=pin:raise ValueError('SAT encoder dependency differs')
    if sha(campaign/'campaign.json')!=config['campaign_sha256']:raise ValueError('campaign policy differs')
    guard=CampaignGuard(80,DEADLINE,guard_state=campaign/'operations-v3/state.json',campaign_dir=campaign);poller=CancelPoller(guard,lambda:start+80);reason=None
    def check(name='loop'):
        if name=='loop':
            if poller.cancelled():poller.force_check(name)
        else:poller.force_check(name)
    def fresh(name):
        nonlocal reason
        try:check(name);return True
        except CampaignHold as error:reason=error.reason;return False
    check('pre_code_sat_input');dictionary_payload=Path(config['dictionary']).read_bytes()
    if hashlib.sha256(dictionary_payload).hexdigest()!=DICT_SHA:raise ValueError('persisted input dictionary bytes differ')
    dictionary=json.loads(dictionary_payload);code=checked_input(dictionary,check);check('post_code_sat_input');problem=build_problem(*code,budget=92);check('post_code_sat_encoder')
    if problem['metadata']['formula_sha256']!=config['formula_sha256']:raise ValueError('frozen exact formula differs')
    if time.time()+110>guard.deadline:raise ValueError('outer envelope doesnotfitUTC')
    if a.preview:print(json.dumps(dict(status='PREVIEW_ONLY',zero_mutations=True,solver_calls=0,formula=problem['metadata'])));return 0
    os.sched_setaffinity(0,{3});configure_background_priority();resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP));resource.setrlimit(resource.RLIMIT_CORE,(0,0));out.mkdir();signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop());signal.signal(signal.SIGALRM,lambda *_:guard.stop());signal.setitimer(signal.ITIMER_REAL,max(.001,80-(time.monotonic()-start)))
    def save(name,value):
        payload=value if isinstance(value,bytes) else raw(value)
        if sum(f.stat().st_size for f in out.rglob('*') if f.is_file())+len(payload)>CAP:raise ValueError('32MiB query output cap')
        freeze(out/name,payload)
    result=None;emitted=False;status='UNKNOWN';complete=False
    try:
        save('config.json',config);save('.formula.raw',problem);check('pre_formula_reread');persisted=verified_formula_payload((out/'.formula.raw').read_bytes(),problem)
        check('pre_only_solver_call');result=solve(persisted,seconds=60,memory_mb=1024,cancelled=poller.cancelled,deadline_utc=DEADLINE);save('.raw-sat-returns/result.raw',result);check('post_only_solver_call')
        if result['status']=='SAT':
            check('pre_literal_orbit_expansion');candidate=expand_model(dictionary,result);check('post_literal_orbit_expansion');emitted=safe.retain_target(out,candidate,fresh,target=92)
            if emitted:status='TARGET_EMITTED_TO_GLOBAL_GUARD';complete=True
            else:status='UNKNOWN'
        elif result['status']=='FINITE_CODE_UNSAT' and result['complete'] is True and result['finite_dictionary_complete'] is True:
            check('pre_finite_negative_commit');status='FINITE_366_DICTIONARY_UNSAT';complete=True
        elif result['status']=='ERROR':status='ERROR'
        check('post_query_result')
    except CampaignHold as error:reason=error.reason;status='UNKNOWN';complete=False
    except Exception as error:
        status='ERROR';complete=False;reason=type(error).__name__+': '+str(error);save('.raw-sat-returns/error.raw',dict(error=reason,result=result))
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    if not fresh('pre_summary_commit'):status='UNKNOWN';complete=False
    summary=dict(format='cyclic-native-orbit7-one-SAT-v1',status=status,complete=complete,solver_calls=int(bool(result and result.get('worker_started'))),dictionary_sha256=DICT_SHA,dictionary_manifest_sha256=MANIFEST_SHA,formula_sha256=problem['metadata']['formula_sha256'],formula_metadata=problem['metadata'],raw_result_sha256=sha(out/'.raw-sat-returns/result.raw') if(out/'.raw-sat-returns/result.raw').exists() else None,solver_version=result.get('solver_version') if result else None,solver_stats=result.get('solver_stats') if result else None,worker_reaped=result.get('worker_reaped') if result else None,worker_exitcode=result.get('worker_exitcode') if result else None,eligible_target_emitted=emitted,reason=reason,elapsed_seconds=time.monotonic()-start,parent_cpu_seconds=time.process_time()-cpu_start,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,guard=guard.observation(),poller=poller.metrics(),config_sha256=a.expected_config_sha256,runtime_code_sha256=config['runtime_code_sha256'],scope='One exact cost<=92 query in supplied366-orbit finitecode only. UNSATisnotglobalranklowerbound; UNKNOWNnotnegative; no continuation/localWINNER.')
    save('summary.json',summary)
    if not fresh('post_summary_commit'):
        os.replace(out/'summary.json',out/'.raw-sat-returns/late-summary.raw');summary.update(status='UNKNOWN',complete=False,reason=reason);save('summary.json',summary)
    save('checksums.json',{str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file()});print(json.dumps({k:summary[k] for k in ('status','complete','solver_calls','solver_version','solver_stats','worker_reaped','worker_exitcode','eligible_target_emitted','reason','elapsed_seconds')}));return 1 if summary['status']=='ERROR' else 0
if __name__=='__main__':raise SystemExit(main())
