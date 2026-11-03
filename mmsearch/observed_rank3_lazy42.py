"""New lazy rank3 runtime; frozen v1 mathematical functions remain unchanged."""
import json
import os
from pathlib import Path
import time
from types import FunctionType
from . import observed_rank342 as core
from . import observed_rank3_bounded42 as bounded
from .common_delta42 import columns_from_rows
from .recombine import digest


def clone(function, namespace):
    return FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)


def logical(value):
    """Replay hashes exclude measured timing; all mathematical/status fields remain."""
    if isinstance(value,dict):return {k:logical(v) for k,v in value.items() if k not in ('elapsed_seconds','worker_stats','wall_seconds')}
    if isinstance(value,list):return [logical(v) for v in value]
    return value


_decoder_globals=dict(core.__dict__,digest=lambda value:digest(logical(value)))
decode_rank3=clone(core.decode_rank3,_decoder_globals)
_worker_globals=dict(bounded.__dict__,decode_rank3=decode_rank3)
_worker=clone(bounded._worker,_worker_globals)
_entry=clone(bounded._entry,dict(bounded.__dict__,_worker=_worker))
search_bounded=clone(bounded.search_bounded,dict(bounded.__dict__,_entry=_entry))


class SourceRuntime:
    """Cache only immutable source columns; use unchanged checked quotient/lift code."""
    def __init__(self,system):
        self.system=system;self.columns=columns_from_rows(system)
        def cached_columns(candidate):
            if candidate is not system:raise AssertionError('cached source identity changed')
            return self.columns
        namespace=dict(core.__dict__,columns_from_rows=cached_columns)
        self.validate=clone(core.validate_space,namespace);namespace['validate_space']=self.validate
        self.prepare=clone(core.prepare_space,namespace)
        self.lift=clone(core.lift_space,namespace);namespace['lift_space']=self.lift
        self.decode_hit=clone(core.decode_space_hit,namespace)


class Hold(Exception):pass


class FreshGuard:
    def __init__(self,path,limit=5*1024**3,max_age=60):
        self.path=Path(path);self.limit=limit;self.max_age=max_age;self.cached=None;self.stamp=None;self.last_poll=0
    def check(self):
        try:
            now=time.time()
            if now-self.last_poll>=.5 or self.cached is None:
                stamp=self.path.stat().st_mtime_ns
                if stamp!=self.stamp:self.cached=json.loads(self.path.read_text());self.stamp=stamp
                self.last_poll=now
            state=self.cached
            from datetime import datetime
            age=now-datetime.fromisoformat(state['updated_utc'].replace('Z','+00:00')).timestamp()
            if age< -5 or age>self.max_age:return 'resource guard stale'
            if state.get('stop_reason'):return 'resource guard stop: '+str(state['stop_reason'])
            pid=int(state['pid']);tail=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()
            if int(tail[19])!=int(state['process_identity']['start_ticks']):return 'resource guard process identity changed'
            if state['campaign_allocated_bytes']>=self.limit:return 'resource guard working storage reached 5GiB'
            return None
        except (OSError,ValueError,KeyError,TypeError):return 'resource guard unavailable or invalid'


def directory_bytes(path):
    return sum(item.stat().st_size for item in Path(path).rglob('*') if item.is_file())


def chain_append(path,value,chain):
    event=dict(value=value,previous_sha256=chain);event['sha256']=digest(event)
    raw=(json.dumps(event,sort_keys=True)+'\n').encode()
    with Path(path).open('ab') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return event['sha256']


def chain_read(path,initial):
    events=[];chain=initial;path=Path(path)
    if path.exists():
        raw=path.read_bytes()
        if raw and not raw.endswith(b'\n'):raise ValueError('incomplete result journal tail requires review')
        for line in raw.splitlines():
            event=json.loads(line)
            if event['previous_sha256']!=chain or event['sha256']!=digest({k:v for k,v in event.items() if k!='sha256'}):raise ValueError('result journal chain mismatch')
            events.append(event['value']);chain=event['sha256']
    return events,chain
