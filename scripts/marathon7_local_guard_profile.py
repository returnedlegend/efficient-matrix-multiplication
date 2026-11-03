#!/usr/bin/env python3
"""Read-only callback profiling of the actual frozen factory; no tensor query."""
import argparse
import cProfile
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pstats
import sys
import tempfile
import time
from datetime import datetime,timezone
from unittest.mock import patch


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--iterations',type=int,default=100);p.add_argument('--candidate-guard-file',type=Path);a=p.parse_args()
    if not 1<=a.iterations<=200:p.error('bounded1..200 callbacks required')
    runtime=a.bundle.resolve()/'runtime';sys.path.insert(0,str(runtime))
    from scripts import marathon7_local_campaign as actual_runner
    from mmsearch import marathon7_cached_guard as cached
    factory=actual_runner.CampaignGuard;campaign=a.campaign.resolve()
    def direct_glob(path,pattern):
        if pattern!='*/WINNER.json':return original_glob(path,pattern)
        candidates=[]
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=True):
                    marker=Path(entry.path)/'WINNER.json'
                    if marker.exists():candidates.append(marker)
        return iter(candidates)
    original_glob=Path.glob;observations={};constructors=[('actual_factory',factory),('same_factory_direct_child_marker_probe',factory)]
    if a.candidate_guard_file:
        spec=importlib.util.spec_from_file_location('mmsearch.candidate_guard_profile',a.candidate_guard_file.resolve());candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate);constructors.append(('candidate_guard',candidate.CampaignGuard))
    for label,constructor in constructors:
        guard=constructor(30,'2026-11-03T19:24:17Z',campaign_dir=campaign,guard_state=campaign/'operations-v3/state.json')
        if guard.reason(force=True):raise ValueError('live guard already held')
        profile=cProfile.Profile();begin=time.perf_counter()
        with patch.object(Path,'glob',direct_glob if label.endswith('probe') else original_glob):
            profile.enable()
            for _ in range(a.iterations):
                reason=guard.reason(force=True)
                if reason:raise ValueError('live guard held: '+reason)
            profile.disable()
        elapsed=time.perf_counter()-begin;stats=pstats.Stats(profile);top=[]
        for (file,line,function),(primitive,calls,own,cumulative,callers) in sorted(stats.stats.items(),key=lambda item:item[1][3],reverse=True)[:20]:
            top.append(dict(file=file,line=line,function=function,calls=calls,own_seconds=own,cumulative_seconds=cumulative))
        observations[label]=dict(iterations=a.iterations,seconds=elapsed,cache=guard.cache.metrics(),top=top)
    synthetic={}
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);state=root/'operations-v3/state.json';state.parent.mkdir();(root/'queue_state.json').write_text('{}')
        ticks=int(Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')',1)[1].split()[19]);value=dict(pid=os.getpid(),process_identity=dict(start_ticks=ticks),updated_utc=datetime.now(timezone.utc).isoformat(),campaign_allocated_bytes=0,stop_reason=None,padding='')
        encode=lambda value:json.dumps(value,separators=(',',':')).encode();value['padding']='x'*(1400000-len(encode(value)));state.write_bytes(encode(value));assert state.stat().st_size==1400000
        for label,constructor in [('actual_frozen_factory',factory),('bare_cached',cached.CampaignGuard)]:
            guard=constructor(30,'2026-11-03T19:24:17Z',campaign_dir=root,guard_state=state);begin=time.perf_counter()
            for _ in range(50):assert guard.reason(force=True) is None
            synthetic[label]=dict(seconds=time.perf_counter()-begin,iterations=50,cache=guard.cache.metrics())
    sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    result=dict(status='PASS_READ_ONLY_PROFILE',production_queries=0,source_mutations=0,factory_is_bare_cached=factory is cached.CampaignGuard,mro=[item.__module__+'.'+item.__name__ for item in factory.__mro__],
        runner_sha256=sha(actual_runner.__file__),guard_sha256=sha(cached.__file__),campaign_children=sum(path.is_dir() for path in campaign.iterdir()),
        observations=observations,synthetic_1400000_byte_factory_vs_bare=synthetic,measured_probe_speedup=observations['actual_factory']['seconds']/observations['same_factory_direct_child_marker_probe']['seconds'],candidate_guard_sha256=sha(a.candidate_guard_file) if a.candidate_guard_file else None,
        scope='Read-only actual guard callbacks; process-local marker-probe instrumentation only. No source/core/decoder call or publication.')
    a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n');print(json.dumps({key:result[key] for key in ['status','production_queries','factory_is_bare_cached','mro','measured_probe_speedup']},sort_keys=True))


if __name__=='__main__':main()
