"""Read-only completed-scope audit and unlaunched round-robin chunk templates."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import statistics


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def freeze(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    raw=value if isinstance(value,bytes) else (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    with path.open('xb') as stream:stream.write(raw)
    path.chmod(0o444)


def verify_prefix(state):
    prefix=state['completed_prefix'];chain=digest([state['input_sha256'],state['branch_catalog_sha256']])
    if state['next_branch']!=len(prefix):raise ValueError('nested prefix count mismatch')
    for i,record in enumerate(prefix):
        if record['branch']!=i or not record['child_status'].startswith('NO_WEIGHT_LE'):raise ValueError('nested prefix not contiguous negative')
        chain=digest([chain,record])
    if chain!=state['prefix_chain_sha256']:raise ValueError('nested prefix chain mismatch')
    if state.get('active_child') is not None:raise ValueError('completed negative retains an unresolved child')
    if state.get('lower_cursor') is not None:verify_prefix(state['lower_cursor'])


def prepared_bundle(b):
    bindings=read(b/'integrity.json')
    for name,expected in bindings.items():
        if sha(b/name)!=expected:raise ValueError('prepared source/code binding mismatch: '+name)
    plan=read(b/'plan.json');items={}
    for chunk in plan['chunks']:
        raw=(b/chunk['plan']).read_bytes();rows=json.loads(gzip.decompress(raw))
        if hashlib.sha256(raw).hexdigest()!=chunk['compressed_sha256'] or digest(rows)!=chunk['plan_sha256'] or len(rows)!=chunk['count']:
            raise ValueError('chunk plan binding mismatch')
        items[chunk['id']]=rows
    return plan,items,bindings


def audit_completed(b,output,expected_count,code_file):
    plan,items,bindings=prepared_bundle(b);config=read(output/'config.json');report=read(output/'report-launch000.json')
    if config['prepared_integrity_sha256']!=sha(b/'integrity.json') or config['plan_sha256']!=digest(plan):raise ValueError('completed config source mismatch')
    if report['config_sha256']!=digest(config) or report['status']!='SELECTED_CHUNKS_COMPLETE' or report['target_queries_this_launch']!=expected_count or report['reason'] is not None:
        raise ValueError('completion report missing/partial')
    if report['terminal_counts']!={'NO_ONE_SUBSPACE_GAIN':expected_count}:raise ValueError('completed report contains nonnegative/unknown/error')
    selected=[c for c in plan['chunks'] if c['id'] in config['chunk_ids']]
    if [c['id'] for c in selected]!=config['chunk_ids']:raise ValueError('unknown/reordered completed chunk')
    identities=set();summaries=[];case_results=[];all_kinds=Counter()
    for chunk in selected:
        directory=output/'chunks'/chunk['id'];chain=digest([digest(config),chunk]);events=[];kinds=Counter();branches=0
        raw=(directory/'results.jsonl').read_bytes()
        if not raw.endswith(b'\n'):raise ValueError('incomplete completed journal')
        for i,line in enumerate(raw.splitlines()):
            event=json.loads(line)
            if event['previous_sha256']!=chain or event['sha256']!=digest({k:v for k,v in event.items() if k!='sha256'}):raise ValueError('result chain mismatch')
            chain=event['sha256'];value=event['value'];result=value['result'];case=items[chunk['id']][i]
            if value['index']!=i or value['case']!=case or value['source_id']!=chunk['source_id'] or value['source_system_sha256']!=plan['sources'][chunk['source_id']]['system_sha256']:
                raise ValueError('completed case source/identity mismatch')
            if value['decoder_code_sha256']!=bindings[code_file] or result['status']!='NO_ONE_SUBSPACE_GAIN' or not result.get('complete_for_requested_bound') or result['searched_bound']!=case['weight_bound']:
                raise ValueError('not an exact bound-complete negative')
            if result['quotient_sha256']!=value['quotient_sha256'] or not result['worker_reaped'] or result['worker_exitcode']!=0:raise ValueError('worker/quotient result invalid')
            archive=directory/value['branch_ledger'];compressed=archive.read_bytes();branchraw=gzip.decompress(compressed)
            if hashlib.sha256(compressed).hexdigest()!=value['branch_ledger_sha256'] or hashlib.sha256(branchraw).hexdigest()!=value['branch_ledger_uncompressed_sha256']:
                raise ValueError('negative branch archive hash mismatch')
            records=branchraw.splitlines();last=None;branchchain=None
            if len(records)!=value['branch_records']:raise ValueError('branch count mismatch')
            for j,branchline in enumerate(records):
                branch=json.loads(branchline);record=branch['record'];state=branch['cursor']
                if branch['quotient_sha256']!=value['quotient_sha256'] or record['branch']!=j or state['next_branch']!=j+1 or not record['child_status'].startswith('NO_WEIGHT_LE'):
                    raise ValueError('branch identity/negative mismatch')
                if last is None:branchchain=digest([state['input_sha256'],state['branch_catalog_sha256']])
                elif any(state[k]!=last[k] for k in ('version','input_sha256','branch_catalog_sha256')):raise ValueError('branch binding changed')
                branchchain=digest([branchchain,record])
                if branchchain!=state['prefix_chain_sha256']:raise ValueError('branch chain mismatch')
                last=state;kinds[record['kind']]+=1
            state=result.get('cursor')
            if state is not None:
                if state['next_branch']!=len(records):raise ValueError('result cursor count mismatch')
                expected=branchchain if records else digest([state['input_sha256'],state['branch_catalog_sha256']])
                if state['prefix_chain_sha256']!=expected:raise ValueError('result cursor chain mismatch')
                if state.get('active_child') is not None:raise ValueError('negative has unresolved child')
                if state.get('lower_cursor') is not None:verify_prefix(state['lower_cursor'])
            identity=(chunk['source_id'],tuple(case['space']))
            if identity in identities:raise ValueError('repeated completed case')
            identities.add(identity);events.append(value);case_results.append((chunk['source_id'],result));branches+=len(records)
        cursor=read(directory/'cursor.json');reported=next(c for c in report['chunks'] if c['id']==chunk['id'])
        if len(events)!=chunk['count'] or cursor['next_index']!=len(events) or cursor['result_chain_sha256']!=chain or not reported['complete'] or reported['result_chain_sha256']!=chain:
            raise ValueError('chunk completion/cursor mismatch')
        if (directory/'current').exists():raise ValueError('completed negative chunk retained current partial')
        summaries.append(dict(id=chunk['id'],source_id=chunk['source_id'],cases=len(events),plan_sha256=chunk['plan_sha256'],result_chain_sha256=chain,
            journal_sha256=hashlib.sha256(raw).hexdigest(),branch_records=branches,branch_kind_counts=dict(kinds),reported_bytes=reported['bytes']))
        all_kinds.update(kinds)
    if len(identities)!=expected_count:raise ValueError('completed identity count mismatch')
    stats={}
    for source in sorted({s for s,r in case_results}):
        results=[r for s,r in case_results if s==source];elapsed=[r['elapsed_seconds'] for r in results]
        stats[source]=dict(cases=len(results),worker_elapsed_sum_seconds=sum(elapsed),worker_elapsed_max_seconds=max(elapsed),worker_elapsed_mean_seconds=statistics.mean(elapsed),
            worker_cpu_seconds=sum(r['worker_stats']['user_seconds']+r['worker_stats']['system_seconds'] for r in results),
            worker_max_rss_kib=max(r['worker_stats']['max_rss_kib'] for r in results))
    evidence=dict(status='EXACT_FINITE_COMPLETION_VERIFIED',prepared_dir=str(b),output_dir=str(output),prepared_integrity_sha256=sha(b/'integrity.json'),
        config_sha256=sha(output/'config.json'),report_sha256=sha(output/'report-launch000.json'),exact_cases=expected_count,
        report=report,chunks=summaries,per_source_stats=stats,total_branch_kind_counts=dict(all_kinds),target_queries_during_audit=0)
    return evidence,identities,plan,items


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared-dir',type=Path,required=True);p.add_argument('--completed-dir',type=Path,required=True)
    p.add_argument('--budget6-prepared-dir',type=Path,required=True);p.add_argument('--budget6-completed-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();b=a.prepared_dir.resolve();completed=a.completed_dir.resolve();out=a.output_dir.resolve()
    first,closed,plan,items=audit_completed(b,completed,6000,'code/mmsearch/observed_rank3_lazy42.py')
    budget6,b6closed,_,_=audit_completed(a.budget6_prepared_dir.resolve(),a.budget6_completed_dir.resolve(),46,'code/mmsearch/observed_budget642.py')
    job_result=a.budget6_completed_dir.parent/(a.budget6_completed_dir.name+'-job.result.json')
    launch=read(job_result)
    if launch['exit_code']!=0 or launch['timed_out'] or launch['interrupted']:raise ValueError('budget6 lifecycle did not complete cleanly')
    budget6['launcher_result']=launch;budget6['launcher_result_sha256']=sha(job_result)
    budget6['resource_outcome']=dict(complete=46,unknown=0,time_holds=0,storage_holds=0,cpu_limit_holds=0,errors=0,
        launcher_wall_seconds=launch['elapsed_seconds'],launcher_cpu_seconds=launch['cpu_seconds'],launcher_max_rss_kib=launch['max_rss_kib'])
    exclusions=read(b/'pilot-exclusions.json');pilot={(e['case']['source_id'],tuple(e['case']['space'])) for e in exclusions}
    if len(pilot)!=18 or pilot&closed or pilot&b6closed or closed&b6closed:raise ValueError('closed scope overlap')
    all_pending=set();remaining=[];completed_ids={c['id'] for c in first['chunks']}
    for chunk in plan['chunks']:
        identities={(chunk['source_id'],tuple(case['space'])) for case in items[chunk['id']]}
        if len(identities)!=chunk['count'] or identities&all_pending or identities&pilot or identities&b6closed:raise ValueError('plan/pilot/other-budget overlap')
        all_pending|=identities
        if chunk['id'] not in completed_ids:
            if identities&closed:raise ValueError('remaining chunk overlaps completed6000')
            remaining.append(chunk)
    if len(remaining)!=23 or sum(c['count'] for c in remaining)!=41722 or all_pending-closed!={(c['source_id'],tuple(i['space'])) for c in remaining for i in items[c['id']]}:
        raise ValueError('remaining scope mismatch')
    sources=sorted(plan['sources']);by_source={s:sorted([c for c in remaining if c['source_id']==s],key=lambda c:c['source_offset']) for s in sources}
    rounds=[]
    while any(by_source.values()):rounds.append([by_source[s].pop(0) for s in sources if by_source[s]])
    out.mkdir(parents=True,exist_ok=False);freeze(out/'code'/Path(__file__).name,Path(__file__).read_bytes());freeze(out/'completed6000-audit.json',first);freeze(out/'budget6-result-audit.json',budget6)
    jobs=[];jobscope=set()
    for number,chunks in enumerate(rounds,1):
        identity='observed-rank3-remaining-'+f'{number:03d}';output=b.parent/identity
        if output.exists():raise ValueError('proposed fresh output already exists: '+str(output))
        command=['python3','-B',str(b/'code/scripts/campaign_observed_rank3_lazy42.py'),'--prepared-dir',str(b),'--output-dir',str(output),
            '--seconds','840','--per-case-seconds','20','--memory-mb','1024','--guard-state',str(b.parent/'operations-v3/state.json')]
        for chunk in chunks:command.extend(['--chunk-id',chunk['id']])
        job=dict(id=identity,enabled=False,cpu=1,memory_mb=1024,seconds=900,command=command);name='jobs/'+f'{number:03d}.json';freeze(out/name,job)
        identities=sorted((c['source_id'],case['space']) for c in chunks for case in items[c['id']])
        for source,space in identities:
            key=(source,tuple(space))
            if key in jobscope:raise ValueError('duplicate future job identity')
            jobscope.add(key)
        jobs.append(dict(sequence=number,id=identity,template=name,template_sha256=sha(out/name),fresh_output_dir=str(output),chunks=chunks,cases=len(identities),identity_sha256=digest(identities),
            resume_command=command+['--restart']))
    if len(jobscope)!=41722 or jobscope&closed or jobscope&pilot or jobscope&b6closed:raise ValueError('job scope overlap/missing')
    ledger=dict(status='UNLAUNCHED_TEMPLATES_READY',jobs=jobs,job_count=len(jobs),remaining_chunks=23,remaining_cases=41722,
        source_remaining={s:sum(c['count'] for c in remaining if c['source_id']==s) for s in sources},
        original_prepared_dir=str(b),original_integrity_sha256=sha(b/'integrity.json'),original_plan_sha256=sha(b/'plan.json'),
        runner_sha256=sha(b/'code/scripts/campaign_observed_rank3_lazy42.py'),runtime_sha256=sha(b/'code/mmsearch/observed_rank3_lazy42.py'),
        source_bindings=plan['sources'],pilot18_exclusions_sha256=sha(b/'pilot-exclusions.json'),completed6000_audit_sha256=sha(out/'completed6000-audit.json'),budget6_audit_sha256=sha(out/'budget6-result-audit.json'),
        cumulative_observed_spaces=dict(cheap_k3_rank_bound=263002,exact_pilot18=18,exact_first_continuation=6000,exact_budget6=46,exact_total_with_cheap_bound=269066,pending=41722,original_catalogued=310788),
        scheduling='Root launches one job at a time and may interleave strategies. At most one next chunk per available source per job. A new job has a fresh output directory. Resume UNKNOWN with exactly its same job command plus --restart; do not advance an unfinished chunk as negative.',
        coverage='Only explicit observed3D palettes on the frozen sources; no all-image-rank3 or unrestricted rank nonexistence claim.',target_queries_during_preparation=0,queue_edits=0)
    freeze(out/'coverage-ledger.json',ledger)
    freeze(out/'README.md',b'''# Unlaunched remaining observed-rank3 chunk jobs

The ten disabled job templates cover all23 remaining chunks/41,722 cases, with no overlap with the exact first6000, pilot18 or46 budget6 cases. Each job takes at most one next chunk from each available source in AE/diverse/new order, preserving each source's frozen k6/k5/k4 and lexicographic order. As a source finishes, later jobs contain fewer chunks. Every job uses a fresh output directory. No search or queue edit was performed during preparation.

Root schedules one template at a time, interleaved with other strategies. Each requests CPU1,1024MiB,900wall seconds,840internal seconds and20seconds per case. A complete finite negative allows root to review/schedule the next template. UNKNOWN leaves work open: resume exactly the same command with --restart and unchanged prepared/code/chunk bindings. ERROR pauses for review. A verified winner stops campaign target work. Templates must not be combined into the same output directory because chunk selection is part of that directory's immutable config.

coverage-ledger.json binds sources, original immutable code/plan, all chunk plans and job templates. It records exact nonoverlap and cumulative finite scope. completed6000-audit.json independently checks source/case/code bindings, result chains, compressed branch hashes, branch chains and terminal statuses. budget6-result-audit.json performs the same46case audit and records wall/CPU/memory and zeroUNKNOWN/time/storage/CPUholds. No quotient was regenerated or decoder called by these audits. Full quotients remain lazy in the existing runtime; its fresh5GiB guard and128MiB per-chunk logical-byte cap remain mandatory.

Only the explicit catalogued observed spaces can close. No unrestricted rank or all-image-rank3 conclusion follows from completion of these jobs.
''')
    manifest={str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()};freeze(out/'manifest.json',manifest)
    print(json.dumps(dict(status='READY',job_count=len(jobs),remaining_chunks=23,remaining_cases=41722,job_case_counts=[j['cases'] for j in jobs],manifest_sha256=sha(out/'manifest.json'),budget6_complete=46,target_queries=0),sort_keys=True))


if __name__=='__main__':main()
