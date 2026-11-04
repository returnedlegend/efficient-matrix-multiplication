"""Read-only evidence for four exact derived-source native starts."""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from scripts import campaign_native_baseline7 as safe

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def summarize(campaign):
    known=set()
    for pattern in ['native-portfolio7-p*/summary.json','native-bandit7-e*/summary.json']:
        for path in campaign.glob(pattern):known.update(json.loads(path.read_bytes()).get('raw_exports',{}))
    anchors=json.loads((campaign/'tensor-code-source-anchors-v1/manifest.json').read_bytes())
    known.update(row['identity']['term_set_sha256']for row in anchors['known_input_train_states'])
    corpus=json.loads((campaign/'tensor-code-native-corpus-prep-001/prepared.json').read_bytes())
    known.update(row['identity']['term_set_sha256']for row in corpus['source_records'])
    rows=[];union=set()
    for number in range(1,5):
        name=f'native-xor3-p{number:02d}';directory=campaign/name;outcome=directory/'outcome.json'
        if not outcome.exists():rows.append(dict(id=name,status='OPEN_NO_OUTCOME'));continue
        result=json.loads(outcome.read_bytes());native=json.loads((directory/'summary.json').read_bytes());input_record=json.loads((directory/'input-contract.json').read_bytes())
        wrapper=campaign/(name+'-job.result.json');accounting=json.loads(wrapper.read_bytes())if wrapper.exists()else{}
        hashes=set(native['raw_exports']);union.update(hashes);best,_=safe.base.snapshot(directory/'native/walk.best.txt',5);best_hash=safe.base.term_set_sha256(best)
        row=dict(id=name,status=result['status'],outcome_sha256=sha(outcome),native_summary_sha256=sha(directory/'summary.json'),
            input_rank=input_record['input_rank'],source_index=result['source_index'],parents=input_record['source_receipt']['parent_indices'],
            profile=native['profile'],execution=native['execution'],best_rank=native['stats']['best_rank'],current_rank=native['stats']['current_rank'],
            maximum_visited_rank=native['stats']['max_visited_rank'],native_steps=native['stats']['steps'],history=native['stats']['history'],
            raw_canonical_unique=len(hashes),raw_unique_vs_pre_crossover_observed=len(hashes-known),
            raw_productcount_histogram=native['exploration_metrics']['raw_productcount_histogram'],
            best_term_set_sha256=best_hash,best_exact_state_previously_observed=best_hash in known,
            final_checks_complete=native['final_checks_complete'],target_emitted=native['eligible_target_emitted'],
            supervisor={key:accounting.get(key)for key in ['exit_code','timed_out','interrupted','elapsed_seconds','cpu_seconds','max_rss_kib']})
        if wrapper.exists():row['supervisor_result_sha256']=sha(wrapper)
        rows.append(row)
    return dict(schema='native-xor3-plateau7.evidence.v1',observed_utc=dt.datetime.now(dt.timezone.utc).isoformat(),profiles=rows,
        status_counts=dict(Counter(row['status']for row in rows)),raw_canonical_union_count=len(union),raw_union_vs_pre_crossover_observed=len(union-known),
        claim='New refers only to exact source/observed-state hashes. Return to rank93 is not a new record. No mathematical novelty or global rank bound.')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--campaign',type=Path,required=True);args=parser.parse_args()
    print(json.dumps(summarize(args.campaign.resolve()),sort_keys=True,indent=2,allow_nan=False))

if __name__=='__main__':main()
