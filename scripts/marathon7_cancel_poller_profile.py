#!/usr/bin/env python3
"""Read-only actual-factory inner-callback comparison and one N2 control."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--poller-file',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    runtime=a.bundle.resolve()/'runtime';sys.path.insert(0,str(runtime))
    from scripts import marathon7_local_campaign as runner
    from mmsearch.compact_rank2_edges43 import solve_core
    from mmsearch.local_ten43 import planted_small
    from mmsearch.recombine import digest
    spec=importlib.util.spec_from_file_location('mmsearch.candidate_poller_profile',a.poller_file.resolve());module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    observations={};campaign=a.campaign.resolve()
    for label in ['direct_inner','polled_inner']:
        guard=runner.CampaignGuard(30,'2026-11-03T19:24:17Z',campaign_dir=campaign,guard_state=campaign/'operations-v3/state.json');guard.check('pre_profile');deadline=[guard.monotonic()+20]
        poller=module.CancelPoller(guard,lambda:deadline[0]);callback=poller.cancelled if label=='polled_inner' else lambda:guard.reason() is not None or guard.monotonic()>=deadline[0]
        before=guard.cache.metrics();begin=time.perf_counter()
        for _ in range(1000):assert not callback()
        elapsed=time.perf_counter()-begin;guard.check('post_profile')
        observations[label]=dict(callbacks=1000,seconds=elapsed,cache_before=before,cache_after=guard.cache.metrics(),poller=poller.metrics() if label=='polled_inner' else None)
    # One existing closed N2/F2 positive, once per callback implementation.
    _,data,_=planted_small();controls={}
    for label in ['direct_inner','polled_inner']:
        guard=runner.CampaignGuard(30,'2026-11-03T19:24:17Z',campaign_dir=campaign,guard_state=campaign/'operations-v3/state.json');guard.check('pre_n2');deadline=[guard.monotonic()+2]
        poller=module.CancelPoller(guard,lambda:deadline[0]);callback=poller.cancelled if label=='polled_inner' else lambda:guard.reason() is not None or guard.monotonic()>=deadline[0]
        begin=time.perf_counter();result=solve_core(data['core'],data['shape'],3,axis=0,cancelled=callback);elapsed=time.perf_counter()-begin;guard.check('post_n2')
        assert result['status']=='SAT';controls[label]=dict(seconds=elapsed,result_sha256=digest(result),status=result['status'],poller=poller.metrics() if label=='polled_inner' else None)
    assert controls['direct_inner']['result_sha256']==controls['polled_inner']['result_sha256']
    report=dict(status='PASS_ACTUAL_FACTORY_CALLBACK_PROFILE',production_n5_queries=0,known_n2_control_decisions=2,poller_sha256=hashlib.sha256(a.poller_file.read_bytes()).hexdigest(),
        observations=observations,callback_speedup=observations['direct_inner']['seconds']/observations['polled_inner']['seconds'],n2_controls=controls,
        scope='Live guard callback profiling and existing closed N2 positive only. Forced pre/post barriers unchanged; no N5 source or target decoding.')
    a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({key:report[key] for key in ['status','production_n5_queries','callback_speedup','n2_controls']},sort_keys=True))


if __name__=='__main__':main()
