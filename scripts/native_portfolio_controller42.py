"""Root-armed queue-only native portfolio; no subprocess launch or signals.

Only reviewed H6/H12 profiles, known exact93 starts, and bounded structural
coverage scheduling. Exact<=92 verification is decisive; histograms are not
mathematical novelty. Existing queue/guard remain sole launch/stop owners.
"""
from __future__ import annotations
import argparse
from collections import Counter
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import shutil
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from scripts.phase_coordinator42_v2 import (atomic,identity,job_digest,queue_value,read,stamp,utc,validate_job)
from scripts.select_diverse93_seeds import rank_histogram
from mmsearch.native_bridge import canonical_terms,term_set_sha256
from mmsearch.verify import verify_candidate

GIB=1024**3
PROFILES={'h6':{'headroom':6,'plus_every':50000,'restart_every':100000000},
          'h12':{'headroom':12,'plus_every':20000,'restart_every':50000000}}


def digest(raw):return hashlib.sha256(raw).hexdigest()

def immutable(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('xb') as stream:stream.write(raw)
    except FileExistsError:
        if path.read_bytes()!=raw:raise ValueError('immutable source/config collision: '+str(path))
    path.chmod(0o444)


def checked_certificate(path):
    raw=Path(path).read_bytes();value=json.loads(raw);terms=canonical_terms(value)
    if value['dimension']!=5:raise ValueError('portfolio requires n5 F2')
    report=verify_candidate(value,random_trials=0)
    if not report['valid'] or report['exact_entries_checked']!=15625:raise ValueError('invalid full tensor certificate')
    if len(terms)>93:raise ValueError('only verified rank93 inputs/outputs are eligible')
    return {'path':str(Path(path).resolve()),'sha256':digest(raw),'term_hash':term_set_sha256(terms),
            'rank':len(terms),'histogram':list(rank_histogram(terms)),
            'histogram_sha256':digest(json.dumps(rank_histogram(terms)).encode()),
            'verification':report,'record':len(terms)<=92}


class Portfolio:
    def __init__(self,plan_path,gate_path,*,now=time.time,pid_identity=identity,disk_free=None):
        self.plan_path=Path(plan_path).resolve();self.gate_path=Path(gate_path).resolve()
        self.plan,self.plan_sha=read(self.plan_path);self.code_sha=digest(Path(__file__).read_bytes())
        self.now,self.pid_identity=now,pid_identity;self.disk_free=disk_free or (lambda path:shutil.disk_usage(path).free)
        self.c=Path(self.plan['campaign']).resolve();self.root=self.c/'native-portfolio42'
        if (self.plan.get('format')!='native-portfolio-plan-v1' or self.plan.get('profiles')!=PROFILES
            or self.plan.get('cpu')!=2 or self.plan.get('memory_mb')!=768 or self.plan.get('phase_seconds')!=1800
            or self.plan.get('pool_cap')!=32 or self.plan.get('seed_block')!=1000000):raise ValueError('unreviewed native plan policy')
        self.feature_sha=digest((Path(rank_histogram.__code__.co_filename).read_bytes()))
        self.hash_cache={};self.dirty=False;self.state={'format':'native-portfolio-state-v1','plan_sha256':self.plan_sha,
            'feature_sha256':self.feature_sha,'controller_sha256':self.code_sha,'ledger':[],'outcomes':{},'pool':[],'seen_terms':[],
            'seen_histograms':[],'certificates':{},'pending':None,'error':None}
        if (self.root/'state.json').exists():
            self.state,_=read(self.root/'state.json')
            if (self.state.get('format')!='native-portfolio-state-v1' or self.state.get('plan_sha256')!=self.plan_sha
                or self.state.get('feature_sha256')!=self.feature_sha or self.state.get('controller_sha256')!=self.code_sha):raise ValueError('state/feature basis differs; no reset fallback')

    def bound(self,path,expected):
        path=Path(path);info=path.stat();sig=(info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_ino)
        cached=self.hash_cache.get(str(path))
        if cached is None or cached[0]!=sig:self.hash_cache[str(path)]=(sig,digest(path.read_bytes()))
        if self.hash_cache[str(path)][1]!=expected:raise ValueError('frozen source hash mismatch: '+str(path))

    def arm(self):
        if not self.gate_path.exists():return False
        gate,_=read(self.gate_path)
        if gate.get('armed') is False:return False
        if (gate.get('format')!='native-portfolio-arm-v1' or gate.get('owner')!='root' or gate.get('armed') is not True
            or gate.get('plan_sha256')!=self.plan_sha or gate.get('controller_sha256')!=self.code_sha):raise ValueError('root native gate differs')
        for path,expected in self.plan['bindings'].items():self.bound(path,expected)
        return True

    def resources(self):
        self.queue,_=queue_value(self.c/'queue.json');self.queue_state,_=read(self.c/'queue_state.json')
        campaign,_=read(self.c/'campaign.json');self.deadline=stamp(campaign['deadline_utc'])
        if (campaign.get('dimension')!=5 or campaign.get('field')!=2 or campaign.get('max_cpu_cores')!=4
            or campaign.get('max_ram_gib')!=8 or campaign['deadline_utc']!=self.plan['deadline_utc']):raise ValueError('campaign identity differs')
        if self.now()>=self.deadline:return 'DEADLINE'
        if (self.c/'guard_stopped.json').exists() or self.queue_state.get('stop_reason'):return 'CAMPAIGN_STOP'
        if any(path.exists() for path in [self.c/'WINNER.json',*self.c.glob('*/WINNER.json')]):return 'WINNER'
        guard,_=read(self.c/'operations-v3/state.json')
        pid=guard.get('pid');tick=guard.get('process_identity',{}).get('start_ticks')
        if type(pid) is not int or pid<1 or type(tick) is not int or self.pid_identity(pid)!=tick:return 'GUARD_IDENTITY'
        if self.now()-stamp(guard['updated_utc'])>60 or self.now()<stamp(guard['updated_utc'])-5:return 'GUARD_CLOCK'
        if guard.get('stop_reason'):return 'GUARD_STOP'
        if guard.get('rss_bytes',8*GIB)>7*GIB:return 'RAM_HOLD'
        if guard.get('filesystem_free_bytes',0)<8*GIB or self.disk_free(self.c)<8*GIB:return 'GLOBAL_DISK_HOLD'
        if guard.get('campaign_allocated_bytes',8*GIB)>=5*GIB:return 'WORKING_DATA_HOLD_5GIB'
        return None

    def completed(self,name):return (self.c/(name+'-job.result.json')).exists()

    def cpu_free(self):
        reserved={job['id']:job for job in self.queue['jobs'] if job['enabled'] and not self.completed(job['id'])}
        for path in self.c.glob('*-job.running.json'):
            value,_=read(path);pid=value.get('pid')
            if type(pid) is int and pid>0 and self.pid_identity(pid) is not None:
                reserved[path.name.removesuffix('-job.running.json')]=value
        if any(job.get('cpu')==2 for job in reserved.values()):return False
        return sum(job.get('memory_mb',6144) for job in reserved.values())+768<=6144

    def certificate(self,path):
        path=Path(path);raw=path.read_bytes();key=digest(raw)+':'+self.feature_sha
        if key not in self.state['certificates']:
            self.state['certificates'][key]=checked_certificate(path);self.dirty=True
        value=dict(self.state['certificates'][key],path=str(path.resolve()))
        if value['sha256']!=digest(raw):raise ValueError('certificate cache invalidation failed')
        return value

    def initialize_pool(self):
        if self.state['pool']:return
        pool=[]
        for source in self.plan['initial_pool']:
            self.bound(source['path'],source['sha256']);record=self.certificate(source['path'])
            if record['record']:raise ValueError('record requires root freeze')
            record.update(initial=True,uses=0,origin='root-frozen-initial')
            if record['term_hash'] not in {old['term_hash'] for old in pool}:pool.append(record)
        if not 1<=len(pool)<=32:raise ValueError('invalid bounded initial pool')
        self.state['pool']=pool;self.state['seen_terms']=sorted({x['term_hash'] for x in pool})
        self.state['seen_histograms']=sorted({x['histogram_sha256'] for x in pool});self.dirty=True

    def consume(self,name,profile,expected_command):
        result_path=self.c/(name+'-job.result.json')
        if not result_path.exists():
            status=self.queue_state.get('jobs',{}).get(name,{}).get('status')
            if status in ('failed_to_launch','held_ambiguous','completed'):raise ValueError('predecessor result unavailable/ambiguous')
            return None
        result,result_sha=read(result_path)
        if (result.get('exit_code')!=0 or result.get('timed_out') is not False or result.get('interrupted') is not False
            or result.get('command')!=expected_command):raise ValueError('predecessor ERROR or command mismatch')
        folder=self.c/name;summary,summary_sha=read(folder/'summary.json');manifest,manifest_sha=read(folder/'manifest.json')
        files=sorted((folder/'verified').glob('*.json'))
        if len(files)>32:raise ValueError('native rank93 archive cap exceeded')
        table=[]
        for path in files:
            info=path.stat();table.append((str(path),info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_ino))
        fingerprint=digest(json.dumps([result_sha,summary_sha,manifest_sha,table,self.feature_sha],sort_keys=True).encode())
        previous=self.state['outcomes'].get(name)
        if previous:
            if previous['fingerprint']!=fingerprint:raise ValueError('completed outcome changed; cache invalidated for owner review')
            return previous
        if summary.get('winner') or (folder/'WINNER.json').exists():raise ValueError('WINNER requires root freeze')
        if not summary.get('phases') or not math.isfinite(result.get('cpu_seconds',0)) or result['cpu_seconds']<=0:raise ValueError('missing finite completed phase CPU/outcome')
        selected=PROFILES[profile]
        if (manifest.get('headroom')!=selected['headroom'] or manifest.get('target_rank')!=92 or manifest.get('cyclic') is not False
            or manifest.get('binary_sha256')!=self.plan['worker_sha256']):raise ValueError('native profile/worker identity differs')
        for phase in summary['phases']:
            command=phase['command'];stats=phase['final_stats']
            def arg(key):return command[command.index(key)+1]
            if (int(arg('--plus-every'))!=selected['plus_every'] or int(arg('--restart-every'))!=selected['restart_every']
                or phase['source_essential_rank']!=93 or phase['max_rank']!=93+selected['headroom']
                or stats.get('exact') is not True or stats.get('tensor_invariant_checked') is not True or stats.get('target_rank')!=92):raise ValueError('native move budget/source/stats differs')
        outputs=[];new_terms=0;new_hist=0
        seen_terms=set(self.state['seen_terms']);seen_hist=set(self.state['seen_histograms'])
        for path in files:
            value=self.certificate(path)
            if value['record']:raise ValueError('verified<=92 requires root freeze; no continuation')
            report_path=folder/'verification'/(path.stem+'.verification.json');report,report_sha=read(report_path)
            if not report.get('valid') or report.get('rank')!=93 or report.get('exact_entries_checked')!=15625:raise ValueError('saved native verification report differs')
            value.update(initial=False,uses=0,origin=name,existing_report=str(report_path),existing_report_sha256=report_sha)
            new_terms+=value['term_hash'] not in seen_terms;new_hist+=value['histogram_sha256'] not in seen_hist
            seen_terms.add(value['term_hash']);seen_hist.add(value['histogram_sha256']);outputs.append(value)
        candidates={value['term_hash']:value for value in self.state['pool']}
        for value in outputs:
            if value['term_hash'] not in candidates:candidates[value['term_hash']]=value
        # Keep root initial states; fill the remaining bounded slots using
        # structural buckets, then lower reuse. Every raw output path stays in
        # the outcome ledger even if it is not selected for the next input pool.
        chosen=[value for value in candidates.values() if value.get('initial')]
        remaining=[value for value in candidates.values() if not value.get('initial')]
        hist={value['histogram_sha256'] for value in chosen}
        while len(chosen)<32 and remaining:
            value=min(remaining,key=lambda x:(x['histogram_sha256'] in hist,x['uses'],x['term_hash']))
            chosen.append(value);hist.add(value['histogram_sha256']);remaining.remove(value)
        self.state['pool']=chosen;self.state['seen_terms']=sorted(seen_terms);self.state['seen_histograms']=sorted(seen_hist)
        outcome={'job':name,'profile':profile,'fingerprint':fingerprint,'result_sha256':result_sha,'summary_sha256':summary_sha,
            'manifest_sha256':manifest_sha,'feature_sha256':self.feature_sha,'cpu_seconds':result['cpu_seconds'],
            'new_exact_term_states':new_terms,'new_histogram_buckets':new_hist,'histograms_per_cpu_minute':new_hist/(result['cpu_seconds']/60),
            'best_verified_rank':93,'verified_output_links':outputs,'raw_summary':str(folder/'summary.json'),
            'raw_phase_links':[str(folder/f"phase-{phase['phase']:03d}") for phase in summary['phases']],
            'interpretation':'coverage proxy only; known93 remains a fitness tie; no algorithm inequivalence or record claimed'}
        self.state['outcomes'][name]=outcome;self.dirty=True;return outcome

    def choose_profile(self,sequence):
        slot=(sequence-1)%3
        if slot==1:return 'h6','guaranteed H6 coverage'
        if slot==2:return 'h12','guaranteed H12 coverage'
        rates={}
        for profile in PROFILES:
            values=[x for x in self.state['outcomes'].values() if x['profile']==profile][-3:]
            rates[profile]=sum(x['new_histogram_buckets'] for x in values)/max(1e-9,sum(x['cpu_seconds'] for x in values)/60)
        if max(rates.values())==0:
            counts=Counter(x['profile'] for x in self.state['outcomes'].values());return min(PROFILES,key=lambda p:(counts[p],p)),'zero proxy gain: rotate by allocation count'
        return min(PROFILES,key=lambda p:(-rates[p],p)),'one adaptive slot per3, verified histogram/CPU proxy'

    def proposal(self):
        if self.state['error']:return None,'ERROR: '+self.state['error']
        barrier=self.resources()
        if barrier:return None,barrier
        if not self.arm():return None,'UNARMED'
        self.initialize_pool()
        if self.state['pending']:return self.state['pending'],'DURABLE_INTENT'
        ledger=self.state['ledger']
        if ledger:
            parent=ledger[-1];name=parent['job']['id']
            if self.consume(name,parent['profile'],parent['job']['command']) is None:return None,'WAITING_PREDECESSOR'
        else:
            for parent in self.plan['predecessors']:
                name=parent['id']
                if self.consume(name,parent['profile'],parent['command']) is None:return None,'WAITING_PREDECESSOR'
        if not self.cpu_free():return None,'CPU2_OR_MEMORY_BUSY'
        seconds=min(1800,int(self.deadline-self.now())-15)
        if seconds<30:return None,'DEADLINE_REMAINDER_TOO_SHORT'
        sequence=len(ledger)+1;profile,reason=self.choose_profile(sequence)
        pool=self.state['pool'];selected=min(pool,key=lambda x:(x['uses'],x['histogram_sha256'],x['term_hash']))
        seed=self.plan['seed_base']+sequence*1000000
        if seed+1009*1000>=2**64:raise ValueError('native seed exceeds safe block')
        jobid=f'native42-portfolio-{sequence:03d}';outdir=self.c/jobid;pooldir=self.root/'pools'/f'{sequence:03d}'
        paths={x['term_hash']:str(pooldir/(x['sha256']+'.json')) for x in pool}
        command=['python3','-B',self.plan['wrapper'],'--binary',self.plan['worker'],'--input',paths[selected['term_hash']],
            '--pool',str(pooldir),'--output-dir',str(outdir),'--seconds',str(seconds),'--phase-seconds','600','--seed',str(seed),
            '--headroom',str(PROFILES[profile]['headroom']),'--plus-every',str(PROFILES[profile]['plus_every']),
            '--restart-every',str(PROFILES[profile]['restart_every']),'--archive-size','16']
        job={'id':jobid,'cpu':2,'memory_mb':768,'seconds':seconds+15,'command':command,'enabled':True};validate_job(job)
        fingerprint=digest(json.dumps([profile,seed,selected['sha256'],[(x['term_hash'],x['sha256']) for x in pool]],sort_keys=True).encode())
        if any(x['fingerprint']==fingerprint or x['seed']==seed for x in ledger):raise ValueError('duplicate native recipe/seed')
        return {'job':job,'job_sha256':job_digest(job),'sequence':sequence,'profile':profile,'seed':seed,'fingerprint':fingerprint,
            'selected_term_hash':selected['term_hash'],'pool_snapshot':json.loads(json.dumps(pool)),'pool_dir':str(pooldir),'reason':reason,
            'parent_job':name,'parent_outcome_fingerprint':self.state['outcomes'][name]['fingerprint'],'utc':utc(self.now())},'PROPOSED'

    def save(self):
        self.root.mkdir(parents=True,exist_ok=True);atomic(self.root/'state.json',self.state);self.dirty=False

    def append(self,action):
        validate_job(action['job'])
        if action['job_sha256']!=job_digest(action['job']):raise ValueError('durable job intent changed')
        for value in action['pool_snapshot']:
            self.bound(value['path'],value['sha256']);immutable(Path(action['pool_dir'])/(value['sha256']+'.json'),Path(value['path']).read_bytes())
        immutable(self.root/'pool-manifests'/(str(action['sequence']).zfill(3)+'.json'),(json.dumps(action['pool_snapshot'],sort_keys=True)+'\n').encode())
        lock=(self.c/'queue_append.lock').open('a')
        try:
            fcntl.flock(lock,fcntl.LOCK_EX);barrier=self.resources()
            if barrier or not self.arm():return 'HOLD: '+str(barrier or 'UNARMED')
            existing=next((job for job in self.queue['jobs'] if job['id']==action['job']['id']),None)
            if existing is not None and existing!=action['job']:raise ValueError('queue job ID collision')
            if existing is None:
                if not self.cpu_free():return 'HOLD: CPU2_OR_MEMORY_BUSY'
                if self.now()+action['job']['seconds']>self.deadline:return 'HOLD: intent crosses deadline'
                if (self.c/action['job']['id']).exists():raise ValueError('fresh native output directory exists')
                self.queue['jobs'].append(action['job']);atomic(self.c/'queue.json',self.queue)
            if not any(item['job']['id']==action['job']['id'] for item in self.state['ledger']):
                self.state['ledger'].append(action)
                for value in self.state['pool']:
                    if value['term_hash']==action['selected_term_hash']:value['uses']+=1
            self.state['pending']=None;self.save();return 'QUEUED'
        finally:fcntl.flock(lock,fcntl.LOCK_UN);lock.close()

    def tick(self,*,preview=False):
        try:
            action,status=self.proposal()
            if preview:return {'status':status,'action':action,'zero_mutations':True}
            if action is not None:
                if self.state['pending'] is None:self.state['pending']=action;self.save()
                status=self.append(action)
            if self.dirty or not (self.root/'state.json').exists():self.save()
            report={'utc':utc(self.now()),'status':status,'pending':self.state['pending'] is not None,'ledger_phases':len(self.state['ledger'])}
            atomic(self.root/'status.json',report);return report
        except (OSError,ValueError,KeyError,TypeError) as error:
            if preview:return {'status':'ERROR','reason':str(error),'zero_mutations':True}
            self.state['error']=str(error);self.save();atomic(self.root/'status.json',{'status':'ERROR','reason':str(error),'utc':utc(self.now())});return {'status':'ERROR','reason':str(error)}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('preview','run'));parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--gate',type=Path,required=True);args=parser.parse_args(argv)
    os.sched_setaffinity(0,{2});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
    controller=Portfolio(args.plan,args.gate)
    if args.mode=='preview':print(json.dumps(controller.tick(preview=True)));return 0
    controller.root.mkdir(parents=True,exist_ok=True)
    with (controller.root/'supervisor.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            report=controller.tick();print(json.dumps(report),flush=True)
            if report['status'] in ('DEADLINE','CAMPAIGN_STOP','WINNER') or report['status'].startswith('ERROR'):return 2 if report['status'].startswith('ERROR') else 0
            time.sleep(10)


if __name__=='__main__':raise SystemExit(main())
