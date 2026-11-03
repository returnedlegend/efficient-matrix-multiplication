"""Static exterior projection of the approved C3 column span, no search."""
import argparse
from functools import lru_cache
import itertools
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from mmsearch import cyclic_tensor_code7 as c
from mmsearch.compact_sat import BinaryBasis
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.marathon7_cancel_poller import CancelPoller
from scripts.audit_c3_cube_space7 import column_basis,seal_check,xor
from scripts.audit_c3_mixed_s4_space7 import (BASE,BASE_DICT,BASE_MANIFEST,CAMPAIGN,CAMPAIGN_SHA,CAP,DEADLINE,code_pins,sha)
from scripts.audit_cyclic_tensor_code7 import independent_orbit_tensor,raw
OUT=CAMPAIGN/'c3-quotient-wedge-audit-001'


@lru_cache(maxsize=25)
def triples(width):
    if type(width) is not int or not 0<=width<=25:raise ValueError('literal width0..25 required')
    return tuple(itertools.combinations(range(width),3))


def quotient_projection(kernel,width):
    if type(width) is not int or not 0<=width<=25 or any(type(v) is not int or v<0 or v>>width for v in kernel):raise ValueError('invalid quotient kernel')
    basis=BinaryBasis(kernel);remaining=[i for i in range(width) if i not in basis.pivots]
    def project(value):
        residue=value^basis.expand(basis.coordinates(value))
        return sum(((residue>>position)&1)<<i for i,position in enumerate(remaining))
    columns=[project(1<<i) for i in range(width)]
    return dict(width=width,quotient_width=len(remaining),kernel_basis=basis.vectors,
                remaining_coordinate_positions=remaining,projection_columns=columns)


def project(value,columns):
    if type(value) is not int or value<0 or value>>len(columns):raise ValueError('invalid projection vector')
    return xor(columns,value)


def wedge(a,b,d,width):
    if any(type(v) is not int or v<0 or v>>width for v in (a,b,d)):raise ValueError('invalid exterior factor')
    answer=0
    for index,(i,j,k) in enumerate(triples(width)):
        value=(((a>>i)&1)*((b>>j)&1)*((d>>k)&1)
             ^((a>>i)&1)*((b>>k)&1)*((d>>j)&1)
             ^((a>>j)&1)*((b>>i)&1)*((d>>k)&1)
             ^((a>>j)&1)*((b>>k)&1)*((d>>i)&1)
             ^((a>>k)&1)*((b>>i)&1)*((d>>j)&1)
             ^((a>>k)&1)*((b>>j)&1)*((d>>i)&1))
        answer|=value<<index
    return answer


def full_tensor_projection(tensor,projection,quotient_width):
    """Coefficient-level natural exterior map, independent of orbit factors."""
    width=len(projection);answer=0;lookup={value:i for i,value in enumerate(triples(quotient_width))}
    while tensor:
        bit=tensor&-tensor;flat=bit.bit_length()-1;tensor^=bit
        a,b,d=flat//(width*width),flat//width%width,flat%width
        for i,j,k in itertools.product(*(tuple(c._bits(projection[x])) for x in (a,b,d))):
            if len({i,j,k})==3:answer^=1<<lookup[tuple(sorted((i,j,k)))]
    return answer


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--authorize-static-wedge-audit',action='store_true');a=p.parse_args(argv)
    if not a.authorize_static_wedge_audit:p.error('explicit root-authorized exterior audit required')
    started=time.monotonic();cpu_started=time.process_time()
    if OUT.exists() or sha(CAMPAIGN/'campaign.json')!=CAMPAIGN_SHA:raise ValueError('new output/matching campaign required')
    os.sched_setaffinity(0,{1});os.setpriority(os.PRIO_PROCESS,0,10)
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    guard=CampaignGuard(30,DEADLINE,guard_state=CAMPAIGN/'operations-v3/state.json',campaign_dir=CAMPAIGN)
    guard.check('pre_static_inputs');poller=CancelPoller(guard,lambda:started+30)
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    def check(name='loop'):
        if name=='loop':
            if poller.cancelled():poller.force_check(name)
        else:poller.force_check(name)
    seal_check(BASE,BASE_DICT,BASE_MANIFEST);pins=code_pins();OUT.mkdir();progress={'columns_projected':0}
    def save(name,value):
        check('pre_publication');payload=raw(value)
        if sum(q.stat().st_size for q in OUT.iterdir() if q.is_file())+len(payload)>CAP:raise RuntimeError('32MiB aggregate audit cap')
        with (OUT/name).open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        check('post_publication')
    def alarm(*_):raise TimeoutError('30s exterior static audit alarm')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,max(.001,30-(time.monotonic()-started)))
    try:
        save('config.json',dict(format='c3-quotient-wedge-static-config-v1',base_dictionary_sha256=BASE_DICT,base_manifest_sha256=BASE_MANIFEST,
             seconds=30,cpu=1,nice=10,memory_mib=1024,runtime_code_sha256=pins,solver_calls=0,decoder_calls=0,optimization_calls=0))
        base=json.loads((BASE/'dictionary.json').read_bytes());cube_indices=[i for i,w in enumerate(base['weights']) if w==1]
        forms=[base['representatives'][i][0] for i in cube_indices]
        if forms!=[4096,262208,16777217] or len(base['representatives'])!=275:raise ValueError('approved base/cubes differ')
        projection=quotient_projection(forms,25);q=projection['quotient_width'];columns=projection['projection_columns']
        if q!=22 or any(project(f,columns) for f in forms) or len(column_basis(columns)[0])!=22:raise ValueError('quotient projection kernel/rank differs')
        save('quotient-projection.json',projection)
        exterior=[];payload=[];full=[int(v,16) for v in base['full_columns_hex']]
        for index,term in enumerate(base['representatives']):
            check();factors=[project(v,columns) for v in term]
            value=0 if base['weights'][index]==1 else wedge(*factors,q)
            if index<8:
                tensor=independent_orbit_tensor(c.orbit(term,5),25)
                if tensor!=full[index] or full_tensor_projection(tensor,columns,q)!=value:raise ValueError('independent fulltensor exterior projection differs')
            exterior.append(value);payload.append(dict(column=index,weight=base['weights'][index],quotient_factors_hex=[hex(v) for v in factors],exterior_column_hex=hex(value)))
            progress['columns_projected']+=1
        base_basis,old_indices=column_basis(full,check);projected_basis,projected_indices=column_basis(exterior,check)
        if len(base_basis)!=201:raise ValueError('old fulltensor rank differs')
        # A linear map must annihilate every old full-tensor relation, not only
        # match an inferred orbit count. Reconstruct all275 dependencies.
        for index,value in enumerate(full):
            check();mask=0
            for bit in sorted(base_basis,reverse=True):
                if value>>bit&1:
                    row,witness=base_basis[bit];value^=row;mask^=witness
            if value or xor(exterior,mask)!=exterior[index]:raise ValueError('exterior map doesnot respect fulltensor column relation')
        kernel_dim=201-len(projected_basis);cube_tensors=[full[i] for i in cube_indices]
        if len(column_basis(cube_tensors)[0])!=3 or any(exterior[i] for i in cube_indices):raise ValueError('oldcube kernel inclusion failed')
        witness=dict(base_rank=201,exterior_rank=len(projected_basis),kernel_on_old_span_dimension=kernel_dim,
          base_independent_column_indices=old_indices,projected_independent_column_indices=projected_indices,
          exterior_pivot_basis=[dict(pivot=bit,reduced_column_hex=hex(row),original_column_mask_hex=hex(mask)) for bit,(row,mask) in sorted(projected_basis.items(),reverse=True)],
          old_cube_indices=cube_indices,old_cube_product_weights=[1]*3,all275_fulltensor_relations_respected=True)
        save('column-projections.json',payload);save('rank-witness.json',witness)
        seal_check(BASE,BASE_DICT,BASE_MANIFEST)
        if any(sha(ROOT/name)!=pin for name,pin in pins.items()):raise ValueError('runtime changed')
        manifest=dict(format='c3-quotient-wedge-static-audit-v1',status='SEALED_STATIC_AUDIT',base_dictionary_sha256=BASE_DICT,base_manifest_sha256=BASE_MANIFEST,
          quotient_width=q,exterior_coordinates=len(triples(q)),base_rank=201,projected_rank=len(projected_basis),kernel_on_old_span_dimension=kernel_dim,
          kernel_exact_oldcube_span=kernel_dim==3,quotient_dependent_whole_orbit_extensions_dominated=kernel_dim==3,coupling_potential_only=kernel_dim>3,
          independent_fulltensor_columns_checked=8,independent_fulltensor_entries_checked=8*15625,
          projection_sha256=sha(OUT/'quotient-projection.json'),column_projection_sha256=sha(OUT/'column-projections.json'),rank_witness_sha256=sha(OUT/'rank-witness.json'),
          elapsed_seconds=time.monotonic()-started,process_cpu_seconds=time.process_time()-cpu_started,runtime_code_sha256=pins,guard=guard.observation(),poller=poller.metrics(),
          solver_calls=0,decoder_calls=0,optimization_calls=0,extended_dictionaries_generated=0,
          scope='Static exterior projection of approvedold201-dimensional span only. No feasibility query, candidate, newdictionary, or globalCP lower bound.')
        save('manifest.json',manifest);save('checksums.json',{q.name:sha(q) for q in OUT.iterdir() if q.is_file()});save('COMPLETE.json',dict(manifest_sha256=sha(OUT/'manifest.json'),checksums_sha256=sha(OUT/'checksums.json')))
        for q in OUT.iterdir():
            if q.is_file():q.chmod(0o444)
        print(json.dumps({k:manifest[k] for k in ('status','projected_rank','kernel_on_old_span_dimension','kernel_exact_oldcube_span','elapsed_seconds','process_cpu_seconds')},sort_keys=True));return 0
    except Exception as error:
        with (OUT/'UNKNOWN.json').open('xb') as stream:stream.write(raw(dict(status='UNKNOWN_STATIC_AUDIT',reason=type(error).__name__+': '+str(error),progress=progress,solver_calls=0,decoder_calls=0)))
        raise
    finally:signal.setitimer(signal.ITIMER_REAL,0)


if __name__=='__main__':raise SystemExit(main())
