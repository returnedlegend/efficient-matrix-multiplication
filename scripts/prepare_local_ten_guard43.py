"""Preserve V1 and freeze a guarded overlay with byte-identical12 core inputs."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,sha,read


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--v1-bundle',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    old=a.v1_bundle.resolve();out=a.output_dir.resolve();parent=read(old/'manifest.json')['files']
    for name,expected in parent.items():
        if sha(old/name)!=expected:raise ValueError('V1source changed: '+name)
    out.mkdir(parents=True,exist_ok=False);excluded={'READY.json','manifest.json','launch-manifest.json','README.md','PROPOSED-JOB.json'}
    for path in sorted(old.rglob('*')):
        if path.is_file() and str(path.relative_to(old)) not in excluded:freeze(out/path.relative_to(old),path.read_bytes())
    for source,dest in [('mmsearch/local_guard43.py','runtime/mmsearch/local_guard43.py'),('scripts/campaign_local_ten_guard43.py','runtime/campaign_local_ten_guard43.py'),
        ('scripts/campaign_local_ten_guard43.py','runtime/scripts/campaign_local_ten_guard43.py'),('tests/test_local_ten_guard43.py','runtime/tests/test_local_ten_guard43.py')]:
        freeze(out/dest,(ROOT/source).read_bytes())
    freeze(out/'runtime/tests/__init__.py',b'');freeze(out/'prepare_local_ten_guard43.py',Path(__file__).read_bytes())
    same={}
    for pattern in ['plan.json','source-*.json','cases/*.core.json','small-source.json','small-core.json','small-plan.json']:
        for path in old.glob(pattern):
            name=str(path.relative_to(old))
            if (out/name).read_bytes()!=path.read_bytes():raise ValueError('overlay changed mathematics/data')
            same[name]=sha(path)
    freeze(out/'PARENT-DATA-BINDINGS.json',dict(parent_bundle=str(old),parent_manifest_sha256=sha(old/'manifest.json'),unchanged_files=same,
        source_core_plan_bytes_unchanged=True,old_v1_unlaunched_preserved=True))
    before=(old/'runtime/campaign_local_ten_coset43.py').read_text().splitlines(True);after=(ROOT/'scripts/campaign_local_ten_guard43.py').read_text().splitlines(True)
    freeze(out/'GUARD-DIFF.patch',''.join(difflib.unified_diff(before,after,fromfile='v1/campaign_local_ten_coset43.py',tofile='v2/campaign_local_ten_guard43.py')).encode())
    freeze(out/'launch-manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    campaign=out.parent;command=['python3','-B',str(out/'runtime/campaign_local_ten_guard43.py'),'--bundle',str(out),'--output-dir',str(campaign/'local-ten43-pilot12-001'),
        '--seconds','150','--memory-mb','1024','--deadline-utc','2026-11-04T21:31:16Z','--guard-state',str(campaign/'operations-v3/state.json')]
    freeze(out/'PROPOSED-JOB.json',dict(id='local-ten43-pilot12-001',enabled=False,cpu=1,memory_mb=1024,seconds=180,command=command))
    print(json.dumps(dict(status='GUARDED_OVERLAY_PREPARED',unchanged_input_files=len(same),launch_manifest_sha256=sha(out/'launch-manifest.json'),target_queries=0)))


if __name__=='__main__':main()
