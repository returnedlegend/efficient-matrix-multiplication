#!/usr/bin/env python3
"""Query-free source/mask releases for new Marathon7 rank-two-edge searches."""
import argparse
from collections import Counter,deque
import gzip
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import read,sha,freeze
from mmsearch.recombine import digest
from mmsearch.marathon7_local import SourceCache,select_plan,DEADLINE
from scripts.phase_coordinator42_v2 import validate_job


def check_manifest(bundle,name='manifest.json'):
    for filename,expected in read(bundle/name)['files'].items():
        path=(bundle/filename).resolve()
        if not path.is_relative_to(bundle) or sha(path)!=expected:raise ValueError('historical release changed: '+str(path))


def pilot_exclusions(old,parent):
    """Validate prior exact identical-input negatives without calling a decoder."""
    pilot=old/'local-ten43-pilot12-001';bundle=old/'local-ten43-ready-v3'
    check_manifest(bundle);config=read(pilot/'config.json');summary=read(pilot/'summary.json');cursor=read(pilot/'cursor.json')
    if config['launch_manifest_sha256']!=sha(bundle/'launch-manifest.json') or config['controls_only'] or config['small_control']:raise ValueError('pilot query model differs')
    configsha=digest(config)
    # Historical config hashes used compact default JSON separators, not digest().
    import hashlib
    configsha=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    cases=read(bundle/'plan.json')['cases']
    if len(cases)!=12 or summary['status']!='LOCAL_PORTFOLIO_UNSAT' or summary['queries_this_invocation']!=12 or not summary['terminal'] or cursor['next_case']!=12 or not cursor['terminal'] or summary['results']!=cursor['results']:raise ValueError('pilot12 incomplete')
    records=[]
    for case,entry in zip(cases,summary['results']):
        resultfile=pilot/entry['result_file'];result=read(resultfile)
        if entry['case']!=case['id'] or entry['status']!='LOCAL_UNSAT' or sha(resultfile)!=entry['result_sha256'] or result['status']!='LOCAL_UNSAT' or result.get('complete') is not True or result.get('after_cutoff') or result['config_sha256']!=configsha:raise ValueError('pilot exact result binding differs')
        if result['core_sha256']!=case['core_sha256'] or result['shape']!=case['shape'] or result['axis']!=case['free_axis'] or result['mode_rank']!=8 or result['target']!=9:raise ValueError('pilot exact core/model differs')
        if sha(parent/case['source'])!=case['source_sha256']:raise ValueError('pilot source differs from local10 survivors')
        ids=case['original_source_indices'];mask=sum(1<<i for i in ids)
        records.append(dict(source_id=case['source_id'],mask_lo=mask&((1<<64)-1),mask_hi=mask>>64,source_indices=ids,source_sha256=case['source_sha256'],
            result_file=str(resultfile),result_sha256=sha(resultfile),core_sha256=case['core_sha256'],historical_launch_manifest_sha256=sha(bundle/'launch-manifest.json'),
            reason='Reused identical fixed-source/mask d8 target9 exact complete negative; no new decoder call.'))
    if len({(r['source_id'],r['mask_lo'],r['mask_hi']) for r in records})!=12:raise ValueError('duplicate pilot exclusions')
    return records


def prepare(old,out,family,chunk_size):
    local10=family=='local10';parent=old/('local-ten-lowrank-span43-ready-v1' if local10 else 'extend-eight43-bulk-ready-v1')
    parent_manifest='manifest.json' if (parent/'manifest.json').exists() else 'launch-manifest.json'
    check_manifest(parent,parent_manifest)
    if local10:
        rows=[list(map(int,line.split())) for line in gzip.decompress((parent/'survivors.tsv.gz').read_bytes()).decode().splitlines()]
        exclusions=pilot_exclusions(old,parent);excluded={(r['source_id'],r['mask_lo'],r['mask_hi']) for r in exclusions}
        if len(rows)!=111605 or not excluded<={tuple(r[:3]) for r in rows}:raise ValueError('local10 survivor/pilot mismatch')
        rows=[r for r in rows if tuple(r[:3]) not in excluded]
    else:
        plan=read(parent/'plan.json');payload=(parent/plan['catalog']).read_bytes()
        if sha(parent/plan['catalog'])!=plan['catalog_sha256']:raise ValueError('extension8 catalog changed')
        rows=[r+[i] for i,r in enumerate(json.loads(gzip.decompress(payload)))];exclusions=[]
        if len(rows)!=5929:raise ValueError('extension8 pending count differs')
        # Refuse preparation if any bulk query outputs appeared after this inventory.
        if any((d/'cursor.json').exists() for d in old.glob('extend-eight43-bulk-*')):raise ValueError('historical bulk results require explicit exclusion audit')
    if len({tuple(r[:3]) for r in rows})!=len(rows):raise ValueError('duplicate pending source/mask')
    queues={s:deque(sorted((r for r in rows if r[0]==s),key=lambda r:(r[7],sum(r[3:6]),r[3:6],r[2],r[1]))) for s in range(4)};ordered=[]
    while any(queues.values()):
        for s in range(4):
            if queues[s]:ordered.append(queues[s].popleft())
    out.mkdir(parents=True,exist_ok=False)
    for s in range(4):freeze(out/f'source-{s}.json',(parent/f'source-{s}.json').read_bytes())
    small=old/'local-ten43-ready-v3'
    for name in ['small-source.json','small-core.json','small-plan.json']:freeze(out/name,(small/name).read_bytes())
    chunks=[]
    for start in range(0,len(ordered),chunk_size):
        selected=ordered[start:start+chunk_size];name=f'catalogs/{start//chunk_size:03d}.json.gz'
        freeze(out/name,gzip.compress(json.dumps(selected,separators=(',',':')).encode(),compresslevel=1,mtime=0))
        chunks.append(dict(id=f'{start//chunk_size:03d}',count=len(selected),catalog=name,catalog_sha256=sha(out/name),rows_sha256=digest(selected),source_counts=dict(Counter(r[0] for r in selected))))
    plan=dict(version=1,family=dict(name=family,local_products=10 if local10 else 8,target_products=9 if local10 else 7,mode_rank=8 if local10 else 6,max_vectors=255 if local10 else 63),
        pending_cases=len(ordered),prior_exact_negative_exclusions=len(exclusions),chunks=chunks,sources={str(s):dict(sha256=sha(out/f'source-{s}.json')) for s in range(4)},
        row_schema='source lo hi shape0 shape1 shape2 freeaxis ambient_pairpointdomain provenance_ordinal',
        ordering='Round robin sources; within source pair domain, shape, mask. No previous closed union family.',parent=str(parent),parent_manifest_file=parent_manifest,parent_manifest_sha256=sha(parent/parent_manifest),
        deadline_utc=DEADLINE,decoder='compact_rank2_edges43.solve_core',decoder_sha256=sha(ROOT/'mmsearch/compact_rank2_edges43.py'),
        storage=dict(per_chunk_logical_bytes=128*1024**2,full_core_policy='Current UNKNOWN and winner only',negative_policy='Compact rank census and full-result digest; deterministic source/mask replay'),
        scope='Only explicit source/mask fixed-outside residuals; necessary-survivor status is not existence evidence. UNKNOWN stays open.')
    freeze(out/'plan.json',plan);freeze(out/'EXCLUSIONS.json',exclusions)
    # Freeze Python source dependencies; no source decoding or N5 queries here.
    for path in (ROOT/'mmsearch').glob('*.py'):freeze(out/'runtime/mmsearch'/path.name,path.read_bytes())
    for name in ['__init__.py','verify_record42_independent.py','marathon7_local_campaign.py']:
        path=ROOT/'scripts'/name
        freeze(out/'runtime/scripts'/name,path.read_bytes() if path.exists() else b'')
    freeze(out/'runtime/marathon7_local_campaign.py',(ROOT/'scripts/marathon7_local_campaign.py').read_bytes())
    freeze(out/'runtime/tests/__init__.py',b'')
    freeze(out/'runtime/tests/test_marathon7_local.py',(ROOT/'tests/test_marathon7_local.py').read_bytes())
    freeze(out/'marathon7_local_prepare.py',Path(__file__).read_bytes())
    # One lazy historical core rebuild per source, without a decoder call.
    controls=[];cache=SourceCache(out)
    selection=select_plan(out,chunks[0]['id'])
    for case in selection['cases'][:4]:
        source,data,checked,source_sha,core_sha,input_sha=cache.core(case)
        controls.append(dict(case=case['id'],source_id=case['source_id'],source_sha256=source_sha,core_sha256=core_sha,input_sha256=input_sha,full_source_entries=checked['exact_entries_checked'],decoder_calls=0))
    freeze(out/'LAZY-CONTROLS.json',controls)
    freeze(out/'launch-manifest.json',dict(files={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}))
    jobs=[]
    for chunk in chunks:
        identity=f'marathon7-local-{family}-{chunk["id"]}';command=['python3','-B',str(out/'runtime/marathon7_local_campaign.py'),'--bundle',str(out),'--output-dir',str(out.parent/identity),'--chunk-id',chunk['id'],
            '--seconds','300','--per-case-seconds','2','--memory-mb','1024','--deadline-utc',DEADLINE,'--guard-state',str(out.parent/'operations-v3/state.json')]
        job=dict(id=identity,enabled=False,cpu=2,memory_mb=1024,seconds=330,command=command)
        validate_job(job)  # The queue process supplies nice10; schema has six keys.
        name=f'jobs/{chunk["id"]}.json';freeze(out/name,job);jobs.append(dict(chunk=chunk['id'],cases=chunk['count'],file=name,sha256=sha(out/name),resume_command=command+['--resume']))
    freeze(out/'JOB-INDEX.json',jobs);freeze(out/'PROPOSED-JOB.json',read(out/jobs[0]['file']))
    freeze(out/'READY.json',dict(status='PREPARED_DISABLED_PENDING_ROOT_AND_INDEPENDENT_QA',family=family,pending_cases=len(ordered),chunks=len(chunks),chunk_size=chunk_size,prior_exact_negatives_excluded=len(exclusions),
        launch_manifest_sha256=sha(out/'launch-manifest.json'),decoder_sha256=plan['decoder_sha256'],production_decoder_queries=0,full_per_case_cores_written=0,deadline_utc=DEADLINE))
    freeze(out/'manifest.json',dict(files={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}))
    return read(out/'READY.json')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--old-campaign',type=Path,required=True);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--family',choices=['local10','extension8'],required=True);p.add_argument('--chunk-size',type=int,default=500);p.add_argument('--version',type=int,default=2);a=p.parse_args()
    if not 1<=a.chunk_size<=500:p.error('chunk-size must be1..500')
    if a.version<2:p.error('preserve frozen v1; use version2 or newer')
    out=a.campaign.resolve()/f'marathon7-local-{a.family}-ready-v{a.version}'
    print(json.dumps(prepare(a.old_campaign.resolve(),out,a.family,a.chunk_size),sort_keys=True))


if __name__=='__main__':main()
