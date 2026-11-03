#!/usr/bin/env python3
"""Disabled bounded witness generation for the separate pair-escape selector.

This generates algebraic five-term witnesses only. No extension-kernel prepare,
heuristic search, SAT query, source split change, or automatic launch follows.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import math
import signal
import time
import json
import os
from pathlib import Path
import resource
import shutil
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from mmsearch.tensor_code7_extension import authenticate_base,raw_sha
from mmsearch.tensor_code7_extension_selector import SELECTOR_SCHEMA,select_witnesses
from scripts.tensor_code7 import Stop,runtime,write_json
from mmsearch.marathon7_cached_guard import CampaignGuard
from scripts.tensor_code7_extension import code_hashes

CACHED_GUARD_SHA256='09ac03c4ac1123eeb2ddba8a72653cc299aca052df9ad6c82ad618ed5cbd5cd9'
OUTPUT_LIMIT=32*1024**2


class DirectGuard:
    def __init__(self,args):
        if not math.isfinite(args.seconds) or not 0<args.seconds<=120:
            raise ValueError('finite reviewed wall budget in(0,120] required')
        config_raw=(args.campaign_dir/'campaign.json').read_bytes()
        if raw_sha(config_raw)!=args.campaign_sha256:raise ValueError('campaign raw pin mismatch')
        config=json.loads(config_raw)
        caller=datetime.fromisoformat(args.hard_utc.replace('Z','+00:00'))
        configured=datetime.fromisoformat(config['deadline_utc'].replace('Z','+00:00'))
        if caller.tzinfo is None or configured.tzinfo is None:raise ValueError('timezone required')
        self.hard=min(caller,configured,datetime.fromisoformat('2026-11-03T19:24:17+00:00'))
        module=REPO/'mmsearch/marathon7_cached_guard.py'
        if raw_sha(module.read_bytes())!=CACHED_GUARD_SHA256:raise ValueError('direct cached guard differs from independently reviewed pin')
        self.canonical=CampaignGuard(args.seconds,self.hard.isoformat(),guard_state=args.guard_state,campaign_dir=args.campaign_dir)
        if self.canonical.resources is None:raise ValueError('fresh resource guard required')
        self.started=self.canonical.started;self.seconds=args.seconds
        signal.signal(signal.SIGTERM,lambda *_:self.canonical.stop())
        signal.signal(signal.SIGINT,lambda *_:self.canonical.stop())

    def __call__(self,barrier='loop'):
        if datetime.now(timezone.utc).timestamp()>=self.hard.timestamp()-3:
            raise Stop('hard_utc_postcheck_reserve:'+barrier)
        reason=self.canonical.reason(force=barrier!='loop')
        if reason:raise Stop(reason+':'+barrier)
        if datetime.now(timezone.utc).timestamp()>=self.hard.timestamp()-3:
            raise Stop('hard_utc_postcheck_reserve:'+barrier)


def allocated_bytes(root):
    return sum(max(path.stat().st_size,path.stat().st_blocks*512) for path in [root,*root.rglob('*')])


def output_check(root,reserve=0):
    if allocated_bytes(root)+reserve>OUTPUT_LIMIT:raise Stop('32MiB_output_budget')


EXTRA_CODE=('mmsearch/tensor_code7_extension_selector.py','scripts/tensor_code7_extension_select.py',
            'tests/test_tensor_code7_extension_selector.py','research/tensor_code7_extension_selector.md')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-prepared',type=Path);p.add_argument('--base-sha256')
    p.add_argument('--source-manifest',type=Path);p.add_argument('--source-manifest-sha256')
    p.add_argument('--approved-root',type=Path);p.add_argument('--campaign-dir',type=Path)
    p.add_argument('--campaign-sha256');p.add_argument('--guard-state',type=Path)
    p.add_argument('--hard-utc',default='2026-11-03T19:24:17Z');p.add_argument('--seconds',type=float,default=120)
    p.add_argument('--max-attempts',type=int,default=8192);p.add_argument('--max-relations',type=int,default=16)
    p.add_argument('--max-new-atoms',type=int,default=100);p.add_argument('--outdir',type=Path)
    p.add_argument('--authorize-witness-generation',action='store_true');p.add_argument('--qa-approval',choices=('root-reviewed',))
    a=p.parse_args(argv)
    if not a.authorize_witness_generation or a.qa_approval!='root-reviewed':
        print(json.dumps(dict(schema=SELECTOR_SCHEMA,status='DISABLED_PENDING_ROOT_SELECTOR_QA',
            production_inputs_read=False,n5_witnesses_generated=False,target_query_called=False),sort_keys=True));return 0
    for key in ('base_prepared','base_sha256','source_manifest','source_manifest_sha256','approved_root',
                'campaign_dir','campaign_sha256','guard_state','outdir'):
        if getattr(a,key) is None:p.error('enabled generation requires --'+key.replace('_','-'))
    if not 1<=a.max_attempts<=8192 or not 1<=a.max_relations<=16 or not 1<=a.max_new_atoms<=100:p.error('reviewed selector bounds exceeded')
    guard=DirectGuard(a)
    try:guard('pre_dispatch')
    except Stop as exc:
        print(json.dumps(dict(schema=SELECTOR_SCHEMA,status='UNKNOWN',complete=False,stop_reason=str(exc),
            production_inputs_read=False,n5_witnesses_generated=False,target_query_called=False),sort_keys=True));return 0
    os.sched_setaffinity(0,{1})
    if os.getpriority(os.PRIO_PROCESS,0)<10:os.nice(10-os.getpriority(os.PRIO_PROCESS,0))
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(OUTPUT_LIMIT,OUTPUT_LIMIT))
    root=a.outdir.resolve()
    if root.is_relative_to(a.base_prepared.resolve().parent) or root.is_relative_to(a.approved_root.resolve()):
        raise ValueError('output must not mutate immutable base/source packages')
    root.mkdir(parents=True,exist_ok=False);scratch=root/'source-recheck';scratch.mkdir()
    hashes=code_hashes();hashes.update({name:raw_sha((REPO/name).read_bytes()) for name in EXTRA_CODE})
    for name,expected in hashes.items():
        target=root/'code'/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((REPO/name).read_bytes())
        if raw_sha(target.read_bytes())!=expected:raise ValueError('code changed while snapshotting')
    write_json(root/'launch.json',dict(schema=SELECTOR_SCHEMA,code_sha256=hashes,runtime=runtime(),
        arguments={key:str(value) if isinstance(value,Path) else value for key,value in vars(a).items()}),exclusive=True)
    manifest=None;audit=None;exit_code=0
    try:
        base,receipt=authenticate_base(a.base_prepared,a.base_sha256,a.source_manifest,a.source_manifest_sha256,a.approved_root,scratch,guard)
        expected=base.get('lifecycle_config',{})
        actual=dict(campaign_sha256=a.campaign_sha256,campaign_dir=str(a.campaign_dir.resolve()),
            guard_state=str(a.guard_state.resolve()),deadline_utc=guard.hard.isoformat())
        if any(expected.get(key)!=value for key,value in actual.items()):raise ValueError('selector lifecycle config differs from approved base')
        output_check(root,allocated_bytes(a.base_prepared.resolve().parent)+1024**2)
        shutil.copytree(a.base_prepared.resolve().parent,root/'base');guard('post_base_snapshot');output_check(root,1024**2)
        manifest,audit=select_witnesses(base,a.base_sha256,a.max_relations,a.max_new_atoms,a.max_attempts,guard,receipt,True)
        guard('post_witness_generation');output_check(root,1024**2);write_json(root/'audit.json',audit,exclusive=True)
        if manifest['relations']:
            guard('pre_witness_publication');write_json(root/'witnesses.json',manifest,exclusive=True);guard('post_witness_publication')
        result=dict(status='GENERATED_ALGEBRAIC_WITNESSES_ONLY',complete=audit['requested_count_reached'],
            accepted_relations=audit['accepted_relations'],attempted_pair_axis_records=audit['attempted_pair_axis_records'],
            derived_new_atom_count=audit['derived_new_atom_count'],target_query_called=False,
            witness_manifest_sha256=raw_sha((root/'witnesses.json').read_bytes()) if (root/'witnesses.json').exists() else None)
    except Stop as exc:
        hidden=root/'.raw-witnesses';hidden.mkdir(exist_ok=True)
        for name in ('witnesses.json','audit.json'):
            if (root/name).exists():(root/name).unlink()
        write_json(hidden/'after-cutoff.json',dict(status='UNKNOWN',complete=False,after_cutoff=True,
            no_within_budget_claim=True,raw=dict(witnesses=manifest,audit=audit)),exclusive=True)
        result=dict(status='UNKNOWN',complete=False,stop_reason=str(exc),target_query_called=False)
    except Exception as exc:
        result=dict(status='FAILED_CLOSED',complete=False,error_type=type(exc).__name__,error=str(exc),target_query_called=False);exit_code=2
    result.update(schema=SELECTOR_SCHEMA,runtime=runtime(),code_sha256=hashes,
        direct_cached_guard_sha256=CACHED_GUARD_SHA256,guard_cache_metrics=guard.canonical.cache.metrics(),
        elapsed_seconds=time.monotonic()-guard.started,output_limit_bytes=OUTPUT_LIMIT)
    write_json(root/'result.json',result,exclusive=True)
    write_json(root/'checksums.json',{str(path.relative_to(root)):raw_sha(path.read_bytes()) for path in sorted(root.rglob('*')) if path.is_file()},exclusive=True)
    output_check(root)
    print(json.dumps(result,sort_keys=True));return exit_code


if __name__=='__main__':raise SystemExit(main())
