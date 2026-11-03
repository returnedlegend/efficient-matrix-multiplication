#!/usr/bin/env python3
"""Query-free exact nine-core pin supplement to the immutable Native catalogue."""
import argparse
import json
import os
from pathlib import Path
import resource
import signal
import sys
REPO=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(REPO))
from mmsearch.binary_packet_adapter7 import (C7,PREP,PINS,SOURCE,SOURCE_SHA,
    build_packet_data,literal_terms,pinned,raw,select_plan,sha)
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import verify_bytes

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--authorize-core-preparation',action='store_true')
    args=p.parse_args()
    if not args.authorize_core_preparation:
        print(json.dumps(dict(status='DISABLED',queries_started=0)));return
    os.sched_setaffinity(0,{1})
    if os.getpriority(os.PRIO_PROCESS,0)<10:os.nice(10-os.getpriority(os.PRIO_PROCESS,0))
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
    guard=CampaignGuard(30,'2026-11-03T19:24:17Z',campaign_dir=C7,guard_state=C7/'operations-v3/state.json')
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    out=args.outdir.resolve()
    if out.exists() or not out.is_relative_to(C7):raise ValueError('fresh C7 output required')
    out.mkdir();guard.check('pre_metadata')
    plan=select_plan();guard.check('post_metadata')
    source_raw=pinned(SOURCE);source=json.loads(source_raw);literal_terms(source)
    primary=verify_candidate(source,random_trials=0);secondary=verify_bytes(source_raw)
    guard.check('post_source_checks')
    if not primary['valid'] or primary['exact_entries_checked']!=15625 or not secondary['valid'] or secondary['exact_entries_checked']!=15625:raise ValueError('source failed complete ambient validation')
    (out/'source.json').write_bytes(source_raw);cases=[]
    for i,row in enumerate(plan['cases']):
        guard.check('pre_core')
        data=build_packet_data(source,row,allow_unpinned_preparation=True)
        guard.check('post_core');payload=raw(data)
        (out/f'case-{i:02d}.json').write_bytes(payload)
        cases.append(dict(case=row['id'],native_row_sha256=sha(raw(row)),core_sha256=data['target_core_sha256'],
            ambient_sha256=data['target_ambient_sha256'],core_input_sha256=sha(payload),core_file=f'case-{i:02d}.json',
            actual_mode_ranks=[11]*3,full_ambient_entries_checked=15625,
            removed_source_index=data['removed_source_index'],initial_loss=data['initial_loss']))
    guard.check('pre_manifest_publication')
    result=dict(status='PREPARED_NINE_CORES_NO_QUERY',source_sha256=SOURCE_SHA,
        native_catalog_sha256=PINS[PREP+'/catalog.json.gz'],input_sha256=PINS,cases=cases,
        decoder_queries=0,optimization_called=False,target_sat_called=False,
        source_verifications=dict(primary=primary,independent=secondary),guard=guard.observation(),
        cpu_affinity=sorted(os.sched_getaffinity(0)),nice=os.getpriority(os.PRIO_PROCESS,0),
        max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    (out/'manifest.json').write_bytes(raw(result));guard.check('post_manifest_publication')
    (out/'checksums.json').write_bytes(raw({str(path.relative_to(out)):sha(path.read_bytes()) for path in out.rglob('*') if path.is_file()}))
    print(json.dumps(dict(status=result['status'],cases=len(cases),manifest_sha256=sha(raw(result)),outdir=str(out),queries_started=0),sort_keys=True))
if __name__=='__main__':main()
