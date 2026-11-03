"""Preview or root-apply a lossless V2->V3 coordinator epoch migration.

Preview never writes or signals. Apply signals ONLY the pidfd-pinned, hash/argv/
start-tick-checked V2 coordinator with SIGTERM, waits for its current tick to
finish, then copies all history into a new epoch. Queue/guard/workers are never
modified or signaled. V3 is not launched or armed by this utility.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import time
import uuid


def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('duplicate JSON key: '+key)
        result[key]=value
    return result


def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def payload(value): return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def utc(): return dt.datetime.now(dt.timezone.utc).isoformat()


def read(path):
    raw=Path(path).read_bytes();value=json.loads(raw,object_pairs_hook=unique,
        parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON constant')))
    if not isinstance(value,dict): raise ValueError('expected JSON object: '+str(path))
    return value,sha(raw)


def process_info(pid):
    try:
        raw=Path(f'/proc/{pid}/stat').read_text();fields=raw[raw.rfind(')')+2:].split()
        if fields[0] in ('Z','X'): return None
        argv=[x.decode(errors='replace') for x in Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0') if x]
        return {'pid':pid,'start_ticks':int(fields[19]),'argv':argv}
    except (OSError,ValueError,IndexError): return None


def check_identity(context,info):
    if info is None: return False
    if info['start_ticks']!=context['old_start_ticks']: raise ValueError('V2 PID reused/start identity differs; never signal')
    if context['old_code_path'] not in info['argv'] or 'run' not in info['argv']:
        raise ValueError('live PID argv is not the approved V2 coordinator; never signal')
    for key,expected in (('--plan',context['old_plan_path']),('--gate',context['old_gate_path'])):
        argv=info['argv']
        if key not in argv or str(Path(argv[argv.index(key)+1]).resolve())!=expected:
            raise ValueError('live V2 plan/gate argv differs; never signal')
    return True


def clean_state(state):
    if state.get('format')!='mmsearch-phase-coordinator-v2': raise ValueError('requires V2 coordinator state')
    if state.get('pending_action') is not None: raise ValueError('unresolved unqueued pending intent: migration refused')
    if not isinstance(state.get('held_actions',{}),dict) or state.get('held_actions'):
        raise ValueError('unresolved held actions: migration refused')
    if not isinstance(state.get('ledger'),list): raise ValueError('missing full V2 ledger')


def validate_history(state,plan,queue):
    clean_state(state)
    if set(queue)!={'jobs'}: raise ValueError('unexpected queue format')
    jobs={job['id']:job for job in queue['jobs']}
    if len(jobs)!=len(queue['jobs']): raise ValueError('duplicate queue IDs')
    branches={(b['kind'],b['name']):b for b in plan['branches']}
    groups=defaultdict(list);seen=set()
    for entry in state['ledger']:
        key=(entry['kind'],entry['branch'])
        if key not in branches: raise ValueError('ledger branch absent from unchanged plan')
        job=entry['job'];identifier=job['id'];sequence=entry['sequence'];branch=branches[key]
        if identifier in seen or type(sequence) is not int or sequence<1: raise ValueError('duplicate/invalid ledger sequence')
        seen.add(identifier);groups[key].append(sequence)
        if identifier!=f"{branch['prefix']}-{sequence:03d}": raise ValueError('ledger prefix/sequence differs')
        if sha(canonical(job))!=entry['job_sha256'] or jobs.get(identifier)!=job:
            raise ValueError('ledger job digest or live queue spec differs: '+identifier)
        if Path(entry['outdir']).resolve()!=Path(plan['campaign']).resolve()/identifier:
            raise ValueError('ledger output directory differs')
    for key,sequences in groups.items():
        if sequences!=list(range(1,len(sequences)+1)): raise ValueError('ledger sequences have gaps/reset/order changes')
    for branch in plan['branches']:
        prefix=branch['prefix']+'-'
        for identifier in jobs:
            if identifier.startswith(prefix) and identifier[len(prefix):].isdigit() and identifier not in seen:
                raise ValueError('reserved prefix job exists outside full ledger: '+identifier)
    return {kind+':'+name:len(groups[(kind,name)]) for kind,name in branches}


def inspect(campaign,old_plan,old_gate,old_launch,new_plan,new_code,new_gate,*,expected_new_plan_sha,expected_new_code_sha):
    campaign=Path(campaign).resolve();old_root=campaign/'phase-coordinator42-v2';new_root=campaign/'phase-coordinator42-v3'
    if new_root.exists() or Path(new_gate).exists(): raise ValueError('V3 state/gate already exists; never overwrite or reset')
    if not Path(new_gate).resolve().is_relative_to(campaign): raise ValueError('V3 gate must stay under the declared campaign')
    old,old_plan_sha=read(old_plan);new,new_plan_sha=read(new_plan)
    if old.get('format')!='mmsearch-phase-plan-v2' or new.get('format')!='mmsearch-phase-plan-v3': raise ValueError('wrong epoch plan format')
    if {k:v for k,v in old.items() if k!='format'}!={k:v for k,v in new.items() if k!='format'}:
        raise ValueError('V3 plan changes more than epoch format; limits/lineage/prefix changes forbidden')
    if Path(old['campaign']).resolve()!=campaign: raise ValueError('plan campaign differs')
    if new_plan_sha!=expected_new_plan_sha or sha(Path(new_code).read_bytes())!=expected_new_code_sha:
        raise ValueError('reviewed V3 code/plan hash differs')
    gate,old_gate_sha=read(old_gate);launch,launch_sha=read(old_launch)
    if type(launch.get('pid')) is not int or launch['pid']<=1 or type(launch.get('start_ticks')) is not int or launch['start_ticks']<1:
        raise ValueError('V2 launch PID/start ticks must be explicit positive integers')
    if (gate.get('format')!='mmsearch-phase-arm-v2' or gate.get('owner')!='root' or gate.get('armed') is not True
        or gate.get('plan_sha256')!=old_plan_sha or gate.get('coordinator_sha256')!=launch['source_sha256']
        or launch.get('plan_sha256')!=old_plan_sha): raise ValueError('V2 gate/launch/plan bindings differ')
    argv=launch['command'];script=Path(argv[argv.index('run')-1]).resolve()
    if script.name!='phase_coordinator42_v2.py' or sha(script.read_bytes())!=launch['source_sha256']:
        raise ValueError('V2 launched source differs')
    for key,path in (('--plan',old_plan),('--gate',old_gate)):
        if str(Path(argv[argv.index(key)+1]).resolve())!=str(Path(path).resolve()): raise ValueError('V2 launch paths differ')
    state,state_sha=read(old_root/'state.json');queue,queue_sha=read(campaign/'queue.json')
    if state.get('plan_sha256')!=old_plan_sha: raise ValueError('V2 state plan differs')
    counts=validate_history(state,old,queue)
    context={'format':'coordinator-migration-preview-v1','campaign':str(campaign),'old_root':str(old_root),'new_root':str(new_root),
        'old_pid':launch['pid'],'old_start_ticks':launch['start_ticks'],'old_code_path':str(script),
        'old_plan_path':str(Path(old_plan).resolve()),'old_gate_path':str(Path(old_gate).resolve()),
        'old_launch_path':str(Path(old_launch).resolve()),'new_plan_path':str(Path(new_plan).resolve()),
        'new_code_path':str(Path(new_code).resolve()),'new_gate_path':str(Path(new_gate).resolve()),
        'old_code_sha256':launch['source_sha256'],'new_code_sha256':expected_new_code_sha,
        'old_plan_sha256':old_plan_sha,'new_plan_sha256':new_plan_sha,'old_gate_sha256':old_gate_sha,
        'old_launch_sha256':launch_sha,'pre_stop_state_sha256':state_sha,'queue_sha256_at_inspection':queue_sha,
        'ledger_entries':len(state['ledger']),'sequence_counts':counts,'ledger_sha256':sha(canonical(state['ledger'])),
        'armed_kinds_preserved':gate['armed_kinds'],'rl_clearance_preserved':gate.get('rl_clearance'),
        'zero_mutations':True,'utc':utc()}
    context['v2_live']=check_identity(context,process_info(context['old_pid']))
    return context


def stop_v2(context,*,timeout=35):
    info=process_info(context['old_pid'])
    if not check_identity(context,info): return {'status':'already_stopped','utc':utc(),'signal_sent':False}
    if not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal'):
        raise ValueError('pidfd support required; no unsafe signal fallback')
    descriptor=os.pidfd_open(context['old_pid'],0)
    try:
        if not check_identity(context,process_info(context['old_pid'])):
            return {'status':'stopped_before_signal','utc':utc(),'signal_sent':False}
        signal.pidfd_send_signal(descriptor,signal.SIGTERM,None,0)
    finally: os.close(descriptor)
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        current=process_info(context['old_pid'])
        if current is None or current['start_ticks']!=context['old_start_ticks']:
            return {'status':'stopped_after_clean_tick_request','utc':utc(),'signal_sent':True,
                    'only_pid':context['old_pid'],'only_start_ticks':context['old_start_ticks'],'signal':'SIGTERM via pidfd'}
        time.sleep(.05)
    raise ValueError('V2 did not stop within35s; no KILL and no migration; queue/guard/workers untouched')


def exclusive(path,raw,mode=0o444):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream: stream.write(raw);stream.flush();os.fsync(stream.fileno())
    path.chmod(mode)


def apply(context,*,stopper=stop_v2):
    """Explicit root-only mutation step. Never launches or arms V3."""
    old_root=Path(context['old_root']);new_root=Path(context['new_root']);new_gate=Path(context['new_gate_path'])
    if new_root.exists() or new_gate.exists(): raise ValueError('V3 destination already exists')
    # Revalidate approved source/gate bindings before requesting shutdown.
    for path,key in ((context['old_code_path'],'old_code_sha256'),(context['new_code_path'],'new_code_sha256'),
                     (context['old_plan_path'],'old_plan_sha256'),(context['new_plan_path'],'new_plan_sha256'),
                     (context['old_gate_path'],'old_gate_sha256'),(context['old_launch_path'],'old_launch_sha256')):
        if sha(Path(path).read_bytes())!=context[key]: raise ValueError('pre-stop migration binding changed: '+path)
    before,_=read(old_root/'state.json');clean_state(before)
    stopped=stopper(context)
    if check_identity(context,process_info(context['old_pid'])): raise ValueError('V2 is still live; no migration')
    # Holding V2's unchanged singleton lock prevents restart during copying.
    legacy=(old_root/'supervisor.lock').open('r')
    try: fcntl.flock(legacy,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BaseException:
        legacy.close();raise
    stage=new_root.with_name(new_root.name+'.pending-'+uuid.uuid4().hex)
    try:
        state,old_state_sha=read(old_root/'state.json');clean_state(state)
        old_plan,_=read(context['old_plan_path']);queue,queue_sha=read(Path(context['campaign'])/'queue.json')
        counts=validate_history(state,old_plan,queue)
        stage.mkdir();copied=[]
        for path in sorted(old_root.rglob('*')):
            if path.is_symlink(): raise ValueError('symlink in V2 history; migration refused')
            if not path.is_file() or path.name=='supervisor.lock': continue
            relative=path.relative_to(old_root);raw=path.read_bytes();target=stage/relative
            exclusive(target,raw,path.stat().st_mode&0o777)
            copied.append({'path':str(relative),'sha256':sha(raw),'size':len(raw)})
        if sha((old_root/'state.json').read_bytes())!=old_state_sha: raise ValueError('V2 state changed after shutdown')
        inputs=stage/'migration-inputs'
        source_inputs={'v2-state.json':old_root/'state.json','v2-plan.json':Path(context['old_plan_path']),
            'v2-gate.json':Path(context['old_gate_path']),'v2-launch.json':Path(context['old_launch_path']),
            'phase_coordinator42_v2.py':Path(context['old_code_path']),'v3-plan.json':Path(context['new_plan_path']),
            'phase_coordinator42_v3.py':Path(context['new_code_path'])}
        for name,path in source_inputs.items(): exclusive(inputs/name,path.read_bytes())
        migrated=json.loads(json.dumps(state));migrated.update(format='mmsearch-phase-coordinator-v3',plan_sha256=context['new_plan_sha256'])
        migrated['migration']={'format':'coordinator-epoch-migration-v1','old_state_sha256':old_state_sha,
            'old_plan_sha256':context['old_plan_sha256'],'new_plan_sha256':context['new_plan_sha256'],
            'old_code_sha256':context['old_code_sha256'],'new_code_sha256':context['new_code_sha256'],
            'ledger_entries_preserved':len(state['ledger']),'old_ledger_sha256':sha(canonical(state['ledger'])),'utc':utc()}
        if migrated['ledger']!=state['ledger']: raise ValueError('migration changed a ledger entry')
        # The copied original state remains additionally frozen in inputs/.
        (stage/'state.json').unlink();exclusive(stage/'state.json',payload(migrated),0o644)
        receipt={**context,'format':'coordinator-migration-receipt-v1','zero_mutations':False,'old_state_sha256':old_state_sha,
            'pre_stop_ledger_entries':context['ledger_entries'],'pre_stop_ledger_sha256':context['ledger_sha256'],
            'ledger_entries':len(state['ledger']),'ledger_sha256':sha(canonical(state['ledger'])),
            'new_initial_state_sha256':sha(payload(migrated)),'old_ledger_sha256':sha(canonical(state['ledger'])),
            'new_ledger_sha256':sha(canonical(migrated['ledger'])),'sequence_counts':counts,'queue_sha256_at_copy':queue_sha,
            'copied_history_files':copied,'v2_stop':stopped,'completed_utc':utc(),
            'migration_helper_sha256':sha(Path(__file__).read_bytes()),'v3_launched':False,'v3_armed':False}
        exclusive(stage/'migration-receipt.json',payload(receipt))
        gate,_=read(context['old_gate_path']);gate.update(format='mmsearch-phase-arm-v3',armed=False,
            plan_sha256=context['new_plan_sha256'],coordinator_sha256=context['new_code_sha256'],
            migration_receipt_sha256=sha(payload(receipt)))
        # Verify every copied history artifact before publishing the new epoch.
        for item in copied:
            target=inputs/'v2-state.json' if item['path']=='state.json' else stage/item['path']
            if sha(target.read_bytes())!=item['sha256']: raise ValueError('copied history checksum mismatch')
        for path,key in ((context['old_code_path'],'old_code_sha256'),(context['new_code_path'],'new_code_sha256'),
                         (context['old_plan_path'],'old_plan_sha256'),(context['new_plan_path'],'new_plan_sha256'),
                         (context['old_gate_path'],'old_gate_sha256'),(context['old_launch_path'],'old_launch_sha256')):
            if sha(Path(path).read_bytes())!=context[key]: raise ValueError('migration binding changed after shutdown: '+path)
        stage.rename(new_root)
        descriptor=os.open(new_root.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
        exclusive(new_gate,payload(gate))
        return receipt
    finally: legacy.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('preview','apply'))
    for name in ('campaign','old-plan','old-gate','old-launch','new-plan','new-code','new-gate'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--expected-new-plan-sha256',required=True);p.add_argument('--expected-new-code-sha256',required=True)
    args=p.parse_args(argv)
    context=inspect(args.campaign,args.old_plan,args.old_gate,args.old_launch,args.new_plan,args.new_code,args.new_gate,
        expected_new_plan_sha=args.expected_new_plan_sha256,expected_new_code_sha=args.expected_new_code_sha256)
    result=context if args.mode=='preview' else apply(context)
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=='__main__':main()
