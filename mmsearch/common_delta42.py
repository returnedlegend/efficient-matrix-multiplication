"""Exact one-common-delta kernel repair via a witnessed neutral quotient.

This searches all binary kernel supports with one chosen nonzero free-vector
delta. It does not restrict supports to a supplied circuit catalogue.
"""
from __future__ import annotations

import math
import multiprocessing as mp
from pathlib import Path
import signal
import tempfile
import time
import json

from .free_factor_sat import decode_vectors,satisfies
from .recombine import digest
from .recombine_sat import bits
from .verify import verify_candidate


def columns_from_rows(system):
    count = len(system['baseline_vectors'])
    columns = [0]*count
    for r,row in enumerate(system['coefficients']):
        if type(row) is not int or row<0 or row>>count:
            raise ValueError('invalid original coefficient row')
        for g in bits(row):
            columns[g] |= 1<<r
    return columns


def multiply(columns,mask):
    result = 0
    for g in bits(mask):
        result ^= columns[g]
    return result


def reduce_with_basis(value,basis):
    witness = 0
    for pivot,column,proof in basis:
        if value>>pivot&1:
            value ^= column
            witness ^= proof
    return value,witness


def prepare_quotient(system,delta,gain=1):
    vectors = system['baseline_vectors']
    width = system['metadata']['width']
    if type(delta) is not int or not 0<delta<1<<width or type(gain) is not int or gain<1:
        raise ValueError('nonzero in-range delta and positive integer gain required')
    if delta not in vectors or not satisfies(system,vectors):
        raise ValueError('observed delta and exact feasible baseline required')
    columns = columns_from_rows(system)
    neutral = [g for g,v in enumerate(vectors) if v and v!=delta]
    relevant = [g for g,v in enumerate(vectors) if not v or v==delta]
    removed = [g for g,v in enumerate(vectors) if v==delta]
    basis = {}
    for g in neutral:
        value,proof = columns[g],1<<g
        while value:
            pivot = (value&-value).bit_length()-1
            if pivot not in basis:
                basis[pivot] = (value,proof)
                break
            column,witness = basis[pivot]
            value ^= column
            proof ^= witness
    rows = [(pivot,*basis[pivot]) for pivot in sorted(basis)]
    syndromes,lifts = [],[]
    for g in relevant:
        value,proof = reduce_with_basis(columns[g],rows)
        syndromes.append(value)
        lifts.append(proof)
    target_original = multiply(columns,sum(1<<g for g in removed))
    target,target_lift = reduce_with_basis(target_original,rows)
    quotient = dict(delta=delta,gain=gain,k=len(removed),weight_bound=len(removed)-gain,
        relevant_groups=relevant,neutral_groups=neutral,delta_groups=removed,
        neutral_basis=[[p,hex(c),hex(w)] for p,c,w in rows],
        column_syndromes_hex=[hex(v) for v in syndromes],
        column_neutral_lifts_hex=[hex(v) for v in lifts],
        target_syndrome_hex=hex(target),target_original_hex=hex(target_original),
        target_neutral_lift_hex=hex(target_lift),neutral_rank=len(rows),
        original_column_count=len(columns),original_row_count=len(system['coefficients']),
        original_coefficients_sha256=digest([hex(v) for v in system['coefficients']]),
        baseline_vectors_sha256=digest(vectors),
        scope='All binary kernel supports on these fixed pairs using exactly one common chosen free-vector delta; no claim about multiple simultaneous deltas or unrestricted tensor rank.')
    quotient['quotient_sha256'] = digest(quotient)
    validate_quotient(system,quotient)
    return quotient


def validate_quotient(system,q):
    vectors = system['baseline_vectors']
    delta = q['delta']
    columns = columns_from_rows(system)
    expected_neutral = [g for g,v in enumerate(vectors) if v and v!=delta]
    expected_relevant = [g for g,v in enumerate(vectors) if not v or v==delta]
    expected_removed = [g for g,v in enumerate(vectors) if v==delta]
    if (q['neutral_groups']!=expected_neutral or q['relevant_groups']!=expected_relevant
            or q['delta_groups']!=expected_removed or q['k']!=len(expected_removed)
            or q['weight_bound']!=len(expected_removed)-q['gain']
            or q['original_coefficients_sha256']!=digest([hex(v) for v in system['coefficients']])
            or q['baseline_vectors_sha256']!=digest(vectors)):
        raise AssertionError('quotient split, bound or input digest mismatch')
    payload = {k:v for k,v in q.items() if k!='quotient_sha256'}
    if digest(payload)!=q['quotient_sha256']:
        raise AssertionError('quotient content hash mismatch')
    neutral_mask = sum(1<<g for g in expected_neutral)
    rows = [(p,int(c,16),int(w,16)) for p,c,w in q['neutral_basis']]
    if [p for p,_,_ in rows]!=sorted(set(p for p,_,_ in rows)):
        raise AssertionError('neutral pivots are not unique and ordered')
    for pivot,column,proof in rows:
        if not column or (column&-column).bit_length()-1!=pivot or proof&~neutral_mask:
            raise AssertionError('invalid neutral elimination row')
        if multiply(columns,proof)!=column:
            raise AssertionError('neutral elimination witness failed')
    if any(reduce_with_basis(columns[g],rows)[0] for g in expected_neutral):
        raise AssertionError('neutral basis does not span all neutral columns')
    if len(q['column_syndromes_hex'])!=len(expected_relevant) or len(q['column_neutral_lifts_hex'])!=len(expected_relevant):
        raise AssertionError('quotient mapping length mismatch')
    for g,syndrome,proof in zip(expected_relevant,q['column_syndromes_hex'],q['column_neutral_lifts_hex']):
        syndrome,proof = int(syndrome,16),int(proof,16)
        if proof&~neutral_mask or columns[g]^multiply(columns,proof)!=syndrome:
            raise AssertionError('relevant column neutral-lift witness failed')
        if reduce_with_basis(columns[g],rows)[0]!=syndrome:
            raise AssertionError('relevant quotient column is not canonical')
    original = multiply(columns,sum(1<<g for g in expected_removed))
    if original!=int(q['target_original_hex'],16):
        raise AssertionError('wrong delta-group target')
    target,proof = reduce_with_basis(original,rows)
    if (target,proof)!=(int(q['target_syndrome_hex'],16),int(q['target_neutral_lift_hex'],16)):
        raise AssertionError('target neutral-lift witness failed')
    return True


def low_weight_search(q,*,max_weight=4,seconds=60,max_work_mb=512):
    if (type(max_weight) is not int or not 0<=max_weight<=4 or not math.isfinite(seconds) or seconds<=0
            or not math.isfinite(max_work_mb) or max_work_mb<=0):
        raise ValueError('invalid bounded low-weight search limits')
    start = time.monotonic()
    deadline = start+seconds
    values = [int(v,16) for v in q['column_syndromes_hex']]
    target = int(q['target_syndrome_hex'],16)
    bound = min(max_weight,q['weight_bound'])
    operations = 0
    def check():
        if time.monotonic()>=deadline:
            raise TimeoutError('cooperative low-weight wall limit')
    def hit(indices):
        parity = set()
        for i in indices:
            if i in parity:parity.remove(i)
            else:parity.add(i)
        answer = sorted(parity)
        value = 0
        for i in answer:value ^= values[i]
        if value!=target or len(answer)>bound:
            raise AssertionError('low-weight hit failed exact syndrome/weight check')
        return dict(status='HIT',y_indices=answer,weight=len(answer),searched_bound=bound,
            elapsed_seconds=time.monotonic()-start,operations=operations)
    try:
        check()
        if bound<0:
            return dict(status='NO_ONE_DELTA_GAIN',searched_bound=bound,complete_for_requested_gain=True,
                reason='requested gain exceeds maximum removable delta-group count',operations=0)
        if target==0:return hit([])
        singles = {}
        if bound>=1:
            for i,value in enumerate(values):
                operations += 1
                if value==target:return hit([i])
                singles.setdefault(value,i)
                if not operations%4096:check()
        if bound>=2:
            for i,value in enumerate(values):
                operations += 1
                other = singles.get(target^value)
                if other is not None:return hit([i,other])
                if not operations%4096:check()
        if bound>=3:
            for i,a in enumerate(values):
                for j in range(i+1,len(values)):
                    operations += 1
                    other = singles.get(target^a^values[j])
                    if other is not None:return hit([i,j,other])
                    if not operations%4096:check()
        if bound>=4:
            pairs = len(values)*(len(values)-1)//2
            estimate = pairs*((q['original_row_count']+7)//8+176)
            if estimate>max_work_mb*1024**2:
                return dict(status='UNKNOWN',reason='conservative pair-map memory estimate exceeds cap',
                    estimated_pair_map_mb=math.ceil(estimate/1024**2),operations=operations)
            seen = {}
            for i,a in enumerate(values):
                for j in range(i+1,len(values)):
                    operations += 1
                    syndrome = a^values[j]
                    previous = seen.get(target^syndrome)
                    if previous is not None:
                        return hit([i,j,previous>>32,previous&0xffffffff])
                    # One representative is sufficient: overlapping pairs
                    # cancel by symmetric difference and still give weight<=4.
                    seen.setdefault(syndrome,(i<<32)|j)
                    if not operations%4096:check()
        check()
        complete = q['weight_bound']<=bound
        return dict(status='NO_ONE_DELTA_GAIN' if complete else f'NO_WEIGHT_LE{bound}',
            low_weight_status=f'NO_WEIGHT_LE{bound}',searched_bound=bound,
            complete_for_requested_gain=complete,elapsed_seconds=time.monotonic()-start,
            operations=operations,scope=q['scope'])
    except (TimeoutError,MemoryError) as exc:
        return dict(status='UNKNOWN',reason=f'{type(exc).__name__}: {exc}',
            elapsed_seconds=time.monotonic()-start,operations=operations)


def lift_hit(system,q,y_indices):
    validate_quotient(system,q)
    if (not isinstance(y_indices,list) or len(set(y_indices))!=len(y_indices)
            or any(type(i) is not int or not 0<=i<len(q['relevant_groups']) for i in y_indices)):
        raise ValueError('invalid quotient assignment')
    columns = columns_from_rows(system)
    value = 0
    neutral = int(q['target_neutral_lift_hex'],16)
    z = sum(1<<g for g in q['delta_groups'])
    for i in y_indices:
        value ^= int(q['column_syndromes_hex'][i],16)
        neutral ^= int(q['column_neutral_lifts_hex'][i],16)
        z ^= 1<<q['relevant_groups'][i]
    if value!=int(q['target_syndrome_hex'],16):
        raise AssertionError('quotient assignment violates syndrome')
    z ^= neutral
    if multiply(columns,z):
        raise AssertionError('lifted update violates original Pz=0')
    vectors = [v^(q['delta'] if z>>g&1 else 0) for g,v in enumerate(system['baseline_vectors'])]
    if not satisfies(system,vectors):
        raise AssertionError('lifted update violates original complete tensor rows')
    before = sum(bool(v) for v in system['baseline_vectors'])
    after = sum(bool(v) for v in vectors)
    if after-before!=len(y_indices)-q['k']:
        raise AssertionError('actual active-rank change disagrees with quotient weight')
    return dict(vectors=vectors,z_hex=hex(z),y_indices=y_indices,
        rank_before=before,rank_after=after,actual_gain=before-after,
        original_kernel_verified=True,original_tensor_rows_verified=len(system['coefficients']))


def decode_hit(system,q,y_indices):
    lifted = lift_hit(system,q,y_indices)
    if lifted['actual_gain']<q['gain']:
        raise AssertionError('lifted hit does not meet requested gain')
    candidate = decode_vectors(system,lifted['vectors'],dict(method='one-common-delta-neutral-quotient',
        delta_hex=hex(q['delta']),quotient_sha256=q['quotient_sha256'],field_claim='F2 only'))
    report = verify_candidate(candidate,random_trials=0)
    if (not report['valid'] or report['rank']!=lifted['rank_after']
            or report['exact_entries_checked']!=system['metadata']['width']**3):
        raise AssertionError('decoded one-delta repair failed independent full tensor verification')
    return dict(status='SAT',candidate=candidate,verification=report,lift=lifted)


def _worker(q,max_weight,seconds,memory_mb,max_work_mb,sender):
    import resource
    try:
        for kind,soft,hard in [(resource.RLIMIT_AS,memory_mb*1024**2,memory_mb*1024**2),
                (resource.RLIMIT_CPU,math.ceil(seconds)+1,math.ceil(seconds)+2)]:
            _,inherited = resource.getrlimit(kind)
            effective = hard if inherited==resource.RLIM_INFINITY else min(hard,inherited)
            resource.setrlimit(kind,(min(soft,effective),effective))
        result = low_weight_search(q,max_weight=max_weight,seconds=seconds,max_work_mb=max_work_mb)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        result['worker_stats']=dict(user_seconds=usage.ru_utime,system_seconds=usage.ru_stime,max_rss_kib=usage.ru_maxrss,
            address_space_limit_bytes=resource.getrlimit(resource.RLIMIT_AS)[0],
            cpu_limit_seconds=resource.getrlimit(resource.RLIMIT_CPU)[0])
        sender.send(result)
    except Exception as exc:
        sender.send(dict(status='ERROR',error=f'{type(exc).__name__}: {exc}'))
    finally:
        sender.close()


def _entry(*args):
    signal.signal(signal.SIGTERM,signal.SIG_DFL)
    signal.signal(signal.SIGINT,signal.SIG_DFL)
    _worker(*args)


def search_bounded(q,*,seconds=60,memory_mb=768,max_work_mb=512,max_weight=4,cancelled=None):
    if not math.isfinite(seconds) or seconds<=0 or type(memory_mb) is not int or not 128<=memory_mb<=768:
        raise ValueError('invalid hard resource bounds')
    context = mp.get_context('fork')
    receiver,sender = context.Pipe(duplex=False)
    child = context.Process(target=_entry,args=(q,max_weight,seconds,memory_mb,max_work_mb,sender))
    started = time.monotonic()
    child.start()
    sender.close()
    result = None
    try:
        while result is None:
            left = seconds-(time.monotonic()-started)
            if left<=0 or (cancelled is not None and cancelled()):
                result = dict(status='UNKNOWN',reason='hard parent wall limit or stop signal')
            elif receiver.poll(min(left,.1)):
                try:result = receiver.recv()
                except EOFError:result = dict(status='ERROR',error='low-weight worker exited without result')
    finally:
        child.join(timeout=.02)
        if child.is_alive():child.terminate()
        child.join(timeout=.1)
        if child.is_alive():child.kill();child.join()
        receiver.close()
    result.update(worker_pid=child.pid,worker_reaped=not child.is_alive(),worker_exitcode=child.exitcode,
        hard_wall_seconds=seconds,memory_mb=memory_mb,elapsed_seconds=time.monotonic()-started,
        quotient_sha256=q['quotient_sha256'],scope=q['scope'])
    return result
