"""Read-only exact portfolio evidence table; no search, policy updates or writes."""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def summarize(campaign):
    rows=[];raw_union=set();verified_union=set();last=None
    for epoch in range(1,9):
        directory=campaign/f'native-bandit7-e{epoch:02d}';outcome=directory/'outcome.json';summary=directory/'summary.json'
        if not outcome.exists():rows.append(dict(epoch=epoch,status='OPEN_NO_OUTCOME'));continue
        value=json.loads(outcome.read_bytes());row=dict(epoch=epoch,status=value['status'],outcome_sha256=sha(outcome))
        wrapper=campaign/(directory.name+'-job.result.json')
        if wrapper.exists():
            accounting=json.loads(wrapper.read_bytes())
            row['supervisor_result_sha256']=sha(wrapper)
            row['supervisor']={key:accounting.get(key)for key in ['exit_code','timed_out','interrupted','elapsed_seconds','cpu_seconds','max_rss_kib']}
        if summary.exists():
            native=json.loads(summary.read_bytes());stats=native.get('stats')or{};metrics=native.get('exploration_metrics')or{}
            raw_union.update(metrics.get('raw_canonical_hashes',[]))
            row.update(profile=native['profile'],execution=native.get('execution'),steps=stats.get('steps'),
                best_rank=stats.get('best_rank'),current_rank=stats.get('current_rank'),max_visited_rank=stats.get('max_visited_rank'),
                native_summary_sha256=sha(summary),final_checks_complete=native.get('final_checks_complete'),
                raw_canonical_unique=metrics.get('raw_canonical_unique'),above_best_steps=metrics.get('above_best_residency_steps'),
                raw_productcount_histogram=metrics.get('raw_productcount_histogram'),
                steps_per_child_cpu_second=metrics.get('steps_per_child_cpu_second'))
        if value['status']=='COMPLETED_EXPLORATION':
            reward=value['reward_evidence'];checkpoint=directory/'checkpoint.json'
            if sha(checkpoint)!=value['checkpoint_sha256']:raise ValueError('checkpoint drift')
            last=json.loads(checkpoint.read_bytes());verified_union.update(reward['accepted_hashes'])
            row.update(reward=reward['reward'],doubleverified_samples=reward['doubleverified_samples'],
                new_atom_count=reward['new_atom_count'],checkpoint_sha256=value['checkpoint_sha256'],
                context=value['choice']['context'],arm_name=value['choice']['arm_name'])
        rows.append(row)
    context=[]
    for name in ['supervisor-affinity-change-v1.json','native-bandit7-v5-root-final-metadata-allowance.json']:
        path=campaign/name
        if path.exists():context.append(dict(path=str(path),sha256=sha(path)))
    return dict(schema='native-bandit7.evidence.v1',observed_utc=dt.datetime.now(dt.timezone.utc).isoformat(),epochs=rows,
        status_counts=dict(Counter(row['status']for row in rows)),raw_canonical_union_count=len(raw_union),
        doubleverified_reward_state_union_count=len(verified_union),new_verified_atom_count=sum(row.get('new_atom_count',0)for row in rows),
        final_policy={key:last[key]for key in ['completed_epochs','counts','reward_sums','contexts','used_seeds','manifest_sha256']}if last else None,
        operational_context_pins=context,
        scheduling_context='Root moved supervisors3790/5156 fromCPU2 toCPU1 at16:30:52UTC. E4 spans change; E5..8 have less CPU2 competition. No causal profile or throughput superiority claim.',
        claim='Online bandit policy updates; no gradient training. Hash/reward novelty is relative to the frozen comparison and observed ledger, not mathematical novelty. No global tensor rank bound.')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--campaign',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(summarize(args.campaign.resolve()),sort_keys=True,indent=2,allow_nan=False))

if __name__=='__main__':main()
