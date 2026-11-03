#!/usr/bin/env python3
"""Freeze a guard-only local runtime overlay and reuse exact negative evidence."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import freeze,read,sha
from scripts.phase_coordinator42_v2 import validate_job
from mmsearch.marathon7_local import select_plan,restore_journal
from mmsearch.recombine import digest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--old-bundle',type=Path,required=True);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--cache-review',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--generation',type=int,default=4);p.add_argument('--poller-review',type=Path);p.add_argument('--prepare-jobs',type=int);a=p.parse_args()
    if a.generation<4:p.error('preserve frozen v3; new overlays use generation4 or later')
    old=a.old_bundle.resolve();campaign=a.campaign.resolve();out=a.output_dir.resolve();review=read(a.cache_review);guard=ROOT/'mmsearch/marathon7_cached_guard.py'
    if review.get('status')!='PASS' or review.get('module_sha256')!=sha(guard):raise ValueError('cached guard independent QA missing or wrong version')
    if a.generation>=5:
        if a.poller_review is None:raise ValueError('generation5 requires independent inner-poller QA')
        pollreview=read(a.poller_review)
        if pollreview.get('status')!='PASS' or pollreview.get('module_sha256',pollreview.get('poller_sha256'))!=sha(ROOT/'mmsearch/marathon7_cancel_poller.py') or pollreview.get('runner_sha256')!=sha(ROOT/'scripts/marathon7_local_campaign_v5.py'):raise ValueError('inner poller or exact runner review differs')
    for name,expected in read(old/'manifest.json')['files'].items():
        path=(old/name).resolve()
        if not path.is_relative_to(old) or sha(path)!=expected:raise ValueError('frozen old bundle changed')
    plan=read(old/'plan.json');closed={};inputs=[];openprior=[]
    for prior in sorted(campaign.glob('marathon7-local-local10-*')):
        if not (prior/'cursor.json').exists():continue
        config=read(prior/'config.json')
        if config['launch_manifest_sha256']!=sha(old/'launch-manifest.json'):continue
        selection=select_plan(old,config['chunk_id']);cases=selection['cases']
        if config['selected_plan_sha256']!=selection['selected_sha256'] or config['catalog_plan_sha256']!=selection['catalog_plan_sha256'] or config['small_control'] or config['controls_only']:raise ValueError('historical selected query scope changed')
        configsha=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest();state=read(prior/'cursor.json');records,chain=restore_journal(prior,cases,configsha)
        if state['next_case']!=len(records) or state['results']!=records or state['config_sha256']!=configsha or state['result_chain_sha256']!=chain:raise ValueError('historical cursor/journal differs')
        pinned=dict(directory=str(prior),config_sha256=sha(prior/'config.json'),cursor_sha256=sha(prior/'cursor.json'),journal_sha256=sha(prior/'completed.jsonl'),result_chain_sha256=chain,completed=len(records));inputs.append(pinned)
        for index,entry in enumerate(records):
            case=cases[index];resultfile=prior/entry['result_file'];result=read(resultfile);key=(case['source_id'],case['mask_lo'],case['mask_hi'])
            if key in closed or result['status']!='LOCAL_UNSAT' or result.get('complete') is not True or result.get('after_cutoff') or result['source_sha256']!=case['source_sha256'] or result['shape']!=case['shape'] or result['axis']!=case['free_axis'] or result['target_rank']!=8 or result['budget']!=9:raise ValueError('historical negative source/mask/model mismatch')
            if result['span_vectors']!=255 or result['enumerated_vectors']!=255 or result.get('bucket_span_max',result['inside_rank'])>=8:raise ValueError('historical edge negative incomplete')
            closed[key]=dict(source_id=key[0],mask_lo=key[1],mask_hi=key[2],case=case['id'],source_sha256=case['source_sha256'],core_math_sha256=result['core_math_sha256'],core_input_sha256=result['core_input_sha256'],
                result_file=str(resultfile),result_sha256=entry['result_sha256'],config_sha256=configsha,proof_chain_sha256=chain,status='REUSED_IDENTICAL_SOURCE_MASK_EXACT_NEGATIVE')
        if state.get('pending_unknown'):
            pending=state['pending_unknown'];path=prior/pending['result_file']
            if sha(path)!=pending['result_sha256'] or read(path)['status']!='UNKNOWN':raise ValueError('prior UNKNOWN changed')
            openprior.append(dict(directory=str(prior),pending=pending,case=cases[len(records)],status='OPEN_UNKNOWN_NOT_EXCLUDED'))
    rows=[]
    for chunk in plan['chunks']:
        path=old/chunk['catalog']
        if sha(path)!=chunk['catalog_sha256']:raise ValueError('historical catalogue changed')
        selected=json.loads(gzip.decompress(path.read_bytes()))
        if digest(selected)!=chunk['rows_sha256'] or len(selected)!=chunk['count']:raise ValueError('historical chunk changed')
        rows.extend(selected)
    keys={tuple(row[:3]) for row in rows}
    if len(keys)!=len(rows) or not set(closed)<=keys:raise ValueError('closure scope outside old source/mask family')
    pending=[row for row in rows if tuple(row[:3]) not in closed]
    # A concurrent old cursor update requires a new consistent snapshot.
    for item in inputs:
        prior=Path(item['directory'])
        if sha(prior/'cursor.json')!=item['cursor_sha256'] or sha(prior/'completed.jsonl')!=item['journal_sha256']:raise ValueError('old completion evidence changed during overlay prep')
    out.mkdir(parents=True,exist_ok=False)
    for name in ['small-source.json','small-core.json','small-plan.json','EXCLUSIONS.json','LAZY-CONTROLS.json']:
        if (old/name).exists():freeze(out/name,(old/name).read_bytes())
    for s in range(4):freeze(out/f'source-{s}.json',(old/f'source-{s}.json').read_bytes())
    chunks=[]
    for start in range(0,len(pending),500):
        selected=pending[start:start+500];name=f'catalogs/{start//500:03d}.json.gz';freeze(out/name,gzip.compress(json.dumps(selected,separators=(',',':')).encode(),compresslevel=1,mtime=0))
        chunks.append(dict(id=f'{start//500:03d}',count=len(selected),catalog=name,catalog_sha256=sha(out/name),rows_sha256=digest(selected)))
    inherited=plan.get('inherited_campaign_exact_negatives_reused',0)+plan.get('campaign_exact_negatives_reused',0)
    updated=dict(plan,chunks=chunks,pending_cases=len(pending),campaign_exact_negatives_reused=len(closed),inherited_campaign_exact_negatives_reused=inherited,previous_bundle=str(old),previous_bundle_manifest_sha256=sha(old/'manifest.json'),
        ordering='Old frozen row order with only source/mask-identical exact completed negatives removed; prior UNKNOWN masks remain open.',guard_sha256=sha(guard),cached_guard_review_sha256=sha(a.cache_review))
    if a.generation>=5:updated.update(inner_cancel_poll_interval_seconds=.05,inner_cancel_poller_sha256=sha(ROOT/'mmsearch/marathon7_cancel_poller.py'),inner_cancel_poller_review_sha256=sha(a.poller_review))
    freeze(out/'plan.json',updated);freeze(out/'CLOSED-NEGATIVES.json.gz',gzip.compress(json.dumps(list(closed.values()),separators=(',',':')).encode(),compresslevel=1,mtime=0));freeze(out/'CLOSURE-INPUTS.json',inputs);freeze(out/'OPEN-PRIOR.json',openprior)
    changes=[]
    for path in (old/'runtime').rglob('*.py'):
        content=path.read_bytes();relative=path.relative_to(old/'runtime')
        if str(relative) in ['mmsearch/marathon7_cached_guard.py','tests/test_marathon7_cached_guard.py','scripts/marathon7_local_cached_guard_review.py']:
            replacement=guard if str(relative)=='mmsearch/marathon7_cached_guard.py' else ROOT/str(relative)
            changes.append(dict(path=str(relative),old_sha256=sha(path),new_sha256=sha(replacement),change='Guard implementation or its synthetic controls only'))
            continue
        if str(relative) in ['marathon7_local_campaign.py','scripts/marathon7_local_campaign.py']:
            original=b'from mmsearch.marathon7_local import CampaignGuard,CampaignHold';replacement=b'from mmsearch.marathon7_cached_guard import CampaignGuard,CampaignHold'
            if content.count(original)==1:
                content=content.replace(original,replacement);changes.append(dict(path=str(relative),old_sha256=sha(path),new_sha256=hashlib.sha256(content).hexdigest(),change='Guard import only'))
            elif content.count(replacement)!=1:raise ValueError('expected one direct cached guard import in frozen runner')
            if a.generation>=5:
                original=b' case_deadline=None\n def cancelled():return guard.reason() is not None or (case_deadline is not None and time.monotonic()>=case_deadline)'
                replacement=b' case_deadline=None\n inner_poller=CancelPoller(guard,lambda:case_deadline)\n def cancelled():return inner_poller.cancelled()'
                if content.count(original)!=1:raise ValueError('expected exact unchanged decoder cancellation callback')
                content=content.replace(original,replacement).replace(b'from mmsearch.marathon7_cached_guard import CampaignGuard,CampaignHold',b'from mmsearch.marathon7_cached_guard import CampaignGuard,CampaignHold\nfrom mmsearch.marathon7_cancel_poller import CancelPoller')
                content=content.replace(b'backend=a.backend,per_case_seconds=a.per_case_seconds,result_chain_sha256=chain,queries_this_invocation=query_count,',b'backend=a.backend,per_case_seconds=a.per_case_seconds,result_chain_sha256=chain,queries_this_invocation=query_count,inner_callback_polling=inner_poller.metrics(),')
                if content!=(ROOT/'scripts/marathon7_local_campaign_v5.py').read_bytes():raise ValueError('generated runner differs from reviewed v5 source')
                changes.append(dict(path=str(relative),old_sha256=sha(path),new_sha256=hashlib.sha256(content).hexdigest(),change='Inner cancelled predicate only plus poller import/summary metrics; forced barriers unchanged'))
        freeze(out/'runtime'/relative,content)
    freeze(out/'runtime/mmsearch/marathon7_cached_guard.py',guard.read_bytes());freeze(out/'runtime/tests/test_marathon7_cached_guard.py',(ROOT/'tests/test_marathon7_cached_guard.py').read_bytes())
    freeze(out/'runtime/scripts/marathon7_local_cached_guard_review.py',(ROOT/'scripts/marathon7_local_cached_guard_review.py').read_bytes())
    freeze(out/'CACHED-GUARD-INDEPENDENT-QA.json',a.cache_review.read_bytes());freeze(out/'GUARD-ONLY-DIFF.json',dict(changes=changes,all_existing_other_runtime_bytes_identical=True,rank2_decoder_sha256=sha(old/'runtime/mmsearch/compact_rank2_edges43.py'),guard_sha256=sha(guard)))
    if a.generation>=5:
        freeze(out/'POLLING-INDEPENDENT-QA.json',a.poller_review.read_bytes());freeze(out/'runtime/mmsearch/marathon7_cancel_poller.py',(ROOT/'mmsearch/marathon7_cancel_poller.py').read_bytes())
        freeze(out/'runtime/scripts/marathon7_local_campaign_v5.py',(ROOT/'scripts/marathon7_local_campaign_v5.py').read_bytes())
        for name in ['test_marathon7_cancel_poller.py','test_marathon7_poller_runner.py']:freeze(out/'runtime/tests'/name,(ROOT/'tests'/name).read_bytes())
    freeze(out/'marathon7_local_cached_overlay.py',Path(__file__).read_bytes())
    freeze(out/'launch-manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    jobs=[]
    prepared=chunks if a.prepare_jobs is None else chunks[:a.prepare_jobs]
    if not prepared:raise ValueError('atleastone bounded job required')
    for chunk in prepared:
        identity=f'marathon7-local-local10-v{a.generation}-{chunk["id"]}';job=dict(id=identity,enabled=False,cpu=2,memory_mb=1024,seconds=330,command=['python3','-B',str(out/'runtime/marathon7_local_campaign.py'),'--bundle',str(out),'--output-dir',str(campaign/identity),'--chunk-id',chunk['id'],'--seconds','300','--per-case-seconds','2','--memory-mb','1024','--deadline-utc','2026-11-03T19:24:17Z','--guard-state',str(campaign/'operations-v3/state.json')])
        validate_job(job);name=f'jobs/{chunk["id"]}.json';freeze(out/name,job);jobs.append(dict(chunk=chunk['id'],cases=chunk['count'],file=name,sha256=sha(out/name)))
    freeze(out/'JOB-INDEX.json',jobs);freeze(out/'PROPOSED-JOB.json',read(out/jobs[0]['file']))
    freeze(out/'READY.json',dict(status='GUARD_ONLY_OVERLAY_DISABLED_PENDING_ROOT_AND_QA',old_pending=len(rows),exact_negatives_reused=len(closed),inherited_exact_negatives_reused=inherited,total_campaign_exact_negatives_reused=inherited+len(closed),pending=len(pending),prior_unknowns_kept=len(openprior),chunks=len(chunks),prepared_jobs=len(jobs),decoder_queries=0,launch_manifest_sha256=sha(out/'launch-manifest.json')))
    freeze(out/'manifest.json',dict(files={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}))
    print(json.dumps(dict(status='GUARD_ONLY_OVERLAY_DISABLED_PENDING_ROOT_AND_QA',exact_negatives_reused=len(closed),pending=len(pending),chunks=len(chunks),decoder_queries=0,manifest_sha256=sha(out/'manifest.json'),proposal_sha256=sha(out/'PROPOSED-JOB.json'))))


if __name__=='__main__':main()
