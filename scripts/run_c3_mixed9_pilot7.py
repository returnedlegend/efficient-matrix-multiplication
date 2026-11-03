"""One guarded pass over the nine accepted mixed-orbit residuals; no resume."""
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
from mmsearch.marathon7_cached_guard import CampaignGuard,CampaignHold
from mmsearch.marathon7_cancel_poller import CancelPoller
from mmsearch.extend_eight_bulk43 import SourceCache
from mmsearch.compact_rank2_edges43 import solve_core
from mmsearch.compact_eight43 import bits,expand_core,replace_and_verify
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import verify_bytes,_check_all_basis_outputs

DECODER_SHA='40ef2057d481b712040575b663b31585460b2e5addc58a24a5cbf94aa0f686a7'
SOURCE_SHA='56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b'
CATALOG_SHA='ab52e0debe73b857da75765b196ec64f2bb1497c8092754aa19c56ecdfb3fd31'
PROPOSAL_SHA='aac671d6f46521e4e8dfc4bbbd0ce13c9b9b611b0c3f3600d61e02349cf4533b'
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


def run_case(cache,case,out,guard,*,seconds=5,solver=solve_core,control_expected_rank=None):
    out=Path(out);deadline=guard.monotonic()+seconds;poller=CancelPoller(guard,lambda:deadline);decoder=None;candidate=None;full=None;strict=None;data=None;source_sha=None;called=False;destination=None
    def check(name):poller.force_check(name)
    try:
        check('pre_case_source');source,data,source_verified,source_sha,core_math_sha,core_input_sha=cache.core(case);check('post_case_source_core')
        if case.get('prep_ambient_sha256'):
            ambient=expand_core(data['core'],data['shape'],data['image_bases'],25)
            if sha_bytes(ambient.to_bytes(1954,'little'))!=case['prep_ambient_sha256']:raise ValueError('retained preparation ambient identity differs')
        check('pre_solve');called=True;decoder=solver(data['core'],data['shape'],case['target_local_products'],axis=case['free_axis'],max_vectors=65535,cancelled=poller.cancelled);check('post_solve')
        if decoder['status']=='SAT':
            products=[]
            for term in decoder['products']:
                lifted=[]
                for coordinate,basis in zip(term,data['image_bases']):
                    value=0
                    for index in bits(coordinate):value^=basis[index]
                    lifted.append(value)
                products.append(lifted)
            check('pre_lift_full');candidate,_=replace_and_verify(source,data['source_indices'],products,{'method':'C3mixed9 exact reviewed rank2edge local repair','case':case['id']});check('post_lift_full')
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


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--expected-config-sha256',required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--preview',action='store_true');a=p.parse_args(argv)
    if sha(a.config)!=a.expected_config_sha256:raise ValueError('frozen configuration differs')
    config=read(a.config);campaign=Path(config['campaign']);out=a.output_dir.resolve();bundle=Path(config['bundle'])
    if out!=campaign/'c3-mixed9-packets7-pilot009-001' or out.exists() or len(config['cases'])!=9:raise ValueError('one authorized nine-case launch/new output required')
    if sha(Path(config['prep'])/'catalog.json')!=CATALOG_SHA or sha(Path(config['prep'])/'pilot-proposal.json')!=PROPOSAL_SHA or sha(bundle/'inputs/source.json')!=SOURCE_SHA or sha(ROOT/'mmsearch/compact_rank2_edges43.py')!=DECODER_SHA:raise ValueError('approved source/family/reviewed decoder pin differs')
    if sha(campaign/'campaign.json')!=config['campaign_sha256']:raise ValueError('campaign configuration differs')
    for name,digest in config['runtime_code_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('runtime pin differs: '+name)
    guard=CampaignGuard(60,DEADLINE,guard_state=campaign/'operations-v3/state.json',campaign_dir=campaign);guard.check('pre_launch')
    if time.time()+90>guard.deadline:raise ValueError('outer envelope cannot fit absolute deadline')
    if a.preview:print(json.dumps({'status':'PREVIEW_ONLY','zero_mutations':True,'decoder_calls':0,'cases':9},sort_keys=True));return 0
    os.sched_setaffinity(0,{3});resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_CORE,(0,0));out.mkdir(parents=True);freeze(out/'config.json',config)
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop());results=[];cache=SourceCache(bundle)
    for case in config['cases']:
        if guard.reason(force=True):break
        result=run_case(cache,case,out,guard,seconds=5)
        if not (out/(case['id']+'.result.json')).exists():freeze(out/(case['id']+'.result.json'),result)
        results.append(result)
        if result['status']=='TARGET_EMITTED_TO_GLOBAL_GUARD':break
    statuses=[item['status'] for item in results];all_negative=len(results)==9 and all(status=='LOCAL_UNSAT' for status in statuses)
    guard_reason=guard.reason(force=True)
    if guard_reason:all_negative=False
    summary={'status':'TARGET_EMITTED_TO_GLOBAL_GUARD' if 'TARGET_EMITTED_TO_GLOBAL_GUARD' in statuses else 'NINE_LITERAL_PACKETS_LOCAL_UNSAT' if all_negative else 'UNKNOWN_WITHIN_ONE_PILOT','planned_cases':9,'attempted_cases':len(results),'decoder_calls':sum(item['decoder_called'] for item in results),'results':results,'config_sha256':a.expected_config_sha256,'stop_reason':guard_reason,'guard':guard.observation(),'runtime_code_sha256':config['runtime_code_sha256'],'global_record_freeze_owned_by_guard':True,'scope':'Only these nine literal9-to8 residuals with outside84 frozen. No global lower bound or automatic continuation.'}
    freeze(out/'summary.json',summary);print(json.dumps({'status':summary['status'],'decoder_calls':summary['decoder_calls'],'statuses':statuses,'stop_reason':summary['stop_reason']},sort_keys=True));return 0

if __name__=='__main__':raise SystemExit(main())
