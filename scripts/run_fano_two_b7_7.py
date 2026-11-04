"""Exactly one pinned b7 Fano query per invocation; branch-only negatives."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.xor-deps')]
from mmsearch import binary_packet_adapter7 as packet
from mmsearch.compact_coset43 import digest,mode_slices
from mmsearch.fano_quotient_adapter7 import CORE_MANIFEST,load_pinned_case
from mmsearch.fano_quotient_sat7 import build_problem,solve_core,DEADLINE
from mmsearch.marathon7_cached_guard import CampaignGuard,CampaignHold
from mmsearch.marathon7_cancel_poller import CancelPoller
from mmsearch.verify import verify_candidate
from scripts.run_c3_mixed12_pilot7 import run_case,freeze,raw
from scripts.verify_record42_independent import verify_bytes


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class BoundPacketCache:
    def __init__(self,campaign,prepared):
        self.campaign=Path(campaign);self.prepared=prepared
        self.plan=packet.select_plan(root=self.campaign,core_pin_path=self.campaign/'binary-block-nine-core-prep-001/manifest.json',core_pin_sha256=CORE_MANIFEST)
        self.row=self.plan['cases'][prepared['ordinal']]
        if self.row['id']!=prepared['case']:raise ValueError('approved source plan case differs')
        source_bytes=packet.pinned(packet.SOURCE,root=self.campaign);self.source=json.loads(source_bytes)
        self.primary=verify_candidate(self.source,random_trials=0);strict=verify_bytes(source_bytes)
        if not self.primary['valid'] or not strict['valid'] or self.primary['exact_entries_checked']!=15625 or strict['exact_entries_checked']!=15625 or strict['essential_rank']!=93:raise ValueError('original full source must pass both checks')
    def core(self,case):
        if case['id']!=self.prepared['case'] or case['target_local_products']!=14:raise ValueError('only the prepared fixed case may run')
        if hashlib.sha256(packet.pinned(packet.SOURCE,root=self.campaign)).hexdigest()!=packet.SOURCE_SHA:raise ValueError('source changed')
        data=packet.build_packet_data(self.source,self.row,production=True)
        if (data['core']!=self.prepared['core'] or data['shape']!=self.prepared['shape'] or hashlib.sha256(raw(data)).hexdigest()!=self.prepared['input_core_sha256']):raise ValueError('all source indices/mode bases/core bytes must match sealed preparation')
        return self.source,data,self.primary,packet.SOURCE_SHA,digest(dict(shape=data['shape'],core=data['core'])),self.prepared['input_core_sha256']


def run_branch(cache,case,out,guard,*,seconds=75,solver,control_expected_rank=None):
    legacy=run_case(cache,case,out,guard,seconds=seconds,solver=solver,control_expected_rank=control_expected_rank)
    decoder=legacy.get('raw_decoder',{})
    status=legacy['status'];branch_complete=False
    if (status=='UNKNOWN' and not legacy.get('after_cutoff') and decoder.get('status')=='FANO_BRANCH_UNSAT'
            and decoder.get('complete') is True and decoder.get('fano_branch_complete') is True
            and not decoder.get('assumptions')):
        guard.check('pre_fano_branch_negative_acceptance')
        status='FANO_BRANCH_UNSAT';branch_complete=True
    return dict(status=status,case=case['id'],fano_branch_complete=branch_complete,
                full_CP14_negative=False,global_rank_lower_bound=False,legacy_result=legacy,
                scope='Only this Fano branch; prior CP<=13 and every repeated-pair branch remain separate.')


def publish_receipt(out,result,guard):
    out=Path(out);path=out/'branch-receipt.json'
    guard.check('pre_fano_branch_receipt');freeze(path,result)
    try:guard.check('post_fano_branch_receipt')
    except CampaignHold:
        hidden=out/'.raw-returns';hidden.mkdir(exist_ok=True,parents=True)
        os.replace(path,hidden/'late-branch-receipt.raw');raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True);parser.add_argument('--expected-config-sha256',required=True)
    parser.add_argument('--preview',action='store_true');args=parser.parse_args()
    if sha(args.config)!=args.expected_config_sha256:raise ValueError('frozen invocation configuration differs')
    config=json.loads(args.config.read_bytes());campaign=Path(config['campaign']);out=campaign/config['job_id'];bundle=Path(config['prepared_bundle'])
    if config['ordinal'] not in (2,3) or config['solver_seconds']!=60 or config['inner_seconds']!=75 or config['outer_seconds']!=100 or config['memory_mb']!=1024 or config['cpu'] not in (0,3):raise ValueError('only the authorized two 60/75/100 CPU0-or-CPU3 invocations are supported')
    if out.exists() or sha(bundle/'manifest.json')!=config['prepared_manifest_sha256'] or sha(campaign/'campaign.json')!=config['campaign_sha256']:raise ValueError('new output and exact approved preparation/campaign required')
    for name,pin in config['runtime_code_sha256'].items():
        if sha(ROOT/name)!=pin:raise ValueError('runtime bytes differ: '+name)
    guard=CampaignGuard(75,DEADLINE,stop_markers=[config['series_stop_marker']],guard_state=campaign/'operations-v3/state.json',campaign_dir=campaign)
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    guard.check('pre_fano_invocation');prepared=load_pinned_case(campaign,config['ordinal'])
    receipt=json.loads((bundle/'manifest.json').read_bytes())['cases'][config['ordinal']-2]
    if receipt['case']!=prepared['case'] or prepared['problem']['metadata']['formula_sha256']!=receipt['formula_sha256']:raise ValueError('actual prepared formula differs from fixed input/formula pin')
    cache=BoundPacketCache(campaign,prepared);guard.check('post_fano_source_validation')
    case=dict(id=prepared['case'],target_local_products=14,free_axis=0,prep_ambient_sha256=cache.row['branch_metadata']['ambient_sha256'])
    if args.preview:
        print(json.dumps(dict(status='PREVIEW_ONLY',case=case['id'],formula_sha256=receipt['formula_sha256'],source_sha256=packet.SOURCE_SHA,solver_calls=0),sort_keys=True));return 0
    out.mkdir();freeze(out/'config.json',config);freeze(out/'formula-metadata.json',prepared['problem']['metadata'])
    calls=[0]
    def solver(core,shape,target,axis=0,max_vectors=65535,cancelled=None):
        if calls[0] or target!=14 or axis!=0 or core!=prepared['core'] or shape!=[11]*3:raise ValueError('only one exact pinned solver call is authorized')
        guard.check('pre_single_fano_solver');calls[0]+=1
        result=solve_core(core,shape,prepared['backbone_points'],axis=0,space_basis=prepared['space_basis'],seconds=60,memory_mb=1024,cancelled=cancelled,deadline_utc=DEADLINE)
        if result.get('formula_sha256') not in (None,receipt['formula_sha256']):raise ValueError('executed formula identity differs')
        return result
    try:
        result=run_branch(cache,case,out,guard,seconds=75,solver=solver)
        result.update(solver_calls=calls[0],formula_sha256=receipt['formula_sha256'],input_core_sha256=prepared['input_core_sha256'],metadata_case_sha256=prepared['metadata_case_sha256'],solver_seed_policy=config['solver_seed_policy'])
        publish_receipt(out,result,guard)
    except CampaignHold as error:
        result=dict(status='UNKNOWN',case=case['id'],after_cutoff=True,reason=error.reason,solver_calls=calls[0],full_CP14_negative=False)
        freeze(out/'.raw-returns/held-invocation.raw',result)
    if result['status'] in ('ERROR','TARGET_EMITTED_TO_GLOBAL_GUARD'):
        marker=Path(config['series_stop_marker'])
        if not marker.exists():freeze(marker,dict(status='STOP_FANO_SERIES',reason=result['status'],case=case['id']))
    print(json.dumps({k:result.get(k) for k in ('status','case','solver_calls','fano_branch_complete','full_CP14_negative','formula_sha256')},sort_keys=True))
    return 1 if result['status']=='ERROR' else 0


if __name__=='__main__':raise SystemExit(main())
