"""Audit one completed C7 validation from existing metadata; never evaluates."""
import argparse
from collections import Counter,defaultdict
import hashlib,json,math
from pathlib import Path
import sys
sys.dont_write_bytecode=True;ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.collect_operator44_pilots import read,encoded,sha,freeze,collect_native

ARMS=('learned','frozenwarm','random')

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('campaign','proposal','output-dir'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args(argv);campaign,proposal,out=[Path(x).resolve() for x in (a.campaign,a.proposal,a.output_dir)]
    if campaign.name!='marathon7_20261103T122417Z' or not out.is_relative_to(campaign) or out.exists():raise ValueError('fresh explicit C7 analysis output required')
    job=read(proposal/'proposed_job.json');directory=campaign/job['id'];result_path=campaign/(job['id']+'-job.result.json')
    result=read(result_path)
    if result['exit_code']!=0 or result['timed_out'] or result['interrupted'] or result['command']!=job['command']:raise ValueError('validation incomplete or command differs from reviewed proposal')
    summary=read(directory/'summary.json');rows=read(directory/'results.json');manifest=read(proposal/'manifest.json');task_index=read(proposal/'validation-task-index.json');tasks={item['term_hash']:item for item in task_index}
    reserved=set(manifest['validation']['reserved_final_test_source_hashes']);validation=set(manifest['validation']['validation_source_hashes'])
    if summary['heldout_subset']!='validation' or set(summary['reserved_source_hashes'])!=validation or validation&reserved:raise ValueError('reserved source split changed')
    if set(summary['heldout_hashes'])!=set(tasks) or summary['heldout_tasks']!=14 or len(tasks)!=14 or summary['training_tasks_evaluated']!=0 or summary['record'] is not None:raise ValueError('unexpected validation scope/record')
    if summary['step_limit_per_action']!=50000 or summary['max_actions']!=4:raise ValueError('matched budget differs')
    identities=summary['policy_identities'];pairs=defaultdict(list);matched=[]
    for row in rows:
        task=tasks[row['task_hash']]
        if row['source_hash']!=task['source_term_hash'] or row['source_hash'] not in validation or row['source_hash'] in reserved:raise ValueError('out-of-scope task/source evaluated')
        expected_seed=(4411034407+row['repeat']*104729+int(row['task_hash'][:8],16))%(2**31)
        if not 0<=row['repeat']<16 or row['seed']!=expected_seed or row['pair_id']!=row['task_hash']+':'+str(row['repeat']):raise ValueError('paired task/seed identity differs')
        if row['training'] is not False or row['exact'] is not True or row['record_target_reached'] or row['known_rank']!=93 or row['best_rank']<93:raise ValueError('unexpected training/exactness/record result')
        if row['success']!=(row['best_rank']<=93):raise ValueError('success is not known93 recovery')
        if row['actions']!=row['dm_env_steps'] or not 0<=row['actions']<=4 or row['step_limit_per_action']!=50000 or row['attempted_moves']>row['actions']*50000:raise ValueError('step/action cap differs')
        identity=identities[row['arm']]
        if row['policy_sha256_before']!=row['policy_sha256_after'] or row['policy_sha256_before']!=identity['weight_sha256_before']:raise ValueError('inference weights changed')
        pairs[row['pair_id']].append(row)
    for pair,group in pairs.items():
        if len({row['arm'] for row in group})!=len(group) or any(row['arm'] not in ARMS for row in group):raise ValueError('duplicate/unrecognized arm')
        common=len(group)==3 and not any(row['stop_reason'] in ('global_wall_budget','external_stop') for row in group)
        if any(row['paired_complete'] is not common for row in group):raise ValueError('pair completion/censoring differs')
        if len({(row['task_hash'],row['seed'],row['repeat']) for row in group})!=1:raise ValueError('unmatched tasks/seeds')
        if common:matched+=group
    complete=len(matched)//3
    if complete!=summary['complete_pairs'] or len(rows)!=summary['all_rows']:raise ValueError('summary pair/row counts differ')
    arms={};sources={}
    for arm in ARMS:
        selected=[row for row in matched if row['arm']==arm];reported=summary['arms'][arm]
        got=dict(matched_episodes=len(selected),successes=sum(row['success'] for row in selected),attempted_moves=sum(row['attempted_moves'] for row in selected),cpu_seconds=sum(row['cpu_seconds'] for row in selected),unrecovered_within_limits=sum(not row['success'] for row in selected))
        for key in ('matched_episodes','successes','attempted_moves'):assert got[key]==reported[key]
        assert got['unrecovered_within_limits']==reported['censored'] and math.isclose(got['cpu_seconds'],reported['cpu_seconds'],abs_tol=1e-8)
        got['success_rate']=got['successes']/len(selected);arms[arm]=got
        identity=identities[arm]
        if identity['unchanged'] is not True or identity['updates_before']!=identity['updates_after'] or identity['weight_sha256_before']!=identity['weight_sha256_after'] or sha(Path(identity['path']).read_bytes())!=identity['checkpoint_sha256']:raise ValueError('source/frozen inference policy changed')
    for source in sorted(validation):
        source_rows=[row for row in matched if row['source_hash']==source];sources[source]={arm:{'episodes':sum(row['arm']==arm for row in source_rows),'successes':sum(row['arm']==arm and row['success'] for row in source_rows)} for arm in ARMS}
    differences={reference:sum(sources[source]['learned']['successes']/sources[source]['learned']['episodes']-sources[source][reference]['successes']/sources[source][reference]['episodes'] for source in validation)/len(validation) for reference in ('frozenwarm','random')}
    for reference,value in differences.items():assert math.isclose(value,summary['source_cluster_comparisons']['comparisons']['learned_vs_'+reference]['source_equal_weight_rate_difference'],abs_tol=1e-12)
    bindings=identities['learned']['operator44_binding'];references=[];action_counts={arm:Counter() for arm in ARMS};event_rows=[]
    for line in (directory/'events.jsonl').read_text().splitlines():
        event=json.loads(line)
        if event.get('event')=='evaluation_result':event_rows.append({k:v for k,v in event.items() if k!='event'})
        if event.get('event')!='evaluation_transition':continue
        arm=event['arm'];action_counts[arm][event['action']]+=1
        if event['training'] is not False or event['learning'] is not None or event['updates']!=identities[arm]['updates_before'] or event['novelty_bonus']!=0 or event['global_novelty_paid']!=25 or event['rank']>event['best_rank']+6:raise ValueError('frozen inference/update/novelty/cap invariant failed')
        native=event.get('native',{})
        if native.get('run_dir'):references.append(dict(run_dir=native['run_dir'],action=event['action'],task_kind=event['task_kind'],attempted_moves=native['attempted_moves'],native_current_rank=native['current_rank'],controller_rank=event['rank'],controller_best_rank=event['best_rank'],accepted=event['accepted']))
    if event_rows!=rows:raise ValueError('persisted result/event rows differ')
    cache={};missing=collect_native(references,bindings,campaign,cache)
    if missing or len(cache)!=len(references) or not all(all(row['checks'].values()) for row in cache.values()):raise ValueError('native stats missing or invariant differs')
    planned=224;started=len(pairs);partial=[pair for pair,group in pairs.items() if not all(row['paired_complete'] for row in group)]
    output=dict(status='PASS',completed=True,validation_runs_analyzed=1,new_evaluation_calls=0,training_calls=0,old42_writes=0,planned_triplets=planned,started_triplets=started,complete_triplets=complete,partial_triplets=len(partial),not_started_triplets=planned-started,all_result_rows=len(rows),unpaired_result_rows=len(rows)-len(matched),partial_pair_ids=partial,arms=arms,source_results=sources,source_equal_weight_rate_differences=differences,action_counts={k:dict(v) for k,v in action_counts.items()},native_runs_checked=len(references),policy_weights_updates_frozen=True,validation_sources_only=True,final_test_sources_untouched=True,record=None,promotion_authorized=False,
        interpretation='Known93recoveries only. Learned shows no advantage here; two-source finite-budget validation is descriptive. No repeat assessment or final-test call was made.',summary_sha256=sha((directory/'summary.json').read_bytes()),results_sha256=sha((directory/'results.json').read_bytes()),events_sha256=sha((directory/'events.jsonl').read_bytes()),job_result_sha256=sha(result_path.read_bytes()),driver_wall_seconds=summary['wall_seconds'],wrapper_wall_seconds=result['elapsed_seconds'],wrapper_CPU_seconds=result['cpu_seconds'])
    out.mkdir();freeze(out/'REPORT.json',encoded(output));freeze(out/'native-stats-cache.json',encoded(cache));freeze(out/'analyze_marathon7_rl_validation.py',Path(__file__).read_bytes());freeze(out/'checksums.json',encoded({str(path.relative_to(out)):sha(path.read_bytes()) for path in out.iterdir() if path.is_file()}))
    print(encoded({k:v for k,v in output.items() if k not in ('source_results','action_counts')}).decode());return 0

if __name__=='__main__':raise SystemExit(main())
