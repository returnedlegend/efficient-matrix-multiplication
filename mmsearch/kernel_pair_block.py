"""Exact two-kernel-direction sparsity optimization, including zero shifts."""
from collections import Counter

from .free_factor_kernel import decode_checked,pair_column,validate_circuit


def partition(s1,s2):
    a=set(s1);b=set(s2)
    return sorted(a-b),sorted(b-a),sorted(a&b)


def single_optimum(vectors,support):
    counts=Counter(vectors[g] for g in support)
    if not counts:return dict(d=0,delta=0,score=0)
    d=min(counts,key=lambda value:(-counts[value],value))
    return dict(d=d,delta=counts[0]-counts[d],score=counts[d])


def optimize_pair(vectors,s1,s2):
    a,b,c=partition(s1,s2)
    counts=[Counter(vectors[g] for g in group) for group in (a,b,c)]
    ca,cb,cc=counts;zeros=ca[0]+cb[0]+cc[0]
    candidates={(0,0)}
    candidates.update((d,0) for d in ca);candidates.update((0,e) for e in cb)
    candidates.update((0,t) for t in cc);candidates.update((t,0) for t in cc)
    candidates.update((d,e) for d in ca for e in cb)
    candidates.update((d,d^t) for d in ca for t in cc)
    candidates.update((e^t,e) for e in cb for t in cc)
    def score(move):
        d,e=move;return ca[d]+cb[e]+cc[d^e]
    d,e=min(candidates,key=lambda move:(-score(move),move))
    best=score((d,e))
    return dict(d=d,e=e,score=best,initial_zeros=zeros,delta=zeros-best,
                upper_bound=sum(max(count.values(),default=0) for count in counts),
                candidate_count=len(candidates),partition=dict(a=a,b=b,c=c))


def apply_pair(vectors,s1,s2,d,e):
    result=list(vectors)
    for group in s1:result[group]^=d
    for group in s2:result[group]^=e
    return result


def validate_pair_solution(system,circuits,record):
    i,j=record['circuit_i'],record['circuit_j']
    if type(i) is not int or type(j) is not int or not 0<=i<j<len(circuits):
        raise ValueError('invalid native circuit-pair witness indices')
    d,e=record['d'],record['e'];width=system['metadata']['width']
    if any(type(value) is not int or not 0<=value<1<<width for value in (d,e)):
        raise ValueError('invalid native two-direction masks')
    columns=[pair_column(pair,width) for pair in system['pairs']]
    for index in (i,j):validate_circuit(columns,circuits[index]['support'])
    optimum=optimize_pair(system['baseline_vectors'],circuits[i]['support'],circuits[j]['support'])
    moved=apply_pair(system['baseline_vectors'],circuits[i]['support'],circuits[j]['support'],d,e)
    rank=sum(bool(w) for w in moved)
    if rank!=sum(bool(w) for w in system['baseline_vectors'])+optimum['delta'] or rank!=record['after_rank']:
        raise ValueError('native witness is not an exact optimal block result')
    candidate,report=decode_checked(system,moved,dict(method='exact-two-kernel-direction-block',
                                  circuit_i=i,circuit_j=j,d=d,e=e,exact_block_optimum=optimum))
    return moved,candidate,report
