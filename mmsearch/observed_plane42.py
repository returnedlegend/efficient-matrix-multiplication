"""Witnessed observed-value planes and exact group-weight-at-most-three decode.

The independent proof/oracle is an external audit input. This implementation
does not import its decoder or use its output to construct search witnesses.
"""
from __future__ import annotations

from collections import Counter
import itertools
import math
import multiprocessing as mp
import signal
import time

from .common_delta42 import columns_from_rows,multiply,reduce_with_basis
from .free_factor_sat import decode_vectors,satisfies
from .recombine import digest
from .recombine_sat import bits
from .verify import verify_candidate


def syndrome_rank(a,b):
    return 0 if not (a or b) else 1 if not a or not b or a==b else 2


def active_certificate(system):
    columns=columns_from_rows(system)
    active=[g for g,v in enumerate(system['baseline_vectors']) if v]
    basis={}
    for g in active:
        value,proof=columns[g],1<<g
        while value:
            pivot=value.bit_length()-1
            if pivot not in basis:
                basis[pivot]=(value,proof);break
            value^=basis[pivot][0];proof^=basis[pivot][1]
    certificate=dict(active_groups=active,rank=len(basis),independent=len(basis)==len(active),
        basis=[[p,hex(c),hex(w)] for p,(c,w) in sorted(basis.items(),reverse=True)],
        coefficients_sha256=digest([hex(c) for c in system['coefficients']]))
    validate_active_certificate(system,certificate)
    return certificate


def validate_active_certificate(system,certificate):
    columns=columns_from_rows(system)
    active=[g for g,v in enumerate(system['baseline_vectors']) if v]
    mask=sum(1<<g for g in active)
    if (active!=certificate['active_groups'] or certificate['rank']!=len(certificate['basis'])
            or certificate['independent']!=(certificate['rank']==len(active))
            or certificate['coefficients_sha256']!=digest([hex(c) for c in system['coefficients']])):
        raise AssertionError('active-column certificate metadata mismatch')
    rows=[(p,int(c,16),int(w,16)) for p,c,w in certificate['basis']]
    if [p for p,_,_ in rows]!=sorted({p for p,_,_ in rows},reverse=True):
        raise AssertionError('active-column pivots are not distinct')
    for p,c,w in rows:
        if not c or c.bit_length()-1!=p or w&~mask or multiply(columns,w)!=c:
            raise AssertionError('active-column independence witness failed')
    for g in active:
        value=columns[g]
        for p,c,_ in rows:
            if value>>p&1:value^=c
        if value:raise AssertionError('active-column certificate does not span all active columns')
    return True


def plane_plan(system):
    counts=Counter(v for v in system['baseline_vectors'] if v)
    planes={tuple(sorted((a,b,a^b))) for a,b in itertools.combinations(counts,2)}
    result=[]
    for plane in planes:
        k=sum(counts[d] for d in plane)
        result.append(dict(plane=list(plane),k=k,weight_bound=k-1,
            observed_values=[d for d in plane if counts[d]],
            full_case_at_weight3=k-1<=3))
    return sorted(result,key=lambda p:(-p['k'],p['plane']))


def prepare_plane(system,plane,gain=1):
    plane=sorted(plane)
    if (len(plane)!=3 or len(set(plane))!=3 or not all(type(v) is int and v>0 for v in plane)
            or plane[0]^plane[1]!=plane[2] or type(gain) is not int or gain<1):
        raise ValueError('canonical nonzero binary plane and positive gain required')
    vectors=system['baseline_vectors'];width=system['metadata']['width']
    if any(v>=1<<width for v in plane) or not satisfies(system,vectors):
        raise ValueError('in-range plane and exact baseline required')
    a,b=plane[:2];coordinates={0:0,a:1,b:2,a^b:3}
    columns=columns_from_rows(system)
    relevant=[g for g,v in enumerate(vectors) if v in coordinates]
    neutral=[g for g,v in enumerate(vectors) if v not in coordinates]
    removed=[g for g,v in enumerate(vectors) if v in plane]
    basis={}
    for g in neutral:
        value,proof=columns[g],1<<g
        while value:
            p=(value&-value).bit_length()-1
            if p not in basis:basis[p]=(value,proof);break
            value^=basis[p][0];proof^=basis[p][1]
    rows=[(p,*basis[p]) for p in sorted(basis)]
    h,lifts=[],[]
    for g in relevant:
        value,proof=reduce_with_basis(columns[g],rows);h.append(hex(value));lifts.append(hex(proof))
    originals=[];targets=[];target_lifts=[]
    for bit in range(2):
        original=multiply(columns,sum(1<<g for g in removed if coordinates[vectors[g]]>>bit&1))
        target,proof=reduce_with_basis(original,rows)
        originals.append(hex(original));targets.append(hex(target));target_lifts.append(hex(proof))
    q=dict(plane=plane,basis_values=[a,b],gain=gain,k=len(removed),weight_bound=len(removed)-gain,
        relevant_groups=relevant,neutral_groups=neutral,removed_groups=removed,
        old_coordinates=[coordinates[vectors[g]] for g in relevant],
        neutral_basis=[[p,hex(c),hex(w)] for p,c,w in rows],neutral_rank=len(rows),
        column_syndromes_hex=h,column_neutral_lifts_hex=lifts,
        targets_hex=targets,target_originals_hex=originals,target_neutral_lifts_hex=target_lifts,
        target_rank=syndrome_rank(*map(lambda v:int(v,16),targets)),
        coefficients_sha256=digest([hex(c) for c in system['coefficients']]),
        baseline_vectors_sha256=digest(vectors),
        scope='All updates valued in this selected observed plane on the complete fixed-pair dictionary. A weight<=3 negative is complete only if k-gain<=3. No unrestricted rank nonexistence claim.')
    q['quotient_sha256']=digest(q)
    validate_plane(system,q)
    return q


def validate_plane(system,q):
    if digest({k:v for k,v in q.items() if k!='quotient_sha256'})!=q['quotient_sha256']:
        raise AssertionError('plane quotient content hash mismatch')
    plane=q['plane'];a,b=q['basis_values']
    if plane!=sorted([a,b,a^b]) or not a or not b or a==b:
        raise AssertionError('plane basis mismatch')
    vectors=system['baseline_vectors'];columns=columns_from_rows(system)
    coordinates={0:0,a:1,b:2,a^b:3}
    relevant=[g for g,v in enumerate(vectors) if v in coordinates]
    neutral=[g for g,v in enumerate(vectors) if v not in coordinates]
    removed=[g for g,v in enumerate(vectors) if v in plane]
    if (q['relevant_groups']!=relevant or q['neutral_groups']!=neutral or q['removed_groups']!=removed
            or q['k']!=len(removed) or q['weight_bound']!=len(removed)-q['gain']
            or q['old_coordinates']!=[coordinates[vectors[g]] for g in relevant]
            or q['coefficients_sha256']!=digest([hex(c) for c in system['coefficients']])
            or q['baseline_vectors_sha256']!=digest(vectors)):
        raise AssertionError('plane split or input digest mismatch')
    rows=[(p,int(c,16),int(w,16)) for p,c,w in q['neutral_basis']]
    mask=sum(1<<g for g in neutral)
    if [p for p,_,_ in rows]!=sorted({p for p,_,_ in rows}) or len(rows)!=q['neutral_rank']:
        raise AssertionError('neutral plane pivots invalid')
    for p,c,w in rows:
        if not c or (c&-c).bit_length()-1!=p or w&~mask or multiply(columns,w)!=c:
            raise AssertionError('plane neutral witness failed')
    if any(reduce_with_basis(columns[g],rows)[0] for g in neutral):
        raise AssertionError('plane neutral basis is incomplete')
    if len(q['column_syndromes_hex'])!=len(relevant) or len(q['column_neutral_lifts_hex'])!=len(relevant):
        raise AssertionError('plane quotient mapping length mismatch')
    for g,h,w in zip(relevant,q['column_syndromes_hex'],q['column_neutral_lifts_hex']):
        h,w=int(h,16),int(w,16)
        if w&~mask or columns[g]^multiply(columns,w)!=h or reduce_with_basis(columns[g],rows)[0]!=h:
            raise AssertionError('plane column lift witness failed')
    for bit in range(2):
        original=multiply(columns,sum(1<<g for g in removed if coordinates[vectors[g]]>>bit&1))
        target,lift=reduce_with_basis(original,rows)
        if [hex(original),hex(target),hex(lift)]!=[q['target_originals_hex'][bit],q['targets_hex'][bit],q['target_neutral_lifts_hex'][bit]]:
            raise AssertionError('plane target witness failed')
    if q['target_rank']!=syndrome_rank(*[int(t,16) for t in q['targets_hex']]):
        raise AssertionError('target syndrome rank mismatch')
    return True


def _column_solution(columns,target):
    """Local at-most-three-column solve, implemented independently of audit."""
    basis={}
    for index,column in enumerate(columns):
        value,proof=column,1<<index
        while value:
            pivot=(value&-value).bit_length()-1
            if pivot not in basis:basis[pivot]=(value,proof);break
            value^=basis[pivot][0];proof^=basis[pivot][1]
    proof=0
    for pivot in sorted(basis):
        if target>>pivot&1:target^=basis[pivot][0];proof^=basis[pivot][1]
    return None if target else proof


def decode_weight3(columns,targets,bound=3,seconds=5):
    if type(bound) is not int or not 0<=bound<=3 or not math.isfinite(seconds) or seconds<=0:
        raise ValueError('weight bound0..3 and positive finite seconds required')
    if len(targets)!=2:raise ValueError('two syndrome targets required')
    started=time.monotonic();deadline=started+seconds
    ta,tb=targets;r=syndrome_rank(ta,tb)
    def check():
        if time.monotonic()>=deadline:raise TimeoutError('cooperative plane decoder timeout')
    def answer(support,kind):
        support=list(dict.fromkeys(support));chosen=[columns[i] for i in support]
        pa,pb=_column_solution(chosen,ta),_column_solution(chosen,tb)
        if pa is None or pb is None:raise AssertionError('selected support does not span both targets')
        entries=[[index,((pa>>j)&1)|(((pb>>j)&1)<<1)] for j,index in enumerate(support)]
        entries=[entry for entry in entries if entry[1]]
        if len(entries)>bound:raise AssertionError('decoded plane group weight exceeds bound')
        for bit,target in enumerate(targets):
            value=0
            for i,c in entries:
                if c>>bit&1:value^=columns[i]
            if value!=target:raise AssertionError('decoded plane target check failed')
        return dict(status='HIT',entries=entries,weight=len(entries),case=kind,target_rank=r,
            searched_bound=bound,elapsed_seconds=time.monotonic()-started)
    try:
        check()
        if not r:return answer([],'zero_syndrome')
        unique={}
        for i,h in enumerate(columns):unique.setdefault(h,i)
        if r==1:
            target=ta or tb
            if bound>=1 and target in unique:return answer([unique[target]],'scalar_projection')
            values=list(unique)
            if bound>=2:
                for n,h in enumerate(values):
                    if target^h in unique:return answer([unique[h],unique[target^h]],'scalar_projection')
                    if not n%4096:check()
            if bound>=3:
                for n,h in enumerate(values):
                    for other in values[n+1:]:
                        third=unique.get(target^h^other)
                        if third is not None:return answer([unique[h],unique[other],third],'scalar_projection')
                    check()
        elif bound>=2:
            plane={0,ta,tb,ta^tb}
            inside=[h for h in unique if h and h in plane]
            if len(inside)>=2:return answer([unique[inside[0]],unique[inside[1]]],'two_target_plane_points')
            if bound>=3:
                buckets={}
                for index,h in enumerate(unique):
                    if h in plane:continue
                    key=min(h,h^ta,h^tb,h^ta^tb)
                    bucket=buckets.setdefault(key,[]);bucket.append(h)
                    if len(bucket)>4:raise AssertionError('binary plane coset exceeds four distinct values')
                    if not index%4096:check()
                for bucket in buckets.values():
                    if len(bucket)>=3:return answer([unique[h] for h in bucket[:3]],'three_affine_plane_points')
                    if inside and len(bucket)==2 and bucket[0]^bucket[1]!=inside[0]:
                        return answer([unique[inside[0]],unique[bucket[0]],unique[bucket[1]]],
                            'target_plane_point_plus_parallel_pair')
        check()
        return dict(status=f'NO_WEIGHT_LE{bound}',target_rank=r,searched_bound=bound,
            elapsed_seconds=time.monotonic()-started)
    except (TimeoutError,MemoryError) as exc:
        return dict(status='UNKNOWN',reason=f'{type(exc).__name__}: {exc}',target_rank=r,
            elapsed_seconds=time.monotonic()-started)


def lift_plane(system,q,entries,*,require_gain=True):
    validate_plane(system,q)
    if (not isinstance(entries,list) or len({v[0] for v in entries})!=len(entries)
            or any(not isinstance(v,list) or len(v)!=2 or type(v[0]) is not int or
                not 0<=v[0]<len(q['relevant_groups']) or type(v[1]) is not int or not 1<=v[1]<=3 for v in entries)):
        raise ValueError('invalid two-coordinate quotient assignment')
    columns=columns_from_rows(system);updates=[0,0];neutral=[int(v,16) for v in q['target_neutral_lifts_hex']]
    for i,old in enumerate(q['old_coordinates']):
        for bit in range(2):
            if old>>bit&1:updates[bit]^=1<<q['relevant_groups'][i]
    for i,value in entries:
        for bit in range(2):
            if value>>bit&1:
                updates[bit]^=1<<q['relevant_groups'][i]
                neutral[bit]^=int(q['column_neutral_lifts_hex'][i],16)
    for bit in range(2):
        updates[bit]^=neutral[bit]
        if multiply(columns,updates[bit]):raise AssertionError('plane lift violates original coordinate kernel')
    a,b=q['basis_values'];vectors=[]
    for g,w in enumerate(system['baseline_vectors']):
        vectors.append(w^(a if updates[0]>>g&1 else 0)^(b if updates[1]>>g&1 else 0))
    if not satisfies(system,vectors):raise AssertionError('plane lift violates original tensor rows')
    before=sum(bool(v) for v in system['baseline_vectors']);after=sum(bool(v) for v in vectors)
    if after-before!=len(entries)-q['k']:raise AssertionError('plane group-weight/rank identity failed')
    if require_gain and before-after<q['gain']:raise AssertionError('plane lift does not achieve requested gain')
    return dict(vectors=vectors,coordinate_kernel_masks_hex=list(map(hex,updates)),
        rank_before=before,rank_after=after,actual_gain=before-after,group_weight=len(entries),
        original_kernel_coordinates_verified=2,original_tensor_rows_verified=len(system['coefficients']))


def decode_plane_hit(system,q,entries):
    lift=lift_plane(system,q,entries)
    candidate=decode_vectors(system,lift['vectors'],dict(method='observed-plane-neutral-quotient-weight3',
        plane_hex=list(map(hex,q['plane'])),quotient_sha256=q['quotient_sha256'],field_claim='F2 only'))
    report=verify_candidate(candidate,random_trials=0)
    if not report['valid'] or report['rank']!=lift['rank_after'] or report['exact_entries_checked']!=system['metadata']['width']**3:
        raise AssertionError('plane candidate failed independent exact tensor verification')
    return dict(status='SAT',candidate=candidate,verification=report,lift=lift)


def _worker(q,seconds,memory_mb,sender):
    import resource
    try:
        for kind,soft,hard in [(resource.RLIMIT_AS,memory_mb*1024**2,memory_mb*1024**2),
                (resource.RLIMIT_CPU,math.ceil(seconds)+1,math.ceil(seconds)+2)]:
            _,inherited=resource.getrlimit(kind)
            limit=hard if inherited==resource.RLIM_INFINITY else min(hard,inherited)
            resource.setrlimit(kind,(min(soft,limit),limit))
        bound=min(3,q['weight_bound'])
        result=decode_weight3([int(v,16) for v in q['column_syndromes_hex']],
            [int(v,16) for v in q['targets_hex']],bound,seconds)
        if result['status'].startswith('NO_WEIGHT'):
            result['complete_for_requested_gain']=q['weight_bound']<=3
            if q['weight_bound']<=3:result['status']='NO_ONE_SUBSPACE_GAIN'
        usage=resource.getrusage(resource.RUSAGE_SELF)
        result['worker_stats']=dict(user_seconds=usage.ru_utime,system_seconds=usage.ru_stime,
            max_rss_kib=usage.ru_maxrss,address_space_limit_bytes=resource.getrlimit(resource.RLIMIT_AS)[0])
        sender.send(result)
    except Exception as exc:sender.send(dict(status='ERROR',error=f'{type(exc).__name__}: {exc}'))
    finally:sender.close()


def _entry(*args):
    signal.signal(signal.SIGTERM,signal.SIG_DFL);signal.signal(signal.SIGINT,signal.SIG_DFL)
    _worker(*args)


def search_plane_bounded(q,seconds=5,memory_mb=1024,cancelled=None):
    if not math.isfinite(seconds) or seconds<=0 or type(memory_mb) is not int or not 128<=memory_mb<=1024:
        raise ValueError('invalid plane search resource bounds')
    context=mp.get_context('fork');receiver,sender=context.Pipe(duplex=False)
    child=context.Process(target=_entry,args=(q,seconds,memory_mb,sender));started=time.monotonic();result=None
    child.start();sender.close()
    try:
        while result is None:
            left=seconds-(time.monotonic()-started)
            if left<=0 or (cancelled is not None and cancelled()):result=dict(status='UNKNOWN',reason='hard wall limit or stop')
            elif receiver.poll(min(left,.1)):
                try:result=receiver.recv()
                except EOFError:result=dict(status='ERROR',error='plane worker exited without result')
    finally:
        child.join(timeout=.02)
        if child.is_alive():child.terminate()
        child.join(timeout=.1)
        if child.is_alive():child.kill();child.join()
        receiver.close()
    result.update(quotient_sha256=q['quotient_sha256'],worker_reaped=not child.is_alive(),worker_exitcode=child.exitcode,
        wall_seconds=seconds,memory_mb=memory_mb,elapsed_seconds=time.monotonic()-started,scope=q['scope'])
    return result
