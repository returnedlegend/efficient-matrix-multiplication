#!/usr/bin/env python3
"""Preserve frozen bundles; derive strict six-key queue job proposals."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.phase_coordinator42_v2 import validate_job
from scripts.prepare_local_ten43 import freeze,read,sha


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    bundle=a.bundle.resolve();out=a.output_dir.resolve();manifest=read(bundle/'manifest.json')
    for name,expected in manifest['files'].items():
        path=(bundle/name).resolve()
        if not path.is_relative_to(bundle) or sha(path)!=expected:raise ValueError('frozen input changed')
    out.mkdir(parents=True,exist_ok=False);records=[]
    for item in read(bundle/'JOB-INDEX.json'):
        source=bundle/item['file'];original=read(source)
        if sha(source)!=item['sha256']:raise ValueError('job input binding differs')
        if original.get('nice')!=10:raise ValueError('expected inherited nice10 advisory')
        job={key:value for key,value in original.items() if key!='nice'}
        validate_job(job)
        name=Path(item['file']).name;freeze(out/name,job)
        records.append(dict(id=job['id'],chunk=item['chunk'],cases=item['cases'],file=name,sha256=sha(out/name),original_file=str(source),original_sha256=sha(source),only_removed_field=dict(nice=10)))
    freeze(out/'INDEX.json',dict(bundle=str(bundle),bundle_manifest_sha256=sha(bundle/'manifest.json'),jobs=records,validator_sha256=sha(ROOT/'scripts/phase_coordinator42_v2.py'),
        policy='Actual queue validate_job called on every six-key proposal; niceness10 is inherited from queue parent, not an accepted job field. No queue mutation.',jobs_validated=len(records)))
    freeze(out/'marathon7_local_job_overlay.py',Path(__file__).read_bytes())
    freeze(out/'manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    print(json.dumps(dict(status='QUEUE_PROPOSALS_VALIDATED_NO_QUEUE_MUTATION',jobs_validated=len(records),manifest_sha256=sha(out/'manifest.json'))))


if __name__=='__main__':main()
