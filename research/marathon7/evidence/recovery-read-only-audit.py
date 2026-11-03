"""Read-only replay of persisted observed-palette result/ledger chains.

No tensor decoder or search is called. Output belongs to the fresh campaign.
"""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import resource
import time


def read(path):
    return json.loads(path.read_bytes())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (25, 30))
    started = time.process_time()
    out = Path(__file__).resolve().parent
    repo = out.parents[1]
    campaign = repo / 'artifacts/rl_campaign42_20261103T033116Z'
    prepared = campaign / 'observed-rank3-lazy-ready-v2'
    plan = read(prepared / 'plan.json')
    chunks = {item['id']: item for item in plan['chunks']}
    ledger_path = campaign / 'observed-rank3-remaining-jobs-v1/coverage-ledger.json'
    ledger = read(ledger_path)
    jobs, counts, sources = [], Counter(), Counter()
    branches = 0
    for number in range(1, 11):
        directory = campaign / f'observed-rank3-remaining-{number:03d}'
        config = read(directory / 'config.json')
        config_hash = digest(config)
        report_path = directory / 'report-launch000.json'
        report = read(report_path)
        assert config['plan_sha256'] == digest(plan)
        assert report['status'] == 'SELECTED_CHUNKS_COMPLETE' and report['reason'] is None
        completed = []
        for name in config['chunk_ids']:
            chunk = chunks[name]
            compressed = (prepared / chunk['plan']).read_bytes()
            items = json.loads(gzip.decompress(compressed))
            assert sha(compressed) == chunk['compressed_sha256']
            assert digest(items) == chunk['plan_sha256']
            current = directory / 'chunks' / name
            cursor = read(current / 'cursor.json')
            rows = (current / 'results.jsonl').read_bytes().splitlines()
            chain = digest([config_hash, chunk])
            assert len(rows) == cursor['next_index'] == len(items) == chunk['count']
            assert cursor['config_sha256'] == config_hash
            for index, line in enumerate(rows):
                event = json.loads(line)
                value = event['value']
                assert event['previous_sha256'] == chain
                assert event['sha256'] == digest({k: v for k, v in event.items() if k != 'sha256'})
                chain = event['sha256']
                assert value['index'] == index and value['case'] == items[index]
                assert value['source_id'] == chunk['source_id']
                assert value['source_system_sha256'] == plan['sources'][chunk['source_id']]['system_sha256']
                result = value['result']
                assert result['status'] == 'NO_ONE_SUBSPACE_GAIN'
                assert result['complete_for_requested_bound'] is True and result['worker_reaped'] is True
                assert result['requested_bound'] == items[index]['weight_bound']
                archive = (current / value['branch_ledger']).read_bytes()
                assert sha(archive) == value['branch_ledger_sha256']
                raw = gzip.decompress(archive)
                assert sha(raw) == value['branch_ledger_uncompressed_sha256']
                assert len(raw.splitlines()) == value['branch_records']
                counts[result['status']] += 1
                sources[chunk['source_id']] += 1
                branches += value['branch_records']
            assert chain == cursor['result_chain_sha256']
            completed.append(dict(id=name, cases=len(rows), chain_sha256=chain))
        count = sum(item['cases'] for item in completed)
        assert count == report['target_queries_this_launch'] == ledger['jobs'][number - 1]['cases']
        result_path = campaign / f'observed-rank3-remaining-{number:03d}-job.result.json'
        result = read(result_path)
        assert result['exit_code'] == 0 and not result['timed_out'] and not result['interrupted']
        jobs.append(dict(sequence=number, cases=count, chunks=completed,
                         report_sha256=sha(report_path.read_bytes()), result_sha256=sha(result_path.read_bytes())))
    assert sum(counts.values()) == 41722
    prior = ledger['cumulative_observed_spaces']
    assert prior['original_catalogued'] == 310788
    assert prior['exact_total_with_cheap_bound'] == 269066
    assert 269066 + 41722 == 310788
    cpdir = campaign / 'cp7-rank3-completion-audit-v1'
    cp_path = cpdir / 'CP7-FINITE-FAMILY.json'
    cp = read(cp_path)
    assert sha(cp_path.read_bytes()) == read(cpdir / 'manifest.json')['files']['CP7-FINITE-FAMILY.json']
    assert cp['total_supplied_eight_union_residuals'] == 981476
    assert cp['new_CP7_negatives'] == 21380 and cp['prior_exact_masks'] == 449
    assert cp['p1_rank8_exclusions'] == 959647 and 21380 + 449 + 959647 == 981476
    result = dict(status='COMPLETE_REMAINING_FINITE_PALETTE_CHAIN_AUDIT_PASS',
                  created_utc=datetime.now(timezone.utc).isoformat(), remaining_cases_replayed=41722,
                  terminal_counts=dict(counts), source_counts=dict(sources), branch_records=branches,
                  jobs=jobs, prior_closed_cases_from_frozen_coverage_ledger=269066,
                  prior_closed_evidence=prior, original_catalogued=310788,
                  closed_frozen_catalog=310788, remaining=0, decoder_calls=0,
                  audit_cpu_seconds=time.process_time() - started,
                  scope='Frozen explicit observed3D palette catalog for recorded fixed sources/P/W and requested groupweight<=5 bounds only. Prior269066 closures are carried from frozen coverage ledger; recovery replays all41722 remaining cases. No all-image-rank3 or global-rank claim.',
                  coverage_ledger_sha256=sha(ledger_path.read_bytes()),
                  prior_cp7_summary_integrity_checked=True, cp7_summary_sha256=sha(cp_path.read_bytes()),
                  cp7_scope=cp['scope'],
                  cp7_recovery_limit='Saved CP7 summary integrity and count partition checked; prior21380 archive audit was not repeated in recovery.')
    with (out / 'recovered-rank3-closure.json').open('x') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({key: value for key, value in result.items() if key not in ('jobs', 'prior_closed_evidence')}))


if __name__ == '__main__':
    main()
