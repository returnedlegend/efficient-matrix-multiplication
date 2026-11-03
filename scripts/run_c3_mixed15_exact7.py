"""One guarded pass over the bounded supported mixed15 residuals; no resume."""
from __future__ import annotations
import argparse
import hashlib
import gzip
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
from mmsearch.marathon7_cached_guard import CampaignGuard,CampaignHold
from mmsearch.marathon7_cancel_poller import CancelPoller
from mmsearch.extend_eight_bulk43 import SourceCache
from mmsearch.compact_rank2_edges43 import solve_core as solve_one
from mmsearch.surplus_two7 import solve_core as solve_two
from mmsearch.compact_eight43 import bits,expand_core,replace_and_verify
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import verify_bytes,_check_all_basis_outputs

DECODER_SHA='40ef2057d481b712040575b663b31585460b2e5addc58a24a5cbf94aa0f686a7'
SOURCE_SHA='56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b'
CATALOG_SHA='b6df6ab005954168bf9a656d5f0c7e4d78fd3c5029a32dfb74f281ea836dc7c5'
PROPOSAL_SHA='735a60bb293275df2f939bb7dec1ac582360d8e3888f72da925c26b915f2558e'
SURPLUS_TWO_SHA='3fb2d76b3297b0f5962175af9054b8c33ae02a351bab8f603d88f29e71d31107'
DEADLINE='2026-11-03T19:24:17Z'


def sha_bytes(payload):return hashlib.sha256(payload).hexdigest()
def sha(path):return sha_bytes(Path(path).read_bytes())
def raw(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def read(path):return json.loads(Path(path).read_bytes())
def freeze(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);payload=value if isinstance(value,bytes) else raw(value)
    with path.open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
    path.chmod(0o444)


def independent(candidate,payload):
    if candidate['dimension']==5:return verify_bytes(payload)
    n=candidate['dimension'];check=_check_all_basis_outputs(n,[(tuple(t['u']),tuple(t['v']),tuple(t['w'])) for t in candidate['terms']])
    return {'valid':check['mismatch_count']==0,'essential_rank':len(candidate['terms']),'exact_entries_checked':check['output_bits_checked'],'control_only':True}


def reviewed_solver(core,shape,target,axis=0,max_vectors=65535,cancelled=None):
    d=shape[axis]
    if target in (d,d+1):return solve_one(core,shape,target,axis=axis,max_vectors=max_vectors,cancelled=cancelled)
    if target==d+2:return solve_two(core,shape,target,axis=axis,max_vectors=1023,max_extensions=1533,max_mode_rank=9,cancelled=cancelled,timeout_seconds=20,deadline_utc=DEADLINE)
    return {'status':'UNKNOWN','complete':False,'case':'unsupported_surplus','shape':shape}


def run_case(cache,case,out,guard,*,seconds=20,solver=reviewed_solver,control_expected_rank=None):
    out=Path(out);deadline=guard.monotonic()+seconds;poller=CancelPoller(guard,lambda:deadline);decoder=None;candidate=None;full=None;strict=None;data=None;source_sha=None;called=False;destination=None
    def check(name):poller.force_check(name)
    try:
        check('pre_case_source');source,data,source_verified,source_sha,core_math_sha,core_input_sha=cache.core(case);check('post_case_source_core')
        if case.get('prep_ambient_sha256'):
            ambient=expand_core(data['core'],data['shape'],data['image_bases'],25)
            if sha_bytes(ambient.to_bytes(1954,'little'))!=case['prep_ambient_sha256']:raise ValueError('retained preparation ambient identity differs')
        check('pre_solve');called=True;decoder=solver(data['core'],data['shape'],case['target_local_products'],axis=case['free_axis'],max_vectors=65535,cancelled=poller.cancelled);check('post_solve')
        if decoder['status']=='ERROR':raise RuntimeError('decoder returned ERROR')
        if decoder['status']=='SAT':
            products=[]
            for term in decoder['products']:
                lifted=[]
                for coordinate,basis in zip(term,data['image_bases']):
                    value=0
                    for index in bits(coordinate):value^=basis[index]
                    lifted.append(value)
                products.append(lifted)
            check('pre_lift_full');candidate,_=replace_and_verify(source,data['source_indices'],products,{'method':'C3mixed15 exact reviewed CP(d)/CP(d+1)/CP(d+2) local repair','case':case['id']});check('post_lift_full')
            payload=raw(candidate);digest=sha_bytes(payload);hidden=out/'.raw-returns';freeze(hidden/(case['id']+'.candidate.raw'),payload);persisted=(hidden/(case['id']+'.candidate.raw')).read_bytes()
            check('pre_persisted_primary');full=verify_candidate(json.loads(persisted),random_trials=0);check('post_persisted_primary_full')
            strict=independent(json.loads(persisted),persisted);check('post_strict_independent_full')
            n=source['dimension'];rank=len(candidate['terms'])
            if not full['valid'] or not strict['valid'] or full['exact_entries_checked']!=n**6 or strict['exact_entries_checked']!=n**6 or strict['essential_rank']!=rank:raise ValueError('persisted full candidate verification failed')
            if n==5:
                if rank>92 or strict.get('record_eligible') is not True:raise ValueError('production target eligibility differs')
            elif control_expected_rank is None or rank!=control_expected_rank:raise ValueError('tiny whole-matrix control rank differs')
            proof={'case':case,'source_sha256':source_sha,'core_math_sha256':core_math_sha,'core_input_sha256':core_input_sha,'candidate_sha256':digest,'decoder':decoder,'primary':full,'independent':strict,'input_core':data}
            freeze(out/'proofs'/(case['id']+'.proof.raw'),proof);check('pre_eligible_publication');destination=out/'records'/(digest+'.json');destination.parent.mkdir(parents=True,exist_ok=True);pending=hidden/(case['id']+'.pending.raw');freeze(pending,persisted);check('pre_canonical_rename');os.replace(pending,destination)
            try:check('post_eligible_publication')
            except CampaignHold:
                os.replace(destination,hidden/(case['id']+'.late-canonical.raw'));raise
            status='TARGET_EMITTED_TO_GLOBAL_GUARD' if n==5 else 'SMALL_CONTROL_PASSED'
        elif decoder['status']=='LOCAL_UNSAT' and decoder.get('complete') is True:
            check('pre_negative_commit');status='LOCAL_UNSAT'
        else:
            check('post_unknown_return');status='UNKNOWN'
        result={'status':status,'case':case['id'],'decoder_called':called,'complete':status in ('LOCAL_UNSAT','TARGET_EMITTED_TO_GLOBAL_GUARD','SMALL_CONTROL_PASSED'),'decoder_status':decoder['status'],'decoder_case':decoder.get('case'),'raw_decoder':decoder,'source_sha256':source_sha,'core_math_sha256':core_math_sha,'core_input_sha256':core_input_sha,'poller':poller.metrics(),'shape':data['shape'],'elapsed_case_seconds':seconds-(deadline-guard.monotonic())}
        if candidate is not None:result.update(candidate_rank=len(candidate['terms']),primary=full,independent=strict)
        check('pre_result_publication');freeze(out/(case['id']+'.result.json'),result);check('post_result_publication');check('post_case');return result
    except CampaignHold as error:
        visible=out/(case['id']+'.result.json')
        if visible.exists():
            hidden=out/'.raw-returns';hidden.mkdir(parents=True,exist_ok=True);os.replace(visible,hidden/(case['id']+'.late-visible-result.raw'))
        if destination is not None and destination.exists():os.replace(destination,out/'.raw-returns'/(case['id']+'.late-canonical.raw'))
        if decoder is not None:freeze(out/'.raw-returns'/(case['id']+'.late-result.raw'),{'status':'UNKNOWN','after_cutoff':True,'no_within_budget_claim':True,'case':case['id'],'reason':error.reason,'barrier':error.barrier,'raw_decoder':decoder,'candidate':candidate,'primary':full,'independent':strict,'core_input':data,'source_sha256':source_sha})
        return {'status':'UNKNOWN','case':case['id'],'complete':False,'decoder_called':called,'after_cutoff':True,'reason':error.reason,'barrier':error.barrier,'raw_retained':decoder is not None,'poller':poller.metrics()}
    except Exception as error:
        visible=out/(case['id']+'.result.json')
        if visible.exists():os.replace(visible,out/'.raw-returns'/(case['id']+'.error-visible.raw'))
        if destination is not None and destination.exists():os.replace(destination,out/'.raw-returns'/(case['id']+'.error-canonical.raw'))
        freeze(out/'.raw-returns'/(case['id']+'.error.raw'),{'status':'ERROR','case':case['id'],'error_type':type(error).__name__,'error':str(error),'raw_decoder':decoder,'candidate':candidate,'primary':full,'independent':strict,'core_input':data})
        return {'status':'ERROR','case':case['id'],'complete':False,'decoder_called':called,'error_type':type(error).__name__,'error':str(error),'poller':poller.metrics()}



def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--expected-config-sha256',required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--preview',action='store_true');a=p.parse_args(argv)
    if sha(a.config)!=a.expected_config_sha256:raise ValueError('frozen configuration differs')
    config=read(a.config);campaign=Path(config['campaign']);out=a.output_dir.resolve();bundle=Path(config['bundle'])
    if out!=campaign/config['job_id'] or not config['job_id'].startswith('c3-mixed15-exact7-') or out.exists() or not 1<=len(config['cases'])<=250:raise ValueError('one authorized bounded supported-case launch/new output required')
    if sha(Path(config['prep'])/'catalog.json.gz')!=CATALOG_SHA or sha(Path(config['prep'])/'pilot-proposal.json')!=PROPOSAL_SHA or sha(bundle/'inputs/source.json')!=SOURCE_SHA or sha(ROOT/'mmsearch/compact_rank2_edges43.py')!=DECODER_SHA or sha(ROOT/'mmsearch/surplus_two7.py')!=SURPLUS_TWO_SHA:raise ValueError('approved source/family/reviewed decoder pin differs')
    if any(case['shape'] not in ([13]*3,[14]*3) or case['target_local_products']!=14 or case['source_local_products']!=15 for case in config['cases']):raise ValueError('only supported target14 mixed15 cases authorized')
    if sha(campaign/'campaign.json')!=config['campaign_sha256']:raise ValueError('campaign configuration differs')
    for name,digest in config['runtime_code_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('runtime pin differs: '+name)
    guard=CampaignGuard(500,DEADLINE,guard_state=campaign/'operations-v3/state.json',campaign_dir=campaign);guard.check('pre_launch')
    if time.time()+530>guard.deadline:raise ValueError('outer envelope cannot fit absolute deadline')
    if a.preview:print(json.dumps({'status':'PREVIEW_ONLY','zero_mutations':True,'decoder_calls':0,'cases':len(config['cases'])},sort_keys=True));return 0
    os.sched_setaffinity(0,{3});resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_CORE,(0,0));out.mkdir(parents=True);freeze(out/'config.json',config)
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop());results=[];cache=SourceCache(bundle)
    for case in config['cases']:
        if guard.reason(force=True):break
        result=run_case(cache,case,out,guard,seconds=20)
        if not (out/(case['id']+'.result.json')).exists():freeze(out/(case['id']+'.result.json'),result)
        results.append(result)
        if result['status'] in ('TARGET_EMITTED_TO_GLOBAL_GUARD','ERROR','UNKNOWN'):break
    statuses=[item['status'] for item in results];all_negative=len(results)==len(config['cases']) and all(status=='LOCAL_UNSAT' for status in statuses)
    guard_reason=guard.reason(force=True)
    if guard_reason:all_negative=False
    summary={'status':'TARGET_EMITTED_TO_GLOBAL_GUARD' if 'TARGET_EMITTED_TO_GLOBAL_GUARD' in statuses else 'SUPPORTED_BATCH_LOCAL_UNSAT' if all_negative else 'ERROR' if 'ERROR' in statuses else 'UNKNOWN_WITHIN_ONE_PILOT','planned_cases':len(config['cases']),'attempted_cases':len(results),'decoder_calls':sum(item['decoder_called'] for item in results),'results':results,'config_sha256':a.expected_config_sha256,'stop_reason':guard_reason,'guard':guard.observation(),'runtime_code_sha256':config['runtime_code_sha256'],'global_record_freeze_owned_by_guard':True,'scope':'Only selected literal15-to14 residuals with outside78 frozen; all121 unsupported cases retained/unqueried. No global lower bound.'}
    freeze(out/'summary.json',summary);freeze(out/'result-manifest.json',{'format':'c3-mixed15-supported-results-v1','config_sha256':a.expected_config_sha256,'summary_sha256':sha(out/'summary.json'),'result_files':{item['case']+'.result.json':sha(out/(item['case']+'.result.json')) for item in results},'runtime_code_sha256':config['runtime_code_sha256'],'guard':guard.observation()});print(json.dumps({'status':summary['status'],'decoder_calls':summary['decoder_calls'],'statuses':statuses,'stop_reason':summary['stop_reason']},sort_keys=True));return 1 if summary['status']=='ERROR' else 0

if __name__=='__main__':raise SystemExit(main())
