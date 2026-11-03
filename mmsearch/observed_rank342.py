"""Exact rank-three target decoding through group weight five, with branch cursors."""
from __future__ import annotations
from collections import Counter
from itertools import combinations
import math
import time
from .common_delta42 import columns_from_rows,multiply,reduce_with_basis
from .free_factor_sat import decode_vectors,satisfies
from .observed_plane42 import _column_solution,decode_weight3
from .observed_weight442 import decode_weight4
from .recombine import digest
from .verify import verify_candidate


def echelon(values):
    rows={}
    for original in values:
        value=original
        for pivot in sorted(rows):
            if value>>pivot&1:value^=rows[pivot]
        if value:rows[(value&-value).bit_length()-1]=value
    return sorted(rows.items())


def reduce(value,rows):
    for pivot,row in rows:
        if value>>pivot&1:value^=row
    return value


def rank(values):return len(echelon(values))


def basis_values(values):
    result=[]
    for value in values:
        if rank(result+[value])>len(result):result.append(value)
    return result


def palette(basis):
    values=[0]
    for value in basis:values += [old^value for old in values]
    return sorted(values[1:])


def observed_space_plan(system):
    counts=Counter(value for value in system['baseline_vectors'] if value);spaces={}
    for triple in combinations(sorted(counts),3):
        if rank(triple)!=3:continue
        space=tuple(palette(triple));spaces.setdefault(space,triple)
    result=[]
    for space,observed_generators in spaces.items():
        basis=basis_values(space);k=sum(counts[value] for value in space)
        result.append(dict(space=list(space),basis_values=basis,observed_generators=list(observed_generators),k=k,
            weight_bound=k-1,decoder_bound_supported=k<=6,observed_values=[value for value in space if counts[value]]))
    return sorted(result,key=lambda item:(-item['k'],item['space']))


def _emit(columns,targets,support,bound,case,**metadata):
    support=list(dict.fromkeys(support));chosen=[columns[i] for i in support]
    solutions=[_column_solution(chosen,target) for target in targets]
    if any(solution is None for solution in solutions):raise AssertionError('original three targets fail reconstruction')
    entries=[]
    for j,index in enumerate(support):
        value=sum(((solution>>j)&1)<<bit for bit,solution in enumerate(solutions))
        if value:entries.append([index,value])
    if len(entries)>bound:raise AssertionError('group weight exceeds requested bound')
    for bit,target in enumerate(targets):
        actual=0
        for i,value in entries:
            if value>>bit&1:actual^=columns[i]
        if actual!=target:raise AssertionError('original coordinate reconstruction failed')
    return dict(status='HIT',entries=entries,weight=len(entries),case=case,searched_bound=bound,**metadata)


def _cursor(input_sha,branch_sha,prefix):
    chain=digest([input_sha,branch_sha])
    for record in prefix:chain=digest([chain,record])
    return dict(version=1,input_sha256=input_sha,branch_catalog_sha256=branch_sha,next_branch=len(prefix),
                prefix_chain_sha256=chain,completed_prefix=prefix)


def decode_rank3(columns,targets,bound=5,seconds=30,cursor=None,progress=None,max_branches=0):
    if (len(targets)!=3 or any(type(v) is not int or v<0 for v in [*columns,*targets]) or rank(targets)!=3 or
            type(bound) is not int or bound<0 or not math.isfinite(seconds) or seconds<=0 or type(max_branches) is not int or max_branches<0):
        raise ValueError('rank3 independent targets, nonnegative columns/bound and finite budget required')
    requested=bound;bound=min(bound,5);start=time.monotonic();deadline=start+seconds;prefix=[];state=None;branches_done=0
    input_sha=digest(dict(columns_hex=list(map(hex,columns)),targets_hex=list(map(hex,targets)),requested_bound=requested,algorithm='rank3-weight5-v1'))
    def check():
        if time.monotonic()>=deadline:raise TimeoutError('cooperative rank3 decoder timeout')
    def finish(result):
        result.update(elapsed_seconds=time.monotonic()-start,requested_bound=requested,complete_for_requested_bound=
            result['status'].startswith('NO_WEIGHT') and requested<=5,input_sha256=input_sha)
        if state is not None:result['cursor']=state
        return result
    try:
        check()
        if bound<3:return finish(dict(status=f'NO_WEIGHT_LE{bound}',reason='target rank3 exceeds group budget',searched_bound=bound))
        representatives={}
        for i,h in enumerate(columns):
            if h:representatives.setdefault(h,i)
            if not i%1024:check()
        values=sorted(representatives);trows=echelon(targets);inside=[];buckets={}
        for n,h in enumerate(values):
            residue=reduce(h,trows)
            if not residue:inside.append(h)
            else:buckets.setdefault(residue,[]).append(h)
            if not n%1024:check()
        chosen_inside=[]
        for h in inside:
            if rank(chosen_inside+[h])>len(chosen_inside):chosen_inside.append(h)
        if len(chosen_inside)==3:return finish(_emit(columns,targets,[representatives[h] for h in chosen_inside],bound,'three_in_target_columns'))
        if bound==3:return finish(dict(status='NO_WEIGHT_LE3',searched_bound=3,inside_rank=len(chosen_inside)))
        for residue in sorted(buckets):
            check();bucket=buckets[residue];anchor=bucket[0];span=list(chosen_inside);selected=[]
            for h in bucket[1:]:
                difference=h^anchor
                if rank(span+[difference])>len(span):span.append(difference);selected.append(h)
            if len(span)==3:
                support=[representatives[h] for h in chosen_inside]+[representatives[anchor]]+[representatives[h] for h in selected]
                return finish(_emit(columns,targets,support,bound,'one_coset_differences_plus_inside'))
        if bound==4:return finish(dict(status='NO_WEIGHT_LE4',searched_bound=4,inside_rank=len(chosen_inside),cosets=len(buckets)))
        if len(inside)>3 or any(len(bucket)>4 for bucket in buckets.values()):
            raise AssertionError('weight4 negative violates rank3 contraction preconditions')
        branches=[('inside',[representatives[h]]) for h in inside]
        branches += [('same_coset_pair',[representatives[a],representatives[b]]) for residue in sorted(buckets)
                     for a,b in combinations(buckets[residue],2)]
        branch_sha=digest(branches)
        if cursor is not None:
            prefix=[dict(record) for record in cursor.get('completed_prefix',[])]
            expected=_cursor(input_sha,branch_sha,prefix)
            if expected!=cursor or len(prefix)>len(branches):raise AssertionError('rank3 resume cursor binding/prefix mismatch')
            for index,record in enumerate(prefix):
                kind,indices=branches[index]
                if (record.get('branch')!=index or record.get('kind')!=kind or record.get('contracted_indices')!=indices or
                        record.get('child_status')!=('NO_WEIGHT_LE4' if kind=='inside' else 'NO_WEIGHT_LE3')):
                    raise AssertionError('rank3 resume prefix is not completed negative branches')
        state=_cursor(input_sha,branch_sha,prefix)
        for index in range(len(prefix),len(branches)):
            check()
            if max_branches and branches_done>=max_branches:raise TimeoutError('branch work budget')
            kind,contracted=branches[index];crows=echelon([columns[i] for i in contracted])
            projected_targets=[reduce(target,crows) for target in targets];target_basis=basis_values(projected_targets)
            if len(target_basis)!=2:raise AssertionError('eligible contraction does not leave target rank2')
            projected=[reduce(h,crows) for h in columns];left=max(1e-9,deadline-time.monotonic())
            child=(decode_weight4(projected,target_basis,left) if kind=='inside' else decode_weight3(projected,target_basis,3,left))
            if child['status']=='HIT':
                return finish(_emit(columns,targets,contracted+[entry[0] for entry in child['entries']],bound,
                    'inside_contraction_rank2_weight4' if kind=='inside' else 'pair_contraction_rank2_weight3',
                    contraction_kind=kind,contracted_indices=contracted,child_case=child.get('case'),branch=index))
            if child['status']=='UNKNOWN':raise TimeoutError('contracted rank2 decoder unresolved')
            expected='NO_WEIGHT_LE4' if kind=='inside' else 'NO_WEIGHT_LE3'
            if child['status']!=expected:raise AssertionError('unexpected exact contracted-decoder status')
            record=dict(branch=index,kind=kind,contracted_indices=contracted,child_status=expected,child_result_sha256=digest(child))
            previous_chain=state['prefix_chain_sha256'];prefix.append(record)
            state=dict(version=1,input_sha256=input_sha,branch_catalog_sha256=branch_sha,next_branch=len(prefix),
                       prefix_chain_sha256=digest([previous_chain,record]),completed_prefix=prefix);branches_done+=1
            if progress is not None:progress(record,{key:value for key,value in state.items() if key!='completed_prefix'})
        return finish(dict(status='NO_WEIGHT_LE5',searched_bound=5,contraction_branches=len(branches),inside_columns=len(inside),
                           distinct_nonzero_columns=len(values),nonzero_cosets=len(buckets)))
    except (TimeoutError,MemoryError) as error:
        return finish(dict(status='UNKNOWN',reason=f'{type(error).__name__}: {error}',searched_bound=bound,
                           branches_completed_this_call=branches_done))


def prepare_space(system,basis,gain=1):
    width=system['metadata']['width'];vectors=system['baseline_vectors']
    if len(basis)!=3 or rank(basis)!=3 or any(type(v) is not int or not 0<v<1<<width for v in basis) or type(gain) is not int or gain<1:
        raise ValueError('independent in-range rank3 free values required')
    if not satisfies(system,vectors):raise ValueError('inexact baseline')
    space=palette(basis);basis=basis_values(space);coordinates={0:0}
    for value in range(1,8):
        mask=0
        for bit,b in enumerate(basis):
            if value>>bit&1:mask^=b
        coordinates[mask]=value
    columns=columns_from_rows(system);relevant=[g for g,w in enumerate(vectors) if w in coordinates]
    neutral=[g for g,w in enumerate(vectors) if w not in coordinates];removed=[g for g,w in enumerate(vectors) if w in space]
    rows={}
    for g in neutral:
        value,proof=columns[g],1<<g
        while value:
            pivot=(value&-value).bit_length()-1
            if pivot not in rows:rows[pivot]=(value,proof);break
            value^=rows[pivot][0];proof^=rows[pivot][1]
    rows=[(pivot,*rows[pivot]) for pivot in sorted(rows)];syndromes=[];lifts=[]
    for g in relevant:
        value,proof=reduce_with_basis(columns[g],rows);syndromes.append(hex(value));lifts.append(hex(proof))
    originals=[];targets=[];target_lifts=[]
    for bit in range(3):
        original=multiply(columns,sum(1<<g for g in removed if coordinates[vectors[g]]>>bit&1))
        target,proof=reduce_with_basis(original,rows);originals.append(hex(original));targets.append(hex(target));target_lifts.append(hex(proof))
    q=dict(space=space,basis_values=basis,gain=gain,k=len(removed),weight_bound=len(removed)-gain,
        relevant_groups=relevant,neutral_groups=neutral,removed_groups=removed,old_coordinates=[coordinates[vectors[g]] for g in relevant],
        neutral_basis=[[pivot,hex(column),hex(proof)] for pivot,column,proof in rows],neutral_rank=len(rows),
        column_syndromes_hex=syndromes,column_neutral_lifts_hex=lifts,targets_hex=targets,
        target_originals_hex=originals,target_neutral_lifts_hex=target_lifts,target_rank=rank([int(v,16) for v in targets]),
        coefficients_sha256=digest([hex(v) for v in system['coefficients']]),baseline_vectors_sha256=digest(vectors),
        scope='Only S-valued updates in this fixedP/source rank3 observed free-value space. Decoder is exact through groupweight5; larger budgets remain nonclosed.')
    q['quotient_sha256']=digest(q);validate_space(system,q);return q


def validate_space(system,q):
    if digest({k:v for k,v in q.items() if k!='quotient_sha256'})!=q['quotient_sha256']:raise AssertionError('space quotient content hash mismatch')
    basis=q['basis_values'];space=q['space'];width=system['metadata']['width'];vectors=system['baseline_vectors'];columns=columns_from_rows(system)
    if len(basis)!=3 or rank(basis)!=3 or palette(basis)!=space or basis_values(space)!=basis or any(not 0<v<1<<width for v in basis):
        raise AssertionError('rank3 space basis/palette mismatch')
    coordinates={0:0}
    for value in range(1,8):
        mask=0
        for bit,b in enumerate(basis):
            if value>>bit&1:mask^=b
        coordinates[mask]=value
    relevant=[g for g,w in enumerate(vectors) if w in coordinates];neutral=[g for g,w in enumerate(vectors) if w not in coordinates]
    removed=[g for g,w in enumerate(vectors) if w in space]
    if (q['relevant_groups']!=relevant or q['neutral_groups']!=neutral or q['removed_groups']!=removed or q['k']!=len(removed) or
        q['weight_bound']!=len(removed)-q['gain'] or q['old_coordinates']!=[coordinates[vectors[g]] for g in relevant] or
        q['coefficients_sha256']!=digest([hex(v) for v in system['coefficients']]) or q['baseline_vectors_sha256']!=digest(vectors)):
        raise AssertionError('rank3 space source/split mismatch')
    rows=[(pivot,int(column,16),int(proof,16)) for pivot,column,proof in q['neutral_basis']];mask=sum(1<<g for g in neutral)
    if [pivot for pivot,_,_ in rows]!=sorted({pivot for pivot,_,_ in rows}) or len(rows)!=q['neutral_rank']:raise AssertionError('neutral pivots invalid')
    for pivot,column,proof in rows:
        if not column or (column&-column).bit_length()-1!=pivot or proof&~mask or multiply(columns,proof)!=column:
            raise AssertionError('neutral row witness invalid')
    if any(reduce_with_basis(columns[g],rows)[0] for g in neutral):raise AssertionError('neutral span incomplete')
    if len(q['column_syndromes_hex'])!=len(relevant) or len(q['column_neutral_lifts_hex'])!=len(relevant):raise AssertionError('column lift length mismatch')
    for g,syndrome,proof in zip(relevant,q['column_syndromes_hex'],q['column_neutral_lifts_hex']):
        syndrome,proof=int(syndrome,16),int(proof,16)
        if proof&~mask or columns[g]^multiply(columns,proof)!=syndrome or reduce_with_basis(columns[g],rows)[0]!=syndrome:
            raise AssertionError('relevant rank3 column lift mismatch')
    for bit in range(3):
        original=multiply(columns,sum(1<<g for g in removed if coordinates[vectors[g]]>>bit&1));target,proof=reduce_with_basis(original,rows)
        if [hex(original),hex(target),hex(proof)]!=[q['target_originals_hex'][bit],q['targets_hex'][bit],q['target_neutral_lifts_hex'][bit]]:
            raise AssertionError('rank3 target lift mismatch')
    if rank([int(t,16) for t in q['targets_hex']])!=q['target_rank']:raise AssertionError('target rank mismatch')
    return True


def lift_space(system,q,entries,require_gain=True):
    validate_space(system,q)
    if (not isinstance(entries,list) or len({entry[0] for entry in entries})!=len(entries) or
        any(not isinstance(entry,list) or len(entry)!=2 or type(entry[0]) is not int or not 0<=entry[0]<len(q['relevant_groups']) or
            type(entry[1]) is not int or not 1<=entry[1]<=7 for entry in entries)):
        raise ValueError('invalid three-coordinate group assignment')
    columns=columns_from_rows(system);updates=[0,0,0];neutral=[int(v,16) for v in q['target_neutral_lifts_hex']]
    for i,old in enumerate(q['old_coordinates']):
        for bit in range(3):
            if old>>bit&1:updates[bit]^=1<<q['relevant_groups'][i]
    for i,value in entries:
        for bit in range(3):
            if value>>bit&1:updates[bit]^=1<<q['relevant_groups'][i];neutral[bit]^=int(q['column_neutral_lifts_hex'][i],16)
    for bit in range(3):
        updates[bit]^=neutral[bit]
        if multiply(columns,updates[bit]):raise AssertionError('original coordinate kernel check failed')
    vectors=[]
    for g,w in enumerate(system['baseline_vectors']):
        for bit,b in enumerate(q['basis_values']):
            if updates[bit]>>g&1:w^=b
        vectors.append(w)
    if not satisfies(system,vectors):raise AssertionError('rank3 lift violates original PW')
    before=sum(bool(w) for w in system['baseline_vectors']);after=sum(bool(w) for w in vectors)
    if after-before!=len(entries)-q['k']:raise AssertionError('rank3 weight/gain identity failed')
    if require_gain and before-after<q['gain']:raise AssertionError('rank3 assignment lacks requested gain')
    return dict(vectors=vectors,rank_before=before,rank_after=after,actual_gain=before-after,group_weight=len(entries),
        coordinate_kernel_masks_hex=list(map(hex,updates)),original_kernel_coordinates_verified=3,original_tensor_rows_verified=len(system['coefficients']))


def decode_space_hit(system,q,entries):
    lift=lift_space(system,q,entries);candidate=decode_vectors(system,lift['vectors'],dict(method='observed-rank3-exact-weight5',
        space_hex=list(map(hex,q['space'])),quotient_sha256=q['quotient_sha256'],field_claim='F2 only'))
    report=verify_candidate(candidate,random_trials=0)
    if not report['valid'] or report['rank']!=lift['rank_after'] or report['exact_entries_checked']!=system['metadata']['width']**3:
        raise AssertionError('rank3 candidate failed full tensor verification')
    return dict(candidate=candidate,verification=report,lift=lift)
