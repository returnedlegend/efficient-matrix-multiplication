#!/usr/bin/env python3
"""Independent synthetic cache invalidation, race, process, and late-stop QA."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mmsearch import marathon7_cached_guard as subject


def main():
    counts={};started=time.monotonic();module_pin=hashlib.sha256((ROOT/'mmsearch/marathon7_cached_guard.py').read_bytes()).hexdigest()
    def passed(name):counts[name]=counts.get(name,0)+1
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);queue=root/'queue_state.json';resource=root/'operations-v3/state.json';resource.parent.mkdir();clock=[subject.HARD_DEADLINE-3600];mono=[0.]
        ticks=int(subject._proc_stat(os.getpid())[19]);good=dict(pid=os.getpid(),process_identity=dict(start_ticks=ticks),updated_utc=datetime.fromtimestamp(clock[0],timezone.utc).isoformat(),campaign_allocated_bytes=0,stop_reason=None)
        def write(path,value):path.write_text(json.dumps(value,separators=(',',':')))
        def reset():write(queue,{});write(resource,good);clock[0]=subject.HARD_DEADLINE-3600;mono[0]=0.
        def guard():return subject.CampaignGuard(100,'2099-01-01T00:00:00Z',guard_state=resource,campaign_dir=root,utc_clock=lambda:clock[0],monotonic=lambda:mono[0])
        reset();g=guard();assert g.reason(force=True) is None
        # Same inode, size and mtime; ctime is the only changed content signature.
        before=resource.stat();write(resource,dict(good,stop_reason='go'));os.utime(resource,ns=(before.st_atime_ns,before.st_mtime_ns));after=resource.stat()
        assert (before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns)
        assert g.reason(force=False) is not None;passed('same_inode_size_mtime_ctime_stop')
        reset();cache=subject.StableJsonCache();assert cache.load(queue)=={}
        actual=cache._signature;flag=[False]
        def change_hit(path):
            signature=actual(path)
            if path==queue and not flag[0]:flag[0]=True;write(queue,dict(stop_reason='hit race'))
            return signature
        with patch.object(cache,'_signature',change_hit):assert cache.load(queue)['stop_reason']=='hit race'
        passed('cached_hit_double_stat_race')
        # A cache miss that is never stable must fail, never reuse an old parse.
        reset();cache=subject.StableJsonCache();counter=[0];actual_load=json.loads
        def churn(raw):
            value=actual_load(raw);counter[0]+=1;write(queue,dict(serial=counter[0]));return value
        try:
            with patch.object(subject.json,'loads',churn):cache.load(queue)
        except OSError:passed('bounded_unstable_read_fail_closed')
        else:raise AssertionError('unstable cache input allowed')
        reset();g=guard();assert g.reason() is None
        # Canonical stop changes during later marker I/O require the same barrier hold.
        actual_glob=Path.glob;flag=[False]
        def marker_hook(function):
            if hasattr(subject,'_immediate_child_winner'):
                return patch.object(subject,'_immediate_child_winner',lambda path:any(function(path,'*/WINNER.json')))
            return patch.object(Path,'glob',function)
        def late_queue(path,pattern):
            values=list(actual_glob(path,pattern))
            if path==root and not flag[0]:flag[0]=True;write(queue,dict(stop_reason='late queue'))
            return iter(values)
        with marker_hook(late_queue):assert g.reason(force=True) is not None
        passed('late_canonical_queue_stop')
        reset();g=guard();assert g.reason() is None
        def late_resource(path,pattern):
            values=list(actual_glob(path,pattern));write(resource,dict(good,campaign_allocated_bytes=5*1024**3));return iter(values)
        with marker_hook(late_resource):assert g.reason(force=True) is not None
        passed('late_resource_storage_stop')
        # A symlink target changes while its final name remains the resource selector.
        reset();link=root/'selector';link.symlink_to(resource);cache=subject.StableJsonCache();assert cache.load(link)['pid']==os.getpid();other=root/'other';write(other,dict(good,pid=1));link.unlink();link.symlink_to(other);assert cache.load(link)['pid']==1;passed('symlink_retarget_invalidates')
        for malformed in [None,[],True,5,'x']:
            reset();write(queue,malformed);assert guard().reason(force=False) is not None;passed('malformed_canonical')
        for change in [dict(pid=True),dict(process_identity=dict(start_ticks=True)),dict(updated_utc='2026-11-03T00:00:00'),dict(campaign_allocated_bytes=True),dict(campaign_allocated_bytes=5*1024**3+1)]:
            reset();write(resource,dict(good,**change));assert guard().reason(force=False) is not None;passed('typed_resource_and_storage')
        reset();g=guard();assert g.reason() is None;clock[0]+=61;assert g.reason(force=False) is not None;passed('cached_age_still_live')
        reset();g=guard();assert g.reason() is None;actual_signature=g.cache._signature
        def late_stat(path):value=actual_signature(path);mono[0]=101.;return value
        with patch.object(g.cache,'_signature',late_stat):assert g.reason(force=True) is not None
        passed('late_cached_stat_monotonic')
        reset();g=guard();assert g.reason() is None;actual_signature=g.cache._signature
        def late_utc(path):value=actual_signature(path);clock[0]=subject.HARD_DEADLINE;return value
        with patch.object(g.cache,'_signature',late_utc):assert g.reason(force=False) is not None
        passed('late_cached_stat_utc')
        # Cached JSON is unchanged while its actual guard process dies during glob.
        reset();child=subprocess.Popen([sys.executable,'-c','import sys;sys.stdin.read()'],stdin=subprocess.PIPE)
        try:
            write(resource,dict(good,pid=child.pid,process_identity=dict(start_ticks=int(subject._proc_stat(child.pid)[19]))));g=guard();assert g.reason() is None
            def die(path,pattern):values=list(actual_glob(path,pattern));child.terminate();child.wait(timeout=5);return iter(values)
            with marker_hook(die):assert g.reason(force=True) is not None
            passed('actual_guard_death_after_marker_io')
        finally:
            if child.poll() is None:child.kill();child.wait()
            child.stdin.close()
        reset();g=guard();assert g.reason() is None;g.stop();assert g.reason(force=False)=='stop signal' and g.reason(force=True)=='stop signal';passed('force_does_not_mask_signal')
        if hasattr(subject,'_immediate_child_winner'):
            reset();child=root/'many-results';child.mkdir()
            for i in range(1000):(child/f'case-{i}.json').write_text('{}')
            actual_scandir=os.scandir;visited=[]
            def only_root(path):
                visited.append(str(path));assert Path(path)==root,'enumerated child contents'
                return actual_scandir(path)
            with patch.object(subject.os,'scandir',only_root):assert not subject._immediate_child_winner(root)
            assert visited==[str(root)];passed('dense_child_contents_never_enumerated')
            (child/'WINNER.json').write_text('{}')
            with patch.object(subject.os,'scandir',only_root):assert subject._immediate_child_winner(root)
            (child/'WINNER.json').unlink();passed('direct_child_marker_detected')
            outside=root.parent/(root.name+'-external-marker-test');outside.mkdir()
            try:
                (outside/'WINNER.json').write_text('{}');link=root/'linked-child';link.symlink_to(outside,target_is_directory=True)
                with patch.object(subject.os,'scandir',only_root):assert subject._immediate_child_winner(root)
                passed('child_directory_symlink_marker_preserved')
            finally:
                link.unlink();(outside/'WINNER.json').unlink();outside.rmdir()
    assert module_pin==hashlib.sha256((ROOT/'mmsearch/marathon7_cached_guard.py').read_bytes()).hexdigest(),'module changed during review'
    report=dict(status='PASS',module_sha256=module_pin,cases=sum(counts.values()),counts=counts,production_queries=0,elapsed_seconds=time.monotonic()-started,
        scope='Independent synthetic file-version/race/live-process/typed-state/clock/stop audit; no N5 source or decoder queries.')
    print(json.dumps(report,sort_keys=True))


if __name__=='__main__':main()
