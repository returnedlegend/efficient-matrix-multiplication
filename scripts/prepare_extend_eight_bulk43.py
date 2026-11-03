"""Query-free lazy bulk metadata for fresh extension8 survivors minus pilot12."""
import argparse
from collections import Counter,deque
import gzip
import json
from pathlib import Path
import resource
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,sha,read
from mmsearch.recombine import digest
from mmsearch.extend_eight_bulk43 import SourceCache,compact_negative


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',type=Path,required=True);p.add_argument('--pilot-output',type=Path,required=True)
    p.add_argument('--pilot-audit',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--chunk-size',type=int,default=256);a=p.parse_args()
    if not 1<=a.chunk_size<=512:p.error('chunk size1..512 required')
    resource.setrlimit(resource.RLIMIT_AS,(1024*1024**2,1024*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(25,26))
    parent=a.parent.resolve();pilot=a.pilot_output.resolve();audit=a.pilot_audit.resolve();out=a.output_dir.resolve()
    for name,expected in read(parent/'manifest.json')['files'].items():
        if sha(parent/name)!=expected:raise ValueError('parent release changed: '+name)
    review=read(audit/'REPORT.json');summary=read(pilot/'summary.json');state=read(pilot/'cursor.json');config=read(pilot/'config.json')
    cases=read(parent/'plan.json')['cases']
    if review['bundle_full_manifest_sha256']!=sha(parent/'manifest.json') or not review['all_complete'] or not review['no_cutoff_UNKNOWN_ERROR'] or review['new_decoder_calls']!=0:
        raise ValueError('independent pilot result audit missing')
    if review['config_sha256']!=sha(pilot/'config.json') or review['cursor_sha256']!=sha(pilot/'cursor.json') or config['launch_manifest_sha256']!=sha(parent/'launch-manifest.json'):
        raise ValueError('independent pilot/source pins changed')
    if summary['status']!='LOCAL_PORTFOLIO_UNSAT' or summary['queries_this_invocation']!=12 or len(summary['results'])!=12 or state['next_case']!=12 or not state['terminal']:
        raise ValueError('pilot incomplete')
    exclusions=[];excluded=set()
    for index,(case,entry) in enumerate(zip(cases,summary['results'])):
        file=pilot/entry['result_file'];result=read(file)
        if entry!=state['results'][index] or entry['case']!=case['id'] or entry['status']!='LOCAL_UNSAT' or sha(file)!=entry['result_sha256'] or result['status']!='LOCAL_UNSAT' or result.get('complete') is not True:
            raise ValueError('pilot negative result not exact/matching')
        if result['core_sha256']!=case['core_sha256'] or result['shape']!=case['shape'] or result['axis']!=case['free_axis'] or result['target']!=7 or result['mode_rank']!=6 or result['all_nonzero_pair_points']!=case['all_pair_points']:
            raise ValueError('pilot result source/core/scope differs')
        compact_negative(result)
        proof=next(r for r in review['records'] if r['id']==case['id'])
        if proof['result_sha256']!=sha(file) or proof['source_sha256']!=case['source_sha256'] or proof['source_mask_indices']!=case['source_indices']:raise ValueError('pilot audit case binding differs')
        mask=sum(1<<i for i in case['source_indices']);key=(case['source_id'],mask&((1<<64)-1),mask>>64)
        if key in excluded:raise ValueError('duplicate pilot exclusion')
        excluded.add(key);exclusions.append(dict(source_id=key[0],mask_lo=key[1],mask_hi=key[2],case=case,prior_result_file=str(file),prior_result_sha256=sha(file),
            status='REUSED_EXACT_LOCAL_UNSAT_AFTER_INDEPENDENT_RESULT_AUDIT',audit_report_sha256=sha(audit/'REPORT.json'),proof_scope=review['proof_scope']))
    rows=[list(map(int,line.split())) for line in gzip.decompress((parent/'survivors.tsv.gz').read_bytes()).decode().splitlines()]
    if len(rows)!=5941 or len({tuple(r[:3]) for r in rows})!=5941 or not excluded<={tuple(r[:3]) for r in rows}:raise ValueError('parent survivor registry/exclusion mismatch')
    pending=[row for row in rows if tuple(row[:3]) not in excluded]
    if len(pending)!=5929:raise ValueError('remaining count differs')
    queues={s:deque(row for row in pending if row[0]==s) for s in range(4)};ordered=[]
    while any(queues.values()):
        for s in range(4):
            if queues[s]:ordered.append(queues[s].popleft())
    out.mkdir(parents=True,exist_ok=False)
    for s in range(4):freeze(out/f'source-{s}.json',(parent/f'source-{s}.json').read_bytes())
    for name in ['small-source.json','small-core.json','small-plan.json']:freeze(out/name,(parent/name).read_bytes())
    compressed=gzip.compress(json.dumps(ordered,separators=(',',':')).encode(),compresslevel=1,mtime=0);freeze(out/'catalog.json.gz',compressed)
    sources={str(s):dict(sha256=sha(out/f'source-{s}.json'),pending_cases=sum(r[0]==s for r in pending)) for s in range(4)}
    chunks=[]
    for start in range(0,len(ordered),a.chunk_size):
        selected=ordered[start:start+a.chunk_size];chunks.append(dict(id=f'{start//a.chunk_size:03d}',start=start,stop=start+len(selected),count=len(selected),rows_sha256=digest(selected),
            source_counts=dict(Counter(r[0] for r in selected)),domain_counts=dict(Counter(r[-1] for r in selected))))
    plan=dict(version=1,family=dict(source_products=93,local_products=8,target_products=7,mode_rank=6,point_cap=3969),catalog='catalog.json.gz',catalog_sha256=sha(out/'catalog.json.gz'),sources=sources,chunks=chunks,
        pending_cases=5929,pilot_exact_negatives_reused=12,parent_manifest_sha256=sha(parent/'manifest.json'),parent_survivor_catalog_sha256=sha(parent/'survivors.tsv.gz'),
        parent_source_mask_registry='Exact5941necessary-survivor source/mask set; remove only the12 audited identical-model pilot masks.',
        ordering='Round robin one next case per available source; preserve each source parent domain/shape/mask priority.',
        available_backends=['python'],native_backend=dict(enabled=False,reason='Pending Operations backend QA and a separately frozen binding; this release cannot select native.'),
        output=dict(full_cores='Only current UNKNOWN or winner',negative_records='Compact status/statistics/hash; replay from frozen source/mask/backend',phase_logical_cap_bytes=128*1024**2),
        scope='Explicit5929fresh masks only; no old6negative transfer or unrestricted/all-image rank conclusion.')
    freeze(out/'plan.json',plan);freeze(out/'PILOT12-EXCLUSIONS.json',exclusions)
    for path in audit.rglob('*'):
        if path.is_file():freeze(out/'independent-pilot-audit'/path.relative_to(audit),path.read_bytes())
    # Rebuild only the historical12known core inputs as a query-free lazy control.
    cache=SourceCache(out);controls=[]
    for case in cases:
        lazy=dict(case);lazy.pop('core');source,data,verified,source_sha,math_sha,input_sha=cache.core(lazy)
        expected=read(parent/case['core'])
        if math_sha!=case['core_sha256'] or any(data[k]!=expected[k] for k in data):raise ValueError('lazy historical core differs from frozen pilot')
        controls.append(dict(case=case['id'],source_sha256=source_sha,core_math_sha256=math_sha,core_input_sha256=input_sha,full_source_entries=verified['exact_entries_checked'],decoder_queries=0))
    freeze(out/'LAZY-PILOT-CONTROLS.json',controls)
    for path in (parent/'runtime').rglob('*.py'):freeze(out/'runtime'/path.relative_to(parent/'runtime'),path.read_bytes())
    freeze(out/'runtime/mmsearch/extend_eight_bulk43.py',(ROOT/'mmsearch/extend_eight_bulk43.py').read_bytes())
    freeze(out/'runtime/campaign_extend_eight_bulk43.py',(ROOT/'scripts/campaign_extend_eight_bulk43.py').read_bytes())
    freeze(out/'runtime/scripts/campaign_extend_eight_bulk43.py',(ROOT/'scripts/campaign_extend_eight_bulk43.py').read_bytes())
    freeze(out/'prepare_extend_eight_bulk43.py',Path(__file__).read_bytes())
    tests=ROOT/'tests/test_extend_eight_bulk43.py'
    if tests.exists():freeze(out/'runtime/tests/test_extend_eight_bulk43.py',tests.read_bytes())
    freeze(out/'launch-manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    jobs=[]
    for chunk in chunks:
        identity='extend-eight43-bulk-'+chunk['id'];command=['python3','-B',str(out/'runtime/campaign_extend_eight_bulk43.py'),'--bundle',str(out),'--output-dir',str(out.parent/identity),
            '--chunk-id',chunk['id'],'--backend','python','--seconds','240','--per-case-seconds','20','--memory-mb','1024','--deadline-utc','2026-11-04T21:31:16Z','--guard-state',str(out.parent/'operations-v3/state.json')]
        job=dict(id=identity,enabled=False,cpu=3,memory_mb=1024,seconds=300,command=command);name='jobs/'+chunk['id']+'.json';freeze(out/name,job)
        jobs.append(dict(chunk_id=chunk['id'],cases=chunk['count'],template=name,sha256=sha(out/name),fresh_output_dir=str(out.parent/identity),resume_command=command+['--resume']))
    freeze(out/'JOB-INDEX.json',jobs);freeze(out/'PROPOSED-JOB.json',read(out/jobs[0]['template']))
    freeze(out/'METRICS.json',dict(parent_cases=5941,exact_pilot_exclusions=12,pending_cases=5929,source_counts={s:sum(r[0]==s for r in pending) for s in range(4)},
        domain_counts=dict(Counter(r[-1] for r in pending)),chunks=len(chunks),chunk_size=a.chunk_size,full_percase_core_files_written=0,lazy_historical_controls=12,N5_decoder_queries=0,
        future10=dict(status='Consider after extension8pilot/bulk measurements; no10targetscope included',catalog_reference='../local-ten-lowrank-span43-ready-v1/survivors.tsv.gz',cases=111605,mode_rank=8,target9=True,point_cap=65025)))
    print(json.dumps(dict(status='LAZY_BULK_PREPARED',cases=5929,chunks=len(chunks),chunk_size=a.chunk_size,source_counts={s:sum(r[0]==s for r in pending) for s in range(4)},N5_decoder_queries=0)))


if __name__=='__main__':main()
