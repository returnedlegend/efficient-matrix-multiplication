"""Static isolated-extension domination and <=11-column C3 cube-space audit.

No dictionary expansion, candidate decoding, solver or optimization is performed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from mmsearch import cyclic_tensor_code7 as c
from scripts.audit_cyclic_tensor_code7 import independent_orbit_tensor,raw
from scripts import tensor_code7 as lifecycle

BASE_DICT='23ff2b7ef344b79277712731cdc80ecc4b030a82026ca77d9fec32a02ebd047b'
BASE_MANIFEST='eb6337722adaf26ecc3e11795cc94865c2a556db7af70d4efd83b917bb0a392b'
EXT_DICT='4b94540939eaa1f7c06d777729bfb2d2f28312eac81dfb2d7a3beb83098c00fb'
EXT_MANIFEST='abaf21f4402c02ef0175b98fe90c82dc76c5c7a2b861a291e9c956346eae2dbd'
DEADLINE='2026-11-03T19:24:17Z'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return lifecycle.strict_load(Path(path).read_bytes())
def xor(values,mask):
    result=0
    for index in c._bits(mask):result^=values[index]
    return result


def column_basis(columns,guard=lambda *_:None):
    basis={};pivots=[]
    for index,value in enumerate(columns):
        guard('loop');witness=1<<index
        while value:
            bit=value.bit_length()-1
            if bit not in basis:basis[bit]=(value,witness);pivots.append(index);break
            row,mask=basis[bit];value^=row;witness^=mask
    return basis,pivots


def intersection_witnesses(base_columns,space_columns,guard=lambda *_:None):
    base,pivots=column_basis(base_columns,guard);space_basis,_=column_basis(space_columns,guard)
    if len(space_basis)!=len(space_columns):raise ValueError('audit space columns must be independent')
    quotient={};quotient_pivots=[];intersection=[]
    for index,original in enumerate(space_columns):
        guard('loop');value=original;base_mask=0;space_mask=1<<index
        for bit in sorted(base,reverse=True):
            if (value>>bit)&1:row,mask=base[bit];value^=row;base_mask^=mask
        while value:
            bit=value.bit_length()-1
            if bit not in quotient:
                quotient[bit]=(value,space_mask,base_mask);quotient_pivots.append(index);break
            row,smask,bmask=quotient[bit];value^=row;space_mask^=smask;base_mask^=bmask
        if not value:
            tensor=xor(space_columns,space_mask)
            if not tensor or tensor!=xor(base_columns,base_mask):raise ValueError('intersection tensor witness differs')
            intersection.append({'space_mask_hex':hex(space_mask),'base_mask_hex':hex(base_mask),'tensor_hex':hex(tensor)})
    if len(column_basis([int(item['tensor_hex'],16) for item in intersection],guard)[0])!=len(intersection):raise ValueError('dependent intersection witnesses')
    union_rank=len(base)+len(quotient)
    if len(base)+len(space_columns)-union_rank!=len(intersection):raise ValueError('intersection rank identity differs')
    return {'base_rank':len(base),'space_rank':len(space_columns),'union_rank':union_rank,'quotient_rank':len(quotient),'intersection_dimension':len(intersection),'base_independent_column_indices':pivots,'quotient_independent_space_indices':quotient_pivots,'intersection_witnesses':intersection}


def domination(base,extension,extension_manifest):
    indices=extension_manifest['new_column_indices'];weights=extension['weights'];kernel=[int(value,16) for value in extension['kernel_hex']];seed=int(extension['seed_state_hex'],16)
    mapping=extension_manifest['old_to_new_column_map']
    if len(mapping)!=len(base['weights']) or set(mapping)!=set(range(len(weights)))-set(indices):raise ValueError('base embedding coordinate map differs')
    for i,j in enumerate(mapping):
        if any(extension[key][j]!=base[key][i] for key in ['representatives','weights','full_columns_hex','compressed_columns_hex']):raise ValueError('base embedding column differs')
    if sum(((seed>>j)&1)<<i for i,j in enumerate(mapping))!=int(base['seed_state_hex'],16):raise ValueError('base source embedding differs')
    if len(column_basis(kernel)[0])!=len(kernel):raise ValueError('extended kernel witness basis is dependent')
    if len(indices)!=3 or len(set(indices))!=3:raise ValueError('exact three new coordinates required')
    projection=[sum(((value>>index)&1)<<j for j,index in enumerate(indices)) for value in kernel]
    rank=len(column_basis(projection)[0]);seed_projection=sum(((seed>>index)&1)<<j for j,index in enumerate(indices))
    relation=int(extension['polarization_relation_hex'],16);new_mask=sum(1<<i for i in indices);old_part=relation&~new_mask
    new_weight=sum(weights[i] for i in indices);old_weight=sum(weights[i] for i in c._bits(old_part));full=[int(value,16) for value in extension['full_columns_hex']]
    if any(xor(full,value) for value in kernel):raise ValueError('extended kernel witness syndrome differs')
    if rank!=1 or set(projection)-{0}!={7} or seed_projection or ((relation&new_mask)!=new_mask) or xor(full,relation):raise ValueError('new-coordinate domination premises fail')
    if new_weight!=7 or old_weight!=2 or any(weights[i]!=1 for i in c._bits(old_part)):raise ValueError('weighted dominance premise differs')
    if extension_manifest['full_rank']!=203 or extension_manifest['nullity']!=75 or len(kernel)!=75 or extension_manifest['independent_kernel_rank']!=75:raise ValueError('complete extended kernel certificate differs')
    return {'new_coordinate_projection_rank':rank,'new_coordinate_projection_masks':sorted(set(projection)),'seed_new_coordinate_mask':seed_projection,'new_coordinate_weights':[weights[i] for i in indices],'new_branch_product_cost':new_weight,'old_toggled_cube_indices':list(c._bits(old_part)),'old_toggle_cost_at_most':old_weight,'strict_cost_decrease_at_least':new_weight-old_weight,'finite_dictionary_optimum_unchanged':True,'proof':'Every affine solution has new coordinates000 or111. For111, XOR the certified zero relation: all new coordinates vanish, removing cost7 while toggling only two old cubes of total cost<=2. This produces a base solution at least5 products cheaper. New000 solutions are already base solutions. Base embeddings show equality of finite-dictionary optima.'}


def seal_check(directory,dictionary_sha,manifest_sha):
    if sha(directory/'dictionary.json')!=dictionary_sha or sha(directory/'manifest.json')!=manifest_sha or (directory/'UNKNOWN.json').exists():raise ValueError('sealed input differs')
    seal=read(directory/'COMPLETE.json')
    if seal['manifest_sha256']!=manifest_sha or sha(directory/'checksums.json')!=seal['checksums_sha256']:raise ValueError('input completion seal differs')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--expected-config-sha256',required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--authorize-space-audit',action='store_true');p.add_argument('--preview',action='store_true');a=p.parse_args(argv)
    if not a.authorize_space_audit:p.error('explicit one-shot static audit authorization required')
    started=time.monotonic();cpu_started=time.process_time()
    if sha(a.config)!=a.expected_config_sha256:raise ValueError('frozen configuration differs')
    config=read(a.config);campaign=Path(config['campaign']);base_path=Path(config['base_audit']);ext_path=Path(config['extension_audit']);out=a.output_dir.resolve()
    if out.exists() or not out.is_relative_to(campaign) or config['max_space_columns']!=11:raise ValueError('new output and <=11-column space required')
    os.sched_setaffinity(0,{1});os.setpriority(os.PRIO_PROCESS,0,10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    guard=lifecycle.Guard(DEADLINE,10,campaign,campaign/'operations-v3/state.json',config['campaign_sha256']);guard('pre_static_inputs');seal_check(base_path,BASE_DICT,BASE_MANIFEST);seal_check(ext_path,EXT_DICT,EXT_MANIFEST)
    for name,digest in config['runtime_code_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('runtime changed: '+name)
    if a.preview:print(json.dumps({'status':'PREVIEW_ONLY','zero_mutations':True,'space_columns_generated':0,'optimization_calls':0},sort_keys=True));return 0
    out.mkdir();progress={'stage':'static_domination'}
    def save(name,value):
        guard('pre_publication');path=out/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(value if isinstance(value,bytes) else raw(value));stream.flush();os.fsync(stream.fileno())
        guard('post_publication')
    def alarm(*_):raise lifecycle.Stop('10s hard static-space audit alarm')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,max(.001,10-(time.monotonic()-started)))
    try:
        save('config.json',a.config.read_bytes());base=read(base_path/'dictionary.json');extension=read(ext_path/'dictionary.json');em=read(ext_path/'manifest.json');dom=domination(base,extension,em);guard('post_static_domination')
        save('single-polarization-domination.json',dom);forms=[term[0] for term,weight in zip(base['representatives'],base['weights']) if weight==1]
        if forms!=[4096,262208,16777217] or len(column_basis(forms)[0])!=3:raise ValueError('approved independent cube forms differ')
        descriptors=[('cube'+str(i),(forms[i],)*3) for i in range(3)]
        descriptors += [('mixed'+str(i)+str(j),(forms[i],forms[i],forms[j])) for i in range(3) for j in range(3) if i!=j]
        descriptors += [('orientation012',tuple(forms)),('orientation021',(forms[0],forms[2],forms[1]))]
        if len(descriptors)!=11:raise ValueError('C3 space basis must have exactly11 tensors')
        guard('pre_space_column_stage');columns=[];basis_payload=[];progress.update(stage='space_columns',checked_columns=0)
        for label,term in descriptors:
            guard('loop');tensor=c.orbit_tensor(term,5)
            if tensor!=independent_orbit_tensor(c.orbit(term,5),25):raise ValueError('independent basis tensor differs')
            compressed=c.compress_invariant(tensor,25)
            if c.expand_invariant(compressed,25)!=tensor:raise ValueError('space projection/inverse differs')
            columns.append(tensor);basis_payload.append({'label':label,'representative':list(c.orbit_representative(term,5)),'full_tensor_hex':hex(tensor),'invariant_tensor_hex':hex(compressed)});progress['checked_columns']=len(columns)
        guard('post_space_column_stage');progress['stage']='intersection_elimination';base_columns=[int(value,16) for value in base['full_columns_hex']]
        guard('pre_intersection_elimination');result=intersection_witnesses(base_columns,columns,lambda _='loop':guard('loop'));guard('post_intersection_elimination')
        if result['base_rank']!=201 or result['space_rank']!=11:raise ValueError('base or space rank differs')
        # The first3 space columns are the actual existing three cube columns.
        for i,form in enumerate(forms):
            old_index=base['representatives'].index([form,form,form])
            if columns[i]!=base_columns[old_index]:raise ValueError('old cube inclusion differs')
        exact_cube_span=result['intersection_dimension']==3
        if exact_cube_span and any(int(item['space_mask_hex'],16)&~7 for item in result['intersection_witnesses']):raise ValueError('intersection exceeds diagonal cube coordinates')
        save('space-basis.json',basis_payload);save('rank-intersection-witness.json',result)
        proof=('LetB be the original column span andS=C3-invariant tensors inV^tensor3. T belongsB. In any extension by whole orbits whose factors lie inV, the sumY of added terms equalsT+old_part and hence liesS intersectionB. This audit finds S intersectionB=span(a1^cube,a2^cube,a3^cube). WriteY=sum lambda_i ai^cube. Independent factor forms imply a flattening rank equal to the number of nonzero lambda_i, so any new-term representation costs at least that many products. ReplacingY by the existing selected cubes and canceling duplicates cannot cost more. Therefore the finite-dictionary optimum is unchanged under the whole pureV orbit closure.' if exact_cube_span else 'Intersection exceeds old cube span. This shows coupling potential only; no weight improvement or target feasibility is established.')
        save('proof.json',{'single_extension':dom['proof'],'whole_space_closure_dominated':exact_cube_span,'proof':proof,'scope':'Finite original dictionary plus orbit factors inside this approved3D cube-factor span only; no claim about interacting outside directions.'})
        for name,digest in config['runtime_code_sha256'].items():
            if sha(ROOT/name)!=digest:raise ValueError('runtime changed during audit')
        seal_check(base_path,BASE_DICT,BASE_MANIFEST);seal_check(ext_path,EXT_DICT,EXT_MANIFEST);guard('final_checks')
        manifest={'format':'c3-cube-space7-static-audit-v1','status':'SEALED_STATIC_SPACE_AUDIT','single_polarization_domination':dom,'cube_forms':forms,'cube_factor_rank':3,'space_columns':11,'space_independent_coefficients_checked':11*15625,'base_rank':201,'space_rank':11,'union_rank':result['union_rank'],'intersection_dimension':result['intersection_dimension'],'intersection_exact_old_cube_span':exact_cube_span,'whole_pure_cube_span_closure_dominated':exact_cube_span,'coupling_potential_only':not exact_cube_span,'base_dictionary_sha256':BASE_DICT,'base_manifest_sha256':BASE_MANIFEST,'extension_dictionary_sha256':EXT_DICT,'extension_manifest_sha256':EXT_MANIFEST,'runtime_code_sha256':config['runtime_code_sha256'],'config_sha256':a.expected_config_sha256,'runtime':lifecycle.runtime(),'guard':guard.observation(),'process_cpu_seconds':time.process_time()-cpu_started,'elapsed_seconds':time.monotonic()-started,'optimization_calls':0,'solver_calls':0,'candidate_states_generated':0,'extended_dictionaries_generated':0}
        save('manifest.json',manifest);save('checksums.json',{str(q.relative_to(out)):sha(q) for q in out.rglob('*') if q.is_file()});save('COMPLETE.json',{'manifest_sha256':sha(out/'manifest.json'),'checksums_sha256':sha(out/'checksums.json'),'acceptance':'Require matching pins and no UNKNOWN.json.'})
        for q in out.rglob('*'):
            if q.is_file():q.chmod(0o444)
        print(json.dumps({key:manifest[key] for key in ['status','base_rank','space_rank','union_rank','intersection_dimension','whole_pure_cube_span_closure_dominated','process_cpu_seconds','elapsed_seconds']},sort_keys=True));return 0
    except Exception as error:
        failure={'status':'UNKNOWN_STATIC_SPACE_AUDIT','reason':type(error).__name__+': '+str(error),'progress':progress,'optimization_calls':0,'solver_calls':0}
        with (out/'UNKNOWN.json').open('xb') as stream:stream.write(raw(failure))
        print(json.dumps(failure,sort_keys=True));return 2
    finally:signal.setitimer(signal.ITIMER_REAL,0)

if __name__=='__main__':raise SystemExit(main())
