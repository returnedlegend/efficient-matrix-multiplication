"""One bounded exact native baseline. No continuation or local WINNER marker.

Raw returns use hidden .raw/.txt files. Only double-verified, fresh target
candidates enter records/ for the global guard's immutable freeze workflow.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from scripts import campaign_native_plus_burst42 as base
from scripts import tensor_code7 as lifecycle
from scripts.verify_record42_independent import verify_bytes,_check_all_basis_outputs
from mmsearch.verify import verify_candidate

INPUT_SHA='56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b'
BINARY_SHA='6e7d6c63fa262bfc50acfe92fbe9c11adb74426e3868a5a6f7ad8d1bf569ac19'
SEED=20261103132901
DEADLINE='2026-11-03T19:24:17Z'


def command(binary,input_path,prefix,*,seconds=300,seed=SEED,n=5,target=92,steps=10**12):
    if n==5 and (seconds!=300 or seed!=SEED or target!=92):raise ValueError('one authorized production budget/seed/target only')
    if n not in (2,5) or not 0<seconds<=300:raise ValueError('invalid control/production budget')
    return [str(binary),'--input',str(input_path),'--output',str(prefix),'--n',str(n),'--target',str(target),'--max-rank',str(105 if n==5 else 20),'--seed',str(seed),'--steps',str(steps),'--seconds',str(seconds),'--checkpoint-seconds','3','--archive-size','16','--archive-every','1000','--plus-every','20000','--restart-every','50000000','--plus-burst','1','--reduction-dwell','0']


def independent(candidate,payload):
    if candidate['dimension']==5:return verify_bytes(payload)
    n=candidate['dimension'];report=_check_all_basis_outputs(n,[(tuple(t['u']),tuple(t['v']),tuple(t['w'])) for t in candidate['terms']])
    return {'valid':report['mismatch_count']==0,'exact_entries_checked':report['output_bits_checked'],'essential_rank':len(candidate['terms']),'record_eligible':report['mismatch_count']==0,'control_only':True}


def retain_target(output,candidate,fresh,*,target=92):
    """Persist hidden raw bytes first; fresh double verification precedes handoff."""
    output=Path(output);payload=base.raw_json(candidate);digest=base.sha(payload);hidden=output/'.raw-native-returns';base.freeze(hidden/(digest+'.candidate.raw'),payload)
    persisted=(hidden/(digest+'.candidate.raw')).read_bytes()
    if not fresh('pre_target_full_tensor'):return False
    first=verify_candidate(json.loads(persisted),random_trials=0)
    if not fresh('post_target_full_tensor'):return False
    second=independent(json.loads(persisted),persisted)
    if not fresh('post_target_strict_independent'):return False
    n=candidate['dimension'];rank=len(candidate['terms'])
    if (candidate.get('field')!=2 or not 0<rank<=target or not first['valid'] or first['exact_entries_checked']!=n**6 or not second['valid'] or second['exact_entries_checked']!=n**6 or second['essential_rank']!=rank or (n==5 and second.get('record_eligible') is not True)):
        raise ValueError('target candidate failed exact primary/strict independent gate')
    base.freeze(hidden/(digest+'.proof.raw'),base.raw_json({'primary':first,'independent':second,'candidate_sha256':digest}))
    destination=output/'records'/(digest+'.json');destination.parent.mkdir(parents=True,exist_ok=True);pending=hidden/(digest+'.pending.raw')
    base.freeze(pending,persisted)
    if not fresh('pre_eligible_canonical_publication'):return False
    os.replace(pending,destination)
    if not fresh('post_eligible_canonical_publication'):
        os.replace(destination,hidden/(digest+'.late-canonical.raw'));return False
    return True


def execute(binary,terms,output,fresh,*,seconds=300,seed=SEED,n=5,target=92,steps=10**12):
    output=Path(output);prefix=output/'native/walk';input_path=output/'native/input.txt';base.freeze(input_path,''.join(f'{a} {b} {c}\n' for a,b,c in terms).encode());argv=command(binary,input_path,prefix,seconds=seconds,seed=seed,n=n,target=target,steps=steps)
    seen={};last_scan=0.;emitted=False
    def drain(force=False):
        nonlocal last_scan,emitted
        if not force and time.monotonic()-last_scan<.5:return False
        last_scan=time.monotonic()
        paths=[Path(str(prefix)+'.best.txt'),Path(str(prefix)+'.current.txt'),*sorted(Path(str(prefix)+'.archive').glob('*.txt'))]
        for path in paths:
            if not path.exists():continue
            state,text=base.snapshot(path,n);digest=base.term_set_sha256(state)
            if digest in seen:continue
            base.freeze(output/'.raw-native-returns'/(digest+'.txt'),text)
            seen[digest]={'rank':len(state),'raw_sha256':base.sha(text),'source_snapshot':str(path.relative_to(output))}
            if len(state)<=target:
                candidate=base.encode_candidate(state,n,method='bounded-native-baseline7',seed=seed,native_command=argv)
                emitted=retain_target(output,candidate,fresh,target=target) or emitted
        return emitted
    def stopped():return not fresh('loop')
    if not fresh('pre_native_launch'):return {'status':'STOPPED_BEFORE_NATIVE','native_queries_started':0,'command':argv}
    with (output/'worker.log').open('x') as log:execution=base.run_child(argv,log,stopped,drain,wall_seconds=seconds)
    # This mandatory drain handles an early successful child exit before polling.
    drain(True);fresh('post_owned_child_return')
    stats_path=Path(str(prefix)+'.stats.json');stats=base.read(stats_path)[0] if stats_path.exists() else None
    final_checks={}
    for name in ['best','current']:
        path=Path(str(prefix)+'.'+name+'.txt')
        if not path.exists():continue
        state,text=base.snapshot(path,n);payload=base.raw_json(base.encode_candidate(state,n))
        if fresh('pre_final_'+name):
            first=verify_candidate(json.loads(payload),random_trials=0)
            if not fresh('post_final_'+name+'_primary'):continue
            second=independent(json.loads(payload),payload)
            if not fresh('post_final_'+name+'_independent'):continue
            if not first['valid'] or not second['valid']:raise ValueError('final native export failed full tensor')
            final_checks[name]={'primary':first,'independent':second,'raw_sha256':base.sha(text)}
    if stats:
        for key,value in {'dimension':n,'seed':seed,'target_rank':target,'max_rank':105 if n==5 else 20,'reduction_dwell':0,'plus_burst':1,'archive_size':min(16,stats['archive_size']),'plus_every':20000,'restart_every':50000000}.items():
            if stats[key]!=value:raise ValueError('native statistics parameter differs: '+key)
        if stats['archive_size']>16 or stats['cyclic'] or not stats['exact'] or not stats['tensor_invariant_checked']:raise ValueError('native cap/exactness claims differ')
    summary={'status':'TARGET_EMITTED_TO_GLOBAL_GUARD' if emitted else 'UNKNOWN_WITHIN_ONE_BASELINE','native_queries_started':1,'eligible_target_emitted':emitted,'global_record_freeze_owned_by_guard':True,'execution':execution,'command':argv,'stats':stats,'stats_sha256':base.sha(stats_path.read_bytes()) if stats_path.exists() else None,'final_full_checks':final_checks,'raw_exports':seen,'raw_export_count':len(seen),'claim':'One bounded exact walk. Raw exports are retained; only final best/current and any eligible target receive parent double verification. No advantage, novelty or lower-bound claim.'}
    base.atomic(output/'summary.json',summary);return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['campaign','input','binary','source-audit','output-dir']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--expected-source-audit-sha256',required=True);parser.add_argument('--expected-code-sha256',required=True);parser.add_argument('--preview',action='store_true');a=parser.parse_args(argv)
    campaign=a.campaign.resolve();output=a.output_dir.resolve()
    if output!=campaign/'baseline-native300-001' or output.exists():raise ValueError('only one new authorized output directory')
    if base.sha(Path(__file__).read_bytes())!=a.expected_code_sha256 or base.sha(a.source_audit.read_bytes())!=a.expected_source_audit_sha256:raise ValueError('runtime/source approval pin differs')
    config_raw=(campaign/'campaign.json').read_bytes();config=json.loads(config_raw)
    if config['dimension']!=5 or config['field']!=2 or config['target_rank']!=92:raise ValueError('campaign target differs')
    guard=lifecycle.Guard(DEADLINE,325,campaign,campaign/'operations-v3/state.json',base.sha(config_raw));guard('pre_baseline_preparation')
    if time.time()+330>guard.hard.timestamp():raise ValueError('outer envelope does not fit absolute deadline')
    source_raw=a.input.read_bytes();binary_raw=a.binary.read_bytes()
    if base.sha(source_raw)!=INPUT_SHA or base.sha(binary_raw)!=BINARY_SHA:raise ValueError('known source/native binary pin differs')
    audit=json.loads(a.source_audit.read_bytes());eligible=next(item for item in audit['sources'] if item['raw_sha256']==INPUT_SHA)
    if eligible['eligibility']!='ELIGIBLE_ROOT_APPROVED_TRAIN_NATIVE_ROOT' or eligible['heldout_evaluation_ancestors']:raise ValueError('known source eligibility differs')
    source=json.loads(source_raw);first=verify_candidate(source,random_trials=0);guard('post_input_primary_full15625');second=verify_bytes(source_raw);guard('post_input_strict_independent')
    if not first['valid'] or not second['valid'] or first['exact_entries_checked']!=15625 or second['essential_rank']!=93:raise ValueError('baseline input is not exact93')
    terms=base.canonical_terms(source);metadata={'format':'one-shot-native-baseline7-v1','source_sha256':INPUT_SHA,'source_audit_sha256':a.expected_source_audit_sha256,'input_primary':first,'input_independent':second,'binary_sha256':BINARY_SHA,'seed':SEED,'n':5,'target':92,'max_rank':105,'cyclic':False,'plus_burst':1,'reduction_dwell':0,'plus_every':20000,'restart_every':50000000,'archive_size':16,'native_seconds':300,'outer_seconds':330,'cpu':0,'memory_mib':768,'deadline':DEADLINE,'code_sha256':a.expected_code_sha256,'guard':guard.observation(),'authorization':'One baseline-native300-001 only; no continuation, optimization controller or local WINNER publication.'}
    if a.preview:print(json.dumps({'status':'PREVIEW_ONLY','zero_mutations':True,**metadata},sort_keys=True));return 0
    os.sched_setaffinity(0,{0});resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2));resource.setrlimit(resource.RLIMIT_CORE,(0,0));output.mkdir(parents=True)
    base.freeze(output/'manifest.json',base.raw_json(metadata));base.freeze(output/'input.json',source_raw);base.freeze(output/'frozen/native-worker',binary_raw,True)
    reason=None
    def fresh(barrier):
        nonlocal reason
        try:guard(barrier);return True
        except lifecycle.Stop as error:reason=str(error);return False
    summary=execute(output/'frozen/native-worker',terms,output,fresh);summary.update(stop_reason=reason,guard_final=guard.observation());base.atomic(output/'summary.json',summary);print(json.dumps({key:summary.get(key) for key in ['status','native_queries_started','eligible_target_emitted','execution','stop_reason']},sort_keys=True));return 0

if __name__=='__main__':raise SystemExit(main())
