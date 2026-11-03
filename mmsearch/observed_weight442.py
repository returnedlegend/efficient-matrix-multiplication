"""Separate exact group-weight-four extension for recorded plane gaps only."""
from __future__ import annotations

import math
import multiprocessing as mp
import signal
import time
from collections import Counter

from .observed_plane42 import _column_solution,decode_weight3,plane_plan,syndrome_rank,validate_plane
from .recombine import digest


def validate_prior_family(system,config,plan,cursor,report,result_manifest):
    if (digest(system)!=config['source_system_sha256'] or digest(plan)!=config['plan_sha256']
            or plane_plan(system)!=plan or cursor['config_sha256']!=digest(config)
            or cursor['plan_sha256']!=digest(plan) or cursor['next_index']!=len(plan)
            or report['status']!='ENUMERATED_PLAN_COMPLETE'
            or report['config_sha256']!=digest(config) or report['plan_sha256']!=digest(plan)
            or report['next_index']!=len(plan)):
        raise AssertionError('prior family source, plan, configuration or completion hash mismatch')
    if [item['index'] for item in result_manifest]!=list(range(len(plan))):
        raise AssertionError('prior result manifest is not the complete indexed plan')
    counts=Counter(item['status'] for item in result_manifest)
    if (set(counts)-{'NO_GAIN_RANK_BOUND','NO_ONE_SUBSPACE_GAIN','NO_WEIGHT_LE3'}
            or dict(counts)!=cursor['terminal_counts'] or dict(counts)!=report['terminal_counts']):
        raise AssertionError('prior family includes incomplete or inconsistent terminal statuses')
    return True


def validate_prior_gap(system,q,prior,plan_item,binding):
    """Reject changed, already-complete, or unrelated prior negative cases."""
    validate_plane(system,q)
    if digest(prior)!=binding['prior_result_canonical_sha256']:
        raise AssertionError('prior result hash mismatch')
    if (prior.get('status')!='NO_WEIGHT_LE3' or prior.get('complete_for_requested_gain') is not False
            or prior.get('full_case') is not False or prior.get('searched_bound')!=3
            or prior.get('k')!=5 or prior.get('weight_bound')!=4 or prior.get('target_rank')!=2
            or prior.get('worker_reaped') is not True or prior.get('worker_exitcode')!=0):
        raise AssertionError('prior is not a clean recorded partial weight3 negative')
    if (q['plane']!=prior['plane'] or q['plane']!=plan_item['plane'] or q['plane']!=binding['plane']
            or q['quotient_sha256']!=prior['quotient_sha256']
            or q['quotient_sha256']!=binding['quotient_sha256']
            or q['k']!=5 or q['gain']!=1 or q['weight_bound']!=4 or q['target_rank']!=2
            or plan_item['k']!=5 or plan_item['weight_bound']!=4
            or plan_item['full_case_at_weight3'] is not False
            or digest(system)!=binding['source_system_sha256']):
        raise AssertionError('prior system, plane or quotient binding mismatch')
    return True


def _pair_rows(a,b):
    """Two-pivot Gaussian quotient, separate from the oracle's coset minima."""
    rows={}
    for value in (a,b):
        for pivot in sorted(rows):
            if value>>pivot&1:value^=rows[pivot]
        if value:
            pivot=(value&-value).bit_length()-1;rows[pivot]=value
    if len(rows)!=2:raise AssertionError('contraction pair is not independent')
    return sorted(rows.items())


def _reduce(value,rows):
    for pivot,row in rows:
        if value>>pivot&1:value^=row
    return value


def decode_weight4(columns,targets,seconds=30):
    if len(targets)!=2 or syndrome_rank(*targets)!=2 or not math.isfinite(seconds) or seconds<=0:
        raise ValueError('independent rank2 target and positive finite seconds required')
    started=time.monotonic();deadline=started+seconds;ta,tb=targets;pairs_tried=0
    def check():
        if time.monotonic()>=deadline:raise TimeoutError('cooperative weight4 timeout')
    def emit(support,kind,pair_type,precondition):
        support=list(dict.fromkeys(support));chosen=[columns[i] for i in support]
        pa,pb=_column_solution(chosen,ta),_column_solution(chosen,tb)
        if pa is None or pb is None:raise AssertionError('contracted support fails original targets')
        entries=[[index,((pa>>j)&1)|(((pb>>j)&1)<<1)] for j,index in enumerate(support)]
        entries=[entry for entry in entries if entry[1]]
        if len(entries)>4:raise AssertionError('weight4 witness exceeds group bound')
        for bit,target in enumerate(targets):
            value=0
            for i,v in entries:
                if v>>bit&1:value^=columns[i]
            if value!=target:raise AssertionError('weight4 witness violates original syndrome')
        return dict(status='HIT',entries=entries,weight=len(entries),case=kind,pair_type=pair_type,
            eligible_pairs_tried=pairs_tried,precondition_weight3=precondition,
            elapsed_seconds=time.monotonic()-started)
    try:
        check()
        precondition=decode_weight3(columns,targets,3,max(1e-9,deadline-time.monotonic()))
        if precondition['status']=='HIT':
            precondition['precondition_weight3']=dict(status='HIT',case=precondition['case'])
            precondition['eligible_pairs_tried']=0
            return precondition
        if precondition['status']=='UNKNOWN':
            return dict(status='UNKNOWN',reason='weight3 precondition unresolved',precondition_weight3=precondition,
                eligible_pairs_tried=0,elapsed_seconds=time.monotonic()-started)
        if precondition['status']!='NO_WEIGHT_LE3':raise AssertionError('unexpected weight3 precondition status')
        representatives={}
        for i,h in enumerate(columns):
            if h:representatives.setdefault(h,i)
        values=list(representatives)
        target_rows=_pair_rows(ta,tb)
        inside=[];buckets={}
        for h in values:
            residue=_reduce(h,target_rows)
            if not residue:inside.append(h)
            else:buckets.setdefault(residue,[]).append(h)
        if len(inside)>1 or any(len(bucket)>2 for bucket in buckets.values()):
            raise AssertionError('weight3 negative violates contraction preconditions')
        def eligible():
            if inside:
                h0=inside[0]
                for h in values:
                    if h!=h0:yield h0,h,'in_target_plus_outside'
            for bucket in buckets.values():
                if len(bucket)==2:yield bucket[0],bucket[1],'same_target_coset'
        for a,b,pair_type in eligible():
            check();rows=_pair_rows(a,b)
            qa,qb=_reduce(ta,rows),_reduce(tb,rows)
            if syndrome_rank(qa,qb)!=1:
                raise AssertionError('eligible contraction does not leave a rank1 target')
            target=qa or qb
            seen={};residual_support=None
            for n,h in enumerate(values):
                value=_reduce(h,rows)
                if value:
                    if value==target:residual_support=[representatives[h]];break
                    seen.setdefault(value,representatives[h])
                if not n%4096:check()
            if residual_support is None:
                for value,index in seen.items():
                    other=seen.get(value^target)
                    if other is not None and other!=index:
                        residual_support=[index,other];break
            pairs_tried+=1
            if residual_support is not None:
                return emit([representatives[a],representatives[b]]+residual_support,
                    'pair_contraction_scalar_weight2',pair_type,precondition)
        check()
        return dict(status='NO_WEIGHT_LE4',searched_bound=4,complete_for_weight4=True,
            eligible_pairs_tried=pairs_tried,deduplicated_nonzero_columns=len(values),
            precondition_weight3=precondition,elapsed_seconds=time.monotonic()-started)
    except (TimeoutError,MemoryError) as exc:
        return dict(status='UNKNOWN',reason=f'{type(exc).__name__}: {exc}',
            eligible_pairs_tried=pairs_tried,elapsed_seconds=time.monotonic()-started)


def _worker(q,seconds,memory_mb,sender):
    import resource
    try:
        for kind,soft,hard in [(resource.RLIMIT_AS,memory_mb*1024**2,memory_mb*1024**2),
                (resource.RLIMIT_CPU,math.ceil(seconds)+1,math.ceil(seconds)+2)]:
            _,inherited=resource.getrlimit(kind);limit=hard if inherited==resource.RLIM_INFINITY else min(hard,inherited)
            resource.setrlimit(kind,(min(soft,limit),limit))
        result=decode_weight4([int(h,16) for h in q['column_syndromes_hex']],
            [int(t,16) for t in q['targets_hex']],seconds)
        if result['status']=='NO_WEIGHT_LE4':
            result.update(status='NO_ONE_SUBSPACE_GAIN',complete_for_requested_gain=q['weight_bound']<=4)
        usage=resource.getrusage(resource.RUSAGE_SELF)
        result['worker_stats']=dict(user_seconds=usage.ru_utime,system_seconds=usage.ru_stime,
            max_rss_kib=usage.ru_maxrss,address_space_limit_bytes=resource.getrlimit(resource.RLIMIT_AS)[0])
        sender.send(result)
    except Exception as exc:sender.send(dict(status='ERROR',error=f'{type(exc).__name__}: {exc}'))
    finally:sender.close()


def _entry(*args):
    signal.signal(signal.SIGTERM,signal.SIG_DFL);signal.signal(signal.SIGINT,signal.SIG_DFL)
    _worker(*args)


def search_weight4_bounded(q,seconds=30,memory_mb=1024,cancelled=None):
    if q['weight_bound']!=4 or q['k']!=5 or q['target_rank']!=2:
        raise ValueError('extension accepts only bound4/rank2 recorded k5 cases')
    if not math.isfinite(seconds) or seconds<=0 or type(memory_mb) is not int or not 128<=memory_mb<=1024:
        raise ValueError('invalid weight4 resources')
    context=mp.get_context('fork');receiver,sender=context.Pipe(duplex=False)
    child=context.Process(target=_entry,args=(q,seconds,memory_mb,sender));start=time.monotonic();result=None
    child.start();sender.close()
    try:
        while result is None:
            left=seconds-(time.monotonic()-start)
            if left<=0 or (cancelled is not None and cancelled()):result=dict(status='UNKNOWN',reason='hard wall limit or stop')
            elif receiver.poll(min(left,.1)):
                try:result=receiver.recv()
                except EOFError:result=dict(status='ERROR',error='weight4 worker exited without result')
    finally:
        child.join(timeout=.02)
        if child.is_alive():child.terminate()
        child.join(timeout=.1)
        if child.is_alive():child.kill();child.join()
        receiver.close()
    result.update(quotient_sha256=q['quotient_sha256'],worker_reaped=not child.is_alive(),worker_exitcode=child.exitcode,
        memory_mb=memory_mb,wall_seconds=seconds,elapsed_seconds=time.monotonic()-start,
        scope='Exact groupweight<=4 in this recorded k5 plane quotient only; no unrestricted rank claim.')
    return result
