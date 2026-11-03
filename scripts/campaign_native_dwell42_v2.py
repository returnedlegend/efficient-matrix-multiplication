"""UNLAUNCHED bounded BFS32 pool harness; profile choice requires root review.

CPU2/768MiB, <=600s per native phase and <=900s total wrapper search window.
No resume or in-place rerun: every output directory is exclusive. Frozen pool
order selects one distinct source per phase; it does not promise all32 coverage.
"""
from __future__ import annotations
import argparse, datetime, json, math, os, pathlib, resource, signal, sys, time
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import campaign_native_dwell42 as base
from mmsearch.native_bridge import _read_terms,term_set_sha256

RUNTIME=[*base.RUNTIME,'scripts/campaign_native_dwell42_v2.py']

def runtime_hashes():return {name:base.sha((ROOT/name).read_bytes()) for name in RUNTIME}

def budgets(seconds,phase_seconds):
    if (not math.isfinite(seconds) or not math.isfinite(phase_seconds)
        or not 0<phase_seconds<=600 or not 0<seconds<=900):raise ValueError('0<total<=900 and0<phase<=600 required')
    count=math.ceil(seconds/phase_seconds)
    if count>32:raise ValueError('at most32 distinct pool sources per invocation')
    return [min(phase_seconds,seconds-i*phase_seconds) for i in range(count)]

def load_pool(path,expected_sha,declaration,declaration_sha):
    pool,raw=base.read(path)
    if base.sha(raw)!=expected_sha or pool.get('format')!='dwell42-bfs32-pool-v1':raise ValueError('frozen BFS32 pool binding differs')
    sources=pool.get('sources')
    if not isinstance(sources,list) or len(sources)!=32:raise ValueError('exactly32 frozen BFS sources required')
    result=[];identities=set();names=set()
    for item in sources:
        name=item['file']
        if not isinstance(name,str) or pathlib.Path(name).name!=name or not name.endswith('.json') or name in names:raise ValueError('pool filename differs')
        names.add(name);source=path.parent/'sources'/name
        if source.is_symlink() or source.parent.is_symlink() or not source.is_file():raise ValueError('pool symlink/nonfile forbidden')
        terms,metadata,source_raw=base.validate_input(source,item['sha256'],declaration,declaration_sha)
        if (metadata['term_set_sha256']!=item['term_hash']
            or metadata['source_term_hash']!=item['source_identity_sha256']
            or metadata['source_term_hash'] in identities):raise ValueError('pool canonical identity differs/duplicates')
        identities.add(metadata['source_term_hash']);result.append(dict(item=item,terms=terms,metadata=metadata,raw=source_raw))
    return pool,result,raw

def command(binary,input_path,prefix,*,seconds,seed,dwell):
    if not math.isfinite(seconds) or not 0<seconds<=600:raise ValueError('phase exceeds600s')
    # Reuse the reviewed V1 construction without weakening its public <=30s API.
    argv=base.command(binary,input_path,prefix,seconds=min(seconds,30),seed=seed,dwell=dwell)
    argv[argv.index('--seconds')+1]=str(seconds)
    return argv

def barrier(campaign,deadline,stopping=False):
    return (stopping or time.time()>=deadline or (campaign/'guard_stopped.json').exists()
            or (campaign/'WINNER.json').exists() or any(campaign.glob('*/WINNER.json')))

def main(argv=None):
    start=time.monotonic();p=argparse.ArgumentParser(description=__doc__)
    for name in ['campaign','pool','binary','heldout-declaration','output-dir']:p.add_argument('--'+name,type=pathlib.Path,required=True)
    for name in ['expected-pool-sha256','expected-binary-sha256','expected-heldout-sha256','expected-runtime-sha256']:p.add_argument('--'+name,required=True)
    p.add_argument('--seconds',type=float,default=900);p.add_argument('--phase-seconds',type=float,default=300)
    p.add_argument('--cpu',type=int,default=2);p.add_argument('--memory-mb',type=int,default=768);p.add_argument('--seed',type=int,required=True)
    p.add_argument('--reduction-dwell',type=int,choices=(0,64,32768),required=True);p.add_argument('--preview',action='store_true');a=p.parse_args(argv)
    if a.cpu!=2 or a.memory_mb!=768 or a.seed<0:p.error('CPU2/768MiB and nonnegative seed required')
    phase_budgets=budgets(a.seconds,a.phase_seconds);campaign=a.campaign.resolve();config,_=base.read(campaign/'campaign.json')
    if config.get('dimension')!=5 or config.get('field')!=2 or config.get('target_rank')!=92:raise ValueError('n5/F2 target92 campaign required')
    deadline=datetime.datetime.fromisoformat(config['deadline_utc'].replace('Z','+00:00')).timestamp()
    if barrier(campaign,deadline) or time.time()+a.seconds+15>deadline:raise ValueError('campaign stop/WINNER/deadline barrier')
    code=runtime_hashes();runtime_sha=base.sha(base.raw_json(code))
    if runtime_sha!=a.expected_runtime_sha256:raise ValueError('frozen runtime binding differs')
    pool,sources,pool_raw=load_pool(a.pool,a.expected_pool_sha256,a.heldout_declaration,a.expected_heldout_sha256)
    binary_raw=a.binary.read_bytes()
    if base.sha(binary_raw)!=a.expected_binary_sha256:raise ValueError('frozen binary binding differs')
    output=a.output_dir.resolve()
    if not output.is_relative_to(campaign) or output==campaign or output.exists():raise ValueError('output must be a NEW campaign subdirectory; resume/rerun forbidden')
    phases=[dict(index=i,source=sources[i]['item'],nominal_seconds=seconds,seed=a.seed+i,
                 command=command(output/'frozen/native-worker',output/f'phases/{i:03}/input.txt',output/f'phases/{i:03}/walk',seconds=seconds,seed=a.seed+i,dwell=a.reduction_dwell))
            for i,seconds in enumerate(phase_budgets)]
    metadata=dict(format='bounded-native-dwell42-pool-v2',cpu=2,memory_mb=768,seconds=a.seconds,phase_seconds=a.phase_seconds,
                  seed=a.seed,reduction_dwell=a.reduction_dwell,pool_sha256=a.expected_pool_sha256,pool_origin=pool['origin'],
                  binary_sha256=a.expected_binary_sha256,runtime_code_sha256=code,runtime_sha256=runtime_sha,phases=phases,
                  rerun_policy='exclusive new output only; no automatic retry/resume; root reviews interrupted runs',
                  claim='profile mechanics only; pilot found no wider n5 excursions; no advantage or all32 coverage claim')
    if a.preview:print(json.dumps(dict(status='PREVIEW_ONLY',zero_mutations=True,**metadata),sort_keys=True,indent=2));return
    os.sched_setaffinity(0,{2});cap=768*1024**2;resource.setrlimit(resource.RLIMIT_AS,(cap,cap));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    output.mkdir(parents=True);base.freeze(output/'pool.json',pool_raw);base.freeze(output/'manifest.json',base.raw_json(metadata))
    base.freeze(output/'heldout-declaration.json',a.heldout_declaration.read_bytes());base.freeze(output/'frozen/native-worker',binary_raw,True)
    for name in code:base.freeze(output/'frozen/runtime'/name,(ROOT/name).read_bytes())
    for source in sources:base.freeze(output/'frozen/sources'/source['item']['file'],source['raw'])
    stopping=False;seen={};ledger=[];end=start+a.seconds;winner=False
    def interrupt(sig,frame):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGINT,interrupt)
    def stopped():return barrier(campaign,deadline,stopping) or time.monotonic()>=end
    for phase in phases:
        remaining=end-time.monotonic()-2
        if stopped() or remaining<=0:break
        seconds=min(phase['nominal_seconds'],remaining);index=phase['index'];source=sources[index];directory=output/f'phases/{index:03}';directory.mkdir(parents=True)
        prefix=directory/'walk';mask_path=directory/'input.txt';base.freeze(mask_path,''.join(f'{x} {y} {z}\n' for x,y,z in source['terms']).encode())
        argv=command(output/'frozen/native-worker',mask_path,prefix,seconds=seconds,seed=phase['seed'],dwell=a.reduction_dwell)
        item=dict(index=index,status='PREPARED',source=source['item'],source_verification=source['metadata'],actual_native_budget_seconds=seconds,seed=phase['seed'],command=argv)
        ledger.append(item);base.atomic(output/'state.json',dict(status='RUNNING',phases=ledger))
        last_scan=0
        def inspect():
            nonlocal last_scan
            if time.monotonic()-last_scan<.5:return False
            last_scan=time.monotonic();return base.drain(prefix,output,dict(runtime_sha256=runtime_sha,pool_sha256=a.expected_pool_sha256,phase=index,source=source['metadata']),seen)
        if stopped():item['status']='STOPPED_BEFORE_NATIVE';base.atomic(output/'state.json',dict(status='STOPPED',phases=ledger));break
        item['status']='RUNNING';base.atomic(output/'state.json',dict(status='RUNNING',phases=ledger))
        with (directory/'worker.log').open('x') as log:execution=base.run_child(argv,log,stopped,inspect,wall_seconds=seconds)
        winner=base.drain(prefix,output,dict(runtime_sha256=runtime_sha,pool_sha256=a.expected_pool_sha256,phase=index,source=source['metadata']),seen) or (output/'WINNER.json').exists()
        item['execution']=execution
        if execution['exit_code']!=0:
            item['status']='STOPPED' if execution['interrupted'] else 'ERROR';base.atomic(output/'state.json',dict(status=item['status'],phases=ledger))
            if item['status']=='ERROR':raise RuntimeError('native child failed; no retry; artifacts retained')
            break
        stats,stats_sha=base.validate_stats(str(prefix)+'.stats.json',seed=phase['seed'],dwell=a.reduction_dwell)
        if len(_read_terms(str(prefix)+'.best.txt',5))!=stats['best_rank'] or len(_read_terms(str(prefix)+'.current.txt',5))!=stats['current_rank']:raise ValueError('rank/export mismatch')
        item.update(status='VERIFIED_TARGET' if winner else 'UNKNOWN_WITHIN_PHASE',stats_sha256=stats_sha,stats=stats)
        base.freeze(directory/'final_stats.json',base.raw_json(stats));base.atomic(output/'state.json',dict(status=item['status'],phases=ledger))
        if winner or execution['interrupted'] or execution['timed_out']:break
    for item in seen.values():item.pop('terms')
    status='VERIFIED_TARGET' if winner else ('STOPPED' if stopped() else 'UNKNOWN_WITHIN_BUDGET')
    summary=dict(status=status,winner=winner,native_queries_started=sum('execution' in x for x in ledger),phases=ledger,
                 exported_certificates=seen,unique_verified_certificates=len(seen),elapsed_seconds=time.monotonic()-start,
                 total_measured_child_cpu_seconds=sum(x.get('execution',{}).get('child_cpu_seconds',0) for x in ledger),claim=metadata['claim'])
    base.atomic(output/'summary.json',summary);base.atomic(output/'state.json',dict(status=status,phases=ledger));print(json.dumps(summary,sort_keys=True))
if __name__=='__main__':main()
