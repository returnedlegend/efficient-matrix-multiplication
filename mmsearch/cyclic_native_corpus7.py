"""Separate C3 portfolio-source contract; the old native522 whitelist is unchanged.

Only frozen portfolio p01/p02/p03 descendants of explicit original train roots
are accepted. Selection uses orbit-set diversity, never a decoder objective.
"""
from collections import Counter
import hashlib,json,sys
from pathlib import Path
from .cyclic_tensor_code7 import orbit,orbit_representative
from .tensor_code7_native_corpus import (parse_native,parse_json_candidate,identities,command_pairs,candidate_from_atoms)

PORTFOLIO_SHA='9882f13aed6d44a92ffbed631613bf0787ddfd37707bbbcb66c5873187758521'
ANCHOR_SHA='26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8'
APPROVAL_SHA='7354183ab6e9c89f76110e1c916738ced4856499632a2f317508b1d6bea7bb55'
CPP_SHA='b65f0bda48a0c217d66d65a4db21e286c93448128373c439e8d66c3b8d8c8c1f'
BINARY_SHA='6e7d6c63fa262bfc50acfe92fbe9c11adb74426e3868a5a6f7ad8d1bf569ac19'
RUNS=('native-portfolio7-p01','native-portfolio7-p02','native-portfolio7-p03')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path,pin=None):
    payload=Path(path).read_bytes()
    if pin is not None and sha(payload)!=pin:raise ValueError('immutable producer/source pin differs: '+str(path))
    return json.loads(payload),payload

def complete_orbits(atoms,n=5):
    atoms=tuple(atoms);lookup=set(atoms)
    if not atoms or len(atoms)!=len(lookup):raise ValueError('nonempty distinct literal products required')
    reps={orbit_representative(t,n) for t in atoms}
    if {term for rep in reps for term in orbit(rep,n)}!=lookup:raise ValueError('selected schema is not complete under C3')
    return frozenset(reps)

def validate_train_node(node,entry,index,pool,armed,split,prohibited):
    identity=node['identity'];evidence=node['root_training_evidence']
    if (node['node_type']!='native_initial_train' or node['root_id']!=node['id'] or node['parent_ids'] or node['parent_files']
        or node['root_approved_train'] is not True or node['split']!='train' or node['heldout_excluded'] is not True or node['evaluation_excluded'] is not True
        or entry['id']!=node['id'] or entry['sha256']!=node['sha256'] or entry['identity']!=identity or set(identity.values())&set(prohibited)
        or evidence['approval_owner']!='root' or evidence['selector']!=['initial_pool',index]
        or pool['sha256']!=node['sha256'] or pool['term_hash']!=identity['term_set_sha256'] or pool['rl_source_hash']!=identity['rl_source_sha256']
        or not armed['armed'] or armed['owner']!='root' or armed['plan_sha256']!=evidence['plan_sha256']
        or identity['rl_source_sha256'] not in split['v43_source_split']['train']):raise ValueError('not an exact original approved training root')

def validate_command(command,profile,binary,input_path,prefix):
    if not isinstance(command,list) or not command or command[-1]!='--cyclic' or command.count('--cyclic')!=1:raise ValueError('only explicit whole-C3 producer mode accepted')
    pairs=command_pairs(command[:-1]);expected={'--input':str(input_path),'--output':str(prefix),'--n':'5','--target':'92','--max-rank':'105','--seed':str(profile['seed']),'--steps':'1000000000000','--seconds':'120','--checkpoint-seconds':'3','--archive-size':'16','--archive-every':'1000','--plus-every':str(profile['plus_every']),'--restart-every':'50000000','--plus-burst':str(profile['plus_burst']),'--reduction-dwell':str(profile['reduction_dwell'])}
    if Path(command[0]).resolve()!=Path(binary).resolve() or pairs!=expected:raise ValueError('producer command is not the frozen bounded cyclic profile')
    return pairs

def validate_outer(outer,run,portfolio,directory):
    command=outer['command']
    expected=['-B',str(Path(portfolio)/'code/scripts/campaign_native_portfolio7.py'),'--bundle',str(portfolio),'--expected-manifest-sha256',PORTFOLIO_SHA,'--profile-id',run,'--output-dir',str(directory)]
    if (outer['cpu']!=0 or outer['memory_mb']!=768 or outer['wall_seconds']!=150 or outer['exit_code']!=0 or outer['timed_out'] is not False or outer['interrupted'] is not False
        or not command or Path(command[0]).resolve()!=Path(sys.executable).resolve() or command[1:]!=expected):raise ValueError('outer producer CPU/memory/wall/driver command differs')


def authenticate_portfolio(campaign,portfolio,cpp_path,producer_pins,guard=lambda *_:None):
    campaign=Path(campaign).resolve();portfolio=Path(portfolio).resolve();guard('pre_portfolio_authority')
    manifest,raw_manifest=load(portfolio/'manifest.json',PORTFOLIO_SHA);anchors,raw_anchors=load(campaign/'tensor-code-source-anchors-v1/manifest.json',ANCHOR_SHA)
    approval,_=load(campaign/'root-review-decisions/tensor-code-source-anchors-approved.json',APPROVAL_SHA)
    if approval.get('approved_manifest_sha256')!=ANCHOR_SHA or approval.get('heldout_evaluation_excluded') is not True or manifest['anchor_manifest_sha256']!=ANCHOR_SHA:raise ValueError('root source authority differs')
    if sha((portfolio/'provenance/approved-anchor-manifest.json').read_bytes())!=ANCHOR_SHA:raise ValueError('producer anchor copy differs')
    for name,pin in manifest['files'].items():
        guard('loop');path=(portfolio/name).resolve()
        if not path.is_relative_to(portfolio) or sha(path.read_bytes())!=pin:raise ValueError('frozen producer runtime/input differs')
    if sha(Path(cpp_path).read_bytes())!=CPP_SHA or sha((portfolio/'native/plus-burst-worker').read_bytes())!=BINARY_SHA:raise ValueError('approved nativeCPP/binary differs')
    registries={}
    for name in ['native_armed','native_initial_plan','v43_split','heldout_declaration']:
        registries[name],_=load(portfolio/'provenance'/(name+'.json'),anchors['registries'][name]['sha256'])
    source_audit,audit_raw=load(portfolio/'source-audit.json');prohibited=set(anchors['prohibited_identities']['heldout'])|set(anchors['prohibited_identities']['evaluation']);records=[];producers={}
    for run,index in zip(RUNS,(0,2,3)):
        guard('pre_producer_authority');profile=next(p for p in manifest['profiles'] if p['id']==run)
        if profile['source_id']!=index or profile['cyclic'] is not True:raise ValueError('wrong source/context producer')
        entry=anchors['known_input_train_states'][index];node=anchors['nodes'][entry['id']]
        validate_train_node(node,entry,index,registries['native_initial_plan']['initial_pool'][index],registries['native_armed'],registries['v43_split'],prohibited)
        ev=node['root_training_evidence']
        if ev['approval_sha256']!=anchors['registries']['native_armed']['sha256'] or ev['plan_sha256']!=anchors['registries']['native_initial_plan']['sha256']:raise ValueError('root approval registry binding differs')
        source=manifest['sources'][str(index)];input_raw=(portfolio/source['file']).read_bytes();input_atoms,_=parse_json_candidate(input_raw)
        if sha(input_raw)!=node['sha256'] or identities(input_atoms)!=node['identity'] or source_audit['sources'][str(index)]['raw_sha256']!=node['sha256']:raise ValueError('producer input differs from authoritative root')
        directory=campaign/run;pins=producer_pins[run];run_manifest,run_raw=load(directory/'manifest.json',pins['run_manifest_sha256']);summary,summary_raw=load(directory/'summary.json',pins['summary_sha256']);native_input=(directory/'native/input.txt').read_bytes()
        if sha(native_input)!=pins['native_input_sha256']:raise ValueError('frozen producer native input differs')
        outer,outer_raw=load(campaign/(run+'-job.result.json'),pins['outer_result_sha256']);validate_outer(outer,run,portfolio,directory)
        if (run_manifest['cpu'],run_manifest['memory_mib'],run_manifest['native_seconds'],run_manifest['outer_seconds'],run_manifest['archive_cap'])!=(0,768,120,150,16):raise ValueError('producer runtime envelope differs')
        if parse_native(native_input)!=input_atoms or run_manifest['manifest_sha256']!=PORTFOLIO_SHA or run_manifest['source_sha256']!=node['sha256'] or run_manifest['binary_sha256']!=BINARY_SHA or run_manifest['profile']!=profile or summary['profile']!=profile:raise ValueError('producer input/config/profile binding differs')
        validate_command(summary['command'],profile,portfolio/'native/plus-burst-worker',directory/'native/input.txt',directory/'native/walk')
        execution=summary['execution'];stats=summary['stats']
        if stats['seconds_budget']!=120 or stats['elapsed_seconds']<119.95 or stats['stopped_by_signal'] is not False or stats['seed']!=profile['seed'] or stats['plus_burst']!=profile['plus_burst'] or stats['reduction_dwell']!=profile['reduction_dwell'] or stats['plus_every']!=profile['plus_every']:raise ValueError('native telemetry differs from bounded profile')
        if execution['exit_code']!=0 or execution['timed_out'] or execution['interrupted'] or summary['stop_reason'] is not None or summary['final_checks_complete'] is not True or summary['native_queries_started']!=1 or stats['exact'] is not True or stats['tensor_invariant_checked'] is not True or stats['cyclic'] is not True:raise ValueError('producer did not complete its exact bounded cyclic profile')
        for name in ('best','current'):
            proof=summary['final_full_checks'][name]
            if not proof['primary']['valid'] or not proof['independent']['valid'] or proof['primary']['exact_entries_checked']!=15625 or proof['independent']['exact_entries_checked']!=15625:raise ValueError('producer final full checks differ')
        producers[run]=dict(profile=profile,outer_result_sha256=sha(outer_raw),summary_sha256=sha(summary_raw),run_manifest_sha256=sha(run_raw),input_json_sha256=sha(input_raw),native_input_sha256=sha(native_input),source_node=node['id'],root_training_evidence=ev,command=summary['command'],cpp_sha256=CPP_SHA,binary_sha256=BINARY_SHA,export_registry_sha256=sha(json.dumps(summary['raw_exports'],sort_keys=True,separators=(',',':')).encode()))
        for identity,row in sorted(summary['raw_exports'].items()):
            guard('loop');path=directory/'.raw-native-returns'/(identity+'.txt');payload=path.read_bytes();atoms=parse_native(payload);actual=identities(atoms)
            if sha(payload)!=row['raw_sha256'] or actual['term_set_sha256']!=identity or len(atoms)!=row['rank'] or not 93<=len(atoms)<=105 or set(actual.values())&prohibited:raise ValueError('export registry/identity/rank/prohibited ancestry differs')
            reps=complete_orbits(atoms)
            records.append(dict(run=run,path=str(path),raw_sha256=sha(payload),identity=identity,rl_identity=actual['rl_source_sha256'],rank=len(atoms),atoms=atoms,orbits=reps))
        guard('post_producer_authority')
    return records,dict(portfolio_manifest_sha256=PORTFOLIO_SHA,anchor_manifest_sha256=ANCHOR_SHA,root_approval_sha256=APPROVAL_SHA,source_audit_sha256=sha(audit_raw),producers=producers,frozen_runtime_files_checked=len(manifest['files']),private_eval_payloads_read=0)

def choose_diverse(records,max_sources=24):
    if type(max_sources) is not int or not 6<=max_sources<=24:raise ValueError('schema selection cap must be6..24')
    unique={}
    for r in sorted(records,key=lambda r:(r['run'],r['identity'])):unique.setdefault(r['identity'],r)
    pool=list(unique.values());chosen=[];used=set();union=set()
    def take(candidates):
        candidates=[r for r in candidates if r['identity'] not in used]
        if not candidates:raise ValueError('mandatory producer/rank stratum absent')
        def score(r):
            distance=min((len(r['orbits']^old['orbits']) for old in chosen),default=2*len(r['orbits']))
            return distance,len(r['orbits']-union),r['identity']
        r=max(candidates,key=score);chosen.append(r);used.add(r['identity']);union.update(r['orbits'])
    for run in RUNS:take(r for r in pool if r['run']==run and r['rank']==93)
    for rank in (95,97,100):take(r for r in pool if r['run']==RUNS[0] and r['rank']==rank)
    while len(chosen)<min(max_sources,len(pool)):take(r for r in pool if r['identity'] not in used)
    return chosen,dict(selected=len(chosen),by_run=dict(Counter(r['run'] for r in chosen)),by_rank=dict(Counter(r['rank'] for r in chosen)),selected_orbit_union=len(union),policy='Cover3producer rank93 strata andp01r95/97/100; then farthest-first orbit-set diversity. No tensor objective/decoder.',optimization_called=False)
