"""One guarded necessary-only pass over the112 deferred rank12 mixed15 packets."""
import argparse,collections,gzip,hashlib,json,os,resource,signal,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from mmsearch.rank2_span_bound7 import classify_pair_image
from mmsearch.extend_eight_bulk43 import SourceCache
from mmsearch.compact_coset43 import mode_slices
from mmsearch.marathon7_cached_guard import CampaignGuard,CampaignHold
from mmsearch.marathon7_cancel_poller import CancelPoller
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import verify_bytes

FILTER_SHA='b4388978ed49e10a9487e7c78c0059381ce680233045ebd5db0580c850f66c4b'
SOURCE_SHA='56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b'
CATALOG_SHA='b6df6ab005954168bf9a656d5f0c7e4d78fd3c5029a32dfb74f281ea836dc7c5'
DEADLINE='2026-11-03T19:24:17Z'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def raw(v):return (json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
def freeze(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(raw(v));f.flush();os.fsync(f.fileno())
    p.chmod(0o444)

def checked_bound(targets,left,right,budget,*,cancelled=None):
    result=classify_pair_image(targets,left,right,budget,max_vectors=4095,cancelled=cancelled)
    if result['status']=='EXCLUDED':
        d=result['image_rank']
        if not result['complete'] or not result['enumeration_complete'] or result['enumerated_vectors']!=(1<<d)-1 or result['rank2_span_rank'] is None or result['rank2_span_rank']>=result['required_rank2_span']:raise ValueError('negative lacks complete low-rank span census')
    elif result['status']=='NOT_EXCLUDED':
        if result['existence_claim'] is not False or result['observed_rank2_span_rank']<result['required_rank2_span']:raise ValueError('necessary pass lacks rank witness')
    elif result['status']!='UNKNOWN':raise ValueError('unexpected necessary-filter status')
    return result

def run_case(cache,case,out,guard,*,classifier=checked_bound):
    poller=CancelPoller(guard);out=Path(out);result=None;destination=out/(case['id']+'.result.json')
    try:
        poller.force_check('pre_filter_source_core');source,data,verified,source_sha,math_sha,input_sha=cache.core(case);poller.force_check('post_filter_source_core')
        slices,other=mode_slices(data['core'],data['shape'],0);poller.force_check('pre_necessary_filter')
        result=classifier(slices,data['shape'][other[0]],data['shape'][other[1]],case['target_local_products'],cancelled=poller.cancelled);poller.force_check('post_necessary_filter')
        if result['image_rank']!=case['mode_rank'] or result['required_rank2_span']!=case['mode_rank']-1:raise ValueError('actual image/threshold differs')
        record=dict(case=case['id'],status=result['status'],complete=result['complete'],necessary_only=True,existence_claim=False,cp_decoder_calls=0,source_sha256=source_sha,source_indices=case['source_indices'],orbit_mask_hex=case.get('orbit_mask_hex'),core_math_sha256=math_sha,core_input_sha256=input_sha,image_bases=data['image_bases'],shape=data['shape'],raw_filter=result,poller=poller.metrics())
        poller.force_check('pre_filter_result_publication');freeze(destination,record);poller.force_check('post_filter_result_publication');return record
    except CampaignHold as error:
        if destination.exists():
            (out/'.raw-returns').mkdir(parents=True,exist_ok=True);os.replace(destination,out/'.raw-returns'/(case['id']+'.late-visible.raw'))
        if result is not None:freeze(out/'.raw-returns'/(case['id']+'.late-filter.raw'),dict(status='UNKNOWN',after_cutoff=True,barrier=error.barrier,reason=error.reason,raw_filter=result))
        return dict(case=case['id'],status='UNKNOWN',complete=False,necessary_only=True,existence_claim=False,cp_decoder_calls=0,reason=error.reason,barrier=error.barrier,poller=poller.metrics())

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--expected-config-sha256',required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--preview',action='store_true');a=p.parse_args();start=time.monotonic();cpu_start=time.process_time()
    if sha(a.config)!=a.expected_config_sha256:raise ValueError('config differs')
    c=read(a.config);campaign=Path(c['campaign']);bundle=Path(c['bundle']);out=a.output_dir.resolve()
    if out!=campaign/'c3-mixed15-rank2-filter112-001' or out.exists() or (c['cpu'],c['memory_mib'],c['seconds'])!=(3,512,120):raise ValueError('exact authorized envelope/new output required')
    if sha(c['catalog'])!=CATALOG_SHA or sha(bundle/'inputs/source.json')!=SOURCE_SHA or sha(ROOT/'mmsearch/rank2_span_bound7.py')!=FILTER_SHA:raise ValueError('input/math pin differs')
    catalog=json.loads(gzip.decompress(Path(c['catalog']).read_bytes()));expected={r['id']:r for r in catalog['packets'] if r['branch_metadata']['d']==12}
    if len(c['cases'])!=112 or len({r['id'] for r in c['cases']})!=112 or {r['id'] for r in c['cases']}!=set(expected):raise ValueError('exact112scope differs')
    for case in c['cases']:
        if case['source_indices']!=expected[case['id']]['source_indices'] or case['orbit_mask_hex']!=expected[case['id']]['orbit_mask_hex'] or case['source_sha256']!=SOURCE_SHA or case['shape']!=[12]*3 or case['target_local_products']!=14 or case['source_local_products']!=15:raise ValueError('source/core scope differs')
    for name,pin in c['runtime_code_sha256'].items():
        if sha(ROOT/name)!=pin:raise ValueError('runtime differs: '+name)
    if sha(campaign/'campaign.json')!=c['campaign_sha256']:raise ValueError('campaign differs')
    guard=CampaignGuard(120,DEADLINE,guard_state=campaign/'operations-v3/state.json',campaign_dir=campaign);guard.check('pre_filter_launch')
    if time.time()+150>guard.deadline:raise ValueError('outer envelope cannot fit UTC')
    if a.preview:print(json.dumps(dict(status='PREVIEW_ONLY',zero_mutations=True,cp_decoder_calls=0,cases=112)));return 0
    os.sched_setaffinity(0,{3});os.setpriority(os.PRIO_PROCESS,0,10);resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2));resource.setrlimit(resource.RLIMIT_FSIZE,(32*1024**2,32*1024**2));resource.setrlimit(resource.RLIMIT_CORE,(0,0));out.mkdir();freeze(out/'config.json',c)
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop());cache=SourceCache(bundle);records=[]
    try:
        guard.check('pre_source_primary');primary=verify_candidate(read(bundle/'inputs/source.json'),random_trials=0);guard.check('post_source_primary');strict=verify_bytes((bundle/'inputs/source.json').read_bytes());guard.check('post_source_independent')
        if not primary['valid'] or not strict['valid'] or strict['essential_rank']!=93 or primary['rank']!=93 or primary['exact_entries_checked']!=strict['exact_entries_checked'] or strict['exact_entries_checked']!=15625:raise ValueError('full source proof differs')
        freeze(out/'source-verification.json',dict(primary=primary,independent=strict,source_sha256=SOURCE_SHA))
        for case in c['cases']:
            guard.check('pre_next_filter_case');record=run_case(cache,case,out,guard);records.append(record)
            if record['status']=='UNKNOWN':break
        guard.check('pre_filter_summary')
    except CampaignHold as error:
        freeze(out/'HOLD.json',dict(status='UNKNOWN',reason=error.reason,barrier=error.barrier,cp_decoder_calls=0))
    counts=collections.Counter(r['status'] for r in records);passed=[r['case'] for r in records if r['status']=='NOT_EXCLUDED'];healthy=guard.reason(force=True) is None
    summary=dict(format='c3-mixed15-rank2-filter112-v1',status='ALL112_COMPLETE_NECESSARY_FILTER' if len(records)==112 and not counts['UNKNOWN'] and healthy else 'UNKNOWN_PARTIAL_FILTER',counts=dict(counts),planned_cases=112,attempted_cases=len(records),passed_case_ids=passed,cp_decoder_calls=0,existence_claim=False,untouched_d11_cases=9,elapsed_seconds=time.monotonic()-start,process_cpu_seconds=time.process_time()-cpu_start,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,results=records,guard=guard.observation(),config_sha256=a.expected_config_sha256,runtime_code_sha256=c['runtime_code_sha256'])
    freeze(out/'summary.json',summary);freeze(out/'manifest.json',dict(summary_sha256=sha(out/'summary.json'),source_sha256=SOURCE_SHA,catalog_sha256=CATALOG_SHA,filter_sha256=FILTER_SHA,config_sha256=a.expected_config_sha256,cp_decoder_calls=0));print(json.dumps({k:summary[k] for k in ['status','counts','attempted_cases','passed_case_ids','elapsed_seconds','process_cpu_seconds','max_rss_kib']}));return 0
if __name__=='__main__':raise SystemExit(main())
