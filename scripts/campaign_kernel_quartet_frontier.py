"""Exact frozen-model quartet scans over an explicit prioritized finite subset.

Preparation never claims coverage of C(catalog_size,3). Resume requires identical
input, executable and ordered quartet-catalog hashes; row cursor is contiguous.
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
from mmsearch.kernel_quartet_block_wide import validate_quartet_solution, basis_workload, frequencies
from mmsearch.kernel_quartet_frontier import reconstruct, select_diverse, verify_export, model_bytes, compress_export, matrix_rank
from scripts.campaign_kernel_walk_v2 import atomic_json, read_vectors
from scripts.freeze_campaign_dictionary import freeze, json_bytes, read_json
from mmsearch.search import decode_candidate
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
_CREATED_OUTPUT = None
SCOPE = ('One frozen feasible W model; exact optimization of supplied unordered direction quartets only. '
         'Both the quartet catalog and retained frontier are bounded samples. Changed W models start fresh coverage; no global nonexistence or all-tie claim.')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def quartet_catalog(circuits, vectors, *, seed=42, priority_first=5, local_anchors=32,
                    neighbors_per_anchor=32, max_quartets=2000):
    """Connected stars and paths from a frozen active/local/seeded pool."""
    if not 0 <= priority_first <= len(circuits) or not 0 <= local_anchors <= 128:
        raise ValueError('invalid quartet anchors')
    if not 3 <= neighbors_per_anchor <= 128 or not 1 <= max_quartets <= 10000:
        raise ValueError('invalid quartet subset limits')
    rng = random.Random(seed)
    supports = [set(c['support']) for c in circuits]
    active = [sum(bool(vectors[g]) for g in s) for s in supports]
    delta = [single_optimum(vectors, s)['delta'] for s in supports]
    def order(i):
        return delta[i], -active[i], len(supports[i]), i
    remaining = list(range(priority_first, len(circuits)))
    short = sorted((i for i in remaining if len(supports[i]) <= 8 and active[i]), key=order)[:local_anchors]
    long = sorted((i for i in remaining if len(supports[i]) > 8 and active[i]), key=order)[:local_anchors]
    anchors = list(dict.fromkeys([*range(priority_first), *short, *long]))
    rest = [i for i in remaining if i not in set(anchors)]
    pool = sorted(set(anchors+rng.sample(rest, min(64, len(rest)))))
    adjacent = {i: [j for j in pool if j != i and supports[i] & supports[j]] for i in pool}
    rows = set()
    for i in anchors:
        neighbors = sorted(adjacent[i], key=lambda j: (-sum(bool(vectors[g]) for g in supports[i]&supports[j]), *order(j)))
        take = min(neighbors_per_anchor, 12, len(neighbors))
        top = (take+1)//2
        chosen = neighbors[:top] + rng.sample(neighbors[top:], take-top)
        rows.update(tuple(sorted((i,j,k,l))) for j,k,l in combinations(chosen,3))
    # Paths retain connected quartets without demanding a degree-three center.
    for _ in range(max_quartets*3):
        chosen = [rng.choice(anchors)] if anchors else []
        while chosen and len(chosen) < 4:
            frontier = sorted(set(j for i in chosen for j in adjacent[i])-set(chosen))
            if not frontier: break
            chosen.append(rng.choice(frontier))
        if len(chosen) == 4: rows.add(tuple(sorted(chosen)))
    priority = sorted(rows, key=lambda t: (-sum(i < priority_first for i in t), sum(delta[i] for i in t), t))
    selected = []
    discarded_bound = 0
    for row in priority:
        counts = frequencies(vectors, [circuits[i]['support'] for i in row])
        potential = sum(max(c.values(), default=0)-c[0] for c in counts)
        if potential < 1:
            discarded_bound += 1
            continue
        work = basis_workload(vectors, [circuits[i]['support'] for i in row])
        selected.append(dict(indices=row, possible_gain_upper=potential, **work))
        if len(selected) == max_quartets: break
    selected.sort(key=lambda item: (-sum(i < priority_first for i in item['indices']), item['exact_rhs_assignments'], item['indices']))
    raw = (f'MMKQUARTETS1 {len(selected)}\n'+''.join(' '.join(map(str,item['indices']))+'\n' for item in selected)).encode()
    return raw, dict(seed=seed, priority_first=priority_first, local_anchors=anchors, pool=pool,
        selected=len(selected), generated_unique=len(rows), safe_bound_discarded_before_cap=discarded_bound,
        cap=max_quartets, overlap_connected=True, full_unordered_family=False,
        catalog_order='new direction count descending; exact full-basis RHS workload ascending; lexicographic quartet',
        rows=selected, scope='Explicit connected star/path subset of the supplied directions; omitted quartets unsearched.')


def main():
    global _CREATED_OUTPUT
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dictionary', type=Path, required=True)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--circuits', type=Path, required=True)
    p.add_argument('--orientation', choices=('uv', 'vw', 'wu'), default='wu')
    p.add_argument('--outdir', '--output-dir', dest='outdir', type=Path, required=True)
    p.add_argument('--binary', type=Path, default=ROOT/'native/free_factor_quartet_frontier_worker')
    p.add_argument('--dimension', type=int, choices=(2,3,5), default=5)
    p.add_argument('--target', type=int, default=92)
    p.add_argument('--frontier-per-row', type=int, default=64)
    p.add_argument('--export-limit', type=int, default=16)
    p.add_argument('--seconds', type=float, default=600)
    p.add_argument('--max-quartets', type=int, default=0, help='native rows per invocation; zero means no row cap')
    p.add_argument('--catalog-cap', type=int, default=2000)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--priority-first', type=int, default=5)
    p.add_argument('--local-anchors', type=int, default=32)
    p.add_argument('--neighbors-per-anchor', type=int, default=32)
    p.add_argument('--quartet-catalog', type=Path, help='reuse an already frozen ordered text catalog')
    p.add_argument('--prepare-only', action='store_true')
    p.add_argument('--resume-from', type=Path)
    p.add_argument('--deadline-utc')
    args = p.parse_args()
    if not math.isfinite(args.seconds) or args.seconds <= 2 or args.max_quartets < 0 or not 0 <= args.export_limit <= 16 or not 0 <= args.seed < 1 << 64 or not 1 <= args.frontier_per_row <= 4096 or args.target < 0:
        p.error('invalid native budgets')
    started = time.monotonic()
    out = args.outdir.resolve(); out.mkdir(parents=True, exist_ok=False)
    _CREATED_OUTPUT = out
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
    system = build_system(read_json(inputs['dictionary']), args.dimension, args.orientation, read_json(inputs['baseline']))
    baseline_candidate, baseline_report = decode_checked(system, system['baseline_vectors'])
    if baseline_report['exact_entries_checked'] != args.dimension**6 or (args.dimension==5 and baseline_report['rank'] not in (93,94)):
        raise ValueError('frontier requires verified93/94 campaign source (small dimensions are controls)')
    circuits = read_json(inputs['circuits'])
    if not 4 <= len(circuits) <= 50000:
        raise ValueError('requires4..50000 distinct circuits')
    columns = [pair_column(pair, args.dimension**2) for pair in system['pairs']]
    seen = set()
    for circuit in circuits:
        validate_circuit(columns, circuit['support'])
        key = tuple(sorted(circuit['support']))
        if key in seen:
            raise ValueError('duplicate circuit support')
        seen.add(key)
    raw_input = native_input(system, circuits)
    if args.quartet_catalog:
        raw_catalog = args.quartet_catalog.read_bytes()
        words = raw_catalog.decode().split()
        if len(words) < 2 or words[0] != 'MMKQUARTETS1':
            raise ValueError('invalid explicit catalog header')
        count = int(words[1]); values = list(map(int, words[2:]))
        if not 0 <= count <= 2000000 or len(values) != 4*count:
            raise ValueError('invalid explicit catalog length')
        rows = [tuple(values[i:i+4]) for i in range(0, len(values), 4)]
        if len(set(rows)) != count or any(not 0 <= i < j < k < l < len(circuits) for i, j, k, l in rows):
            raise ValueError('invalid explicit catalog indices')
        catalog_info = dict(selected=count, full_unordered_family=False, provided_path=str(args.quartet_catalog.resolve()))
    else:
        raw_catalog, catalog_info = quartet_catalog(circuits, system['baseline_vectors'], seed=args.seed,
            priority_first=args.priority_first, local_anchors=args.local_anchors,
            neighbors_per_anchor=args.neighbors_per_anchor, max_quartets=args.catalog_cap)
    input_sha, catalog_sha = digest(raw_input), digest(raw_catalog)
    freeze(out/'kernel_input.txt', raw_input); freeze(out/'quartets.txt', raw_catalog)
    freeze(out/'catalog.json', json_bytes(catalog_info)); freeze(out/'system.json', json_bytes(system))
    freeze(out/'system.audit.json', json_bytes(audit(system)))
    freeze(out/'baseline.verification.json', json_bytes(baseline_report))
    names = ['scripts/campaign_kernel_quartet_frontier.py', 'mmsearch/kernel_quartet_block_wide.py',
             'native/free_factor_quartet_frontier_worker.cpp', 'mmsearch/kernel_quartet_frontier.py', 'mmsearch/pair_column_compression.py', 'mmsearch/slice_compression.py', 'native/kernel_quartet_optimizer.hpp', 'mmsearch/kernel_pair_block.py',
             'mmsearch/free_factor_kernel_wide.py', 'mmsearch/free_factor_kernel.py',
             'mmsearch/free_factor_sat.py', 'mmsearch/verify.py', 'mmsearch/search.py',
             'scripts/campaign_kernel_walk_v2.py', 'scripts/freeze_campaign_dictionary.py']
    code = {name: (ROOT/name).read_bytes() for name in names}
    for name, raw in code.items():
        freeze(out/'code'/name, raw)
    binary_raw = args.binary.read_bytes(); binary_sha = digest(binary_raw)
    binary = out/'native-worker'; freeze(binary, binary_raw); binary.chmod(0o555)
    prior = 0; frontier_load = None
    if args.resume_from:
        previous = args.resume_from.resolve()
        old = read_json((previous/'manifest.json').read_bytes())
        stats = read_json((previous/'native_final_stats.json').read_bytes())
        summary = read_json((previous/'summary.json').read_bytes())
        if summary.get('winner'): raise ValueError('verified target already reached; no continuation permitted')
        if any(old[key] != value for key, value in (
            ('input_sha256', input_sha), ('catalog_sha256', catalog_sha), ('binary_sha256', binary_sha))):
            raise ValueError('resume instance, ordered family, or worker differs')
        prior = summary['coverage']['prefix_completed']
        frontier_load = previous/'native_frontier.txt'
        if digest(frontier_load.read_bytes()) != summary['native_frontier_sha256'] or old['frontier_seed'] != args.seed or old['frontier_per_row'] != args.frontier_per_row or old['target_rank'] != args.target:
            raise ValueError('frontier resume archive/seed binding mismatch')
        if not summary['coverage']['contiguous_from_initial'] or stats['next_row'] != prior:
            raise ValueError('invalid contiguous resume cursor')
    manifest = dict(input_sha256=input_sha, catalog_sha256=catalog_sha, binary_sha256=binary_sha,
        source_sha256={name: digest(raw) for name, raw in inputs.items()},
        source_paths={name: str(getattr(args, name).resolve()) for name in inputs},
        code_sha256={name: digest(raw) for name, raw in code.items()},
        circuits=len(circuits), quartets_total=catalog_info['selected'], baseline_active=baseline_report['rank'], target_rank=args.target, frontier_seed=args.seed, frontier_per_row=args.frontier_per_row,
        start_row=prior, resume_from=str(args.resume_from) if args.resume_from else None,
        resume_summary_sha256=digest((args.resume_from/'summary.json').read_bytes()) if args.resume_from else None,
        scope=SCOPE)
    if args.prepare_only:
        freeze(out/'manifest.json', json_bytes(manifest))
        atomic_json(out/'summary.json', dict(status='PREPARED', native_dispatched=False,
            quartets_total=catalog_info['selected'], scope=SCOPE))
        print(json.dumps(dict(status='PREPARED', quartets_total=catalog_info['selected'], outdir=str(out))))
        return 0
    remaining = args.seconds-(time.monotonic()-started)-2
    if remaining <= 0:
        freeze(out/'manifest.json', json_bytes(manifest))
        atomic_json(out/'summary.json', dict(status='UNKNOWN', reason='preparation exhausted budget', native_dispatched=False))
        return 0
    prefix = out/'phase-000'/'quartet_scan'; prefix.parent.mkdir()
    command = [str(binary), '--input', str(out/'kernel_input.txt'), '--catalog', str(out/'quartets.txt'),
        '--output', str(prefix), '--target', str(args.target), '--seed', str(args.seed), '--frontier-per-row', str(args.frontier_per_row), '--seconds', str(remaining), '--start-row', str(prior),
        '--max-quartets', str(args.max_quartets), '--input-sha256', input_sha, '--catalog-sha256', catalog_sha,
        '--baseline-sha256', manifest['source_sha256']['baseline']]
    if frontier_load is not None: command += ['--frontier-load', str(frontier_load)]
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
    if stats['quartets_total'] != manifest['quartets_total'] or stats['prefix_rows_skipped'] != prior:
        raise ValueError('native finite family mismatch')
    complete = prior + stats['quartets_considered']
    if stats['next_row'] != complete or not prior <= complete <= manifest['quartets_total']:
        raise ValueError('native contiguous row coverage mismatch')
    vectors = read_vectors(Path(str(prefix)+'.best.w.txt'), len(columns), args.dimension**2)
    candidate, report = decode_checked(system, vectors, dict(manifest, method='exact-three-direction-block'))
    freeze(out/'best.json', json_bytes(candidate)); freeze(out/'best.verification.json', json_bytes(report))
    if report['rank'] != stats['best_rank']:
        raise ValueError('native and global verifier rank mismatch')
    if stats['status'] == 'MODEL_FOUND' and Path(str(prefix)+'.solution.json').exists():
        proof_raw = Path(str(prefix)+'.solution.json').read_bytes()
        moved, _, optimum_report = validate_quartet_solution(system, circuits, read_json(proof_raw))
        if vectors != moved:
            raise ValueError('native checkpoint differs from quartet proof')
        freeze(out/'solution.json', proof_raw); freeze(out/'independent-block-verification.json', json_bytes(optimum_report))
    winner = report['valid'] and report['rank'] <= args.target and report['exact_entries_checked'] == args.dimension**6
    if winner:
        freeze(out/'WINNER.json', json_bytes(candidate))
    native_frontier = Path(str(prefix)+'.frontier.txt').read_bytes()
    freeze(out/'native_frontier.txt', native_frontier)
    cat_words = raw_catalog.decode().split(); cat_values = list(map(int, cat_words[2:]))
    cat_rows = [tuple(cat_values[i:i+4]) for i in range(0, len(cat_values), 4)]
    shortlist = reconstruct(system, circuits, cat_rows, native_frontier, prefix, input_sha, catalog_sha, args.seed, complete)
    exports = []; compression_winner = False
    for record in ([] if winner else select_diverse(shortlist, args.export_limit)):
        exported, exported_report, metadata = verify_export(system, circuits, record)
        digest_model = record['model_sha256']; destination = out/'frontier'/(digest_model+'.json')
        metadata.update(source_input_sha256=input_sha, source_catalog_sha256=catalog_sha,
                        source_binary_sha256=binary_sha, source_model_sha256=digest(model_bytes(system['baseline_vectors'])))
        freeze(destination, json_bytes(exported)); freeze(out/'frontier'/(digest_model+'.w.txt'), model_bytes(record['vectors']))
        freeze(out/'frontier'/(digest_model+'.verification.json'), json_bytes(exported_report))
        compressed, compressed_report, compression = compress_export(exported)
        freeze(out/'frontier'/(digest_model+'.compressed.json'), json_bytes(compressed))
        freeze(out/'frontier'/(digest_model+'.compressed.verification.json'), json_bytes(compressed_report))
        freeze(out/'frontier'/(digest_model+'.compression.json'), json_bytes(compression))
        compressed_hist = Counter(tuple(matrix_rank(mask,args.dimension) for mask in term) for term in decode_candidate(compressed,args.dimension))
        metadata.update(compressed_rank=compressed_report['rank'], compressed_certificate_sha256=digest(json_bytes(compressed)),
                        compressed_term_sha256=digest(json_bytes(sorted(decode_candidate(compressed,args.dimension)))),
                        compressed_factor_rank_histogram={'/'.join(map(str,key)):value for key,value in sorted(compressed_hist.items())},
                        compression_fixed_point=compression['fixed_point'],
                        compression_scope='cross-orientation active pair/slice replacements; outside original quartet coverage')
        freeze(out/'frontier'/(digest_model+'.metadata.json'), json_bytes(metadata))
        exports.append(dict(path=str(destination), **metadata))
        if compressed_report['rank'] <= args.target:
            if not (out/'WINNER.json').exists(): freeze(out/'WINNER.json', json_bytes(compressed))
            winner=True; compression_winner=True
            break
    freeze(out/'frontier-index.json', json_bytes(exports))
    coverage = dict(quartets_total=manifest['quartets_total'], quartets_completed_this_run=stats['quartets_considered'],
        prefix_completed=complete, contiguous_from_initial=True,
        supplied_catalog_completed=stats['status']=='NO_TARGET' and complete==manifest['quartets_total'],
        full_unordered_circuit_family_completed=False, next_row=stats['next_row'])
    summary = dict(native_frontier_sha256=digest(native_frontier), native_shortlist=len(shortlist), verified_frontier_exports=len(exports), unexported_shortlist_compression_untested=max(0,len(shortlist)-len(exports)), frontier_sampled=True, source_model_sha256=digest(model_bytes(system['baseline_vectors'])), status='VERIFIED_TARGET' if winner else stats['status'], reason='cross-orientation compressed frontier verified target' if compression_winner else stats['reason'],
        winner=winner, best_rank=min([report['rank']]+[entry['compressed_rank'] for entry in exports]), raw_fixed_pair_best_rank=report['rank'], exact_entries_checked=report['exact_entries_checked'],
        coverage=coverage, bound_pruned=stats['bound_pruned'], exact_evaluated=stats['exact_evaluated'],
        elapsed_seconds=time.monotonic()-started, scope=SCOPE)
    atomic_json(out/'summary.json', summary); print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # Preserve an explicit ERROR on preparation/validation failures too.
        if _CREATED_OUTPUT is not None and not (_CREATED_OUTPUT/'summary.json').exists():
            atomic_json(_CREATED_OUTPUT/'summary.json', dict(status='ERROR', reason=str(error), scope=SCOPE))
        raise
