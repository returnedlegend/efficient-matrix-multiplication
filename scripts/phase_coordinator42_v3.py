"""Empty-root-filtered V3 queue-only coordinator; preview never writes.

No subprocesses, search, policy selection, publication, or process signals.
Every queue writer must cooperate on campaign/queue_append.lock. The existing
queue remains the sole launcher and resource allocator.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import signal
import time

GIB=1024**3
TERMINAL={'completed','failed_to_launch'}
JOB_KEYS={'id','cpu','memory_mb','seconds','command','enabled'}
STORAGE_POLICY={'priority_current_maintenance_bytes':int(4.5*GIB),'hold_new_rl_bytes':5*GIB,
                'hold_other_search_bytes':int(7.5*GIB)}


def sha(raw): return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('duplicate JSON key: '+key)
        result[key]=value
    return result


def read(path):
    raw=Path(path).read_bytes()
    value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
    if not isinstance(value,dict): raise ValueError('expected JSON object: '+str(path))
    return value,sha(raw)


def stamp(value):
    parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None: raise ValueError('UTC offset required')
    return parsed.timestamp()


def utc(now): return dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat()


def atomic(path,value):
    path=Path(path);tmp=path.with_name(path.name+f'.{os.getpid()}.tmp')
    with tmp.open('w') as stream:
        json.dump(value,stream,sort_keys=True,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    tmp.replace(path)
    descriptor=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def job_digest(job): return sha(json.dumps(job,sort_keys=True,separators=(',',':')).encode())


def validate_job(job):
    if not isinstance(job,dict) or set(job)!=JOB_KEYS: raise ValueError('invalid queue job fields')
    if not isinstance(job['id'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',job['id']): raise ValueError('invalid job id')
    if type(job['cpu']) is not int or job['cpu'] not in range(4): raise ValueError('CPU must be0..3')
    if type(job['memory_mb']) is not int or not 64<=job['memory_mb']<=6144: raise ValueError('memory must be64..6144MiB')
    if type(job['seconds']) is not int or job['seconds']<1 or type(job['enabled']) is not bool: raise ValueError('invalid job limit/enabled')
    if not isinstance(job['command'],list) or not job['command'] or any(not isinstance(x,str) or '\0' in x for x in job['command']): raise ValueError('invalid argv')
    if not job['command'][0]: raise ValueError('empty executable')


def queue_value(path):
    value,digest=read(path)
    if set(value)!={'jobs'} or not isinstance(value['jobs'],list): raise ValueError('queue requires only jobs array')
    seen=set()
    for job in value['jobs']:
        validate_job(job)
        if job['id'] in seen: raise ValueError('duplicate queue id')
        seen.add(job['id'])
    return value,digest


def identity(pid):
    try:
        raw=Path(f'/proc/{pid}/stat').read_text();fields=raw[raw.rfind(')')+2:].split()
        return None if fields[0] in ('Z','X') else int(fields[19])
    except (OSError,ValueError,IndexError): return None


def lock_held(path):
    """Read Linux lock state without opening or modifying a production lock."""
    path=Path(path)
    if not path.exists(): return False
    info=path.stat();wanted=(os.major(info.st_dev),os.minor(info.st_dev),info.st_ino)
    for line in Path('/proc/locks').read_text().splitlines():
        fields=line.split()
        if len(fields)<6 or fields[1]!='FLOCK': continue
        try:
            major,minor,inode=fields[5].split(':')
            if (int(major,16),int(minor,16),int(inode))==wanted: return True
        except ValueError: continue
    return False


def contains_real_runs(path):
    """Admission filter only; never follows links or validates/deletes a run."""
    with os.scandir(path) as entries:
        return any(not entry.name.startswith('.') and entry.is_dir(follow_symlinks=False) for entry in entries)


class Coordinator:
    def __init__(self,plan_path,gate_path,*,now=time.time,preview_state=None,preview_gate=None):
        self.plan_path=Path(plan_path).resolve();self.gate_path=Path(gate_path).resolve();self.now=now
        self.plan,self.plan_sha=read(self.plan_path)
        if self.plan.get('format')!='mmsearch-phase-plan-v3': raise ValueError('unsupported coordinator plan')
        if self.plan.get('storage_policy')!=STORAGE_POLICY: raise ValueError('V2 storage policy differs from reviewed4.5/5/7.5GiB thresholds')
        self.directory=Path(self.plan['campaign']).resolve();self.root=self.directory/'phase-coordinator42-v3'
        self.code_sha=sha(Path(__file__).read_bytes());self.hash_cache={}
        self.state={'format':'mmsearch-phase-coordinator-v3','plan_sha256':self.plan_sha,'ledger':[],'held_actions':{},'intent_transitions':[]}
        state_path=self.root/'state.json'
        self.virtual_migration=None
        self.virtual_gate=None
        if preview_state is not None:
            if state_path.exists(): raise ValueError('virtual migration preview requires absent V3 runtime state')
            self.state,old_sha=read(preview_state)
            if self.state.get('format')!='mmsearch-phase-coordinator-v2': raise ValueError('virtual preview requires V2 state')
            if self.state.get('pending_action') or self.state.get('held_actions'): raise ValueError('unresolved V2 intents require owner resolution before migration')
            self.virtual_migration={'old_state_sha256':old_sha,'old_plan_sha256':self.state['plan_sha256'],'ledger_entries':len(self.state['ledger'])}
            self.state.update(format='mmsearch-phase-coordinator-v3',plan_sha256=self.plan_sha)
            if preview_gate is not None: self.virtual_gate,_=read(preview_gate)
        if state_path.exists():
            self.state,_=read(state_path)
            if self.state.get('format')!='mmsearch-phase-coordinator-v3' or self.state.get('plan_sha256')!=self.plan_sha:
                raise ValueError('restart state differs from approved plan; no reset/fallback')
            receipt,_=read(self.root/'migration-receipt.json')
            if (receipt.get('format')!='coordinator-migration-receipt-v1' or receipt.get('new_plan_sha256')!=self.plan_sha
                or receipt.get('new_code_sha256')!=self.code_sha):
                raise ValueError('V3 migration receipt differs from reviewed plan/code')
            original,original_sha=read(self.root/'migration-inputs/v2-state.json')
            if original_sha!=receipt['old_state_sha256'] or self.state.get('migration',{}).get('old_state_sha256')!=original_sha:
                raise ValueError('V3 lost the bound original V2 state')
            if sha(json.dumps(original['ledger'],sort_keys=True,separators=(',',':')).encode())!=receipt['old_ledger_sha256']:
                raise ValueError('original V2 ledger hash differs')
            count=len(original['ledger'])
            if len(self.state['ledger'])<count: raise ValueError('V3 ledger truncated preserved V2 history')
            mutable={'execution_outcome','execution_result_signature','outcome'}
            for old,current in zip(original['ledger'],self.state['ledger'][:count]):
                if {k:v for k,v in old.items() if k not in mutable}!={k:v for k,v in current.items() if k not in mutable}:
                    raise ValueError('V3 changed a preserved V2 job, parent, phase or stream cursor')
        elif preview_state is None:
            raise ValueError('V3 requires preserved migrated V2 state; fresh/reset state is forbidden')

    def bound(self,path,expected):
        path=Path(path);info=path.stat();signature=(info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_ino)
        cached=self.hash_cache.get(str(path))
        if not cached or cached[0]!=signature:
            self.hash_cache[str(path)]=(signature,sha(path.read_bytes()))
        if self.hash_cache[str(path)][1]!=expected: raise ValueError('binding SHA256 mismatch: '+str(path))
        return expected

    def arm(self):
        if not self.gate_path.exists(): return None
        gate,self.gate_sha=read(self.gate_path)
        if gate.get('format')=='mmsearch-phase-arm-v3' and gate.get('armed') is False: return None
        if (gate.get('format')!='mmsearch-phase-arm-v3' or gate.get('owner')!='root' or gate.get('armed') is not True
            or gate.get('plan_sha256')!=self.plan_sha or gate.get('coordinator_sha256')!=self.code_sha):
            raise ValueError('root gate format/owner/plan/source binding mismatch or not armed')
        if not isinstance(gate.get('armed_kinds'),list) or any(k not in ('rl','stream','maintenance') for k in gate['armed_kinds']):
            raise ValueError('invalid armed kinds')
        for path,digest in self.plan.get('bindings',{}).items(): self.bound(path,digest)
        return gate

    def result(self,name):
        path=self.directory/f'{name}-job.result.json'
        if not path.exists():
            state=self.queue_state.get('jobs',{}).get(name,{})
            if state.get('status') in ('failed_to_launch','held_ambiguous'): raise ValueError('predecessor requires owner review: '+name)
            return None
        value,digest=read(path)
        if value.get('exit_code')!=0 or value.get('timed_out') is not False or value.get('interrupted') is not False:
            raise ValueError('predecessor failed/interrupted/timed out: '+name)
        return value,digest

    def completed(self,name): return (self.directory/f'{name}-job.result.json').exists() or self.queue_state.get('jobs',{}).get(name,{}).get('status') in TERMINAL

    def free_cpu(self,cpu,memory_mb):
        reserved={};memory=0
        for job in self.queue['jobs']:
            if job['enabled'] and not self.completed(job['id']): reserved[job['id']]=job
        for path in self.directory.glob('*.running.json'):
            value,_=read(path)
            if identity(value.get('pid')) is not None:
                name=path.name.removesuffix('-job.running.json')
                reserved[name]={'cpu':value['cpu'],'memory_mb':value['memory_mb']}
        for job in reserved.values():
            if type(job['cpu']) is not int or job['cpu'] not in range(4): raise ValueError('invalid live CPU registration')
            if job['cpu']==cpu: return False
            memory+=job['memory_mb']
        return memory+memory_mb<=6144

    def barriers(self):
        config,_=read(self.directory/'campaign.json')
        if (config.get('dimension')!=5 or config.get('field')!=2 or config.get('max_cpu_cores')!=4 or config.get('max_ram_gib')!=8
            or config.get('deadline_utc')!=self.plan['deadline_utc']): raise ValueError('campaign differs from root plan')
        self.deadline=stamp(config['deadline_utc'])
        if self.now()>=self.deadline: return 'global deadline'
        if (self.directory/'guard_stopped.json').exists(): return 'campaign guard stop marker'
        if self.queue_state.get('stop_reason'): return 'queue scheduling stop: '+str(self.queue_state['stop_reason'])
        winners=[self.directory/'WINNER.json',*self.directory.glob('*/WINNER.json')]
        winners.extend(Path(x) for x in self.plan.get('stop_files',[]))
        if any(path.exists() for path in winners): return 'existing WINNER/approved stop file'
        status,_=read(self.directory/'operations-v3/state.json')
        if self.now()-stamp(status['updated_utc'])>60: return 'resource guard heartbeat stale'
        if status.get('stop_reason'): return 'resource guard stopped'
        if status.get('rss_bytes',8*GIB)>7*GIB: return 'RAM barrier'
        if status.get('filesystem_free_bytes',0)<9*GIB: return 'disk scratch barrier'
        self.working_bytes=status.get('campaign_allocated_bytes',8*GIB)
        if type(self.working_bytes) is not int or self.working_bytes<0: raise ValueError('invalid campaign allocated bytes')
        if identity(status.get('pid'))!=status.get('process_identity',{}).get('start_ticks'): return 'resource guard identity unavailable'
        return None

    def storage_hold(self,kind):
        if kind=='rl' and self.working_bytes>=5*GIB: return 'STORAGE_HOLD_NEW_RL_GE_5GIB'
        if kind=='stream' and self.working_bytes>=7.5*GIB: return 'STORAGE_HOLD_SEARCH_GE_7_5GIB'
        return None

    def archive_config(self,branch,sequence):
        template,template_sha=read(branch['config'])
        if template.get('max_runs')!=500 or template.get('max_raw_bytes')!=512*1024**2:
            raise ValueError('maintenance requires root-reviewed max_runs500/maxraw512MiB')
        current_only=self.working_bytes>=4.5*GIB
        policy,_=read(self.directory/'campaign.json')
        campaigns=[self.directory]
        if not current_only and policy.get('prior_campaign'): campaigns.append(Path(policy['prior_campaign']).resolve())
        roots=set()
        patterns=('*/native/record/runs','*/native/runs','*/native/known-recovery/runs')
        for campaign in campaigns:
            for pattern in patterns:
                for path in campaign.glob(pattern):
                    if any(p.is_symlink() for p in (path,*path.parents)):
                        raise ValueError('dynamic native root contains symlink: '+str(path))
                    resolved=path.resolve()
                    if not resolved.is_relative_to(campaign): raise ValueError('dynamic native root escapes authorized campaign')
                    if not resolved.is_dir(): raise ValueError('dynamic native root is not a directory')
                    if not contains_real_runs(resolved): continue
                    roots.add(str(resolved))
        if not roots: return None
        config={**template,'discover_all_native':False,'runs_directories':sorted(roots)}
        mode='current-only' if current_only else 'fair-current-prior'
        path=self.root/'configs'/f"{branch['prefix']}-{sequence:03d}-{mode}.json"
        raw=(json.dumps(config,sort_keys=True,indent=2)+'\n').encode()
        return {'path':str(path),'sha256':sha(raw),'value':config,'mode':mode,'template_sha256':template_sha,
                'exact_runs_directories':sorted(roots),'authorized_campaigns':[str(p) for p in campaigns],
                'working_bytes_at_proposal':self.working_bytes,'discovery_patterns':list(patterns)}

    def branch_history(self,kind,name): return [x for x in self.state['ledger'] if x['kind']==kind and x['branch']==name]

    def job(self,branch,sequence,tokens,*,kind,tier=None,extra_argv=()):
        name=f"{branch['prefix']}-{sequence:03d}"
        outdir=self.directory/name
        values={'job_id':name,'outdir':str(outdir),'sequence':str(sequence),'deadline_utc':self.plan['deadline_utc'],**tokens}
        command=[arg.format_map(values) for arg in branch['command_template']]+list(extra_argv)
        seconds=int(tokens['seconds'])+branch.get('grace_seconds',15)
        job={'id':name,'cpu':branch['cpu'],'memory_mb':branch['memory_mb'],'seconds':seconds,'enabled':True,'command':command}
        validate_job(job)
        if self.now()+seconds>self.deadline: raise ValueError('job would cross global cutoff')
        existing=next((x for x in self.queue['jobs'] if x['id']==name),None)
        if existing is not None and existing!=job: raise ValueError('queue job ID collision: '+name)
        if existing is None and outdir.exists(): raise ValueError('fresh output directory already exists: '+str(outdir))
        return {'kind':kind,'branch':branch['name'],'sequence':sequence,'tier':tier,'job':job,'outdir':str(outdir),
                'parents':{},'decision':'PROPOSED','job_sha256':job_digest(job),'utc':utc(self.now())}

    def coherent_pair(self,path,branch):
        controller,controller_sha=read(path);schedule_path=Path(path).with_suffix('.schedule.json');schedule,schedule_sha=read(schedule_path)
        context=branch['context_key']
        if controller.get('format')!=branch['checkpoint_format'] or schedule.get('format')!=branch['schedule_format']:
            raise ValueError('RL checkpoint/schedule fixed format mismatch')
        config=controller.get('config',{})
        if (type(config.get('n')) is not int or config['n']!=5 or type(config.get('target_rank')) is not int
            or config['target_rank']!=92 or config.get('native_only') is not True
            or config.get('control')!='policy' or config.get('train') is not True):
            raise ValueError('RL checkpoint is not approved n5 native policy training target92')
        if controller.get('state',{}).get('terminal') is True or not isinstance(controller.get('best'),list) or len(controller['best'])<=92:
            raise ValueError('RL terminal/record checkpoint requires owner exact record review')
        if schedule.get('checkpoint_sha256')!=controller_sha: raise ValueError('RL incoherent checkpoint/schedule hash')
        if not controller.get('restart_curriculum') or schedule.get('restart_context')!=controller['restart_curriculum']:
            raise ValueError('RL restart context differs')
        if not controller.get(context) or schedule.get(context)!=controller[context]: raise ValueError('RL phase context differs')
        clock=controller[context]['clock']
        if clock.get('phase_id')!=branch['phase_id'] or clock.get('recovery_fraction')!=.05: raise ValueError('RL phase clock changed')
        ready,ready_sha=read(branch['pool_ready']);manifest_sha=sha(Path(branch['pool_manifest']).read_bytes())
        if ready.get('manifest_sha256')!=manifest_sha or schedule.get('pool_context',{}).get('pool_sha256')!=manifest_sha:
            raise ValueError('RL pool READY/manifest/schedule differs')
        if controller[context].get('curriculum_sha256')!=manifest_sha: raise ValueError('RL curriculum identity differs')
        return {'checkpoint':str(path),'checkpoint_sha256':controller_sha,'schedule_sha256':schedule_sha,
                'pool_ready_sha256':ready_sha,'pool_manifest_sha256':manifest_sha,'phase_context_sha256':sha(json.dumps(controller[context],sort_keys=True).encode())}

    def rl(self,branch,gate):
        template=branch['command_template']
        if (branch.get('phase_seconds')!=900 or '--main-cpu-budget' not in template or
            template[template.index('--main-cpu-budget')+1]!='750'):
            raise ValueError('V2 learning phases require900wall and750mainCPU caps')
        clearance_ref=gate.get('rl_clearance')
        if not clearance_ref: return None,'WAITING_ROOT_PILOT_CLEARANCE'
        self.bound(clearance_ref['path'],clearance_ref['sha256']);clearance,_=read(clearance_ref['path'])
        if (clearance.get('format')!='rl-phase-clearance-v1' or clearance.get('approved') is not True
            or clearance.get('pool_ready') is not True or clearance.get('pilot_completed') is not True
            or clearance.get('control_pair_validated') is not True): raise ValueError('RL pilot/control clearance incomplete')
        if clearance.get('completed_jobs')!=branch['prerequisite_jobs']: raise ValueError('RL clearance prerequisite list differs')
        for name in branch['prerequisite_jobs']:
            result=self.result(name)
            if result is None: return None,'WAITING_PILOT_CONTROL_RESULTS'
            if clearance.get('result_sha256',{}).get(name)!=result[1]: raise ValueError('RL cleared result hash differs: '+name)
        for artifact in clearance.get('validated_artifacts',[]): self.bound(artifact['path'],artifact['sha256'])
        if not clearance.get('validated_artifacts'): raise ValueError('RL clearance needs hashed validation report')
        history=self.branch_history('rl',branch['name'])
        previous=history[-1] if history else None
        predecessor=previous['job']['id'] if previous else branch['initial_predecessor_job']
        result=self.result(predecessor)
        if result is None: return None,'WAITING_PREDECESSOR'
        checkpoint=Path(previous['outdir'])/'checkpoint.json' if previous else Path(branch['initial_checkpoint'])
        if not self.free_cpu(branch['cpu'],branch['memory_mb']): return None,'WAITING_CPU'
        parents=self.coherent_pair(checkpoint,branch);parents.update(predecessor=predecessor,result_sha256=result[1],clearance_sha256=clearance_ref['sha256'])
        if parents['pool_ready_sha256']!=clearance.get('pool_ready_sha256'): raise ValueError('RL cleared pool READY differs')
        cleared=self.coherent_pair(Path(branch['clearance_checkpoint']),branch)
        if (cleared['checkpoint_sha256']!=clearance.get('pilot_checkpoint_sha256') or
            cleared['schedule_sha256']!=clearance.get('pilot_schedule_sha256')):
            raise ValueError('RL cleared first-pilot checkpoint/schedule differs')
        if parents['phase_context_sha256']!=cleared['phase_context_sha256']:
            raise ValueError('RL initial/prearm phase context differs from cleared first pilot')
        parents['cleared_pilot_checkpoint_sha256']=cleared['checkpoint_sha256']
        if previous:
            if parents['phase_context_sha256']!=previous['parents']['phase_context_sha256']:
                raise ValueError('RL phase/novelty clock context reset across hours')
        elif branch.get('initial_resume_checkpoint'):
            command=result[0].get('command',[])
            expected=str(Path(branch['initial_resume_checkpoint']).resolve())
            if '--resume' not in command or str(Path(command[command.index('--resume')+1]).resolve())!=expected:
                raise ValueError('RL prearm result does not bind approved first-pilot resume ancestry')
        cutoff=min(self.deadline,stamp(branch['cutoff_utc']))
        seconds=min(branch['phase_seconds'],int(cutoff-self.now())-branch.get('grace_seconds',15))
        if seconds<branch.get('minimum_phase_seconds',60): return None,'CUTOFF_COMPLETE'
        action=self.job(branch,len(history)+1,{'previous_checkpoint':str(checkpoint),'seconds':str(seconds)},kind='rl')
        action['parents']=parents
        return action,'PROPOSED'

    def stream(self,branch):
        proof,_=read(branch['partition_ready'])
        if proof.get('families_pairwise_disjoint') is not True or proof.get('exclusions_exactly_partition_completed_catalog') is not True:
            raise ValueError('stream tier partition/exclusion proof not READY')
        cases={case['label']:case for case in proof['cases']}
        for tier in branch['tiers']:
            bindings=tier['instance_hashes'];case=cases[tier['label']]
            if (set(bindings)!={'input_sha256','catalog_sha256','binary_sha256'} or bindings['catalog_sha256']!=case['sha256']
                or bindings['input_sha256']!=proof['input_sha256'] or bindings['binary_sha256']!=proof['binary_sha256']
                or tier['total_rows']!=case['selected']): raise ValueError('stream fixed tier differs from partition READY')
        history=self.branch_history('stream',branch['name']);previous=history[-1] if history else None
        tier_index=previous['tier'] if previous else branch['initial_tier']
        predecessor=previous['job']['id'] if previous else branch['initial_predecessor_job']
        result=self.result(predecessor)
        if result is None: return None,'WAITING_PREDECESSOR'
        outdir=Path(previous['outdir']) if previous else Path(branch['initial_outdir'])
        summary,summary_sha=read(outdir/'summary.json')
        if summary.get('status')=='ERROR': raise ValueError('stream ERROR; owner review required')
        if summary.get('status') not in ('UNKNOWN','NO_TARGET'):
            raise ValueError('stream status preserved without automatic continuation: '+str(summary.get('status')))
        manifest,manifest_sha=read(outdir/'manifest.json');stats,stats_sha=read(outdir/'native_final_stats.json')
        tier=branch['tiers'][tier_index]
        for key,value in tier['instance_hashes'].items():
            if manifest.get(key)!=value: raise ValueError('stream instance hash differs: '+key)
        for key in ('input_sha256','catalog_sha256'):
            if stats.get(key)!=manifest.get(key): raise ValueError('stream native hash differs: '+key)
        cover=summary['coverage'];prefix=cover['prefix_completed'];total=cover['triples_total'];start=manifest['start_row']
        if any(type(x) is not int or x<0 for x in (prefix,total,start)) or not start<=prefix<=total or total!=tier['total_rows']:
            raise ValueError('stream invalid cursor bounds')
        if (cover.get('contiguous_from_initial') is not True or cover.get('next_row')!=prefix or stats.get('next_row')!=prefix
            or stats.get('prefix_rows_skipped')!=start or stats.get('triples_considered')!=prefix-start
            or cover.get('triples_completed_this_run')!=prefix-start or manifest.get('triples_total')!=total
            or stats.get('triples_total')!=total): raise ValueError('stream contiguous coverage differs')
        if previous and start!=previous['expected_start_row']: raise ValueError('stream reran covered rows or skipped a gap')
        resume=str(outdir)
        if summary['status']=='UNKNOWN':
            if prefix<=start or prefix>=total or cover.get('supplied_catalog_completed') is not False:
                raise ValueError('stream UNKNOWN made no progress or has inconsistent completion')
        else:
            if cover.get('supplied_catalog_completed') is not True or prefix!=total: raise ValueError('NO_TARGET lacks completed finite catalog')
            tier_index+=1;resume=''
            if tier_index>=len(branch['tiers']): return None,'SUPPLIED_TIERS_NO_TARGET_COMPLETE'
            tier=branch['tiers'][tier_index];prefix=0
        template=tier['command_template']
        target_catalog=template[template.index('--triple-catalog')+1]
        own_ids={entry['job']['id'] for entry in history}|{branch['initial_predecessor_job']}
        for job in self.queue['jobs']:
            argv=job['command']
            if job['id'] in own_ids or '--triple-catalog' not in argv: continue
            if argv[argv.index('--triple-catalog')+1]!=target_catalog: continue
            if not self.completed(job['id']): return None,'WAITING_EXTERNAL_STREAM_CONTINUATION'
            if '--outdir' not in argv: raise ValueError('external same-family job has no reviewable outdir')
            external=Path(argv[argv.index('--outdir')+1])/'summary.json'
            if external.exists():
                other,_=read(external);covered=other.get('coverage',{}).get('prefix_completed',0)
                allowed_prefix=start if resume else 0
                if type(covered) is not int or covered>allowed_prefix:
                    raise ValueError('external same-family coverage requires root rebase; never rerun covered rows')
        if not self.free_cpu(branch['cpu'],branch['memory_mb']): return None,'WAITING_CPU'
        seconds=min(branch['phase_seconds'],int(self.deadline-self.now())-branch.get('grace_seconds',15))
        if seconds<branch.get('minimum_phase_seconds',30): return None,'CUTOFF_COMPLETE'
        command_branch={**branch,'command_template':tier['command_template']}
        if '--resume-from' in tier['command_template']: raise ValueError('stream template must omit resume flag')
        action=self.job(command_branch,len(history)+1,{'seconds':str(seconds),'previous_outdir':resume},kind='stream',tier=tier_index,
                        extra_argv=['--resume-from',resume] if resume else [])
        action['expected_start_row']=prefix
        action['parents']={'predecessor':predecessor,'result_sha256':result[1],'summary_sha256':summary_sha,
                           'manifest_sha256':manifest_sha,'stats_sha256':stats_sha,'reported_status':summary['status'],
                           'completed_prefix':cover['prefix_completed'],'tier_label':tier['label']}
        return action,'PROPOSED'

    def maintenance(self,branch):
        if branch.get('cpu')!=3 or branch.get('memory_mb',513)>512:
            raise ValueError('maintenance is CPU3 with at most512MiB')
        if any(lock_held(self.directory/name) for name in ('recovery-maintenance-v3.lock','native-maintenance-v4.lock')):
            return None,'WAITING_V3_V4_ARCHIVE_LOCK'
        history=self.branch_history('maintenance',branch['name'])
        if history:
            previous=history[-1];result=self.result(previous['job']['id'])
            if result is None: return None,'WAITING_MAINTENANCE'
            log=self.directory/(previous['job']['id']+'-job.log')
            lines=log.read_text().splitlines()
            if not lines: raise ValueError('maintenance outcome log missing')
            outcome=json.loads(lines[-1],object_pairs_hook=unique)
            previous['outcome']={'job_result_sha256':result[1],'log_sha256':sha(log.read_bytes()),'maintenance':outcome}
            if outcome.get('status') not in ('ok','no_sources'): raise ValueError('maintenance outcome requires owner review: '+str(outcome.get('status')))
            # Productive urgent phases may continue immediately. Empty/recent
            # roots retain the normal backoff so storage holds cannot generate
            # thousands of zero-work tickets while artifacts reach minimum age.
            urgent_productive=self.working_bytes>=4.5*GIB and outcome.get('removed_runs',0)>0
            if not urgent_productive and self.now()-stamp(previous['utc'])<branch['minimum_interval_seconds']:
                return None,'WAITING_MAINTENANCE_INTERVAL'
        if not self.free_cpu(3,branch['memory_mb']): return None,'WAITING_PRIORITY_CPU3'
        seconds=min(branch['phase_seconds'],int(self.deadline-self.now())-branch.get('grace_seconds',15))
        if seconds<branch.get('minimum_phase_seconds',60): return None,'CUTOFF_COMPLETE'
        snapshot=self.archive_config(branch,len(history)+1)
        if snapshot is None: return None,'NO_ELIGIBLE_NATIVE_ROOTS'
        action=self.job(branch,len(history)+1,{'seconds':str(seconds),'maintenance_config':snapshot['path']},kind='maintenance')
        action['config_snapshot']=snapshot
        action['storage_priority']=snapshot['mode']=='current-only'
        return action,'PROPOSED_CURRENT_ONLY_PRIORITY' if action['storage_priority'] else 'PROPOSED'

    def preview(self,assume_kinds=None):
        self.queue,self.queue_sha=queue_value(self.directory/'queue.json')
        self.queue_state,_=read(self.directory/'queue_state.json')
        report={'format':'mmsearch-phase-preview-v3','utc':utc(self.now()),'plan_sha256':self.plan_sha,
                'coordinator_sha256':self.code_sha,'queue_sha256':self.queue_sha,'actions':[],'branches':[],'zero_mutations':True}
        if self.virtual_migration is not None: report['virtual_migration_from_v2']=self.virtual_migration
        barrier=self.barriers()
        if barrier: report.update(status='BLOCKED',reason=barrier);return report
        if assume_kinds is not None:
            if any(kind not in ('rl','stream','maintenance') for kind in assume_kinds): raise ValueError('invalid hypothetical kinds')
            for path,digest in self.plan.get('bindings',{}).items(): self.bound(path,digest)
            gate={**(self.virtual_gate or {}),'armed_kinds':list(assume_kinds)};report['hypothetical_unarmed_preview']=True
        else: gate=self.arm()
        if gate is None: report.update(status='UNARMED',reason='root gate absent');return report
        report['root_gate_sha256']=None if assume_kinds is not None else self.gate_sha
        report['status']='READY'
        report['working_bytes']=self.working_bytes
        pending=self.state.get('pending_action')
        if pending:
            validate_job(pending['job'])
            if pending['job_sha256']!=job_digest(pending['job']): raise ValueError('durable append intent changed')
            existing=next((job for job in self.queue['jobs'] if job['id']==pending['job']['id']),None)
            urgent_maintenance=(self.working_bytes>=4.5*GIB and self.free_cpu(3,512) and any(
                branch['kind']=='maintenance' and branch.get('enabled') is True and 'maintenance' in gate['armed_kinds']
                and branch['name'] not in self.state.get('paused_branches',{}) for branch in self.plan.get('branches',[])))
            deferred=(existing is None and pending['kind'] in ('rl','stream') and
                      (self.storage_hold(pending['kind']) or pending['kind'] not in gate['armed_kinds'] or urgent_maintenance))
            superseded=(existing is None and pending['kind']=='maintenance' and self.working_bytes>=4.5*GIB and
                        pending.get('config_snapshot',{}).get('mode')!='current-only')
            if deferred:
                report['defer_pending_action']={'branch':pending['branch'],'job_id':pending['job']['id'],
                    'reason':self.storage_hold(pending['kind']) or 'storage maintenance priority or branch disarmed'}
            elif superseded:
                report['supersede_pending_action']={'branch':pending['branch'],'job_id':pending['job']['id'],
                    'reason':'unlaunched fair archive intent replaced by required CURRENT-only configuration'}
            else:
                if pending['kind'] not in gate['armed_kinds'] and existing is None:
                    report.update(status='UNARMED',reason='pending branch disarmed');return report
                if pending['kind']=='rl' and existing is None and pending['parents'].get('clearance_sha256')!=gate.get('rl_clearance',{}).get('sha256'):
                    report.update(status='UNARMED',reason='pending learning clearance changed; owner review required');return report
                if existing is None:
                    cutoff=self.deadline
                    if pending['kind']=='rl':
                        branch=next(b for b in self.plan['branches'] if b['name']==pending['branch'])
                        cutoff=min(cutoff,stamp(branch['cutoff_utc']))
                    if self.now()+pending['job']['seconds']>cutoff:
                        report.update(status='BLOCKED',reason='stale append intent would cross approved cutoff');return report
                    if not self.free_cpu(pending['job']['cpu'],pending['job']['memory_mb']):
                        report['branches']=[{'name':pending['branch'],'status':'WAITING_DURABLE_INTENT_CPU'}];return report
                report['actions']=[pending];report['branches']=[{'name':pending['branch'],'status':'RECOVERING_DURABLE_APPEND_INTENT'}]
                return report
        proposals=[]
        for branch in self.plan.get('branches',[]):
            kind=branch['kind'];name=branch['name']
            if name in self.state.get('paused_branches',{}):
                report['branches'].append({'name':name,'status':'PAUSED','reason':self.state['paused_branches'][name]});continue
            if branch.get('enabled') is not True or kind not in gate['armed_kinds']:
                report['branches'].append({'name':name,'status':'UNARMED'});continue
            hold=self.storage_hold(kind)
            if hold:
                report['branches'].append({'name':name,'status':hold});continue
            try:
                if kind=='rl': action,status=self.rl(branch,gate)
                elif kind=='stream': action,status=self.stream(branch)
                elif kind=='maintenance': action,status=self.maintenance(branch)
                else: raise ValueError('unknown branch kind')
                report['branches'].append({'name':name,'status':status})
                if action:
                    held=self.state.get('held_actions',{}).get(name)
                    if held:
                        if held['job']!=action['job'] or held.get('parents')!=action.get('parents'):
                            raise ValueError('held unlaunched intent differs from freshly validated continuation')
                        action=held
                        action['recovered_held_intent_at']=utc(self.now())
                    proposals.append(action)
            except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
                report['branches'].append({'name':name,'status':'PAUSED','reason':str(exc)})
        # At most one append per poll. Approved search/learning priorities win
        # before maintenance, which cannot overlap any queued CPU3 work.
        proposals.sort(key=lambda a:(-1 if a.get('storage_priority') else {'rl':0,'stream':1,'maintenance':2}[a['kind']],a['branch']))
        if proposals:
            proposals[0]['root_gate_sha256']=report['root_gate_sha256']
            report['actions']=[proposals[0]]
        return report

    def append(self,action):
        # This method is only reached from explicit run, never preview.
        lock=(self.directory/'queue_append.lock').open('a')
        try:
            fcntl.flock(lock,fcntl.LOCK_EX)
            queue,before=queue_value(self.directory/'queue.json')
            existing=next((x for x in queue['jobs'] if x['id']==action['job']['id']),None)
            if existing is not None:
                if existing!=action['job']: raise ValueError('append ID collision')
                return before,before,'already_present'
            # Re-read all barriers/policy and scheduling decisions under the
            # shared append lock, so stale previews never authorize an append.
            refreshed=self.preview()
            if not refreshed['actions'] or refreshed['actions'][0]['job']!=action['job']:
                return before,before,'admission_changed'
            if len(queue['jobs'])>=self.plan.get('max_total_jobs',2048): raise ValueError('approved job-count bound reached')
            queue['jobs'].append(action['job']);atomic(self.directory/'queue.json',queue)
            _,after=queue_value(self.directory/'queue.json')
            return before,after,'appended'
        finally: lock.close()

    def tick(self):
        if self.virtual_migration is not None: raise ValueError('virtual migration previews cannot write or run')
        report=self.preview();report.update(mode='run',zero_mutations=False);self.root.mkdir(exist_ok=True)
        if report.get('defer_pending_action'):
            pending=self.state.pop('pending_action')
            held=self.state.setdefault('held_actions',{})
            if pending['branch'] in held and held[pending['branch']]!=pending:
                raise ValueError('different held intent already exists for branch')
            held[pending['branch']]=pending
            self.state.setdefault('intent_transitions',[]).append({'utc':utc(self.now()),'decision':'DEFERRED_UNLAUNCHED_SEARCH',
                'reason':report['defer_pending_action']['reason'],'job_id':pending['job']['id'],'job_sha256':pending['job_sha256']})
        if report.get('supersede_pending_action'):
            pending=self.state.pop('pending_action')
            self.state.setdefault('intent_transitions',[]).append({'utc':utc(self.now()),'decision':'SUPERSEDED_UNLAUNCHED_FAIR_ARCHIVE',
                'reason':report['supersede_pending_action']['reason'],'previous_intent':pending})
        if report['actions']:
            action=report['actions'][0]
            snapshot=action.get('config_snapshot')
            if snapshot:
                path=Path(snapshot['path'])
                if not path.is_relative_to(self.root/'configs'): raise ValueError('generated maintenance config escapes snapshot directory')
                raw=(json.dumps(snapshot['value'],sort_keys=True,indent=2)+'\n').encode()
                if sha(raw)!=snapshot['sha256']: raise ValueError('maintenance configuration snapshot changed')
                path.parent.mkdir(exist_ok=True)
                if path.exists(): self.bound(path,snapshot['sha256'])
                else: atomic(path,snapshot['value']);path.chmod(0o444)
            self.state['pending_action']=action
            atomic(self.root/'state.json',self.state)  # Intent before queue mutation.
            before,after,append_status=self.append(action)
            if append_status=='admission_changed':
                report.update(status='WAITING_READMISSION',reason='resource/gate policy changed before atomic queue append',actions=[])
            else:
                action.update(queue_before_sha256=before,queue_after_sha256=after,append_status=append_status)
                self.state['ledger'].append(action)
                self.state.pop('pending_action',None)
                self.state.setdefault('held_actions',{}).pop(action['branch'],None)
                snapshots=self.root/'phases';snapshots.mkdir(exist_ok=True)
                atomic(snapshots/(action['job']['id']+'.json'),action)
        for branch in report['branches']:
            if branch['status']=='PAUSED': self.state.setdefault('paused_branches',{})[branch['name']]=branch['reason']
        for entry in self.state['ledger']:
            result_path=self.directory/(entry['job']['id']+'-job.result.json')
            if not result_path.exists(): continue
            info=result_path.stat();signature=[info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_ino]
            if entry.get('execution_result_signature')==signature: continue
            value,digest=read(result_path)
            execution='LIMITED_OR_INTERRUPTED' if value.get('timed_out') or value.get('interrupted') else 'COMPLETED' if value.get('exit_code')==0 else 'ERROR'
            outcome={'execution':execution,'result_sha256':digest,
                     'exit_code':value.get('exit_code'),'timed_out':value.get('timed_out'),'interrupted':value.get('interrupted')}
            summary_path=Path(entry['outdir'])/'summary.json'
            if summary_path.exists():
                summary,summary_sha=read(summary_path)
                outcome.update(reported_status=summary.get('status'),summary_sha256=summary_sha,coverage=summary.get('coverage'))
            if entry.get('execution_outcome')!=outcome:
                entry['execution_outcome']=outcome
                entry['execution_result_signature']=signature
                snapshots=self.root/'phases';snapshots.mkdir(exist_ok=True)
                atomic(snapshots/(entry['job']['id']+'.outcome.json'),outcome)
        # Record terminal outcomes without relabeling UNKNOWN/LOCAL_UNSAT as
        # global impossibility. The raw summary hash remains in the next action.
        self.state.update(updated_utc=utc(self.now()),last_status=report['status'],last_branches=report['branches'])
        atomic(self.root/'state.json',self.state);atomic(self.root/'status.json',report)
        text='Root-approved queue-only coordinator. No publication or novelty assertion.\n\n'
        text+=f"Plan SHA256: {self.plan_sha}\nStatus: {report['status']} at {report['utc']}\n"
        text+=f"Current working bytes: {report.get('working_bytes','unavailable')}; held unlaunched intents: {len(self.state.get('held_actions',{}))}\n"
        text+='\n'.join(f"{b['name']}: {b['status']} {b.get('reason','')}" for b in report['branches'])+'\n'
        text+=f"\nPreserved phase ledger entries: {len(self.state['ledger'])}. Detailed snapshots: phases/.\n"
        temporary=self.root/'HANDOFF.md.tmp';temporary.write_text(text);temporary.replace(self.root/'HANDOFF.md')
        return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('preview','run'))
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--gate',type=Path,required=True);p.add_argument('--once',action='store_true')
    p.add_argument('--assume-kinds',nargs='+',choices=('rl','stream','maintenance'),help='hypothetical preview only; never authorizes run')
    p.add_argument('--preview-state',type=Path,help='preview-only preserved V2 state; performs a virtual migration without writes')
    p.add_argument('--preview-gate',type=Path,help='preview-only V2 gate for existing root clearance bindings')
    args=p.parse_args(argv)
    if args.mode=='run' and (args.assume_kinds is not None or args.preview_state is not None or args.preview_gate is not None):
        p.error('hypothetical/virtual preview flags cannot authorize run')
    coordinator=Coordinator(args.plan,args.gate,preview_state=args.preview_state,preview_gate=args.preview_gate)
    if args.mode=='preview': print(json.dumps(coordinator.preview(args.assume_kinds),sort_keys=True,indent=2));return
    if args.assume_kinds is not None: p.error('--assume-kinds is preview-only and cannot authorize queue writes')
    os.sched_setaffinity(0,{2});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
    # V2 already uses this singleton lock. Holding it throughout V3's life
    # prevents either epoch from running concurrently without editing V2.
    legacy_lock=(coordinator.directory/'phase-coordinator42-v2/supervisor.lock').open('r')
    try: fcntl.flock(legacy_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BaseException:
        legacy_lock.close();raise
    coordinator.root.mkdir(exist_ok=True)
    lock=(coordinator.root/'supervisor.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    stopped=False
    def stop(sig,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    while not stopped:
        try: report=coordinator.tick()
        except (OSError,ValueError,KeyError,TypeError) as exc:
            atomic(coordinator.root/'status.json',{'status':'PAUSED','reason':str(exc),'utc':utc(time.time())});break
        if args.once or report.get('reason') in ('global deadline','campaign guard stop marker','existing WINNER/approved stop file'): break
        time.sleep(10)


if __name__=='__main__':main()
