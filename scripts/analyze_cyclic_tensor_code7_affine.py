"""Read-only affine metadata analysis; never constructs tensors or searches states."""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def mask_rank(values):
    basis={}
    for value in values:
        while value:
            pivot=value.bit_length()-1
            if pivot not in basis:basis[pivot]=value;break
            value^=basis[pivot]
    return len(basis)


def summarize(weights,seed,kernel,target=92):
    if any(type(w) is not int or w not in (1,3) for w in weights):raise ValueError('literal orbit weights1/3 required')
    if type(seed) is not int or seed<0 or seed.bit_length()>len(weights):raise ValueError('bad seed selection')
    if any(type(value) is not int or value<=0 or value.bit_length()>len(weights) for value in kernel):raise ValueError('bad kernel support')
    cubes=[index for index,weight in enumerate(weights) if weight==1]
    projected=[sum(((value>>index)&1)<<position for position,index in enumerate(cubes)) for value in kernel]
    seed_cube=sum(((seed>>index)&1)<<position for position,index in enumerate(cubes))
    dependencies=[sum((value>>index)&1 for value in kernel) for index in range(len(weights))]
    seed_cost=sum(weight for index,weight in enumerate(weights) if (seed>>index)&1)
    even_kernel=all(value.bit_count()%2==0 for value in kernel)
    # A complete basis with cube projections0/111 means every affine cube state
    # is000 or111. Cost is then3*(nonfixed selections+one cube switch).
    locked_triple=(len(cubes)==3 and seed_cube in (0,7) and set(projected)<={0,7})
    residue=3 if locked_triple and even_kernel and seed_cost%2 else None
    effective=target-((target-residue)%6) if residue is not None else target
    return {'orbit_variables':len(weights),'kernel_variables':len(kernel),'weighted_literals':sum(weights),'cube_columns':cubes,'cube_projection_rank':mask_rank(projected),'kernel_cube_projection_masks':sorted(set(projected)),
            'seed_cube_mask':seed_cube,'cube_all_together':locked_triple,'all_kernel_supports_even':even_kernel,'seed_cost':seed_cost,'all_feasible_costs_mod6':residue,'requested_target':target,'equivalent_bound_from_mod6':effective,
            'dependency_support_histogram':dict(sorted(collections.Counter(dependencies).items())),'dependency_incidences':sum(dependencies),'maximum_dependency':max(dependencies,default=0),'one_variable_selection_rows':dependencies.count(1),
            'xor_gates_with_selection_as_outputs':sum(max(0,count-1) for count in dependencies),'internal_xor_auxiliaries_with_selection_as_outputs':sum(max(0,count-2) for count in dependencies),
            'affine_clause_upper_bound':4*sum(max(0,count-1) for count in dependencies)+2*dependencies.count(1)+dependencies.count(0),
            'scope':'Assumes the input kernel is the complete independently audited kernel. Counts/projection only; no candidate enumeration, minimum-weight calculation, tensor construction, encoding build or solver call.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--audit',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit=a.audit.resolve()
    if (audit/'UNKNOWN.json').exists():raise ValueError('incomplete audit')
    seal=json.loads((audit/'COMPLETE.json').read_bytes());manifest=json.loads((audit/'manifest.json').read_bytes());dictionary=json.loads((audit/'dictionary.json').read_bytes())
    if sha(audit/'manifest.json')!=seal['manifest_sha256'] or sha(audit/'checksums.json')!=seal['checksums_sha256'] or sha(audit/'dictionary.json')!=manifest['dictionary_sha256']:raise ValueError('completed audit byte pins differ')
    kernel=[int(value,16) for value in dictionary['kernel_hex']]
    if len(kernel)!=manifest['nullity'] or manifest['independent_kernel_rank']!=len(kernel):raise ValueError('complete kernel witness metadata differs')
    result=summarize(dictionary['weights'],int(dictionary['seed_state_hex'],16),kernel)
    result.update(format='cyclic-orbit-code7-affine-analysis-v1',audit=str(audit),dictionary_sha256=sha(audit/'dictionary.json'),audit_manifest_sha256=sha(audit/'manifest.json'),source_sha256=sha(__file__),production_queries_started=0,solver_calls=0)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as stream:json.dump(result,stream,sort_keys=True,indent=2);stream.write('\n')
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':main()
