"""Explicitly authorized bounded partial-tensor questions, never M5 candidates."""
import argparse
import copy
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from mmsearch.compact_rank2_edges43 import solve_core as solve_one
from mmsearch.surplus_two7 import solve_core as solve_two
from mmsearch.compact_eight43 import bits,packed_tensor
from mmsearch.marathon7_cached_guard import CampaignGuard,CampaignHold
from mmsearch.marathon7_cancel_poller import CancelPoller
from scripts.audit_c3_mixed_s4_space7 import BASE_DICT,CAMPAIGN,CAMPAIGN_SHA,CAP,DEADLINE,code_pins,sha
from scripts.audit_cyclic_tensor_code7 import raw
PREP=CAMPAIGN/'c3-wedge-kernel63-prep-v1'
OUT=CAMPAIGN/'c3-wedge-kernel63-queries-v1'


def partial_case(case,check,cancelled,cached=None):
    """A fresh forced barrier gates each partial decision; no record publication."""
    decoder=None;witness=None
    try:
        check('pre_partial_decode');d=case['mode_rank'];target=case['target']
        if cached is not None:decoder=copy.deepcopy(cached)
        elif target in (d,d+1):
            decoder=solve_one(case['core'],case['shape'],target,axis=0,max_vectors=1023,cancelled=cancelled)
        elif target==d+2 and d<=9:
            decoder=solve_two(case['core'],case['shape'],target,axis=0,max_vectors=1023,max_extensions=1533,timeout_seconds=2,cancelled=cancelled,deadline_utc=DEADLINE)
        else:
            return dict(status='UNKNOWN',complete=False,case=case['id'],reason='unsupported',publication_eligible=False)
        check('post_partial_decode')
        if decoder['status']=='SAT':
            shape=case['shape'];products=decoder['products']
            if len(products)>target:raise ValueError('partial product budget exceeded')
            for i in range(shape[0]):
                for j in range(shape[1]):
                    for k in range(shape[2]):
                        value=sum(((a>>i)&1)*((b>>j)&1)*((c>>k)&1) for a,b,c in products)%2
                        if value!=case['core'][(i*shape[1]+j)*shape[2]+k]:raise ValueError('independent fullcore equality failed')
            check('post_partial_scalar_core')
            lifted=[]
            for term in products:
                values=[]
                for mask,basis in zip(term,case['image_bases']):
                    value=0
                    for i in bits(mask):value^=basis[i]
                    values.append(value)
                lifted.append(values)
            tensor=0
            for term in lifted:tensor^=packed_tensor(term,25)
            expected=int(case['ambient_tensor_hex'],16)
            if tensor!=expected:raise ValueError('fullambient packed partial equality failed')
            for i in range(25):
                for j in range(25):
                    row=0
                    for a,b,c in lifted:
                        if (a>>i)&(b>>j)&1:row^=c
                    if row!=((expected>>((i*25+j)*25))&((1<<25)-1)):raise ValueError('independent15625 partial equality failed')
            witness=dict(kind='PARTIAL_TENSOR_DECOMPOSITION_ONLY',old_orbit_indices=case['old_orbit_indices'],old_weight=case['old_weight'],target=target,
                products_in_original_25d_modes=lifted,compact_products=products,shape=shape,image_bases=case['image_bases'],ambient_tensor_hex=case['ambient_tensor_hex'],
                exact_ambient_entries_checked=15625,independent_scalar_core_entries_checked=len(case['core']),global_matrix_tensor_verified=False,publication_eligible=False)
            check('post_partial_ambient_verification');status='PARTIAL_TENSOR_SAT'
        elif decoder['status']=='LOCAL_UNSAT' and decoder.get('complete') is True:status='LOCAL_UNSAT'
        else:status='UNKNOWN'
        check('pre_partial_result')
        return dict(status=status,complete=status!='UNKNOWN',case=case['id'],raw_decoder=decoder,partial_witness=witness,
                    publication_eligible=False,scope='Only this exact partialtensor Y; no globalcandidate or rankbound.')
    except CampaignHold as error:
        return dict(status='UNKNOWN',complete=False,case=case['id'],after_cutoff=True,reason=error.reason,barrier=error.barrier,
                    raw_decoder=decoder,raw_partial_witness=witness,publication_eligible=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--authorize-partial-queries',action='store_true');a=p.parse_args(argv)
    if not a.authorize_partial_queries:p.error('explicit root partialtensor-query authorization required')
    started=time.monotonic();cpu_started=time.process_time()
    if OUT.exists() or sha(CAMPAIGN/'campaign.json')!=CAMPAIGN_SHA:raise ValueError('new output/matching campaign required')
    os.sched_setaffinity(0,{1});os.setpriority(os.PRIO_PROCESS,0,10)
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    guard=CampaignGuard(120,DEADLINE,guard_state=CAMPAIGN/'operations-v3/state.json',campaign_dir=CAMPAIGN)
    guard.check('pre_partial_queries');signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    deadline=None;poller=CancelPoller(guard,lambda:deadline)
    def check(name):poller.force_check(name)
    prep=json.loads((PREP/'manifest.json').read_bytes());catalog=json.loads((PREP/'catalog.json').read_bytes())
    if prep['cases']!=63 or prep['base_dictionary_sha256']!=BASE_DICT or len(catalog)!=63:raise ValueError('wrong63partialtensor family')
    for name,pin in json.loads((PREP/'checksums.json').read_bytes()).items():
        if sha(PREP/name)!=pin:raise ValueError('preparedpartialtensor bytes changed')
    pins=code_pins();OUT.mkdir();cache={};records=[];queries=0
    # Only explicit previously completedC3/modeclosure result bytes are checked
    # for a hash-identical core/budget. Such a match stays held for proof reuse.
    historical={}
    for pattern in ('c3-mixed9-*/**/*.result.json','c3-mixed12-*/**/*.result.json','marathon7-modeclosure11-pilot9-v1/*.result.json'):
        for path in CAMPAIGN.glob(pattern):
            value=json.loads(path.read_bytes())
            if value.get('status')=='LOCAL_UNSAT' and value.get('complete') is True and value.get('core_math_sha256'):
                dec=value.get('raw_decoder',value);budget=dec.get('budget',dec.get('target'))
                if type(budget) is int:historical.setdefault(value['core_math_sha256'],[]).append(dict(path=str(path),sha256=sha(path),budget=budget))
    def save(name,value):
        payload=raw(value)
        if sum(q.stat().st_size for q in OUT.rglob('*') if q.is_file())+len(payload)>CAP:raise RuntimeError('32MiB aggregate cap')
        path=OUT/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        path.chmod(0o444)
    def alarm(*_):raise TimeoutError('120s partialquery alarm')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,max(.001,120-(time.monotonic()-started)))
    try:
        save('config.json',dict(format='wedge-kernel63-partial-query-config-v1',prep_manifest_sha256=sha(PREP/'manifest.json'),runtime_code_sha256=pins,
            total_seconds=120,per_case_seconds=2,cpu=1,memory_mib=1024,production_n5_matrix_queries=0,global_candidate_publication=False))
        for record in catalog:
            case=json.loads((PREP/'cases'/f"{int(record['kernel_basis_mask_hex'],16):02x}.json").read_bytes())
            if case['route']=='FLATTENING_PROVES_OLD_COST_OPTIMAL':
                result=dict(status='LOCAL_UNSAT',complete=True,case=case['id'],proof='actual_mode_flattening_rank_exceeds_oldcost_minus_one',decoder_called=False)
            elif guard.reason(force=True):
                result=dict(status='UNKNOWN',complete=False,case=case['id'],reason='global_guard_stop',decoder_called=False)
            elif any(prior['budget']>=case['target'] for prior in historical.get(case['core_math_sha256'],[])):
                result=dict(status='UNKNOWN',complete=False,case=case['id'],reason='hash_identical_closed_core_held_for_scoped_proof_reuse',decoder_called=False,historical_matches=historical[case['core_math_sha256']])
            else:
                deadline=time.monotonic()+2;key=(case['core_math_sha256'],case['target']);cached=cache.get(key)
                result=partial_case(case,check,poller.cancelled,cached)
                result.update(decoder_called=cached is None,reused_exact_core_decision=cached is not None)
                queries+=cached is None
                if result['status'] in ('LOCAL_UNSAT','PARTIAL_TENSOR_SAT'):cache[key]=result['raw_decoder']
                if result.get('partial_witness') is not None:save('.raw-partial-witnesses/'+case['id']+'.raw.json',result['partial_witness'])
            result.update(old_weight=case['old_weight'],target=case['target'],shape=case['shape'],input_ambient_sha256=case['ambient_sha256'],input_core_sha256=case['core_math_sha256'],publication_eligible=False)
            if result['status']=='UNKNOWN' and result.get('raw_decoder') is not None:save('.raw-partial-witnesses/'+case['id']+'.late.raw.json',result)
            if result.get('decoder_called') or result.get('reused_exact_core_decision'):
                try:
                    check('pre_partial_commit');save(case['id']+'.result.json',result);check('post_partial_commit')
                except CampaignHold as error:
                    cache.pop(key,None)
                    path=OUT/(case['id']+'.result.json')
                    if path.exists():
                        hidden=OUT/'.raw-partial-witnesses';hidden.mkdir(exist_ok=True)
                        path.rename(hidden/(case['id']+'.late-commit.raw.json'))
                    result=dict(status='UNKNOWN',complete=False,case=case['id'],reason=error.reason,barrier=error.barrier,
                                after_cutoff=True,raw_result=result,publication_eligible=False)
                    save(case['id']+'.result.json',result)
            else:save(case['id']+'.result.json',result)
            records.append(result)
        deadline=None;check('post_partial_query_phase')
        if any(sha(ROOT/name)!=pin for name,pin in pins.items()):raise ValueError('runtime changed')
        statuses={status:sum(r['status']==status for r in records) for status in ('LOCAL_UNSAT','PARTIAL_TENSOR_SAT','UNKNOWN')}
        manifest=dict(format='wedge-kernel63-partial-query-results-v1',status='ALL63_OLD_COST_OPTIMAL' if statuses['LOCAL_UNSAT']==63 else 'PARTIAL_RELATIONS_FOUND' if statuses['PARTIAL_TENSOR_SAT'] else 'UNKNOWN',
            status_counts=statuses,decoder_calls=queries,raw_partial_positive_cases=[r['case'] for r in records if r['status']=='PARTIAL_TENSOR_SAT'],
            complete_decisions=sum(r.get('complete') is True for r in records),runtime_code_sha256=pins,prep_manifest_sha256=sha(PREP/'manifest.json'),
            elapsed_seconds=time.monotonic()-started,process_cpu_seconds=time.process_time()-cpu_started,guard=guard.observation(),
            global_candidate_publications=0,production_n5_matrix_queries=0,
            scope='Exactpartialtensor Y only. Positives are hidden raw relations; all63negative could establish oldbasis-cost domination but no globalCP lowerbound. NoWINNER/records/globalstop written.')
        save('manifest.json',manifest);save('checksums.json',{str(q.relative_to(OUT)):sha(q) for q in OUT.rglob('*') if q.is_file()});save('COMPLETE.json',dict(manifest_sha256=sha(OUT/'manifest.json'),checksums_sha256=sha(OUT/'checksums.json')))
        print(json.dumps({k:manifest[k] for k in ('status','status_counts','decoder_calls','raw_partial_positive_cases','elapsed_seconds','process_cpu_seconds')},sort_keys=True))
    except Exception as error:
        save('UNKNOWN.json',dict(status='UNKNOWN',complete=False,reason=type(error).__name__+': '+str(error),completed_case_files=len(records),
                                decoder_calls=queries,publication_eligible=False,production_n5_matrix_queries=0))
        raise
    finally:signal.setitimer(signal.ITIMER_REAL,0)


if __name__=='__main__':main()
