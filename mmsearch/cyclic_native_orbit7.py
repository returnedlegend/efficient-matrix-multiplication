"""New native-corpus whole-C3 metadata builder; no solver or optimization.

N5 construction remains disabled unless the caller explicitly authorizes it.
"""
from . import cyclic_tensor_code7 as c
from .cyclic_native_corpus7 import complete_orbits
from .sat_neighborhoods import gf2_rank
from scripts.audit_cyclic_tensor_code7 import audit_columns
from scripts.audit_c3_cube_space7 import column_basis,xor
from scripts.audit_c3_quotient_wedge7 import quotient_projection,project,wedge,full_tensor_projection


def build_metadata(schemas,seed_atoms,old_representatives,old_cube_forms,n,*,allow_n5=False,guard=lambda *_:None,progress=None):
    if type(n) is not int or not 1<=n<=5 or n>3 and (n!=5 or allow_n5 is not True):raise ValueError('N5 dictionary preparation needs explicit authorization')
    if not 1<=len(schemas)<=24:raise ValueError('at most24 complete source schemas')
    width=n*n;old_representatives=tuple(tuple(t) for t in old_representatives);old_set=set(old_representatives);atoms=list(old_representatives)
    for schema in schemas:
        complete_orbits(schema['atoms'],n);atoms.extend(schema['atoms'])
    complete_orbits(seed_atoms,n);atoms.extend(seed_atoms)
    dictionary,report=audit_columns(atoms,seed_atoms,n,guard,max_orbits=2000,progress=progress)
    reps=[tuple(t) for t in dictionary['representatives']];lookup={t:i for i,t in enumerate(reps)};full=[int(v,16) for v in dictionary['full_columns_hex']];target=int(dictionary['target_hex'],16);weights=dictionary['weights'];kernel=[int(v,16) for v in dictionary['kernel_hex']];states=[]
    for schema in schemas:
        guard('loop');state=sum(1<<lookup[t] for t in complete_orbits(schema['atoms'],n));cost=sum(weights[i] for i in c._bits(state))
        if cost!=len(schema['atoms']) or c.xor_columns(full,state)!=target:raise ValueError('registered complete source state fails exact dictionary target')
        states.append(dict(id=schema['id'],state_hex=hex(state),product_cost=cost,source_raw_sha256=schema.get('raw_sha256')))
    projection=quotient_projection(old_cube_forms,width);q=projection['quotient_width'];qcolumns=projection['projection_columns'];exterior=[];projection_records=[];new_nonzero=[];checked=0
    for index,rep in enumerate(reps):
        guard('loop');factors=[project(v,qcolumns) for v in rep];factor_rank=gf2_rank(factors);value=wedge(*factors,q)
        if bool(value)!=(factor_rank==3):raise ValueError('exterior zero and quotient factor dependence differ')
        is_new=rep not in old_set
        if is_new and value:new_nonzero.append(index)
        if is_new and value and checked<8:
            if full_tensor_projection(full[index],qcolumns,q)!=value:raise ValueError('natural fulltensor exterior projection differs')
            checked+=1
        exterior.append(value);projection_records.append(dict(column=index,is_new=is_new,quotient_factor_rank=factor_rank,exterior_hex=hex(value)))
    full_rank=len(column_basis(full,guard)[0]);f_rank=len(column_basis(exterior,guard)[0]);old_indices=[lookup[t] for t in old_representatives]
    old_full_rank=len(column_basis([full[i] for i in old_indices],guard)[0]);old_f_rank=len(column_basis([exterior[i] for i in old_indices],guard)[0])
    for witness in kernel:
        guard('loop')
        if c.xor_columns(exterior,witness):raise ValueError('computed natural exterior map violates a fulltensor relation')
    cubes=[i for i,w in enumerate(weights) if w==1];forms=[reps[i][0] for i in cubes];cube_projection=[sum(((mask>>i)&1)<<j for j,i in enumerate(cubes)) for mask in kernel]
    report.update(old_dictionary_orbits=len(old_representatives),added_orbits=len(reps)-len(old_representatives),quotient_by_old_cube_K=projection,old_cube_K_rank=gf2_rank(old_cube_forms),cube_factor_rank=gf2_rank(forms),cube_factor_rank_added_mod_old_K=gf2_rank(list(forms)+list(old_cube_forms))-gf2_rank(old_cube_forms),kernel_cube_coordinate_projection_rank=len(column_basis(cube_projection,guard)[0]),old_full_rank=old_full_rank,old_F_rank=old_f_rank,F_rank=f_rank,F_rank_added=f_rank-old_f_rank,kernel_of_F_on_dictionary_span_dimension=full_rank-f_rank,new_nonzero_F_orbits=len(new_nonzero),new_nonzero_F_column_indices=new_nonzero,independent_fulltensor_F_columns_checked=checked,all_fulltensor_kernel_relations_respected_by_F=True,registered_source_states=states,barrier_diagnostic='Nonzero F orbit factors are independent modulo old cube K and escape the wedge-zero domination hypothesis. This alone is not a cost improvement or solution existence proof.',optimization_calls=0,solver_calls=0,decoder_calls=0)
    dictionary.update(format='cyclic-native-orbit7-dictionary-v1',registered_source_states=states,old_to_new_column_indices=old_indices,exterior_columns_hex=[hex(v) for v in exterior],scope='New approved nativeC3 finite dictionary; metadata only, nooptimization/noCPexistenceclaim.')
    return dictionary,report,projection_records
