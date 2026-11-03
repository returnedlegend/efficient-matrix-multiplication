"""Restartable campaign guard: exact record freeze, identity-safe stops, bounded IO.

This never launches work or edits queue.json. The owner launches it alongside
the existing queue. guard_stopped.json is the existing queue's dispatch barrier.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.rl_campaign_queue import atomic_json, load_json, parse_time, process_identity, utc, unique_object
from scripts.rl_campaign_queue_v2 import essential_rank
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import verify_bytes as independent_verify_bytes

GIB = 1024**3


def canonical_candidate(value):
    """Only explicit n=5,F2 certificates; no residual counts/checkpoint metadata."""
    essential_rank(value)  # Strict dimensions, bit shapes and bool rejection.
    terms = set()
    for term in value['terms']:
        masks = tuple(sum(x << i for i, x in enumerate(term[a])) for a in ('u','v','w')) if isinstance(term, dict) else tuple(term)
        if not all(masks):
            continue
        if masks in terms:
            terms.remove(masks)
        else:
            terms.add(masks)
    return {'dimension':5, 'field':2, 'terms':[
        {a:[(mask >> i)&1 for i in range(25)] for a,mask in zip(('u','v','w'),masks)}
        for masks in sorted(terms)]}


def eligible_report(candidate, report, target=92):
    return (candidate.get('dimension') == 5 and candidate.get('field') == 2
            and 0 < len(candidate['terms']) <= target and report.get('valid') is True
            and report.get('field_valid') is True and report.get('dimension') == 5
            and report.get('field') == 2 and report.get('rank') == len(candidate['terms'])
            and report.get('exact_entries_checked') == 15625)


def exclusive(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    path.chmod(0o444)


def freeze_record(root, candidate, source, source_raw, target=92):
    """Publish an immutable directory atomically only after full verification."""
    report = verify_candidate(candidate, random_trials=16)
    if not eligible_report(candidate, report, target):
        raise ValueError('record failed exhaustive n5 F2 verification')
    canonical_raw=(json.dumps(candidate,sort_keys=True,indent=2)+'\n').encode()
    independent=independent_verify_bytes(canonical_raw)
    if (independent.get('valid') is not True or independent.get('essential_rank')!=len(candidate['terms'])
        or independent.get('exact_entries_checked')!=15625):
        raise ValueError('record failed second independent exhaustive verifier')
    root = Path(root)
    stage = root.with_name(root.name+f'.pending-{os.getpid()}')
    stage.mkdir()
    values = {'WINNER.json':canonical_raw,
              'WINNER.verification.json':(json.dumps(report,sort_keys=True,indent=2)+'\n').encode(),
              'WINNER.independent.verification.json':(json.dumps(independent,sort_keys=True,indent=2)+'\n').encode(),
              'WINNER.source.raw':source_raw,
              'WINNER.verify.py':(REPO/'mmsearch/verify.py').read_bytes(),
              'WINNER.independent.verify.py':(REPO/'scripts/verify_record42_independent.py').read_bytes(),
              'provenance.json':(json.dumps({'source':str(source),'source_sha256':hashlib.sha256(source_raw).hexdigest(),
                  'guard_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'claim':'exact F2 product count only; novelty and Lean review pending'},sort_keys=True)+'\n').encode()}
    hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in values.items()}
    for name,raw in values.items():
        exclusive(stage/name,raw)
    exclusive(stage/'checksums.json',(json.dumps(hashes,sort_keys=True,indent=2)+'\n').encode())
    # Verify persisted bytes, not only the in-memory candidate.
    persisted,_=load_json(stage/'WINNER.json')
    if not eligible_report(persisted,verify_candidate(persisted,random_trials=16),target):
        raise ValueError('persisted winner failed verification')
    persisted_independent=independent_verify_bytes((stage/'WINNER.json').read_bytes())
    if (persisted_independent.get('valid') is not True or persisted_independent.get('exact_entries_checked')!=15625
        or persisted_independent.get('essential_rank')!=len(persisted['terms'])):
        raise ValueError('persisted winner failed second independent verifier')
    for name,digest in hashes.items():
        if hashlib.sha256((stage/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('persisted record checksum mismatch')
    stage.rename(root)
    fd=os.open(root.parent,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
    return hashes


def registered_groups(directory, identity=process_identity):
    """Adopt only current session leaders matching the launch timestamp."""
    groups=[]
    for path in Path(directory).glob('*.running.json'):
        try:
            value,_=load_json(path); pid=value['pid']; current=identity(pid)
            if not current or abs(current['started_unix']-parse_time(value['started_utc']))>10:
                continue
            if os.getpgid(pid)!=pid or os.getsid(pid)!=pid:
                continue
            group={'pid':pid,'start_ticks':current['start_ticks'],'registration':str(path),'members':[]}
            for member in Path('/proc').iterdir():
                if not member.name.isdigit(): continue
                child=int(member.name)
                try:
                    if os.getpgid(child)==pid and os.getsid(child)==pid:
                        child_identity=identity(child)
                        if child_identity: group['members'].append({'pid':child,'start_ticks':child_identity['start_ticks']})
                except ProcessLookupError: pass
            groups.append(group)
        except (OSError,ValueError,TypeError,KeyError):
            continue
    return groups


def signal_group(group, sig, identity=process_identity, killpg=os.killpg):
    current=identity(group['pid'])
    if current and current['start_ticks']!=group['start_ticks']:
        return False
    witnesses=[{'pid':group['pid'],'start_ticks':group['start_ticks']},*group.get('members',[])]
    for witness in witnesses:
        value=identity(witness['pid'])
        if not value or value['start_ticks']!=witness['start_ticks']: continue
        try:
            if os.getpgid(witness['pid'])==group['pid'] and os.getsid(witness['pid'])==group['pid']:
                killpg(group['pid'],sig); return True
        except ProcessLookupError: pass
    return False


def group_rss(groups):
    """Count each live process once, including detached children via ancestry."""
    table={}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit(): continue
        try:
            raw=(path/'stat').read_text(); fields=raw[raw.rfind(')')+2:].split()
            table[int(path.name)]=(int(fields[1]),int(fields[2]),max(0,int(fields[21]))*os.sysconf('SC_PAGE_SIZE'))
        except (OSError,ValueError,IndexError): pass
    wanted={g['pid'] for g in groups}; changed=True
    while changed:
        added={pid for pid,(parent,pgid,rss) in table.items() if parent in wanted or pgid in wanted}-wanted
        changed=bool(added); wanted.update(added)
    return sum(table.get(pid,(0,0,0))[2] for pid in wanted)


def walk_files(directory,prune=True):
    for root,dirs,files in os.walk(directory,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(root)/d).is_symlink() and
                 (not prune or (not d.startswith('.') and d not in ('operations-record','ops-ready-v1','code','__pycache__')))]
        for name in files:
            path=Path(root)/name
            if not path.is_symlink(): yield path


class Operations:
    def __init__(self,directory,*,now=time.time,identity=process_identity,killpg=os.killpg):
        self.directory=Path(directory).resolve(); self.now=now; self.identity=identity; self.killpg=killpg
        self.root=self.directory/'operations-v3'; self.root.mkdir(exist_ok=True)
        self.state_path=self.root/'state.json'
        self.state,_=load_json(self.state_path) if self.state_path.exists() else ({'format':'campaign-operations-v3','directory':str(self.directory),'pending_stops':[],'cache':{}},None)
        if self.state.get('format')!='campaign-operations-v3' or self.state.get('directory')!=str(self.directory):
            raise ValueError('operations restart state format/directory mismatch')
        self.cache=OrderedDict(self.state.get('cache',{})); self.iterator=iter(walk_files(self.directory))
        self.disk_iterator=iter(walk_files(self.directory,prune=False)); self.disk_bytes=0; self.disk_last=0
        self.last_config=-float('inf'); self.config=None; self.requested_stop=None
        self.last_heartbeat=-float('inf')

    def config_value(self):
        # Reading policy at most once per 10s avoids V1 policy-IO starvation.
        if self.config is None or self.now()-self.last_config>=10:
            value,_=load_json(self.directory/'campaign.json')
            if (type(value.get('dimension')) is not int or value['dimension']!=5 or type(value.get('field')) is not int
                or value['field']!=2 or value.get('max_cpu_cores')!=4 or value.get('max_ram_gib')!=8
                or type(value.get('target_rank')) is not int or value['target_rank']!=92):
                raise ValueError('requires declared n5 F2 target92 four-core 8GiB campaign')
            value['deadline_unix']=parse_time(value['deadline_utc'])
            self.config=value; self.last_config=self.now()
        return self.config

    def save(self):
        self.state.update(cache=dict(self.cache),updated_utc=utc(self.now()),pid=os.getpid(),process_identity=self.identity(os.getpid()))
        atomic_json(self.state_path,self.state)

    def stop(self,reason):
        if self.state.get('stop_reason'): return
        groups=registered_groups(self.directory,self.identity)
        self.state.update(stop_reason=reason,stopped_utc=utc(self.now()),pending_stops=groups,kill_after=self.now()+5)
        # Persist termination intent + dispatch barrier before sending a signal.
        self.save()
        atomic_json(self.directory/'guard_stopped.json',{'reason':reason,'utc':utc(self.now()),'operations_version':3,
                     'record_directory':str(self.directory/'operations-record') if (self.directory/'operations-record').exists() else None})
        for group in groups:
            signal_group(group,signal.SIGTERM,self.identity,self.killpg)

    def reap_stops(self):
        if self.now()<self.state.get('kill_after',float('inf')): return
        pending=[]
        for group in self.state.get('pending_stops',[]):
            if signal_group(group,signal.SIGKILL,self.identity,self.killpg): pending.append(group)
        self.state['pending_stops']=pending

    def scan(self,limit=128):
        before=time.process_time()
        # Promoted records never wait behind thousands of known-recovery files.
        priority=[self.directory/'WINNER.json',self.directory/'FOUND.json']
        for child in self.directory.iterdir():
            if child.is_dir() and not child.is_symlink() and child.name not in ('operations-v3','ops-ready-v1','operations-record'):
                priority.extend(child/name for name in ('WINNER.json','FOUND.json','best.json'))
                if (child/'records').is_dir(): priority.extend((child/'records').glob('*.json'))
        priority_iterator=iter(p for p in priority if p.is_file())
        for _ in range(limit):
            if time.process_time()-before>=.1: break
            try:
                path=next(priority_iterator,None)
                if path is None: path=next(self.iterator)
            except StopIteration:
                self.iterator=iter(walk_files(self.directory)); break
            if path.suffix!='.json' or path.is_relative_to(self.root): continue
            key=str(path.relative_to(self.directory)); signature=None
            try:
                info=path.stat(); signature=[info.st_size,info.st_mtime_ns,info.st_ino]
                if self.cache.get(key)==signature or info.st_size>2*1024**2: continue
                raw=path.read_bytes()
                after=path.stat()
                if (after.st_size,after.st_mtime_ns,after.st_ino)!=tuple(signature): continue
                value=json.loads(raw,object_pairs_hook=unique_object)
                candidate=canonical_candidate(value)
                rank=len(candidate['terms'])
                if 0<rank<=92:
                    report=verify_candidate(candidate,random_trials=8)
                    self.state['last_record_check']={'source':str(path),'rank':rank,'report':report}
                    if eligible_report(candidate,report):
                        freeze_record(self.directory/'operations-record',candidate,path,raw)
                        self.stop('independently verified n5 F2 product count <=92; immutable record preserved')
                        return
            except (OSError,ValueError,TypeError,AttributeError,RecursionError):
                pass
            if signature is None: continue
            self.cache[key]=signature; self.cache.move_to_end(key)
            while len(self.cache)>8192: self.cache.popitem(last=False)

    def disk_step(self,limit=1024):
        for _ in range(limit):
            try: path=next(self.disk_iterator)
            except StopIteration:
                self.state['campaign_allocated_bytes']=self.disk_bytes; self.disk_last=self.now()
                self.disk_bytes=0; self.disk_iterator=iter(walk_files(self.directory,prune=False)); break
            try: self.disk_bytes+=path.stat().st_blocks*512
            except OSError: pass
        stat=os.statvfs(self.directory); free=stat.f_bavail*stat.f_frsize
        self.state['filesystem_free_bytes']=free
        size=self.state.get('campaign_allocated_bytes',0)
        if free<10*GIB or size>=6*GIB:
            atomic_json(self.root/'maintenance-request.json',{'utc':utc(self.now()),'free_bytes':free,'campaign_bytes':size,
                        'action':'root-owned CPU3 archive maintenance requested; preserve all proofs and final models'})
        return ('filesystem free below 8GiB' if free<8*GIB else
                'new campaign storage reached 8GiB' if size>=8*GIB else None)

    def tick(self):
        try: config=self.config_value()
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.stop(f'invalid campaign policy: {exc}')
            self.reap_stops(); self.save()
            return bool(self.state.get('pending_stops'))
        self.reap_stops()
        if self.state.get('stop_reason'):
            self.save(); return bool(self.state.get('pending_stops'))
        reason=self.requested_stop
        if self.now()>=config['deadline_unix']: reason='global campaign deadline reached'
        marker=self.directory/'guard_stopped.json'
        if marker.exists():
            reason='existing campaign guard stop marker; completing identity-safe termination'
        groups=registered_groups(self.directory,self.identity)
        rss=group_rss(groups)
        self.state.update(rss_bytes=rss,maximum_rss_bytes=max(rss,self.state.get('maximum_rss_bytes',0)))
        if rss>7*GIB: reason='conservative 7GiB summed RSS guard for 8GiB limit'
        disk_reason=self.disk_step()
        if disk_reason: reason=disk_reason
        if reason: self.stop(reason)
        else: self.scan()
        if self.now()-self.last_heartbeat>=10 or self.state.get('stop_reason'):
            self.save(); self.last_heartbeat=self.now()
        return True


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path); parser.add_argument('--once',action='store_true')
    args=parser.parse_args(argv)
    os.sched_setaffinity(0,{2}); resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
    lock=(args.directory/'operations-v3.lock').open('a'); fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    ops=Operations(args.directory)
    # Restart after freeze but before stop must complete the already verified stop.
    winner=args.directory/'operations-record/WINNER.json'
    if winner.exists() and not ops.state.get('stop_reason'):
        candidate,_=load_json(winner)
        independent=independent_verify_bytes(winner.read_bytes())
        if (eligible_report(candidate,verify_candidate(candidate,random_trials=16))
            and independent.get('record_eligible') is True and independent.get('exact_entries_checked')==15625):
            ops.stop('restart completed independently verified record stop')
    def terminate(sig,frame): ops.requested_stop=f'operations supervisor signal {sig}'
    signal.signal(signal.SIGTERM,terminate); signal.signal(signal.SIGINT,terminate)
    while ops.tick():
        if args.once: break
        time.sleep(1)
    ops.save()


if __name__=='__main__': main()
