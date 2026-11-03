"""Exact kernel-circuit preparation for fixed-pair/free-vector sparsity walks."""
from __future__ import annotations

from collections import Counter,defaultdict
import hashlib
import itertools
import json
import random

from .free_factor_sat import ORIENTATIONS,build_system,decode_vectors,satisfies
from .verify import verify_candidate


def pair_column(pair,width):
    a,b=pair;result=0
    while a:
        bit=a&-a;i=bit.bit_length()-1;result^=b<<(i*width);a^=bit
    return result


def validate_circuit(columns,support):
    if (not 3<=len(support)<=8 or len(set(support))!=len(support)
            or any(type(index) is not int or not 0<=index<len(columns) for index in support)):
        raise ValueError('kernel circuit requires3..8 distinct in-range group indices')
    total=0
    for index in support:
        total^=columns[index]
    if total:
        raise ValueError('circuit fixed-pair column XOR is nonzero')
    return True


def delta_active(vectors,support,d):
    if type(d) is not int or d<=0:
        raise ValueError('move vector d must be a nonzero integer mask')
    return sum(vectors[index]==0 for index in support)-sum(vectors[index]==d for index in support)


def apply_circuit(vectors,support,d):
    result=list(vectors)
    for index in support:
        result[index]^=d
    if sum(bool(x) for x in result)-sum(bool(x) for x in vectors)!=delta_active(vectors,support,d):
        raise AssertionError('active-count delta formula failed')
    return result


def enumerate_circuits(columns,baseline_vectors,*,max_circuits=50000,seed=0,combos=True):
    """Use O(p+active^2+max_circuits) storage, never all p^2 pair sums."""
    if type(max_circuits) is not int or not 1<=max_circuits<=50000:
        raise ValueError('max_circuits must be1..50000')
    if len(columns)!=len(baseline_vectors) or len(set(columns))!=len(columns) or any(not c for c in columns):
        raise ValueError('distinct nonzero columns and matching baseline vectors required')
    lookup={column:index for index,column in enumerate(columns)}
    active=[index for index,value in enumerate(baseline_vectors) if value]
    anchor_sums=defaultdict(list)
    for i,j in itertools.combinations(active,2):
        anchor_sums[columns[i]^columns[j]].append((i,j))
    circuits=[];seen=set();observed=Counter();retained=Counter()
    base_cap=max_circuits if not combos else max(1,max_circuits*4//5)
    triple_cap=max(1,base_cap//2)
    def add(support,kind,witness,cap):
        key=tuple(sorted(support))
        if key in seen:return
        observed[kind]+=1
        if len(circuits)>=cap:return
        validate_circuit(columns,key);seen.add(key)
        circuits.append(dict(support=list(key),class_id=kind,witness=witness));retained[kind]+=1
    # All pair sums are streamed. No quadratic pair-sum hash map is retained.
    for i in range(len(columns)):
        for j in range(i+1,len(columns)):
            third=lookup.get(columns[i]^columns[j])
            if third is not None and third>j:
                add((i,j,third),0,dict(pair=[i,j],third=third),triple_cap)
    for i in range(len(columns)):
        for j in range(i+1,len(columns)):
            for a,b in anchor_sums.get(columns[i]^columns[j],()):
                if len({i,j,a,b})==4:
                    add((i,j,a,b),1,dict(pair=[i,j],baseline_active_pair=[a,b]),base_cap)
    if combos and len(circuits)<max_circuits:
        base=list(circuits);by_group=defaultdict(list)
        for index,circuit in enumerate(base):
            for group in circuit['support']:by_group[group].append(index)
        rng=random.Random(seed);order=list(range(len(base)));rng.shuffle(order)
        for i in order:
            candidates=set(j for group in base[i]['support'] for j in by_group[group] if j!=i)
            candidates=sorted(candidates);rng.shuffle(candidates)
            for j in candidates[:64]:
                support=set(base[i]['support'])^set(base[j]['support'])
                if 3<=len(support)<=8:
                    add(support,2,dict(xor_of=[i,j]),max_circuits)
                if len(circuits)>=max_circuits:break
            if len(circuits)>=max_circuits:break
    for circuit in circuits:validate_circuit(columns,circuit['support'])
    return circuits,dict(pair_count=len(columns),baseline_active=len(active),
        baseline_pair_sum_keys=len(anchor_sums),retained={str(k):v for k,v in retained.items()},
        observed_before_caps={str(k):v for k,v in observed.items()},max_circuits=max_circuits,
        class_names={'0':'three-column','1':'four-column baseline-pair collision','2':'XOR of two retained3/4 circuits'},
        scope='A capped dictionary of known kernel moves, not an enumeration of all kernel directions.')


def prepare_system(dictionary,baseline,*,dimension=5,orientation='wu',max_circuits=50000,seed=0,combos=True):
    system=build_system(dictionary,dimension,orientation,baseline)
    if system['reduced']['contradictions'] or 'baseline_vectors' not in system:
        raise ValueError('kernel walk requires a verified feasible baseline')
    columns=[pair_column(pair,dimension*dimension) for pair in system['pairs']]
    circuits,summary=enumerate_circuits(columns,system['baseline_vectors'],max_circuits=max_circuits,seed=seed,combos=combos)
    summary.update(linear_rank=system['reduced']['rank'],linear_nullity=system['reduced']['nullity'],
                   orientation=orientation,columns_sha256=hashlib.sha256(json.dumps([hex(c) for c in columns]).encode()).hexdigest())
    return system,circuits,summary


def native_input(system,circuits):
    metadata=system['metadata'];n=metadata['dimension'];p=len(system['pairs'])
    lines=['MMKERNEL1',f'{n} {p} {len(circuits)}',
           ' '.join(map(str,ORIENTATIONS[metadata['orientation']]))]
    for pair,value in zip(system['pairs'],system['baseline_vectors']):
        lines.append(f'{pair[0]} {pair[1]} {value}')
    columns=[pair_column(pair,n*n) for pair in system['pairs']]
    for circuit in circuits:
        validate_circuit(columns,circuit['support'])
        lines.append(' '.join(map(str,[circuit['class_id'],len(circuit['support']),*circuit['support']])))
    return ('\n'.join(lines)+'\n').encode()


def decode_checked(system,vectors,metadata=None):
    if not satisfies(system,vectors):
        raise ValueError('raw free vectors violate original fixed-pair PW=Y equations')
    candidate=decode_vectors(system,vectors,metadata)
    report=verify_candidate(candidate,random_trials=0)
    n=system['metadata']['dimension']
    if (not report['valid'] or report['exact_entries_checked']!=n**6
            or report['rank']!=sum(bool(value) for value in vectors)):
        raise RuntimeError('free-factor axis decode failed independent exhaustive matrix verification')
    return candidate,report
