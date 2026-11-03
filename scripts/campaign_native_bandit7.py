"""Eight guarded contextual native epochs; exact sampled rewards, no training.

Normal completion of a fixed-time native exploration epoch is not a negative
rank claim. Native errors, missing telemetry, guard expiry and incomplete
verification stop the series. Policy selection never uses raw CPU rate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from scripts import campaign_native_portfolio7 as p
from scripts.phase_coordinator42_v2 import validate_job

MIB=1024**2
ARMS=[dict(name='c3-K1-D0-C2000',cyclic=True,plus_burst=1,reduction_dwell=0,plus_every=2000),
      dict(name='c3-K4-D128-C20000',cyclic=True,plus_burst=4,reduction_dwell=128,plus_every=20000),
      dict(name='c3-K4-D0-C200000',cyclic=True,plus_burst=4,reduction_dwell=0,plus_every=200000),
      dict(name='free-K1-D128-C2000',cyclic=False,plus_burst=1,reduction_dwell=128,plus_every=2000),
      dict(name='free-K4-D128-C200000',cyclic=False,plus_burst=4,reduction_dwell=128,plus_every=200000),
      dict(name='free-K4-D0-C20000',cyclic=False,plus_burst=4,reduction_dwell=0,plus_every=20000)]
ORIGINAL_COMMAND=p.command

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def read_pin(path,pin):
    raw=Path(path).read_bytes()
    if sha(raw)!=pin:raise ValueError('immutable input/checkpoint pin differs')
    return json.loads(raw)

def validate_state(state,manifest_sha,baseline_sha):
    if (state.get('schema')!='native-bandit7.checkpoint.v1' or state.get('manifest_sha256')!=manifest_sha
            or state.get('baseline_sha256')!=baseline_sha or type(state.get('completed_epochs')) is not int
            or not 0<=state['completed_epochs']<=8 or len(state.get('counts',[]))!=6
            or len(state.get('reward_sums',[]))!=6 or sum(state['counts'])!=state['completed_epochs']
            or any(type(x)is not int or x<0 for x in state['counts'])
            or any(type(x)not in(int,float) or not math.isfinite(x) or x<0 for x in state['reward_sums'])
            or state.get('status')!='READY_NEXT_EPOCH'):
        raise ValueError('ineligible or malformed policy checkpoint')
    if (not isinstance(state.get('accepted_hashes'),list) or len(state['accepted_hashes'])>32*state['completed_epochs']
            or any(not isinstance(x,str) or len(x)!=64 or any(c not in '0123456789abcdef' for c in x) for x in state['accepted_hashes'])
            or not isinstance(state.get('used_seeds'),list) or len(state['used_seeds'])!=state['completed_epochs']
            or any(type(x)is not int or not 0<=x<2**63 for x in state['used_seeds'])
            or len(state['used_seeds'])!=len(set(state['used_seeds']))):
        raise ValueError('malformed reward hashes or used seed ledger')
    if any(not isinstance(term,list) or len(term)!=3 or any(type(x)is not int or not 0<x<2**25 for x in term) for term in state['known_atoms']):
        raise ValueError('malformed whole-atom coverage ledger')
    if len(state['accepted_hashes'])!=len(set(state['accepted_hashes'])) or len(state['known_atoms'])!=len(set(map(tuple,state['known_atoms']))):
        raise ValueError('checkpoint set representation differs')
    observed=state.get('observed_hashes')
    if (not isinstance(observed,list) or len(observed)!=len(set(observed))
            or any(not isinstance(x,str) or len(x)!=64 or any(c not in '0123456789abcdef' for c in x) for x in observed)
            or not set(state['accepted_hashes']).issubset(observed)):
        raise ValueError('malformed observed raw exclusion ledger')
    rng=random.Random();rng.setstate(tuple_state(state['rng_state']))
    contexts=state.get('contexts',{})
    if set(contexts)!={'cyclic_source','noncyclic_source'}:raise ValueError('exact source contexts required')
    for context in contexts.values():
        if (len(context.get('counts',[]))!=6 or len(context.get('reward_sums',[]))!=6
                or any(type(x)is not int or x<0 for x in context['counts'])
                or any(type(x)not in(int,float) or not math.isfinite(x) or x<0 for x in context['reward_sums'])):
            raise ValueError('malformed source context accounting')
    if any(sum(context['counts'][i] for context in contexts.values())!=state['counts'][i]
            or not math.isclose(sum(context['reward_sums'][i] for context in contexts.values()),state['reward_sums'][i],abs_tol=1e-12)
            or state['reward_sums'][i]>state['counts'][i]+1e-12 for i in range(6)):
        raise ValueError('source context accounting does not match policy totals')
    return state

def choose(state,sources):
    epoch=state['completed_epochs']
    if epoch>=8:raise ValueError('eight authorized epochs exhausted')
    # Two of eight are unconditionally reserved for C3/new-cadence exploration.
    exploratory=epoch in (0,4)
    rng=random.Random();rng.setstate(tuple_state(state['rng_state']))
    eligible=sorted(int(k) for k,v in sources.items() if not exploratory or v['cyclic_complete'])
    if not eligible:raise ValueError('no eligible source for exact arm mode')
    source=rng.choice(eligible)
    context='cyclic_source' if sources[str(source)]['cyclic_complete'] else 'noncyclic_source'
    contextual=state['contexts'][context]
    if exploratory:arm=(0,2)[epoch//4]
    else:
        candidates=[3,4,5] if epoch==7 else [3,4]
        untried=[i for i in candidates if not contextual['counts'][i]]
        arm=untried[0] if untried else max(candidates,key=lambda i:(
            .5*state['reward_sums'][i]/state['counts'][i]+.5*contextual['reward_sums'][i]/contextual['counts'][i]
            +math.sqrt(2*math.log(epoch+1)/contextual['counts'][i]),-i))
    seed=rng.getrandbits(62)|(1<<62)
    while seed==p.safe.SEED or seed in state['used_seeds']:seed=rng.getrandbits(62)|(1<<62)
    profile=p.validate_profile(dict(id=f'native-bandit7-e{epoch+1:02d}',source_id=source,seed=seed,
        **{k:v for k,v in ARMS[arm].items() if k!='name'}))
    return dict(profile=profile,arm=arm,arm_name=ARMS[arm]['name'],context=context,exploration_reserved=exploratory,
        rng_state_after=rng.getstate(),policy='Reserved C3 exploration plus reward UCB over unrestricted arms; no rate-based arm selection.')

def tuple_state(value):return tuple(tuple_state(x) if isinstance(x,list) else x for x in value)

def epoch_command(binary,input_path,prefix,profile,*,seconds=180,n=5,target=92,steps=10**12):
    if n==5:
        if seconds!=180 or target!=92:raise ValueError('authorized native epoch is exactly180seconds/target92')
        argv=ORIGINAL_COMMAND(binary,input_path,prefix,profile,seconds=120,n=n,target=target,steps=steps)
        argv[argv.index('--seconds')+1]='180';return argv
    return ORIGINAL_COMMAND(binary,input_path,prefix,profile,seconds=seconds,n=n,target=target,steps=steps)

def completed_native(summary,expected_seconds=None):
    execution=summary.get('execution',{})
    stats=summary.get('stats') or {}
    seconds=stats.get('seconds_budget');elapsed=stats.get('elapsed_seconds')
    return (execution.get('exit_code')==0 and execution.get('timed_out') is False
        and execution.get('interrupted') is False and stats.get('stopped_by_signal') is False
        and type(seconds) in(int,float) and math.isfinite(seconds) and seconds in(120,180)
        and (expected_seconds is None or seconds==expected_seconds)
        and type(elapsed) in(int,float) and math.isfinite(elapsed) and elapsed>=seconds-.05
        and stats.get('target_reached') is False
        and summary.get('final_checks_complete') is True and summary.get('eligible_target_emitted') is False)

def validate_source(raw,source,cyclic,fresh):
    if (source.get('root_approved_train') is not True or source.get('heldout_evaluation_ancestors') is not False
            or source.get('parent_ids')!=[] or source.get('parent_files')!=[] or sha(raw)!=source['sha256']):
        raise ValueError('ineligible or drifted initial training source')
    candidate=json.loads(raw);p.lifecycle.reject_ineligible_metadata(candidate.get('metadata',{}))
    terms=p.safe.base.canonical_terms(candidate)
    if (p.lifecycle.term_identity(candidate)!=source['identity']['term_set_sha256']
            or p.lifecycle.digest(sorted(terms))!=source['identity']['rl_source_sha256']
            or cyclic and not p.c3_closed(terms)):
        raise ValueError('source identity or cyclic binding failed')
    if not fresh('pre_source_double_verify'):raise p.OutputHold('source guard stopped')
    first=p.safe.verify_candidate(candidate,random_trials=0)
    if not fresh('post_source_primary'):raise p.OutputHold('source primary late')
    second=p.safe.independent(candidate,raw)
    if not fresh('post_source_independent'):raise p.OutputHold('source independent late')
    if not first['valid'] or not second['valid'] or second['essential_rank']!=93 or first['exact_entries_checked']!=15625 or second['exact_entries_checked']!=15625:
        raise ValueError('source full double verification failed')
    return terms,first,second

class Budget:
    def __init__(self,campaign,bundle,current):
        self.campaign,self.bundle,self.current=campaign,bundle,current;self.last=-float('inf')
    def check(self,force=False,pending_bytes=0):
        if type(pending_bytes)is not int or pending_bytes<0:raise ValueError('nonnegative exact pending byte reservation required')
        if not force and not pending_bytes and time.monotonic()-self.last<.5:return
        self.last=time.monotonic();self.current_bytes=p.SpaceBudget.size(self.current)
        self.total_bytes=p.SpaceBudget.size(self.bundle)+sum(p.SpaceBudget.size(self.campaign/f'native-bandit7-e{i:02d}') for i in range(1,9))
        if (self.current_bytes>=28*MIB or self.total_bytes>=248*MIB
                or self.current_bytes+pending_bytes>30*MIB or self.total_bytes+pending_bytes>250*MIB):
            raise p.OutputHold('bandit250MiB aggregate/30MiB epoch reserve hold')

def reserve(fresh,barrier,pending_bytes):
    # Control callbacks may have no disk hook; production always attaches it.
    hook=getattr(fresh,'reserve',None)
    return hook(barrier,pending_bytes) if hook is not None else fresh(barrier)

def sample_rewards(summary,output,state,baseline,fresh,*,cap=32,n=5):
    if type(cap)is not int or not 0<=cap<=32:raise ValueError('maximum32doubleverified samples')
    if set(baseline['known_hashes']) & set(state['accepted_hashes']):raise ValueError('accepted reward overlaps frozen comparison')
    known=set(baseline['known_hashes'])|set(state['observed_hashes']);atoms=set(map(tuple,state['known_atoms']))
    # A deterministic hash order prevents cherry-picking after verification.
    selected=sorted(k for k,v in summary['raw_exports'].items() if v['rank']==93 and k not in known)[:cap]
    accepted=[];before=len(atoms)
    for digest in selected:
        path=output/'.raw-native-returns'/(digest+'.txt');terms,raw=p.safe.base.snapshot(path,n)
        item=summary['raw_exports'][digest]
        if len(terms)!=93 or sha(raw)!=item['raw_sha256'] or p.safe.base.term_set_sha256(terms)!=digest:
            raise ValueError('sampled raw source/hash binding differs')
        if not fresh('pre_reward_double_verify'):raise p.OutputHold('reward late before full checks')
        candidate=p.safe.base.encode_candidate(terms,n);payload=p.safe.base.raw_json(candidate)
        first=p.safe.verify_candidate(candidate,random_trials=0)
        if not fresh('post_reward_primary'):raise p.OutputHold('reward late after primary')
        second=p.safe.independent(candidate,payload)
        if not fresh('post_reward_independent'):raise p.OutputHold('reward late after independent')
        if not first['valid'] or not second['valid'] or first['exact_entries_checked']!=n**6 or second['exact_entries_checked']!=n**6:
            raise ValueError('sampled rank93 full double verification failed')
        if n==5 and second['essential_rank']!=93:raise ValueError('sampled essential rank differs')
        proof=encoded(dict(primary=first,independent=second))
        if not reserve(fresh,'pre_reward_persist',len(payload)+len(proof)):raise p.OutputHold('reward write byte reservation held')
        p.safe.base.freeze(output/'.reward-samples'/(digest+'.candidate.raw'),payload)
        p.safe.base.freeze(output/'.reward-samples'/(digest+'.proof.raw'),proof)
        if not fresh('post_reward_persist'):raise p.OutputHold('reward late after hidden persistence')
        accepted.append(digest);atoms.update(terms)
    new_atoms=len(atoms)-before
    reward=.5*len(accepted)/32+.5*min(new_atoms,512)/512
    return dict(accepted_hashes=accepted,selected_hashes=selected,new_atom_count=new_atoms,
        known_atoms=sorted(atoms),reward=reward,doubleverified_samples=len(accepted),
        claim='New only relative to frozen comparison and accepted reward ledger; no mathematical novelty claim.')

def publish_checkpoint(output,value,fresh):
    raw=encoded(value)
    if not reserve(fresh,'pre_checkpoint_persist',len(raw)):raise p.OutputHold('checkpoint byte reservation held')
    pending=output/'.checkpoint.pending.raw';p.safe.base.freeze(pending,raw)
    if not fresh('pre_checkpoint_handoff'):raise p.OutputHold('late checkpoint remains hidden')
    final=output/'checkpoint.json';os.replace(pending,final)
    if not fresh('post_checkpoint_handoff'):
        os.replace(final,output/'.checkpoint.late.raw');raise p.OutputHold('late checkpoint rolled back')
    return sha(final.read_bytes())

def load_bundle(bundle,pin):
    manifest=read_pin(bundle/'manifest.json',pin)
    for name,expected in manifest['files'].items():
        path=(bundle/name).resolve(strict=True)
        if not path.is_relative_to(bundle) or sha(path.read_bytes())!=expected:raise ValueError('frozen runtime/input differs')
    return manifest

def prepare_job(bundle,pin,checkpoint,checkpoint_sha,proposal):
    manifest=load_bundle(bundle,pin);state=validate_state(read_pin(checkpoint,checkpoint_sha),pin,manifest['baseline_sha256'])
    choice=choose(state,manifest['sources']);campaign=Path(manifest['campaign']);name=choice['profile']['id']
    if (campaign/name).exists():raise ValueError('new epoch output required')
    job=dict(id=name,cpu=2,memory_mb=768,seconds=210,enabled=False,
        command=[sys.executable,'-B',str(bundle/'code/scripts/campaign_native_bandit7.py'),
            '--bundle',str(bundle),'--manifest-sha256',pin,'--checkpoint',str(checkpoint),
            '--checkpoint-sha256',checkpoint_sha,'--output-dir',str(campaign/name),'--execute'])
    validate_job(job);p.safe.base.freeze(proposal,encoded(dict(jobs=[job])))
    return dict(job=job,proposal_sha256=sha(proposal.read_bytes()),choice=choice)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--checkpoint',type=Path,required=True);parser.add_argument('--checkpoint-sha256',required=True)
    parser.add_argument('--output-dir',type=Path);parser.add_argument('--execute',action='store_true')
    parser.add_argument('--prepare-job',type=Path)
    args=parser.parse_args(argv);bundle=args.bundle.resolve()
    if args.prepare_job:
        if args.execute:raise ValueError('preparation is query-free')
        print(json.dumps(prepare_job(bundle,args.manifest_sha256,args.checkpoint.resolve(),args.checkpoint_sha256,args.prepare_job),sort_keys=True));return 0
    if not args.execute:raise ValueError('disabled without explicit execution')
    manifest=load_bundle(bundle,args.manifest_sha256)
    state=validate_state(read_pin(args.checkpoint,args.checkpoint_sha256),args.manifest_sha256,manifest['baseline_sha256'])
    choice=choose(state,manifest['sources']);profile=choice['profile'];campaign=Path(manifest['campaign'])
    output=args.output_dir.resolve()
    if output!=campaign/profile['id'] or output.exists() or args.output_dir.is_symlink():raise ValueError('exclusive exact epoch output required')
    if os.sched_getaffinity(0)!={2}:raise ValueError('queue CPU2 affinity required; no launch on other cores')
    guard=p.lifecycle.Guard(p.DEADLINE,202,campaign,campaign/'operations-v3/state.json',manifest['campaign_sha256'])
    guard.canonical=p.CampaignGuard(202,guard.hard.isoformat(),(),campaign/'operations-v3/state.json',campaign_dir=campaign)
    guard('pre_epoch_input')
    if time.time()+210>guard.hard.timestamp():raise ValueError('epoch envelope exceeds campaign deadline')
    source=manifest['sources'][str(profile['source_id'])]
    raw=(bundle/source['file']).read_bytes()
    def input_fresh(barrier):guard(barrier);return True
    terms,first,second=validate_source(raw,source,profile['cyclic'],input_fresh)
    soft,hard=resource.getrlimit(resource.RLIMIT_AS);cap=min([768*MIB]+[x for x in (soft,hard) if x!=resource.RLIM_INFINITY]);resource.setrlimit(resource.RLIMIT_AS,(cap,hard));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    if os.getpriority(os.PRIO_PROCESS,0)<10:os.nice(10-os.getpriority(os.PRIO_PROCESS,0))
    output.mkdir();p.safe.base.freeze(output/'input.raw',raw)
    p.safe.base.freeze(output/'epoch-input.json',encoded(dict(manifest_sha256=args.manifest_sha256,previous_checkpoint_sha256=args.checkpoint_sha256,choice=choice,source=source,primary=first,independent=second)))
    budget=Budget(campaign,bundle,output);reason=None
    def fresh(barrier,pending_bytes=0):
        nonlocal reason
        try:guard(barrier);budget.check(force=barrier!='loop',pending_bytes=pending_bytes);return True
        except(p.lifecycle.Stop,p.OutputHold)as error:reason=str(error);return False
    fresh.reserve=fresh
    original_atomic=p.safe.base.atomic
    def bounded_atomic(path,value):
        raw=p.safe.base.raw_json(value)
        if not reserve(fresh,'pre_native_summary_persist',len(raw)):raise p.OutputHold('native summary byte reservation held')
        return original_atomic(path,value)
    p.command=epoch_command
    p.safe.base.atomic=bounded_atomic
    try:summary=p.execute(bundle/'native/plus-burst-worker',terms,output,fresh,profile,seconds=180)
    finally:p.command=ORIGINAL_COMMAND;p.safe.base.atomic=original_atomic
    if not (output/'summary.json').exists():p.safe.base.freeze(output/'summary.json',encoded(summary))
    outcome=dict(status='STOPPED_ERROR_OR_UNKNOWN',previous_checkpoint_sha256=args.checkpoint_sha256,choice=choice,
        native_summary_sha256=sha((output/'summary.json').read_bytes()),continue_authorized=False)
    try:
        if summary['eligible_target_emitted']:
            outcome.update(status='TARGET_EMITTED_TO_GLOBAL_GUARD',reward=10**9)
        elif reason or not completed_native(summary,expected_seconds=180):
            outcome['reason']=reason or 'native/telemetry/final-verification incomplete; not a negative result'
        else:
            baseline=read_pin(bundle/'comparison.json',manifest['baseline_sha256'])
            rewards=sample_rewards(summary,output,state,baseline,fresh)
            next_state=json.loads(json.dumps(state));arm=choice['arm']
            next_state['completed_epochs']+=1;next_state['counts'][arm]+=1;next_state['reward_sums'][arm]+=rewards['reward']
            context=next_state['contexts'][choice['context']]
            context['counts'][arm]+=1;context['reward_sums'][arm]+=rewards['reward']
            next_state['accepted_hashes']=sorted(set(state['accepted_hashes'])|set(rewards['accepted_hashes']))
            next_state['observed_hashes']=sorted(set(state['observed_hashes'])|{key for key,item in summary['raw_exports'].items() if item['rank']==93})
            next_state['known_atoms']=rewards['known_atoms'];next_state['rng_state']=choice['rng_state_after']
            next_state['used_seeds'].append(profile['seed']);next_state['previous_checkpoint_sha256']=args.checkpoint_sha256
            next_state['last_epoch_summary_sha256']=outcome['native_summary_sha256']
            checkpoint_sha=publish_checkpoint(output,next_state,fresh)
            outcome.update(status='COMPLETED_EXPLORATION',reward_evidence=rewards,checkpoint_sha256=checkpoint_sha,
                continue_authorized=next_state['completed_epochs']<8)
    except(p.OutputHold,p.lifecycle.Stop,ValueError)as error:outcome['reason']=str(error)
    outcome.update(stop_reason=reason,guard_final=guard.observation(),claim='No global lower bound or novelty claim. Only completed fresh verified epochs update policy.')
    outcome_raw=encoded(outcome)
    if not reserve(fresh,'pre_outcome_persist',len(outcome_raw)):
        outcome=dict(status='STOPPED_ERROR_OR_UNKNOWN',continue_authorized=False,reason='final evidence byte reservation/guard held',
            previous_checkpoint_sha256=args.checkpoint_sha256)
        if(output/'checkpoint.json').exists():os.replace(output/'checkpoint.json',output/'.checkpoint.outcome-held.raw')
        outcome_raw=encoded(outcome)
    p.safe.base.freeze(output/'outcome.json',outcome_raw);print(json.dumps({k:v for k,v in outcome.items() if k!='reward_evidence'},sort_keys=True))
    return 0 if outcome['status'] in('COMPLETED_EXPLORATION','TARGET_EMITTED_TO_GLOBAL_GUARD') else 2

if __name__=='__main__':raise SystemExit(main())
