"""Freeze disjoint streamed triple tiers, excluding an exhausted prior catalog.

This prepares data and bounded zero-row validation controls only. It does not
dispatch a search or change the campaign queue.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import resource
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.free_factor_kernel import decode_checked
from mmsearch.free_factor_kernel_wide import native_input
from mmsearch.kernel_pair_block import single_optimum
from mmsearch.kernel_triple_catalog import choose3, stream_bytes, stream_cursor
from scripts.freeze_campaign_dictionary import freeze, json_bytes, read_json

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-run', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--tier-size', type=int, default=16)
    args = p.parse_args()
    if not 1 <= args.tier_size <= 256:
        p.error('tier size must be1..256')
    start = time.monotonic(); cpu = time.process_time()
    source = args.source_run.resolve(); out = args.output_dir.resolve()
    summary_raw = (source/'summary.json').read_bytes(); summary = read_json(summary_raw)
    old_manifest_raw = (source/'manifest.json').read_bytes(); old_manifest = read_json(old_manifest_raw)
    old_stats = read_json((source/'native_final_stats.json').read_bytes())
    old_catalog = (source/'triples.txt').read_bytes(); words = old_catalog.decode().split()
    if (summary['status'] != 'NO_TARGET' or not summary['coverage']['supplied_catalog_completed'] or
            not summary['coverage']['contiguous_from_initial'] or words[0] != 'MMKTRIPLES1' or
            sha(old_catalog) != old_manifest['catalog_sha256'] or
            old_stats['catalog_sha256'] != old_manifest['catalog_sha256'] or
            old_stats['input_sha256'] != old_manifest['input_sha256']):
        raise ValueError('source does not certify exhaustion of this exact explicit catalog')
    count_completed = int(words[1]); vals = list(map(int, words[2:]))
    if len(vals) != 3*count_completed or summary['coverage']['prefix_completed'] != count_completed:
        raise ValueError('source complete coverage count mismatch')
    old_rows = [tuple(vals[i:i+3]) for i in range(0, len(vals), 3)]
    if len(set(old_rows)) != len(old_rows):
        raise ValueError('duplicate completed source triple')
    circuits_raw = (source/'inputs/circuits.json').read_bytes(); circuits = read_json(circuits_raw)
    system_raw = (source/'system.json').read_bytes(); system = read_json(system_raw)
    if sha(native_input(system, circuits)) != old_manifest['input_sha256']:
        raise ValueError('source system/circuits differ from exhausted native input')
    _, report = decode_checked(system, system['baseline_vectors'])
    if report['rank'] != 93 or report['exact_entries_checked'] != 15625:
        raise ValueError('requires exact frozen5x5 baseline93')
    vectors = system['baseline_vectors']; count = len(circuits)
    if count < 5+3*args.tier_size+2:
        raise ValueError('catalog too small for requested tiers')
    scores = []
    for i, circuit in enumerate(circuits):
        support = circuit['support']
        active = sum(bool(vectors[g]) for g in support)
        scores.append(dict(index=i, size=len(support), active=active,
                           delta=single_optimum(vectors, support)['delta']))
    def order(i):
        s = scores[i]
        return s['delta'], -s['active'], s['size'], i
    long = sorted((i for i in range(5, count) if scores[i]['size'] > 8), key=order)[:args.tier_size]
    short = sorted((i for i in range(5, count) if scores[i]['size'] <= 8), key=order)[:args.tier_size]
    selected = set(range(5)) | set(long) | set(short)
    active_incidence = Counter(g for i in selected for g in circuits[i]['support'] if vectors[g])
    mixed = sorted((i for i in range(5, count) if i not in selected),
        key=lambda i: (-sum(active_incidence[g] for g in circuits[i]['support']), *order(i)))[:args.tier_size]
    if any(len(tier) != args.tier_size for tier in (long, short, mixed)):
        raise ValueError('insufficient distinct long/short/mixed anchors')
    permutation = list(range(5))+long+short+mixed
    permutation += [i for i in range(count) if i not in set(permutation)]
    inverse = {old: new for new, old in enumerate(permutation)}
    reordered = [circuits[i] for i in permutation]
    completed = [tuple(sorted(inverse[i] for i in t)) for t in old_rows]
    raw_input = native_input(system, reordered)
    out.mkdir(parents=True, exist_ok=False)
    for name in ('dictionary', 'baseline'):
        freeze(out/'inputs'/(name+'.json'), (source/'inputs'/(name+'.json')).read_bytes())
    freeze(out/'circuits.json', json_bytes(reordered)); freeze(out/'system.json', system_raw)
    freeze(out/'baseline.verification.json', json_bytes(report)); freeze(out/'kernel_input.txt', raw_input)
    freeze(out/'source/summary.json', summary_raw); freeze(out/'source/manifest.json', old_manifest_raw)
    freeze(out/'source/completed-triples.txt', old_catalog)
    freeze(out/'permutation.json', json_bytes(dict(new_to_old=permutation,
        old_to_new=[inverse[i] for i in range(count)],
        new5=list(range(5)), long_anchors=long, short_anchors=short, mixed_anchors=mixed,
        scores=[scores[i] for i in permutation[:5+3*args.tier_size]])))
    binary_raw = (ROOT/'native/free_factor_triple_block_worker_wide_v2').read_bytes()
    binary = out/'native-worker'; freeze(binary, binary_raw); binary.chmod(0o555)
    names = ['scripts/prepare_kernel_triple_stream42.py', 'scripts/campaign_kernel_triple_block_wide_v2.py',
             'native/free_factor_triple_block_worker_wide_v2.cpp', 'mmsearch/kernel_triple_catalog.py',
             'mmsearch/kernel_triple_block_wide.py', 'tests/test_kernel_triple_catalog.py',
             'tests/test_kernel_triple_block_wide.py']
    code_hashes = {}
    for name in names:
        raw = (ROOT/name).read_bytes(); freeze(out/'code'/name, raw); code_hashes[name] = sha(raw)
    limits = [0, 5, 5+args.tier_size, 5+2*args.tier_size, 5+3*args.tier_size, count-2]
    labels = ['new5', 'old-long', 'old-short', 'old-mixed', 'remainder']
    cases = []; allocated_exclusions = 0; selected_sum = 0
    for label, begin, end in zip(labels, limits, limits[1:]):
        exclusions = [t for t in completed if begin <= t[0] < end]
        allocated_exclusions += len(exclusions)
        raw, info = stream_bytes(count, begin, end, exclusions)
        path = out/'catalogs'/(label+'.txt'); freeze(path, raw)
        selected_sum += info['selected']
        case = dict(label=label, path=str(path.resolve()), sha256=sha(raw), **info)
        # Zero-budget checks validate native catalog cardinality and resume
        # cursor without evaluating any new triple.
        checks = []
        for cursor in sorted(set((0, info['selected']//2, info['selected']))):
            prefix = out/'controls'/f'{label}-{cursor}'
            cmd = [str(binary), '--input', str(out/'kernel_input.txt'), '--catalog', str(path),
                   '--output', str(prefix), '--seconds', '0', '--target', '92', '--start-row', str(cursor)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode:
                raise ValueError(result.stderr)
            stats = read_json(prefix.with_suffix('.stats.json').read_bytes())
            base_cursor, triple_cursor = stream_cursor(count, begin, end, exclusions, cursor)
            if (stats['triples_total'] != info['selected'] or stats['triples_considered'] != 0 or
                    stats['next_base_ordinal'] != base_cursor or
                    tuple(stats[key] for key in ('next_i', 'next_j', 'next_k')) != triple_cursor):
                raise ValueError('native stream cardinality/cursor mismatch')
            checks.append(dict(row=cursor, base_ordinal=base_cursor, triple=triple_cursor, status=stats['status']))
        case['zero_row_controls'] = checks; cases.append(case)
    if allocated_exclusions != count_completed or selected_sum+count_completed != choose3(count):
        raise ValueError('disjoint tier partition/exclusion audit failed')
    manifest = dict(status='READY_FOR_REVIEW', source_run=str(source), source_summary_sha256=sha(summary_raw),
        baseline_rank=93, exact_entries_checked=15625, circuits=count,
        input_sha256=sha(raw_input), binary_sha256=sha(binary_raw), code_sha256=code_hashes,
        all_unordered_triples=choose3(count), previously_completed=count_completed,
        remaining_partition_total=selected_sum, cases=cases,
        families_pairwise_disjoint=True, exclusions_exactly_partition_completed_catalog=True,
        circuit_permutation_is_bijection=len(set(permutation))==count,
        long_search_launched=False, queue_modified=False,
        elapsed_seconds=time.monotonic()-start, preparation_cpu_seconds=time.process_time()-cpu,
        maximum_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        scope='Finite unordered triples of the same9336 supplied directions on one frozen feasible rank93 W model. '
              'Completed source triples are excluded by exact remapped identity. Each streamed interval is lexicographic; '
              'row cursor, base ordinal and next triple are independently checked. Remainder is optional; no full coverage is claimed until exhausted.')
    freeze(out/'READY.json', json_bytes(manifest)); print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
