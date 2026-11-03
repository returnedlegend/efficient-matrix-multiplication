"""Exact frozen-model triple scans over an explicit prioritized finite subset.

Preparation never claims coverage of C(catalog_size,3). Resume requires identical
input, executable and ordered triple-catalog hashes; row cursor is contiguous.
"""
import argparse
from collections import defaultdict
import datetime
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import random
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.free_factor_kernel import decode_checked, pair_column
from mmsearch.free_factor_kernel_wide import native_input, validate_circuit
from mmsearch.free_factor_sat import audit, build_system
from mmsearch.kernel_pair_block import single_optimum
from mmsearch.kernel_triple_block_wide import validate_triple_solution
from scripts.campaign_kernel_walk_v2 import atomic_json, read_vectors
from scripts.freeze_campaign_dictionary import freeze, json_bytes, read_json

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ('One frozen feasible W model; exact optimization of supplied unordered direction triples only. '
         'The prioritized connected catalog is an explicit subset, not all circuit triples or a global nonexistence result.')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def triple_catalog(circuits, vectors, *, seed=42, priority_first=5, local_anchors=48,
                   neighbors_per_anchor=48, max_triples=100000):
    if not 0 <= priority_first <= len(circuits) or not 0 <= local_anchors <= 1000:
        raise ValueError('invalid anchor limits')
    if not 2 <= neighbors_per_anchor <= 256 or not 1 <= max_triples <= 2000000:
        raise ValueError('invalid finite triple limits')
    rng = random.Random(seed)
    supports = [set(c['support']) for c in circuits]
    by_group = defaultdict(list)
    for i, support in enumerate(supports):
        for g in support:
            by_group[g].append(i)
    delta = [single_optimum(vectors, s)['delta'] for s in supports]
    active = [sum(bool(vectors[g]) for g in s) for s in supports]
    local = sorted((i for i in range(priority_first, len(circuits)) if active[i]),
                   key=lambda i: (delta[i], -active[i], len(supports[i]), i))[:local_anchors]
    anchors = list(range(priority_first)) + local
    rows = set()
    for i in anchors:
        adjacent = set(j for g in supports[i] for j in by_group[g] if j != i)
        ordered = sorted(adjacent, key=lambda j: (delta[j], -sum(bool(vectors[g]) for g in supports[i] & supports[j]),
                                                  len(supports[j]), j))
        top = min(len(ordered), (neighbors_per_anchor + 1) // 2)
        chosen = ordered[:top]
        chosen += rng.sample(ordered[top:], min(len(ordered)-top, neighbors_per_anchor-top))
        for j, k in combinations(chosen, 2):
            rows.add(tuple(sorted((i, j, k))))
    # Deterministic priority tiers, then lexicographic indices. Sampling chooses
    # the finite family; changing these parameters changes its frozen hash.
    prioritized = sorted(rows, key=lambda t: (-sum(i < priority_first for i in t),
                                              sum(delta[i] for i in t), t))[:max_triples]
    raw = ('MMKTRIPLES1 ' + str(len(prioritized)) + '\n' +
           ''.join(' '.join(map(str, row)) + '\n' for row in prioritized)).encode()
    return raw, dict(seed=seed, priority_first=priority_first, local_anchors=local,
                     anchors=anchors, neighbors_per_anchor=neighbors_per_anchor,
                     generated_unique=len(rows), selected=len(prioritized), cap=max_triples,
                     overlap_connected=True, full_unordered_family=False,
                     catalog_order='new-direction-count descending; single-delta ascending; lexicographic triple',
                     all_unordered_triples=len(circuits)*(len(circuits)-1)*(len(circuits)-2)//6)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dictionary', type=Path, required=True)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--circuits', type=Path, required=True)
    p.add_argument('--orientation', choices=('uv', 'vw', 'wu'), default='wu')
    p.add_argument('--outdir', '--output-dir', dest='outdir', type=Path, required=True)
    p.add_argument('--binary', type=Path, default=ROOT/'native/free_factor_triple_block_worker_wide')
    p.add_argument('--seconds', type=float, default=600)
    p.add_argument('--max-triples', type=int, default=0, help='native rows per invocation; zero means no row cap')
    p.add_argument('--catalog-cap', type=int, default=100000)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--priority-first', type=int, default=5)
    p.add_argument('--local-anchors', type=int, default=48)
    p.add_argument('--neighbors-per-anchor', type=int, default=48)
    p.add_argument('--triple-catalog', type=Path, help='reuse an already frozen ordered text catalog')
    p.add_argument('--prepare-only', action='store_true')
    p.add_argument('--resume-from', type=Path)
    p.add_argument('--deadline-utc')
    args = p.parse_args()
    if not math.isfinite(args.seconds) or args.seconds <= 2 or args.max_triples < 0:
        p.error('invalid native budgets')
    started = time.monotonic()
    out = args.outdir.resolve(); out.mkdir(parents=True, exist_ok=False)
    if args.deadline_utc:
        cutoff = datetime.datetime.fromisoformat(args.deadline_utc.replace('Z', '+00:00')).timestamp()
        args.seconds = min(args.seconds, max(0, cutoff-time.time()))
    if args.seconds <= 2:
        atomic_json(out/'summary.json', dict(status='UNKNOWN', reason='deadline leaves no scan budget', native_dispatched=False))
        return 0
    inputs = {name: path.read_bytes() for name, path in (
        ('dictionary', args.dictionary), ('baseline', args.baseline), ('circuits', args.circuits))}
    for name, raw in inputs.items():
        freeze(out/'inputs'/(name+'.json'), raw)
    system = build_system(read_json(inputs['dictionary']), 5, args.orientation, read_json(inputs['baseline']))
    baseline_candidate, baseline_report = decode_checked(system, system['baseline_vectors'])
    if baseline_report['rank'] != 93 or baseline_report['exact_entries_checked'] != 15625:
        raise ValueError('campaign requires exact 5x5/F2 baseline rank93')
    circuits = read_json(inputs['circuits'])
    if not 3 <= len(circuits) <= 50000:
        raise ValueError('requires3..50000 distinct circuits')
    columns = [pair_column(pair, 25) for pair in system['pairs']]
    seen = set()
    for circuit in circuits:
        validate_circuit(columns, circuit['support'])
        key = tuple(sorted(circuit['support']))
        if key in seen:
            raise ValueError('duplicate circuit support')
        seen.add(key)
    raw_input = native_input(system, circuits)
    if args.triple_catalog:
        raw_catalog = args.triple_catalog.read_bytes()
        words = raw_catalog.decode().split()
        if len(words) < 2 or words[0] != 'MMKTRIPLES1':
            raise ValueError('invalid explicit catalog header')
        count = int(words[1]); values = list(map(int, words[2:]))
        if not 0 <= count <= 2000000 or len(values) != 3*count:
            raise ValueError('invalid explicit catalog length')
        rows = [tuple(values[i:i+3]) for i in range(0, len(values), 3)]
        if len(set(rows)) != count or any(not 0 <= i < j < k < len(circuits) for i, j, k in rows):
            raise ValueError('invalid explicit catalog indices')
        catalog_info = dict(selected=count, full_unordered_family=False, provided_path=str(args.triple_catalog.resolve()))
    else:
        raw_catalog, catalog_info = triple_catalog(circuits, system['baseline_vectors'], seed=args.seed,
            priority_first=args.priority_first, local_anchors=args.local_anchors,
            neighbors_per_anchor=args.neighbors_per_anchor, max_triples=args.catalog_cap)
    input_sha, catalog_sha = digest(raw_input), digest(raw_catalog)
    freeze(out/'kernel_input.txt', raw_input); freeze(out/'triples.txt', raw_catalog)
    freeze(out/'catalog.json', json_bytes(catalog_info)); freeze(out/'system.json', json_bytes(system))
    freeze(out/'system.audit.json', json_bytes(audit(system)))
    freeze(out/'baseline.verification.json', json_bytes(baseline_report))
    names = ['scripts/campaign_kernel_triple_block_wide.py', 'mmsearch/kernel_triple_block_wide.py',
             'native/free_factor_triple_block_worker_wide.cpp', 'mmsearch/kernel_pair_block.py',
             'mmsearch/free_factor_kernel_wide.py', 'mmsearch/free_factor_kernel.py',
             'mmsearch/free_factor_sat.py', 'mmsearch/verify.py', 'mmsearch/search.py',
             'scripts/campaign_kernel_walk_v2.py', 'scripts/freeze_campaign_dictionary.py']
    code = {name: (ROOT/name).read_bytes() for name in names}
    for name, raw in code.items():
        freeze(out/'code'/name, raw)
    binary_raw = args.binary.read_bytes(); binary_sha = digest(binary_raw)
    binary = out/'native-worker'; freeze(binary, binary_raw); binary.chmod(0o555)
    prior = 0
    if args.resume_from:
        previous = args.resume_from.resolve()
        old = read_json((previous/'manifest.json').read_bytes())
        stats = read_json((previous/'native_final_stats.json').read_bytes())
        summary = read_json((previous/'summary.json').read_bytes())
        if any(old[key] != value for key, value in (
            ('input_sha256', input_sha), ('catalog_sha256', catalog_sha), ('binary_sha256', binary_sha))):
            raise ValueError('resume instance, ordered family, or worker differs')
        prior = summary['coverage']['prefix_completed']
        if not summary['coverage']['contiguous_from_initial'] or stats['next_row'] != prior:
            raise ValueError('invalid contiguous resume cursor')
    manifest = dict(input_sha256=input_sha, catalog_sha256=catalog_sha, binary_sha256=binary_sha,
        source_sha256={name: digest(raw) for name, raw in inputs.items()},
        source_paths={name: str(getattr(args, name).resolve()) for name in inputs},
        code_sha256={name: digest(raw) for name, raw in code.items()},
        circuits=len(circuits), triples_total=catalog_info['selected'], baseline_active=93,
        start_row=prior, resume_from=str(args.resume_from) if args.resume_from else None,
        resume_summary_sha256=digest((args.resume_from/'summary.json').read_bytes()) if args.resume_from else None,
        scope=SCOPE)
    if args.prepare_only:
        freeze(out/'manifest.json', json_bytes(manifest))
        atomic_json(out/'summary.json', dict(status='PREPARED', native_dispatched=False,
            triples_total=catalog_info['selected'], scope=SCOPE))
        print(json.dumps(dict(status='PREPARED', triples_total=catalog_info['selected'], outdir=str(out))))
        return 0
    remaining = args.seconds-(time.monotonic()-started)-2
    if remaining <= 0:
        freeze(out/'manifest.json', json_bytes(manifest))
        atomic_json(out/'summary.json', dict(status='UNKNOWN', reason='preparation exhausted budget', native_dispatched=False))
        return 0
    prefix = out/'phase-000'/'triple_scan'; prefix.parent.mkdir()
    command = [str(binary), '--input', str(out/'kernel_input.txt'), '--catalog', str(out/'triples.txt'),
        '--output', str(prefix), '--target', '92', '--seconds', str(remaining), '--start-row', str(prior),
        '--max-triples', str(args.max_triples), '--input-sha256', input_sha, '--catalog-sha256', catalog_sha,
        '--baseline-sha256', manifest['source_sha256']['baseline']]
    manifest['command'] = command; freeze(out/'manifest.json', json_bytes(manifest))
    stopped = False
    def stop(signum, frame):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    with (out/'worker.log').open('x') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None and not stopped:
                stats_path = prefix.with_suffix('.stats.json')
                if stats_path.exists():
                    atomic_json(out/'progress.json', read_json(stats_path.read_bytes()))
                time.sleep(.2)
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
    if process.returncode != 0:
        atomic_json(out/'summary.json', dict(status='ERROR', exit_code=process.returncode, scope=SCOPE))
        return 2
    stats_raw = prefix.with_suffix('.stats.json').read_bytes(); stats = read_json(stats_raw)
    freeze(out/'native_final_stats.json', stats_raw)
    if stats['input_sha256'] != input_sha or stats['catalog_sha256'] != catalog_sha:
        raise ValueError('native instance/catalog hash mismatch')
    if stats['triples_total'] != manifest['triples_total'] or stats['prefix_rows_skipped'] != prior:
        raise ValueError('native finite family mismatch')
    complete = prior + stats['triples_considered']
    if stats['next_row'] != complete or not prior <= complete <= manifest['triples_total']:
        raise ValueError('native contiguous row coverage mismatch')
    vectors = read_vectors(Path(str(prefix)+'.best.w.txt'), len(columns), 25)
    candidate, report = decode_checked(system, vectors, dict(manifest, method='exact-three-direction-block'))
    freeze(out/'best.json', json_bytes(candidate)); freeze(out/'best.verification.json', json_bytes(report))
    if report['rank'] != stats['best_rank']:
        raise ValueError('native and global verifier rank mismatch')
    if stats['status'] == 'MODEL_FOUND' and Path(str(prefix)+'.solution.json').exists():
        proof_raw = Path(str(prefix)+'.solution.json').read_bytes()
        moved, _, optimum_report = validate_triple_solution(system, circuits, read_json(proof_raw))
        if vectors != moved:
            raise ValueError('native checkpoint differs from triple proof')
        freeze(out/'solution.json', proof_raw); freeze(out/'independent-block-verification.json', json_bytes(optimum_report))
    winner = report['valid'] and report['rank'] <= 92 and report['exact_entries_checked'] == 15625
    if winner:
        freeze(out/'WINNER.json', json_bytes(candidate))
    coverage = dict(triples_total=manifest['triples_total'], triples_completed_this_run=stats['triples_considered'],
        prefix_completed=complete, contiguous_from_initial=True,
        supplied_catalog_completed=stats['status']=='NO_TARGET' and complete==manifest['triples_total'],
        full_unordered_circuit_family_completed=False, next_row=stats['next_row'])
    summary = dict(status='VERIFIED_TARGET' if winner else stats['status'], reason=stats['reason'],
        winner=winner, best_rank=report['rank'], exact_entries_checked=report['exact_entries_checked'],
        coverage=coverage, bound_pruned=stats['bound_pruned'], exact_evaluated=stats['exact_evaluated'],
        elapsed_seconds=time.monotonic()-started, scope=SCOPE)
    atomic_json(out/'summary.json', summary); print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # Preserve an explicit ERROR on preparation/validation failures too.
        if '--outdir' in sys.argv or '--output-dir' in sys.argv:
            key = '--outdir' if '--outdir' in sys.argv else '--output-dir'
            destination = Path(sys.argv[sys.argv.index(key)+1])
            if destination.is_dir() and not (destination/'summary.json').exists():
                atomic_json(destination/'summary.json', dict(status='ERROR', reason=str(error), scope=SCOPE))
        raise
