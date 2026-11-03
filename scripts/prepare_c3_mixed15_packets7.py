"""All27405 C3 fifteen-product packet metadata; no target decoder/filter calls."""
from __future__ import annotations
import argparse
import collections
import gzip
from itertools import combinations
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
from scripts.prepare_c3_mixed_packets7 import literal_terms,source_pair_witnesses,rank_witness,sha,sha_bytes,raw,read,SOURCE_SHA,ANCHOR_SHA,ELIGIBILITY_SHA,CAP,DEADLINE
from mmsearch.compact_sat import BinaryBasis
from mmsearch.compact_eight43 import packed_tensor,expand_core
from mmsearch.compact_coset43 import mode_slices
from mmsearch.sat_neighborhoods import gf2_rank
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import verify_bytes
from scripts import tensor_code7 as lifecycle


def inventory(terms):
    lookup={term:i for i,term in enumerate(terms)};cubes=[];orbits={}
    for i,(a,b,c) in enumerate(terms):
        rotations={(a,b,c),(b,c,a),(c,a,b)}
        if not rotations<=lookup.keys():raise ValueError('incomplete cyclic source orbit')
        if len(rotations)==1:cubes.append(i)
        else:orbits[min(rotations)]=sorted(lookup[term] for term in rotations)
    if len(cubes)!=3:raise ValueError('exactly three source cubes required')
    return sorted(cubes),[orbits[key] for key in sorted(orbits)]


def check_core(record,terms,tensors,width):
    indices=record['source_indices'];basis=BinaryBasis(record['shared_mode_basis']);d=len(basis.vectors)
    if basis.vectors!=record['shared_mode_basis']:raise ValueError('stored common mode basis differs')
    core_mask=0
    for i in indices:
        coordinates=tuple(basis.coordinates(value,require_member=True) for value in terms[i])
        if tuple(basis.expand(value) for value in coordinates)!=terms[i]:raise ValueError('factor coordinate lift differs')
        core_mask^=packed_tensor(coordinates,d)
    core=[(core_mask>>i)&1 for i in range(d**3)];ambient=0
    for i in indices:ambient^=tensors[i]
    if expand_core(core,[d]*3,[basis.vectors]*3,width)!=ambient:raise ValueError('actual core failed full ambient equality')
    actual=[gf2_rank(mode_slices(core,[d]*3,axis)[0]) for axis in range(3)]
    if actual!=[d]*3:raise ValueError('actual core unfolding ranks differ')
    record['branch_metadata'].update(actual_core_checked=True,actual_core_mode_ranks=actual,ambient_entries_checked=width**3,core_entries_checked=d**3,ambient_sha256=sha_bytes(ambient.to_bytes((width**3+7)//8,'little')),actual_core_sha256=sha_bytes(bytes(core)),core_storage='Lazy reconstruction only; no core/model stored.')


def branch_for_dimension(d):
    return 'FLATTENING_EXCLUDED' if d>14 else 'CP(d)' if d==14 else 'CP(d+1)' if d==13 else 'RETAIN_DEFER_HIGHER_SURPLUS'


def prepare(terms,n,guard=lambda *_:None,pilot_cap=25):
    cubes,orbits=inventory(terms);pair_witnesses=source_pair_witnesses(terms,n*n);records=[];byd=collections.defaultdict(list)
    for ordinal,chosen in enumerate(combinations(range(len(orbits)),4)):
        guard('loop');ids=sorted(cubes+[index for orbit in chosen for index in orbits[orbit]])
        if len(ids)!=15 or len(set(ids))!=15:raise ValueError('literal packet must contain exactly15 distinct products')
        factors=[{terms[i][axis] for i in ids} for axis in range(3)]
        if factors[0]!=factors[1] or factors[1]!=factors[2]:raise ValueError('cyclic mode factor sets differ')
        basis=BinaryBasis(sorted(factors[0]));d=len(basis.vectors);witness=rank_witness([terms[i][0] for i in ids])
        if witness['rank']!=d:raise ValueError('factor rank witness differs')
        branch=branch_for_dimension(d)
        # Surplus-two backend max d9; d10..12 and every surplus>=3 remain unsupported.
        mask=sum(1<<i for i in ids);record={'id':'c3-mixed15-p'+'-'.join(f'{i:02}' for i in chosen),'ordinal':ordinal,'source_indices':ids,'term_mask_lo':mask&((1<<64)-1),'term_mask_hi':mask>>64,'orbit_mask_hex':hex(sum(1<<i for i in chosen)),'nonfixed_orbit_quadruple':list(chosen),'shared_mode_basis':basis.vectors,
            'branch_metadata':{'d':d,'mode_shape':[d]*3,'branch':branch,'local_products':15,'target_local_products':14,'outside_products':len(terms)-15,'target_global_products':len(terms)-1,'same_factor_span_all_modes':True,'actual_unfolding_ranks_by_independent_pair_columns':[d]*3,'source_pair_independence_reused':True,'factor_rank_witness':witness,'actual_core_checked':False,'lazy_actual_core_required_before_decode':True,'surplus':14-d,'rank2_span_filter_status':'DEFERRED_IMPLEMENTATION_REVIEW_NOT_BOUND','rank2_span_filter_called':False,'feasibility_status':'EXCLUDED_BY_FLATTENING' if d>14 else 'NOT_QUERIED_RETAINED','future_backend_status':'REVIEWED_CP_D_OR_DPLUS1_ROUTE' if d in (13,14) else 'REQUIRES_SEPARATE_DECODER_REVIEW' if d<=12 else 'NO_DECODER_NEEDED'}}
        records.append(record);byd[d].append(record)
    retained=[record for record in records if record['branch_metadata']['d']<=14]
    retained.sort(key=lambda record:(record['branch_metadata']['branch']=='RETAIN_DEFER_HIGHER_SURPLUS',record['branch_metadata']['d'],record['ordinal']));pilot=retained[:pilot_cap]
    to_check={record['id']:record for d,group in byd.items() for record in group[:3]}
    to_check.update({record['id']:record for record in pilot});tensors=[packed_tensor(term,n*n) for term in terms]
    for record in to_check.values():guard('loop');check_core(record,terms,tensors,n*n)
    if any(not record['branch_metadata']['actual_core_checked'] for record in pilot):raise ValueError('proposed pilot lacks full actual-core check')
    return {'source_order':'0-based original source JSON term order','cube_source_indices':cubes,'nonfixed_orbit_source_indices':orbits,'nonfixed_orbit_order':'Lexicographic minimum literal triple underC3','pair_column_witnesses':pair_witnesses,'packets':records,'dimension_counts':{str(d):len(group) for d,group in sorted(byd.items())},'checked_core_case_ids':list(to_check),'pilot_case_ids':[record['id'] for record in pilot],'core_checks_by_d':{str(d):sum(record['branch_metadata']['actual_core_checked'] for record in group) for d,group in sorted(byd.items())}}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--expected-config-sha256',required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--authorize-preparation',action='store_true');p.add_argument('--preview',action='store_true');a=p.parse_args(argv)
    if not a.authorize_preparation:p.error('explicit census-only authorization required')
    started=time.monotonic();cpu_started=time.process_time()
    if sha(a.config)!=a.expected_config_sha256:raise ValueError('frozen configuration differs')
    config=read(a.config);campaign=Path(config['campaign']);source_path=Path(config['source']);out=a.output_dir.resolve()
    if out.exists() or not out.is_relative_to(campaign) or (config['cpu'],config['nice'],config['memory_mib'],config['seconds'],config['output_bytes'])!=(3,10,512,120,CAP):raise ValueError('new output/exact authorized envelope required')
    if sha(source_path)!=SOURCE_SHA or sha(campaign/'tensor-code-source-anchors-v1/manifest.json')!=ANCHOR_SHA or sha(campaign/'root-review-decisions/tensor-code-source-anchors-approved.json')!=ELIGIBILITY_SHA:raise ValueError('approved source/config pin differs')
    os.sched_setaffinity(0,{3});os.setpriority(os.PRIO_PROCESS,0,10);resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP));resource.setrlimit(resource.RLIMIT_CORE,(0,0));guard=lifecycle.Guard(DEADLINE,120,campaign,campaign/'operations-v3/state.json',config['campaign_sha256']);guard('pre_preparation')
    for name,digest in config['runtime_code_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('runtime changed: '+name)
    if a.preview:print(json.dumps({'status':'PREVIEW_ONLY','zero_mutations':True,'packets_generated':0,'decoder_calls':0},sort_keys=True));return 0
    out.mkdir();progress={'stage':'source_checks'}
    def strict(name):
        guard(name)
        if sum(path.stat().st_size for path in out.rglob('*') if path.is_file())>CAP:raise lifecycle.Stop('32MiB aggregate output cap')
    def save(name,value):
        payload=value if isinstance(value,bytes) else raw(value);strict('pre_publication')
        if sum(path.stat().st_size for path in out.rglob('*') if path.is_file())+len(payload)>CAP:raise lifecycle.Stop('32MiB aggregate output cap')
        with (out/name).open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        strict('post_publication')
    def alarm(*_):raise lifecycle.Stop('120s hard census alarm')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,max(.001,120-(time.monotonic()-started)))
    try:
        payload=source_path.read_bytes();source=lifecycle.strict_load(payload);primary=verify_candidate(source,random_trials=0);strict('post_primary_full15625');independent=verify_bytes(payload);strict('post_independent_full15625')
        if not primary['valid'] or not independent['valid'] or independent['essential_rank']!=93 or primary['exact_entries_checked']!=15625 or independent['exact_entries_checked']!=15625:raise ValueError('exact93 source validation differs')
        terms=literal_terms(source)
        if len(terms)!=93 or source['dimension']!=5 or source['field']!=2:raise ValueError('only approved n5F2 source accepted')
        strict('pre_census');progress['stage']='metadata_and_selected_core_checks';catalog=prepare(terms,5,lambda _='loop':guard('loop'));strict('post_census_and_selected_core_checks')
        if len(catalog['packets'])!=27405 or len(catalog['nonfixed_orbit_source_indices'])!=30:raise ValueError('exact27405 family differs')
        catalog.update(format='c3-mixed15-packet-catalog-v1',source={'path':str(source_path),'raw_sha256':SOURCE_SHA,'source_manifest_sha256':ANCHOR_SHA,'root_eligibility_sha256':ELIGIBILITY_SHA,'essential_products':93},family={'source_cubes':3,'selected_nonfixed_orbits':4,'total_nonfixed_orbits':30,'combinations':27405,'local_products':15,'target_local_products':14,'outside_products':78,'global_product_target':92,'target_queries_authorized':False})
        lookup={record['id']:record for record in catalog['packets']};cases=[lookup[case] for case in catalog['pilot_case_ids']]
        pilot={'format':'c3-mixed15-lowd-first25-proposal-v1','status':'DISABLED_PLAN_ONLY_REQUIRES_ROOT_BACKEND_AND_EXECUTION_REVIEW','enabled':False,'decoder_launch_authorized':False,'source_sha256':SOURCE_SHA,'case_ids':catalog['pilot_case_ids'],'cases':[{key:record[key] for key in ['id','source_indices','orbit_mask_hex','shared_mode_basis','branch_metadata']} for record in cases],'case_count':len(cases),
            'selection_rule':'Supported d13/d14 first, then unsupported retained cases by d; source-orbit lexicographic quadruple order; all selected ambient/actual cores fully checked. Unsupported d10..12 and every surplus>=3 stays retained/deferred, never negative.','rank2_span_filter':'Deferred: mathematical proof/ten controls exist, but separate independent implementation clearance is not bound to this runner. No filter call.','required_pre_dispatch':['Reconstruct and verify every selected ambient/core through lazySourceCache before decoding.','Choose and independently review a backend supporting the actual surplus; This target14 supports only d14/d13 in existing exact decoders; d10..12 and smaller are retained/deferred.','Keep hard per-case/overall/resource/deadline caps and fresh pre/post solve/full-verifier/publication guards; late returns stay UNKNOWN.','Any candidate requires full15625 primary+strict-independent persisted-byte checks and global-guard immutable record handoff.'],'proposed_limits_for_later_review':{'max_cases':25,'cpu':3,'memory_mib':512,'overall_wall_seconds':120,'per_case_wall_seconds':3,'deadline':DEADLINE}}
        save('catalog.json.gz',gzip.compress(json.dumps(catalog,sort_keys=True,separators=(',',':')).encode(),compresslevel=6,mtime=0));save('pilot-proposal.json',pilot)
        if sha(source_path)!=SOURCE_SHA or sha(a.config)!=a.expected_config_sha256:raise ValueError('source/config changed during census')
        for name,digest in config['runtime_code_sha256'].items():
            if sha(ROOT/name)!=digest:raise ValueError('runtime changed during census')
        strict('pre_manifest');counts=collections.Counter(record['branch_metadata']['branch'] for record in catalog['packets']);manifest={'format':'c3-mixed15-preparation-v1','status':'PREPARED_METADATA_NO_TARGET_QUERIES','source':catalog['source'],'family':catalog['family'],'dimension_counts':catalog['dimension_counts'],'branch_counts':dict(counts),'pair_column_ranks':[item['rank'] for item in catalog['pair_column_witnesses']],'actual_core_checks':len(catalog['checked_core_case_ids']),'core_checks_by_d':catalog['core_checks_by_d'],'checked_core_case_ids':catalog['checked_core_case_ids'],'pilot_case_count':len(cases),'retained_low_d_not_discarded':True,'rank2_span_filter_calls':0,'filter_deferred':True,'koszul_calls':0,'decoder_calls':0,'solver_calls':0,'private_eval_payloads_read':0,'catalog_sha256':sha(out/'catalog.json.gz'),'pilot_proposal_sha256':sha(out/'pilot-proposal.json'),'runtime_code_sha256':config['runtime_code_sha256'],'config_sha256':a.expected_config_sha256,'runtime':lifecycle.runtime(),'guard':guard.observation(),'elapsed_seconds':time.monotonic()-started,'process_cpu_seconds':time.process_time()-cpu_started}
        save('manifest.json',manifest);save('checksums.json',{str(path.relative_to(out)):sha(path) for path in out.rglob('*') if path.is_file()});save('COMPLETE.json',{'manifest_sha256':sha(out/'manifest.json'),'checksums_sha256':sha(out/'checksums.json'),'acceptance':'Require matching pins/no UNKNOWN; no decoder execution authorized.'})
        for path in out.rglob('*'):
            if path.is_file():path.chmod(0o444)
        print(json.dumps({key:manifest[key] for key in ['status','dimension_counts','branch_counts','actual_core_checks','core_checks_by_d','pilot_case_count','elapsed_seconds','process_cpu_seconds']},sort_keys=True));return 0
    except Exception as error:
        failure={'status':'UNKNOWN_CENSUS_PREPARATION','reason':type(error).__name__+': '+str(error),'progress':progress,'decoder_calls':0,'solver_calls':0}
        with (out/'UNKNOWN.json').open('xb') as stream:stream.write(raw(failure))
        print(json.dumps(failure,sort_keys=True));return 2
    finally:signal.setitimer(signal.ITIMER_REAL,0)

if __name__=='__main__':raise SystemExit(main())
