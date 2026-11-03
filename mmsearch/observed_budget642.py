"""Separate exact Fano-contraction extension: rank3/weight6 and rank2/weight5.

This prototype has no production catalogue launcher. Time, memory and prefix
limits preserve UNKNOWN. Complete negatives require exhausting every physical
inside/pair/triangle contraction after the exact lower-bound negative.
"""
from itertools import combinations
import math
import time
from .observed_rank342 import echelon,reduce,rank,basis_values,palette,_emit
from .observed_rank3_lazy42 import decode_rank3,logical
from .observed_plane42 import decode_weight3
from .observed_weight442 import decode_weight4
from .recombine import digest


class Cutoff(Exception):pass


def scalar_decode(columns,target,bound=4,seconds=30):
    if type(target) is not int or target<0 or type(bound) is not int or not 0<=bound<=4 or not math.isfinite(seconds) or seconds<=0:
        raise ValueError('scalar nonnegative target/budget<=4 and positive finite seconds required')
    if any(type(h) is not int or h<0 for h in columns):raise ValueError('nonnegative binary columns required')
    start=time.monotonic();deadline=start+seconds;probes=0
    def check():
        if time.monotonic()>=deadline:raise Cutoff('scalar wall limit')
    def emit(indices,case):
        support=[]
        for i in indices:
            if i in support:support.remove(i)
            else:support.append(i)
        result=_emit(columns,[target],support,bound,case)
        result.update(elapsed_seconds=time.monotonic()-start,pair_probes=probes);return result
    try:
        check()
        if not target:return emit([],'scalar_zero')
        if not bound:return dict(status='NO_WEIGHT_LE0',searched_bound=0,complete_for_requested_bound=True)
        representatives={}
        for i,h in enumerate(columns):
            if h:representatives.setdefault(h,i)
            if not i%1024:check()
        if target in representatives:return emit([representatives[target]],'scalar_single')
        if bound==1:return dict(status='NO_WEIGHT_LE1',searched_bound=1,complete_for_requested_bound=True)
        values=sorted(representatives)
        for h in values:
            if h^target in representatives:return emit([representatives[h],representatives[h^target]],'scalar_pair')
        if bound==2:return dict(status='NO_WEIGHT_LE2',searched_bound=2,complete_for_requested_bound=True)
        pairs={}
        for i,a in enumerate(values):
            for j in range(i+1,len(values)):
                b=values[j];x=a^b;probes+=1
                if not probes%4096:check()
                c=target^x
                if c in representatives:return emit([representatives[a],representatives[b],representatives[c]],'scalar_triple')
                if bound==4:
                    previous=pairs.get(c)
                    if previous is not None:
                        u,v=previous>>32,previous&0xffffffff
                        return emit([representatives[a],representatives[b],u,v],'scalar_pair_mitm')
                    # One representative pair per XOR suffices: symmetric
                    # differences remove overlaps and still XOR to the target.
                    pairs.setdefault(x,(representatives[a]<<32)|representatives[b])
        check()
        return dict(status=f'NO_WEIGHT_LE{bound}',searched_bound=bound,complete_for_requested_bound=True,
            pair_probes=probes,pair_map_entries=len(pairs),elapsed_seconds=time.monotonic()-start)
    except (Cutoff,MemoryError) as error:
        return dict(status='UNKNOWN',reason=f'{type(error).__name__}: {error}',searched_bound=bound,
            pair_probes=probes,elapsed_seconds=time.monotonic()-start)


def contractions(columns,targets,check):
    """ALL physical choices; no cross-bucket/modal/dictionary restriction."""
    representatives={}
    for i,h in enumerate(columns):
        if h:representatives.setdefault(h,i)
        if not i%1024:check()
    values=sorted(representatives);rows=echelon(targets);residues=[reduce(h,rows) for h in values];buckets={}
    for j,h in enumerate(values):buckets.setdefault(residues[j],[]).append(h)
    for h in buckets.get(0,[]):
        check();yield 'inside',[representatives[h]]
    for residue in sorted(buckets):
        if not residue:continue
        for a,b in combinations(buckets[residue],2):
            check();yield 'pair',[representatives[a],representatives[b]]
    points=palette(basis_values(targets));lookup={h:j for j,h in enumerate(values)};probes=0
    for i,a in enumerate(values):
        if not residues[i]:continue
        for j in range(i+1,len(values)):
            if not residues[j] or residues[i]==residues[j]:continue
            for t in points:
                probes+=1
                if not probes%1024:check()
                k=lookup.get(a^values[j]^t)
                if k is None or k<=j or not residues[k] or residues[k] in (residues[i],residues[j]):continue
                # Physical XOR equals nonzero t in T; hence these three
                # physically independent columns project to a triangle.
                chosen=[representatives[h] for h in (a,values[j],values[k])]
                yield 'triangle',chosen
    check()


def decode_budget6(columns,targets,bound=6,seconds=30,cursor=None,progress=None,max_branches=0,max_prefix=65536):
    """Exact where supported; a source-bound cursor retains nested partial work.

    Completed-prefix records must be retained by the caller as trusted negative
    events. This prototype bounds each node's retained prefix; reaching that cap
    is UNKNOWN, never a complete negative or a silently truncated catalogue.
    """
    if (any(type(h) is not int or h<0 for h in [*columns,*targets]) or not 1<=len(targets)<=3 or
        type(bound) is not int or bound<0 or not math.isfinite(seconds) or seconds<=0 or
        type(max_branches) is not int or max_branches<0 or type(max_prefix) is not int or max_prefix<1):
        raise ValueError('invalid exact decoder input/resources')
    start=time.monotonic();deadline=start+seconds;target_basis=basis_values(targets);m=len(target_basis)
    if not m:return _emit(columns,targets,[],bound,'zero_target')
    if m>bound:return dict(status=f'NO_WEIGHT_LE{bound}',searched_bound=bound,complete_for_requested_bound=True,reason='target rank bound')
    if m==1:
        if bound>4:return dict(status='UNKNOWN',reason='scalar budget>4 unsupported',complete_for_requested_bound=False)
        result=scalar_decode(columns,target_basis[0],bound,seconds)
        if result['status']=='HIT':return _emit(columns,targets,[entry[0] for entry in result['entries']],bound,'scalar_child')
        return result
    if (m==2 and bound<=4) or (m==3 and bound<=5):
        if m==3:return decode_rank3(columns,target_basis,bound,seconds,cursor,progress,max_branches)
        result=(decode_weight4(columns,target_basis,seconds) if bound==4 else decode_weight3(columns,target_basis,bound,seconds))
        if result['status']=='HIT':return _emit(columns,targets,[entry[0] for entry in result['entries']],bound,'rank2_older')
        if result['status'].startswith('NO_WEIGHT'):result['complete_for_requested_bound']=True
        return result
    if (m,bound) not in ((2,5),(3,6)):
        return dict(status='UNKNOWN',reason='requested rank/budget unsupported',complete_for_requested_bound=False)
    identity=digest(dict(columns_hex=list(map(hex,columns)),targets_hex=list(map(hex,targets)),bound=bound,algorithm='fano-budget6-v1'))
    branch_sha=digest('physical-inside-pair-triangle-v1')
    seed=digest([identity,branch_sha]);prefix=[];active=None;lower_cursor=None;done=0;state=None
    if cursor is not None:
        if cursor.get('version')!=1 or cursor.get('input_sha256')!=identity or cursor.get('branch_catalog_sha256')!=branch_sha:raise AssertionError('budget6 cursor source changed')
        prefix=[dict(record) for record in cursor['completed_prefix']];active=cursor.get('active_child');lower_cursor=cursor.get('lower_cursor')
        if len(prefix)>max_prefix or cursor.get('next_branch')!=len(prefix):raise AssertionError('budget6 prefix exceeds configured cap/count')
        chain=seed
        for i,record in enumerate(prefix):
            if record['branch']!=i or record['child_status']!=f"NO_WEIGHT_LE{record['child_bound']}" or len(record['child_result_sha256'])!=64:raise AssertionError('budget6 cursor prefix invalid')
            chain=digest([chain,record])
        if cursor['prefix_chain_sha256']!=chain:raise AssertionError('budget6 cursor chain changed')
    else:chain=seed
    def snapshot():
        return dict(version=1,input_sha256=identity,branch_catalog_sha256=branch_sha,next_branch=len(prefix),completed_prefix=prefix.copy(),prefix_chain_sha256=chain,
            active_child=active,lower_cursor=lower_cursor)
    def check():
        if time.monotonic()>=deadline:raise Cutoff('Fano contraction wall limit')
    def finish(result):
        result.update(cursor=snapshot(),elapsed_seconds=time.monotonic()-start,input_sha256=identity,
            complete_for_requested_bound=result['status']==f'NO_WEIGHT_LE{bound}',searched_bound=bound)
        return result
    try:
        check()
        # Re-establish the lower-weight negative on every launch. The rank3
        # lower decoder can reuse its exact streamed contraction prefix.
        lower=(decode_rank3(columns,target_basis,5,max(1e-9,deadline-time.monotonic()),lower_cursor) if m==3 else
               decode_weight4(columns,target_basis,max(1e-9,deadline-time.monotonic())))
        lower_cursor=lower.get('cursor')
        if lower['status']=='HIT':return finish(_emit(columns,targets,[e[0] for e in lower['entries']],bound,'lower_weight_hit'))
        if lower['status']=='UNKNOWN':return finish(dict(status='UNKNOWN',reason='lower-weight decoder incomplete',partial_negative=logical(lower)))
        if lower['status']!=f'NO_WEIGHT_LE{bound-1}':raise AssertionError('unexpected lower-weight decoder result')
        total=0
        for number,(kind,chosen) in enumerate(contractions(columns,target_basis,check)):
            total=number+1
            rows=echelon([columns[i] for i in chosen]);child_targets=basis_values([reduce(t,rows) for t in target_basis]);child_bound=bound-len(chosen)
            if len(rows)!=len(chosen) or len(child_targets)!=m-1 or rank([*target_basis,*[columns[i] for i in chosen]])!=m+len(chosen)-1:
                raise AssertionError('physical contraction rank/intersection invalid')
            if number<len(prefix):
                if prefix[number]['kind']!=kind or prefix[number]['contracted_indices']!=chosen or prefix[number]['child_bound']!=child_bound:
                    raise AssertionError('budget6 cursor skipped/replaced a physical branch')
                continue
            if number!=len(prefix):raise AssertionError('noncontiguous Fano prefix')
            check()
            if len(prefix)>=max_prefix:raise Cutoff('retained prefix cap; continuation remains nonclosed')
            if max_branches and done>=max_branches:raise Cutoff('Fano branch budget')
            child_cursor=None
            if active is not None:
                if active['branch']!=number or active['kind']!=kind or active['contracted_indices']!=chosen:raise AssertionError('nested child identity changed')
                child_cursor=active['cursor']
            projected=[reduce(h,rows) for h in columns]
            child=decode_budget6(projected,child_targets,child_bound,max(1e-9,deadline-time.monotonic()),child_cursor,
                max_branches=max_branches,max_prefix=max_prefix)
            if child['status']=='HIT':
                active=None
                return finish(_emit(columns,targets,chosen+[e[0] for e in child['entries']],bound,'fano_'+kind,
                    contraction_kind=kind,contracted_indices=chosen,child_case=child.get('case'),branch=number))
            if child['status']=='UNKNOWN':
                active=dict(branch=number,kind=kind,contracted_indices=chosen,cursor=child.get('cursor'))
                return finish(dict(status='UNKNOWN',reason='contracted child incomplete',child_reason=child.get('reason')))
            if child['status']!=f'NO_WEIGHT_LE{child_bound}':raise AssertionError('unexpected Fano child negative')
            active=None;record=dict(branch=number,kind=kind,contracted_indices=chosen,child_bound=child_bound,child_status=child['status'],
                child_result_sha256=digest(logical(child)))
            chain=digest([chain,record]);prefix.append(record);done+=1
            if progress is not None:progress(record,snapshot())
        if len(prefix)!=total or active is not None:raise AssertionError('prefix extends beyond the physical catalogue')
        return finish(dict(status=f'NO_WEIGHT_LE{bound}',contraction_branches=len(prefix),lower_negative_sha256=digest(logical(lower))))
    except (Cutoff,MemoryError) as error:
        return finish(dict(status='UNKNOWN',reason=f'{type(error).__name__}: {error}',branches_completed_this_call=done))
