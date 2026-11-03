"""Wide3..128 circuit validation/serialization; never calls the old8-group guard."""
from .free_factor_kernel import pair_column
from .free_factor_sat import ORIENTATIONS


def validate_circuit(columns,support):
    if (not 3<=len(support)<=128 or len(set(support))!=len(support)
            or any(type(g) is not int or not 0<=g<len(columns) for g in support)):
        raise ValueError('wide circuit requires3..128 distinct in-range groups')
    total=0
    for g in support:total^=columns[g]
    if total:raise ValueError('wide circuit fixed-pair P*n is nonzero')
    return True


def native_input(system,circuits):
    n=system['metadata']['dimension'];p=len(system['pairs'])
    if len(circuits)>50000:raise ValueError('wide circuit storage cap50000 exceeded')
    lines=['MMKERNELWIDE1',f'{n} {p} {len(circuits)}',
           ' '.join(map(str,ORIENTATIONS[system['metadata']['orientation']]))]
    for pair,w in zip(system['pairs'],system['baseline_vectors']):lines.append(f'{pair[0]} {pair[1]} {w}')
    columns=[pair_column(pair,n*n) for pair in system['pairs']]
    for circuit in circuits:
        support=circuit['support'];kind=circuit['class_id'];validate_circuit(columns,support)
        if type(kind) is not int or kind not in (0,1,2) or (kind==0 and len(support)!=3) or (kind==1 and len(support)!=4):
            raise ValueError('wide circuit class/length metadata mismatch')
        lines.append(' '.join(map(str,[kind,len(support),*support])))
    return ('\n'.join(lines)+'\n').encode()


def modal_admissibility(vectors,circuits,headrooms=(6,9,12,16,24,32)):
    from collections import Counter
    baseline=sum(bool(w) for w in vectors);scores=[]
    for circuit in circuits:
        validate_values=[vectors[g] for g in circuit['support']]
        counts=Counter(w for w in validate_values if w)
        frequency=max(counts.values(),default=0);zeros=sum(w==0 for w in validate_values)
        scores.append(dict(support_size=len(validate_values),baseline_active_support=len(validate_values)-zeros,
                           zeros=zeros,modal_frequency=frequency,delta=zeros-frequency,new_rank=baseline+zeros-frequency))
    return dict(baseline_rank=baseline,counts={str(h):sum(s['delta']<=h for s in scores) for h in headrooms},
                scores=scores,scope='Initial modal proposals only; not a graph-connectivity or nonexistence result.')
