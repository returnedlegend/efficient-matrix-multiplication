"""Read-only portfolio evidence aggregation; no native queries or file writes."""
from __future__ import annotations
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path

def summarize(campaign):
    rows, union = [], set()
    for number in range(1,7):
        name = f'native-portfolio7-p{number:02d}'
        path = campaign/name/'summary.json'
        if not path.exists():
            rows.append(dict(id=name,status='OPEN_NO_SUMMARY'))
            continue
        raw = path.read_bytes(); value = json.loads(raw)
        stats, metrics = value.get('stats') or {}, value['exploration_metrics']
        hashes = set(metrics['raw_canonical_hashes']); previous = len(union); union |= hashes
        classification = ('OWNED_NATIVE_ERROR' if value['execution']['exit_code'] != 0 else
                          'INCOMPLETE_FINAL_VERIFICATION' if not value['final_checks_complete'] else value['status'])
        rows.append(dict(id=name,status=classification,summary_status=value['status'],
            summary_sha256=hashlib.sha256(raw).hexdigest(),profile=value['profile'],execution=value['execution'],
            best_rank=stats.get('best_rank'),current_rank=stats.get('current_rank'),
            maximum_visited_rank=stats.get('max_visited_rank'),steps=stats.get('steps'),
            reduction_dwell_steps=stats.get('dwell_steps'),burst_max_accepted_pluses=stats.get('burst_max_accepted_pluses'),
            eligible_target_emitted=value['eligible_target_emitted'],final_checks_complete=value['final_checks_complete'],
            stop_reason=value.get('stop_reason'),output_bytes=value.get('output_bytes'),
            new_raw_hashes_vs_prior_profiles=len(union)-previous,
            metrics={key:item for key,item in metrics.items() if key!='raw_canonical_hashes'}))
    return dict(schema='native-portfolio7-evidence.v1',observed_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        profiles=rows,profiles_with_summaries=sum(row['status']!='OPEN_NO_SUMMARY' for row in rows),
        raw_canonical_union_count=len(union),state_histogram=dict(Counter(row['status'] for row in rows)),
        claim='Raw hash difference measures sampled exact-state diversity, not mathematical novelty. Bounded failures are not tensor rank lower bounds.')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--campaign',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(summarize(args.campaign.resolve()),sort_keys=True,indent=2,allow_nan=False))

if __name__=='__main__':main()
