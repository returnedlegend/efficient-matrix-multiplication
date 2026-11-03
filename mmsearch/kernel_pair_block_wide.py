"""Wide-support model validation using the unchanged exact pair optimizer."""
from .kernel_pair_block import apply_pair,optimize_pair,partition,single_optimum
from .free_factor_kernel import decode_checked,pair_column
from .free_factor_kernel_wide import validate_circuit


def validate_pair_solution(system,circuits,record):
    i,j=record['circuit_i'],record['circuit_j']
    if type(i) is not int or type(j) is not int or not 0<=i<j<len(circuits):
        raise ValueError('invalid wide native circuit-pair indices')
    d,e=record['d'],record['e'];width=system['metadata']['width']
    if any(type(value) is not int or not 0<=value<1<<width for value in (d,e)):
        raise ValueError('invalid wide native direction mask')
    columns=[pair_column(pair,width) for pair in system['pairs']]
    for index in (i,j):validate_circuit(columns,circuits[index]['support'])
    optimum=optimize_pair(system['baseline_vectors'],circuits[i]['support'],circuits[j]['support'])
    moved=apply_pair(system['baseline_vectors'],circuits[i]['support'],circuits[j]['support'],d,e)
    rank=sum(bool(w) for w in moved)
    if rank!=sum(bool(w) for w in system['baseline_vectors'])+optimum['delta'] or rank!=record['after_rank']:
        raise ValueError('native wide block disagrees with independent exact optimum')
    candidate,report=decode_checked(system,moved,dict(method='exact-wide-two-kernel-direction-block',
                                  circuit_i=i,circuit_j=j,d=d,e=e,exact_block_optimum=optimum))
    return moved,candidate,report
