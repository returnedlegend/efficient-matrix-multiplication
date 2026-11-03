#!/usr/bin/env python3
"""Prepare a pinned strict-schema chunk batch; preview the actual queue helper."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,read,sha
from scripts.phase_coordinator42_v2 import validate_job
from scripts.append_campaign_jobs42 import append_jobs
from mmsearch.marathon7_local import select_plan


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--overlay',type=Path,required=True);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--start',type=int,required=True);p.add_argument('--stop',type=int,required=True);a=p.parse_args()
    if not 0<=a.start<a.stop:p.error('nonempty nonnegative half-open chunk range required')
    b=a.bundle.resolve();overlay=a.overlay.resolve();out=a.output_dir.resolve()
    for release in [b,overlay]:
        for name,expected in read(release/'manifest.json')['files'].items():
            path=(release/name).resolve()
            if not path.is_relative_to(release) or sha(path)!=expected:raise ValueError('release binding differs')
    index=read(overlay/'INDEX.json')
    if index['bundle_manifest_sha256']!=sha(b/'manifest.json'):raise ValueError('overlay bundle binding differs')
    selected=[item for item in index['jobs'] if a.start<=int(item['chunk'])<a.stop]
    if len(selected)!=a.stop-a.start:raise ValueError('chunk range not completely present')
    prior={tuple((case['source_id'],case['mask_lo'],case['mask_hi'])) for number in range(a.start) for case in select_plan(b,f'{number:03d}')['cases']}
    seen=set();jobs=[];cases=0
    for item in selected:
        path=overlay/item['file']
        if sha(path)!=item['sha256']:raise ValueError('overlay job changed')
        job=read(path);validate_job(job)
        if job['enabled'] is not False:raise ValueError('batch proposal must remain disabled')
        selection=select_plan(b,item['chunk']);keys={(case['source_id'],case['mask_lo'],case['mask_hi']) for case in selection['cases']}
        if len(keys)!=item['cases'] or keys&seen or keys&prior:raise ValueError('duplicate or previously selected source/mask')
        seen|=keys;cases+=len(keys);jobs.append(job)
    out.mkdir(parents=True,exist_ok=False);freeze(out/'PROPOSAL.json',dict(jobs=jobs))
    preview=append_jobs(a.campaign.resolve()/'queue.json',out/'PROPOSAL.json',sha(out/'PROPOSAL.json'),out/'unused-preview-receipt.json',apply=False,enable=True)
    if preview['status']!='PREVIEW_ONLY' or not preview['zero_mutations']:raise ValueError('helper failed read-only preview')
    freeze(out/'PREVIEW.json',preview)
    freeze(out/'REPORT.json',dict(status='STRICT_BATCH_VALIDATED_READ_ONLY_PREVIEW',chunks=[item['chunk'] for item in selected],jobs=len(jobs),cases=cases,previous_chunk_source_masks_excluded=len(prior),
        duplicate_masks=0,bundle_manifest_sha256=sha(b/'manifest.json'),overlay_manifest_sha256=sha(overlay/'manifest.json'),proposal_sha256=sha(out/'PROPOSAL.json'),preview_sha256=sha(out/'PREVIEW.json'),
        queue_before_sha256=preview['queue_before_sha256'],actual_queue_validator_called_on_every_job=True,queue_mutations=0))
    freeze(out/'marathon7_local_batch_proposal.py',Path(__file__).read_bytes());freeze(out/'manifest.json',dict(files={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}))
    print(json.dumps(dict(status='STRICT_BATCH_VALIDATED_READ_ONLY_PREVIEW',jobs=len(jobs),cases=cases,proposal_sha256=sha(out/'PROPOSAL.json'),manifest_sha256=sha(out/'manifest.json'),queue_mutations=0)))


if __name__=='__main__':main()
