"""Freeze the46 nonclosed observed k7 spaces for reviewed future lazy pilot."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.observed_budget6_runtime42 import SourceRuntime
from mmsearch.free_factor_sat import decode_vectors
from mmsearch.recombine import digest
from mmsearch.verify import verify_candidate
from scripts.freeze_campaign_dictionary import freeze,json_bytes
ROOT=Path(__file__).resolve().parents[1]
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
READ=lambda p:json.loads(Path(p).read_text())


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    old=a.prepared_dir.resolve();out=a.output_dir.resolve();bindings=READ(old/'integrity.json')
    for name,expected in bindings.items():
        if SHA(old/name)!=expected:raise ValueError('historical source hash mismatch: '+name)
    out.mkdir(parents=True,exist_ok=False);sources={};chunks=[];controls=[]
    for directory in sorted((old/'sources').iterdir()):
        source=directory.name;system=READ(directory/'system.json');runtime=SourceRuntime(system)
        checked=verify_candidate(decode_vectors(system,system['baseline_vectors']),random_trials=0)
        if not checked['valid'] or checked['rank']!=93 or checked['exact_entries_checked']!=15625:raise ValueError('invalid exact93 source')
        for name in ('system.json','active-certificate.json','baseline.verification.json'):freeze(out/'sources'/source/name,(directory/name).read_bytes())
        full=json.loads(gzip.decompress((old/'catalogs'/(source+'.json.gz')).read_bytes()))
        items=[dict(full_catalog_ordinal=i,space=item['space'],basis_values=item['basis_values'],k=item['k'],weight_bound=6) for i,item in enumerate(full) if item['k']==7]
        if any(item['k']>7 for item in full):raise ValueError('newunsupported budget>6 catalog case requires review')
        sources[source]=dict(system_sha256=SHA(out/'sources'/source/'system.json'),original_catalog_content_sha256=digest(full),original_catalog_compressed_sha256=SHA(old/'catalogs'/(source+'.json.gz')),remaining=len(items))
        chunk_id=source+'-k7';name='plans/'+chunk_id+'.json.gz';freeze(out/name,gzip.compress(json_bytes(items),compresslevel=1,mtime=0))
        chunks.append(dict(id=chunk_id,source_id=source,source_offset=0,count=len(items),plan=name,plan_sha256=digest(items),compressed_sha256=SHA(out/name)))
        q=runtime.prepare(system,items[0]['basis_values'])
        old_entries=[[i,value] for i,value in enumerate(q['old_coordinates']) if value]
        lifted=runtime.lift(system,q,old_entries,require_gain=False)
        if q['k']!=7 or q['target_rank']!=3 or lifted['rank_after']!=93 or lifted['coordinate_kernel_masks_hex']!=['0x0']*3:raise ValueError('lazy baseline liftcontrol failed')
        controls.append(dict(source_id=source,verification=checked,first_case_quotient_sha256=q['quotient_sha256'],baseline_kernel_masks=lifted['coordinate_kernel_masks_hex'],target_queries=0))
    if sum(item['count'] for item in chunks)!=46:raise ValueError('unexpected k7 catalogue size')
    plan=dict(version=1,decoder='rank3-budget6-fano-lazy-v1',sources=sources,chunks=chunks,remaining=46,original_prepared_integrity_sha256=SHA(old/'integrity.json'),
        scope='Only46 explicit observed3D k7 palettes on these immutable sources, exact groupweight<=6 via Fano contractions. Time/memory/prefix-cap holds remain UNKNOWN. No unrestricted rank/all-image conclusion.')
    freeze(out/'plan.json',json_bytes(plan));freeze(out/'SOURCE-CONTROLS.json',json_bytes(controls))
    for folder in ('mmsearch','scripts'):
        for path in sorted((ROOT/folder).rglob('*.py')):freeze(out/'code'/path.relative_to(ROOT),path.read_bytes())
    freeze(out/'code/tests/test_observed_budget642.py',(ROOT/'tests/test_observed_budget642.py').read_bytes());freeze(out/'code/tests/__init__.py',b'')
    integrity={str(path.relative_to(out)):SHA(path) for path in sorted(out.rglob('*')) if path.is_file()};freeze(out/'integrity.json',json_bytes(integrity))
    command=['python3','-B',str(out/'code/scripts/campaign_observed_budget642.py'),'--prepared-dir',str(out),'--output-dir',str(out.parent/'observed-budget6-pilot46-001'),
        '--seconds','540','--per-case-seconds','10','--memory-mb','1024','--guard-state',str(out.parent/'operations-v3/state.json')]
    for chunk in chunks:command.extend(['--chunk-id',chunk['id']])
    freeze(out/'PROPOSED-JOB.json',json_bytes(dict(id='observed-budget6-pilot46-001',enabled=False,cpu=1,memory_mb=1024,seconds=600,command=command)))
    print(json.dumps(dict(status='PREPARED_FOR_REVIEW',cases=46,source_counts={source:item['remaining'] for source,item in sources.items()},target_queries=0)))


if __name__=='__main__':main()
