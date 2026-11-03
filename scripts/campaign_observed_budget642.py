"""Separate lazy rank3/groupweight6 pilot; fresh source coverage and storage holds."""
import argparse
from collections import Counter
from datetime import datetime
import fcntl
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import signal
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.observed_rank3_lazy42 import FreshGuard,Hold,directory_bytes,chain_read,chain_append
from mmsearch.observed_budget6_runtime42 import SourceRuntime
from mmsearch.observed_budget6_bounded42 import search_budget6_bounded as search_bounded
from mmsearch.observed_rank3_checkpoint42 import atomic_json
from mmsearch.observed_budget6_checkpoint42 import load_checkpoint,append_checkpoint,save_checkpoint
from mmsearch.free_factor_sat import decode_vectors
from mmsearch.recombine import digest
from mmsearch.verify import verify_candidate
SHA=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
READ=lambda path:json.loads(Path(path).read_text())
CAP=128*1024**2
RESERVE=8*1024**2


def compact(result):
    result=dict(result)
    if result.get('cursor') is not None:result['cursor']={k:v for k,v in result['cursor'].items() if k!='completed_prefix'}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-dir',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--chunk-id',action='append',required=True);parser.add_argument('--guard-state',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=840);parser.add_argument('--per-case-seconds',type=float,default=20)
    parser.add_argument('--memory-mb',type=int,default=1024);parser.add_argument('--restart',action='store_true')
    parser.add_argument('--deadline-utc',default='2026-11-04T21:31:16Z');args=parser.parse_args()
    if not 0<args.per_case_seconds<=args.seconds or not 128<=args.memory_mb<=1536:parser.error('invalid resource allocation')
    b=args.prepared_dir.resolve();out=args.output_dir.resolve();bindings=READ(b/'integrity.json')
    for name,expected in bindings.items():
        if SHA(b/name)!=expected:raise ValueError('frozen continuation hash mismatch: '+name)
    plan=READ(b/'plan.json');selected=[item for item in plan['chunks'] if item['id'] in args.chunk_id]
    if len(set(args.chunk_id))!=len(selected):raise ValueError('unknown or duplicate selected chunk')
    out.mkdir(parents=True,exist_ok=args.restart);lock=(out/'.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    config=dict(prepared_integrity_sha256=SHA(b/'integrity.json'),plan_sha256=digest(plan),chunk_ids=[c['id'] for c in selected],
        decoder=plan['decoder'],chunk_cap_bytes=CAP,guard_limit_bytes=5*1024**3,guard_max_age_seconds=60)
    if args.restart:
        if READ(out/'config.json')!=config:raise ValueError('continuation source/plan/decoder binding changed')
    else:atomic_json(out/'config.json',config)
    config_sha=digest(config);guard=FreshGuard(args.guard_state);start=time.monotonic();stopped=False;queries=0;counts=Counter();global_status='UNKNOWN';reason=None
    cutoff=datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00')).timestamp()
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    def left():return max(0,min(args.seconds-time.monotonic()+start,cutoff-time.time())-1)
    launches=out/'launches';launches.mkdir(exist_ok=True);launch=len(list(launches.glob('*.json')))
    atomic_json(launches/f'{launch:03d}.json',dict(seconds=args.seconds,per_case_seconds=args.per_case_seconds,memory_mb=args.memory_mb,
        guard_state=str(args.guard_state),config_sha256=config_sha,deadline_utc=args.deadline_utc))
    if (out/'WINNER.json').exists():
        checked=verify_candidate(READ(out/'WINNER.json'),random_trials=0)
        if not checked['valid'] or checked['rank']>92 or checked['exact_entries_checked']!=15625:raise ValueError('retained winner invalid')
        print(json.dumps(dict(status='SAT',resumed_without_target_query=True)));return 0
    runtimes={};chunk_reports=[]
    for chunk in selected:
        cd=out/'chunks'/chunk['id'];cd.mkdir(parents=True,exist_ok=True);current=cd/'current';ledgerdir=cd/'ledgers';ledgerdir.mkdir(exist_ok=True)
        items=json.loads(gzip.decompress((b/chunk['plan']).read_bytes()))
        if digest(items)!=chunk['plan_sha256'] or SHA(b/chunk['plan'])!=chunk['compressed_sha256']:raise ValueError('chunk plan changed')
        initial=digest([config_sha,chunk]);events,chain=chain_read(cd/'results.jsonl',initial)
        for i,event in enumerate(events):
            if i>=len(items) or event['index']!=i or event['case']!=items[i] or event['source_id']!=chunk['source_id']:
                raise ValueError('completed case journal identity mismatch')
            if event['result']['status'] not in ('NO_ONE_SUBSPACE_GAIN','NO_GAIN_RANK_BOUND','SAT','ERROR'):raise ValueError('nonterminal journal record')
            archive=cd/event['branch_ledger']
            if SHA(archive)!=event['branch_ledger_sha256']:raise ValueError('completed branch archive changed')
            counts[event['result']['status']]+=1
        if events and events[-1]['result']['status'] in ('SAT','ERROR'):
            global_status=events[-1]['result']['status'];reason='prior terminal result';break
        # The append-only journal is authoritative after a crash between append and cursor update.
        atomic_json(cd/'cursor.json',dict(config_sha256=config_sha,chunk_plan_sha256=chunk['plan_sha256'],next_index=len(events),result_chain_sha256=chain,last_status='RESUMED'))
        if len(events)==len(items):chunk_reports.append(dict(id=chunk['id'],complete=True,completed=len(events),result_chain_sha256=chain));continue
        source=chunk['source_id']
        if source not in runtimes:
            system=READ(b/'sources'/source/'system.json')
            if SHA(b/'sources'/source/'system.json')!=plan['sources'][source]['system_sha256']:raise ValueError('source changed')
            checked=verify_candidate(decode_vectors(system,system['baseline_vectors']),random_trials=0)
            if not checked['valid'] or checked['rank']!=93 or checked['exact_entries_checked']!=15625:raise ValueError('source must be exact93')
            runtimes[source]=SourceRuntime(system)
        runtime=runtimes[source]
        for index in range(len(events),len(items)):
            reason='campaign stop signal' if stopped else ('launch/deadline wall limit' if left()<=0 else guard.check())
            if reason:break
            used=directory_bytes(cd)
            if used+RESERVE>CAP:reason='chunk storage reserve reached 128MiB cap';break
            item=items[index];identity=dict(index=index,case=item,source_id=source,source_system_sha256=plan['sources'][source]['system_sha256'])
            if current.exists():
                meta=READ(current/'case.json')
                # A committed case can leave its old current directory after a crash.
                if meta['index']<index:
                    if meta['index']>=len(events) or events[meta['index']]['quotient_sha256']!=meta['quotient_sha256']:raise ValueError('orphan current case not committed')
                    shutil.rmtree(current)
            q=runtime.prepare(runtime.system,item['basis_values'])
            if q['k']!=item['k'] or q['weight_bound']!=item['weight_bound'] or q['target_rank']!=3:raise ValueError('lazy quotient plan/rank changed')
            if current.exists():
                meta=READ(current/'case.json')
                if meta!=dict(identity,quotient_sha256=q['quotient_sha256']):raise ValueError('partial case source/quotient changed')
                stored=json.loads(gzip.decompress((current/'quotient.json.gz').read_bytes()))
                if stored!=q:raise ValueError('partial stored quotient changed')
            else:
                current.mkdir();atomic_json(current/'case.json',dict(identity,quotient_sha256=q['quotient_sha256']))
                (current/'quotient.json.gz').write_bytes(gzip.compress(json.dumps(q,sort_keys=True).encode(),compresslevel=1,mtime=0))
            state=load_checkpoint(current,q['quotient_sha256']);base_used=directory_bytes(cd)-directory_bytes(current);held=None
            def progress(record,cursor):
                # Bound the current ledger plus a simultaneous compressed archival copy and atomic cursor.
                event_bytes=len(json.dumps(dict(quotient_sha256=q['quotient_sha256'],record=record,cursor=cursor),sort_keys=True).encode())+1
                ledger=current/'branches.jsonl';ledger_bytes=ledger.stat().st_size if ledger.exists() else 0
                if base_used+directory_bytes(current)+ledger_bytes+2*event_bytes+65536>CAP:
                    raise Hold('chunk storage cap reached during branch checkpoint')
                append_checkpoint(current,q['quotient_sha256'],record,cursor)
            def cancelled():
                nonlocal held
                held='campaign stop signal' if stopped else ('launch/deadline wall limit' if left()<=0 else guard.check())
                return held is not None
            # Quotient generation can consume the final slice of the launch budget.
            held='campaign stop signal' if stopped else ('launch/deadline wall limit' if left()<=0 else guard.check())
            if held:
                reason=held;atomic_json(current/'last-unknown.json',dict(status='UNKNOWN',reason=reason));break
            query_seconds=min(args.per_case_seconds,left())
            if query_seconds<=0:
                reason='launch/deadline wall limit';atomic_json(current/'last-unknown.json',dict(status='UNKNOWN',reason=reason));break
            try:
                queries+=1
                result=search_bounded(q,seconds=query_seconds,memory_mb=args.memory_mb,cursor=state,
                    on_progress=progress,cancelled=cancelled)
                if result.get('cursor') is not None and result['status']!='HIT':
                    summary={k:v for k,v in result['cursor'].items() if k!='completed_prefix'}
                    if directory_bytes(cd)+2*len(json.dumps(summary).encode())+65536>CAP:
                        raise Hold('chunk storage cap before nested cursor checkpoint')
                    save_checkpoint(current,q['quotient_sha256'],result['cursor'])
            except Hold as error:
                result=dict(status='UNKNOWN',reason=str(error),quotient_sha256=q['quotient_sha256'],worker_reaped=True)
            if held:result.update(status='UNKNOWN',reason=held)
            if result['status'] in ('UNKNOWN','PARTIAL_NO_WEIGHT_LE5'):
                reason=result.get('reason','incomplete case')
                atomic_json(current/'last-unknown.json',compact(result));break
            if result['status']=='HIT':
                answer=runtime.decode_hit(runtime.system,q,result['entries'])
                checked=answer['verification']
                if checked['rank']>92 or checked['exact_entries_checked']!=15625:raise AssertionError('winner failed full15625')
                atomic_json(current/'candidate.json',answer['candidate']);atomic_json(current/'lift.json',answer['lift']);atomic_json(current/'verification.json',checked)
                atomic_json(out/'WINNER.json',answer['candidate']);atomic_json(out/'WINNER.verification.json',checked);result.update(status='SAT',verification=checked)
            if result['status'] not in ('NO_ONE_SUBSPACE_GAIN','NO_GAIN_RANK_BOUND','SAT','ERROR'):raise ValueError('unexpected decoder status')
            if result['status'].startswith('NO_') and not result.get('complete_for_requested_bound'):raise ValueError('incomplete negative cannot close case')
            raw=(current/'branches.jsonl').read_bytes() if (current/'branches.jsonl').exists() else b''
            archived=gzip.compress(raw,compresslevel=1,mtime=0);archive=ledgerdir/f'{index:05d}.jsonl.gz'
            record=dict(identity,quotient_sha256=q['quotient_sha256'],result=compact(result),branch_ledger=str(archive.relative_to(cd)),
                branch_ledger_sha256=hashlib.sha256(archived).hexdigest(),branch_ledger_uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
                branch_records=len(raw.splitlines()),decoder_code_sha256=bindings['code/mmsearch/observed_budget642.py'])
            # Reserve bounds cover these small files; pause rather than commit if unusually large.
            if directory_bytes(cd)+len(archived)+2*len(json.dumps(record).encode())+65536>CAP:
                reason='chunk storage cap before result commit';atomic_json(current/'last-unknown.json',dict(status='UNKNOWN',reason=reason));break
            archive.write_bytes(archived);chain=chain_append(cd/'results.jsonl',record,chain);counts[result['status']]+=1
            atomic_json(cd/'cursor.json',dict(config_sha256=config_sha,chunk_plan_sha256=chunk['plan_sha256'],next_index=index+1,result_chain_sha256=chain,last_status=result['status']))
            if result['status'] in ('SAT','ERROR'):global_status=result['status'];reason=None;break
            shutil.rmtree(current);reason=None
        latest=READ(cd/'cursor.json');chunk_reports.append(dict(id=chunk['id'],completed=latest['next_index'],selected=len(items),complete=latest['next_index']==len(items),
            result_chain_sha256=latest['result_chain_sha256'],bytes=directory_bytes(cd)))
        if reason or global_status in ('SAT','ERROR'):break
    else:global_status='SELECTED_CHUNKS_COMPLETE'
    report=dict(status=global_status,reason=reason,config_sha256=config_sha,chunks=chunk_reports,terminal_counts=dict(counts),target_queries_this_launch=queries,
        elapsed_seconds=time.monotonic()-start,full_observed_catalog_complete=False,scope=plan['scope'])
    atomic_json(out/f'report-launch{launch:03d}.json',report);print(json.dumps(report,sort_keys=True));return 2 if global_status=='ERROR' else 0


if __name__=='__main__':raise SystemExit(main())
