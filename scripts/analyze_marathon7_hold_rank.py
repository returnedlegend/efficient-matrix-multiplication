"""Query-free audit and matched descriptive analysis of the four C7 hold arms."""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from scripts.audit_burst_long42 import exact_check,term_hash
from scripts.verify_record42_independent import verify_bytes
from scripts.campaign_native_dwell_hold_rank import validate_stats


def sha(raw):return hashlib.sha256(raw).hexdigest()
def raw(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def read(path):return json.loads(Path(path).read_bytes())
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(value)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--campaign',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args()
    campaign=args.campaign.resolve();out=args.output_dir.resolve()
    if out.exists():raise ValueError('new audit output directory required')
    out.mkdir(parents=True);start=time.process_time();code_names=['scripts/analyze_marathon7_hold_rank.py','scripts/audit_burst_long42.py','scripts/verify_record42_independent.py','tests/test_audit_burst_long42.py','tests/fixtures/native_campaign42_rank93.json','tests/fixtures/native_campaign42_rank96.json']
    code={name:sha((ROOT/name).read_bytes()) for name in code_names}
    with (out/'packed-controls.log').open('x') as log:
        controls=subprocess.run([sys.executable,'-B','-m','unittest','tests.test_audit_burst_long42','-v'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=30)
    if controls.returncode:raise ValueError('packed-versus-scalar controls failed')
    plan_path=campaign/'dwell-hold-rank-ready-v1/plan.json';plan=read(plan_path);queue=read(campaign/'queue.json');actual_jobs=[];arms=[];certificate_pins={};run_pins={};all_identities=set();scalar_checks=0
    for arm in plan['arms']:
        job_id=arm['job_id'];run=campaign/job_id;manifest=read(run/'manifest.json');summary=read(run/'summary.json');result_path=campaign/(job_id+'-job.result.json');result=read(result_path)
        job=next(job for job in queue['jobs'] if job['id']==job_id);proposed=next(job for job in plan['jobs'] if job['id']==job_id)
        assert {**job,'enabled':False}==proposed and job['enabled'] is True
        assert job['command']==result['command'] and result['exit_code']==0 and not result['timed_out'] and not result['interrupted']
        assert (job['cpu'],job['memory_mb'],job['seconds'])==(3,768,45)
        assert manifest['dwell_hold_rank']==arm['dwell_hold_rank'] and manifest['seed']==arm['paired_seed']
        source_meta=next(source for source in plan['sources'] if source['label']==arm['source'])
        assert manifest['source']==source_meta['verification']
        assert manifest['source']['raw_sha256']==sha((run/'input.json').read_bytes())
        assert manifest['binary_sha256']==plan['binary_sha256']==sha((run/'frozen/native-worker').read_bytes())
        assert manifest['runtime_sha256']==plan['runtime_sha256']
        for name,digest in manifest['runtime_code_sha256'].items():assert sha((run/'frozen/runtime'/name).read_bytes())==digest
        stats,digest=validate_stats(run/'native/walk.stats.json',seed=arm['paired_seed'],hold_rank=arm['dwell_hold_rank'])
        assert digest==summary['stats_sha256'] and stats==summary['stats'] and stats==read(run/'final_stats.json')
        assert stats['best_rank']==stats['current_rank']==93 and not stats['target_reached'] and summary['winner'] is False and not (run/'WINNER.json').exists()
        assert stats['history']==[{'step':0,'rank':93}] and stats['restarts']==0
        items=summary['exported_diversity']['certificates'];rank_counts=collections.Counter();pins=[];checked_ranks=set();union=set();jaccards=[]
        disk={path.name[:-5] for path in (run/'verified').glob('*.json') if len(path.name)==69}
        assert disk==set(items)
        for identity,item in sorted(items.items()):
            path=Path(item['path']);assert path==run/'verified'/(identity+'.json');payload=path.read_bytes();assert sha(payload)==item['sha256']
            terms,report=exact_check(payload)
            assert report['valid'] and report['exact_entries_checked']==15625 and report['term_set_sha256']==identity and report['essential_rank']==item['rank'] and not report['record_eligible']
            primary=read(path.with_suffix('.verification.json'));assert primary['valid'] and primary['exact_entries_checked']==15625 and primary['rank']==len(terms)
            if len(terms) not in checked_ranks:
                scalar=verify_bytes(payload);assert scalar['valid'] and scalar['essential_rank']==len(terms) and scalar['mismatch_count']==report['mismatch_count'];scalar_checks+=1;checked_ranks.add(len(terms))
            pins.append([identity,item['sha256'],len(terms),sha(path.with_suffix('.verification.json').read_bytes())]);rank_counts[str(len(terms))]+=1;union.update(terms);jaccards.append(item['source_jaccard_distance']);all_identities.add(identity)
        assert len(items)==summary['exported_diversity']['unique_certificates'] and dict(rank_counts)==summary['exported_diversity']['per_rank']
        assert len(union)==summary['exported_diversity']['unique_full_terms']
        certificate_pins[job_id]=pins
        actual_jobs.append(job)
        paths={'manifest':run/'manifest.json','summary':run/'summary.json','stats':run/'native/walk.stats.json','final_stats':run/'final_stats.json','job_result':result_path,'input':run/'input.json','best_snapshot':run/'native/walk.best.txt','current_snapshot':run/'native/walk.current.txt'}
        run_pins[job_id]={key:{'path':str(path.relative_to(ROOT)),'sha256':sha(path.read_bytes())} for key,path in paths.items()}
        hist={int(k):v for k,v in stats['rank_excess_residency_steps'].items()};steps=stats['steps'];execution=summary['execution'];cpu=execution['child_cpu_seconds']
        assert abs(cpu-execution['child_user_seconds']-execution['child_system_seconds'])<1e-8
        arm_result={'job_id':job_id,'source':arm['source'],'seed':arm['paired_seed'],'hold_rank':arm['dwell_hold_rank'],'best_rank':stats['best_rank'],'current_rank':stats['current_rank'],'peak_rank':stats['max_visited_rank'],'peak_excess':stats['max_rank_excess'],
             'steps':steps,'child_cpu_seconds':cpu,'native_wall_seconds':stats['elapsed_seconds'],'wrapper_child_elapsed_seconds':execution['elapsed_seconds'],'outer_job_cpu_seconds':result['cpu_seconds'],'outer_job_elapsed_seconds':result['elapsed_seconds'],'wrapper_cpu_seconds_after_preparation':summary['wrapper_cpu_seconds_after_preparation'],
             'steps_per_child_cpu_second':steps/cpu,'above_best_steps':steps-hist.get(0,0),'above_best_fraction':1-hist.get(0,0)/steps,'mean_rank_excess':sum(k*v for k,v in hist.items())/steps,
             'rank_at_least97_fraction':sum(v for k,v in hist.items() if k>=4)/steps,'excess_residency_steps':stats['rank_excess_residency_steps'],
             'flip_attempts':stats['flip_attempts'],'accepted_flips':stats['accepted_by_kind']['flip'],'rejected_flips':stats['flip_attempts']-stats['accepted_by_kind']['flip'],'flip_rank_changes':stats['rank_changes_by_kind']['flip'],
             'dwell':{k:stats[k] for k in stats if k.startswith('dwell_')},'hold':{k:stats[k] for k in stats if k.startswith('hold_')},'burst':{k:stats[k] for k in stats if k.startswith('burst_')},
             'plus_attempts':stats['plus_attempts'],'plus_rank_changes':stats['rank_changes_by_kind']['plus'],'reductions':stats['accepted_by_kind']['reduction'],'reduction_rank_changes':stats['rank_changes_by_kind']['reduction'],
             'bursts_per_child_cpu_second':stats['burst_windows_started']/cpu,'independent_exports_checked':len(items),'independent_tensor_entries_checked':15625*len(items),'per_rank':dict(rank_counts),
             'diversity':{key:value for key,value in summary['exported_diversity'].items() if key!='certificates'},'mean_sampled_source_jaccard_distance':sum(jaccards)/len(jaccards),'max_sampled_source_jaccard_distance':max(jaccards)}
        if arm['dwell_hold_rank']:
            assert stats['hold_active_rank_loss']==stats['hold_active_rank_loss_moves']==0
            assert stats['hold_rejected_downward_flips']==arm_result['rejected_flips']==stats['rejected_moves']
            assert stats['hold_window_expirations']*128==stats['hold_active_steps'] and stats['hold_window_renewals']==3*stats['hold_window_expirations']
            assert stats['hold_windows_started']==4*stats['hold_window_expirations']
        assert stats['burst_windows_completed']==stats['burst_windows_started'] and stats['burst_forced_accepted']==3*stats['burst_windows_started']
        assert stats['burst_failed_attempts']==stats['burst_attempt_capped']==stats['burst_rank_capped']==0
        arms.append(arm_result)
    pairs=[]
    for source in ['s01','s02']:
        zero=next(arm for arm in arms if arm['source']==source and not arm['hold_rank']);one=next(arm for arm in arms if arm['source']==source and arm['hold_rank'])
        assert zero['seed']==one['seed']
        pairs.append({'source':source,'seed':zero['seed'],'above_best_fraction_flag1_minus_flag0':one['above_best_fraction']-zero['above_best_fraction'],'above_best_fraction_ratio':one['above_best_fraction']/zero['above_best_fraction'],
                      'mean_excess_ratio':one['mean_rank_excess']/zero['mean_rank_excess'],'steps_per_cpu_flag1_div_flag0':one['steps_per_child_cpu_second']/zero['steps_per_child_cpu_second'],'peak_rank_change':one['peak_rank']-zero['peak_rank'],
                      'sampled_termset_intersection':len(set(items[0] for items in certificate_pins[zero['job_id']])&set(items[0] for items in certificate_pins[one['job_id']]))})
    assert all(sha((ROOT/name).read_bytes())==digest for name,digest in code.items())
    write(out/'certificate-pins.json',raw({'schema':'job ID -> [termset sha256, certificate byte sha256, rank, primary report byte sha256]','certificates':certificate_pins}))
    write(out/'actual-jobs.json',raw({'jobs':actual_jobs}));write(out/'source-pins.json',raw({'plan':{'path':str(plan_path.relative_to(ROOT)),'sha256':sha(plan_path.read_bytes())},'code':code,'run_files':run_pins,'source_training_identities':[{'source':item['label'],'raw_sha256':item['verification']['raw_sha256'],'term_set_sha256':item['verification']['term_set_sha256'],'source_term_hash':item['verification']['source_term_hash']} for item in plan['sources']],
            'binary_sha256':plan['binary_sha256'],'runtime_sha256':plan['runtime_sha256'],'heldout_declaration_sha256':plan['heldout_declaration_sha256']}))
    report={'format':'marathon7-hold-rank-pilot-analysis-v1','status':'NO_VERIFIED_RANK92_WITHIN_FOUR_ARMS','new_search_queries_started':0,'completed_queries_analyzed':4,'primary_packed_controls_passed':4,'scalar_export_spotchecks':scalar_checks,
            'independent_exports_checked':sum(a['independent_exports_checked'] for a in arms),'independent_tensor_entries_checked':sum(a['independent_tensor_entries_checked'] for a in arms),'cross_arm_unique_termsets':len(all_identities),'arms':arms,'paired_descriptive_comparisons':pairs,
            'analysis_cpu_seconds':time.process_time()-start,'scope':'Two source/seed pairs, fixed 30s wall per arm, unequal measured CPU. Descriptive mechanics only; no speedup, record or broad search-advantage claim.',
            'recommendation':'Holding works mechanically and increases step residency, but peak stays98 and no rank improvement. Do not promote or lengthen this policy from these two pairs. A small matched step-budget replication across fresh source/seed pairs could test reproducibility before any dwell-length sweep; no launch authorized.'}
    write(out/'analysis.json',raw(report));write(out/'checksums.json',raw({str(p.relative_to(out)):sha(p.read_bytes()) for p in out.rglob('*') if p.is_file()}))
    print(json.dumps({key:report[key] for key in ['status','independent_exports_checked','independent_tensor_entries_checked','cross_arm_unique_termsets','scalar_export_spotchecks','analysis_cpu_seconds','paired_descriptive_comparisons']},sort_keys=True))

if __name__=='__main__':main()
