"""Persist a small, read-only campaign monitoring pulse."""
import json
import os
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.rl_campaign_status import summarize, compact_summary, events


def main():
    os.sched_setaffinity(0, {2})
    os.nice(10)
    path = Path(sys.argv[1])
    detail = compact_summary(summarize(path, scan_disk=False), path)
    result = {key: detail[key] for key in (
        'utc', 'remaining_seconds', 'active_jobs', 'global_best_rank',
        'rss_bytes', 'native_attempts_total', 'sat_status_counts')}
    latest = {}
    for name, value in detail['rl'].items():
        family = name.split('-')[0]
        if family in ('learned', 'random') and value.get('steps', -1) >= latest.get(family, ('', {'steps': -1}))[1]['steps']:
            latest[family] = (name, value)
    result['rl'] = {name: {key: value[key] for key in (
        'steps', 'updates', 'best_rank', 'recovery_episodes', 'recovery_successes')}
        for name, value in latest.values()}
    counts = Counter()
    complete = True
    for event_path in path.glob('orbit-sat*/events.jsonl'):
        rows, window = events(event_path, 16*1024*1024)
        counts.update(row['status'] for row in rows if 'status' in row)
        complete &= window['window_complete']
    result['c3_status_counts'] = dict(counts)
    result['c3_windows_complete'] = complete
    result['free_factor'] = {}
    result['free_factor_controls'] = {}
    for result_path in path.glob('free-factor-*/result.json'):
        try:
            value = json.loads(result_path.read_text())
            result['free_factor'][result_path.parent.name] = {
                key: value.get(key) for key in ('status', 'control_status', 'orientation')}
        except (OSError, ValueError):
            pass
    for control_path in path.glob('free-factor-*/control.result.json'):
        try:
            result['free_factor_controls'][control_path.parent.name] = json.loads(control_path.read_text()).get('status')
        except (OSError, ValueError):
            pass
    detail['c3_status_counts'] = result['c3_status_counts']
    detail['free_factor'] = result['free_factor']
    try:
        result['queue_stop_reason'] = json.loads((path/'queue_state.json').read_text()).get('stop_reason')
    except (OSError, ValueError):
        result['queue_stop_reason'] = None
    result['coordinate'] = {}
    for result_path in path.glob('coordinate-*/result.json'):
        try:
            value = json.loads(result_path.read_text())
            result['coordinate'][result_path.parent.name] = {
                key: value.get(key) for key in ('status', 'control_status', 'winner')}
        except (OSError, ValueError):
            pass
    temporary = path/'live_status.json.tmp'
    temporary.write_text(json.dumps(detail, indent=2)+'\n')
    temporary.replace(path/'live_status.json')
    with (path/'monitor.jsonl').open('a') as stream:
        stream.write(json.dumps(result)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
