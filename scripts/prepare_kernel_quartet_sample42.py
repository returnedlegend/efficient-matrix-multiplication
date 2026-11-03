"""Build a finite sampled quartet catalog; never dispatch an optimizer search."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import random
import resource
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.free_factor_kernel import decode_checked
from mmsearch.kernel_quartet_block_wide import basis_workload, frequencies
from scripts.freeze_campaign_dictionary import freeze, json_bytes, read_json


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_rows(raw, circuit_count):
    stream = io.StringIO(raw.decode())
    header = stream.readline().split()
    if len(header) != 2 or header[0] != 'MMKQUARTETS1':
        raise ValueError('invalid quartet catalog header')
    declared = int(header[1]); seen = set(); rows = []
    for line in stream:
        row = tuple(map(int, line.split()))
        if len(row) != 4 or not 0 <= row[0] < row[1] < row[2] < row[3] < circuit_count:
            raise ValueError('invalid quartet row')
        identity = sum(value << (16*(3-i)) for i, value in enumerate(row))
        if identity in seen:
            raise ValueError('duplicate quartet row')
        seen.add(identity); rows.append(row)
    if len(rows) != declared:
        raise ValueError('quartet count mismatch')
    return rows


def completed_run(directory, expected_input, expected_binary, circuit_count):
    manifest = read_json((directory/'manifest.json').read_bytes())
    summary = read_json((directory/'summary.json').read_bytes())
    stats = read_json((directory/'native_final_stats.json').read_bytes())
    raw = (directory/'quartets.txt').read_bytes()
    if (manifest['input_sha256'] != expected_input or manifest['binary_sha256'] != expected_binary or
            manifest['catalog_sha256'] != sha(raw) or stats['catalog_sha256'] != sha(raw) or
            stats['input_sha256'] != expected_input or stats['status'] != 'NO_TARGET' or
            summary['status'] != 'NO_TARGET' or not summary['coverage']['supplied_catalog_completed'] or
            not summary['coverage']['contiguous_from_initial'] or summary['exact_entries_checked'] != 15625 or
            summary['coverage']['prefix_completed'] != summary['coverage']['quartets_total']):
        raise ValueError('exclusion evidence is not an exhausted catalog on the same exact model/worker')
    rows = read_rows(raw, circuit_count)
    if len(rows) != summary['coverage']['prefix_completed']:
        raise ValueError('exclusion count does not match certified prefix')
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--count', type=int, default=100000)
    p.add_argument('--seed', type=int, default=424303)
    p.add_argument('--seconds', type=float, default=170)
    p.add_argument('--max-attempts', type=int, default=50000000)
    p.add_argument('--max-workload', type=int, default=50000)
    p.add_argument('--pool-factor', type=int, default=2)
    p.add_argument('--exclude-completed-run', type=Path, action='append', default=[])
    args = p.parse_args()
    if not 1 <= args.count <= 1000000 or not 0 <= args.seconds <= 190:
        p.error('preparation limits exceeded')
    started = time.monotonic(); bundle = args.bundle.resolve(); out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    bindings = read_json((bundle/'BINDINGS.json').read_bytes())
    for name, expected in bindings['files'].items():
        if sha((bundle/name).read_bytes()) != expected:
            raise ValueError('frozen preparation binding mismatch: '+name)
    system = read_json((bundle/'inputs/system.json').read_bytes())
    circuits = read_json((bundle/'inputs/circuits.json').read_bytes())
    _, report = decode_checked(system, system['baseline_vectors'])
    if report['rank'] != 93 or report['exact_entries_checked'] != 15625:
        raise ValueError('invalid frozen baseline')
    excluded = set(completed_run(bundle/'completed-source', bindings['input_sha256'],
                                 bindings['exact_worker_sha256'], len(circuits)))
    for directory in args.exclude_completed_run:
        excluded.update(completed_run(directory.resolve(), bindings['input_sha256'],
                                      bindings['exact_worker_sha256'], len(circuits)))
    exclusion_raw = (f'MMKQUARTETS1 {len(excluded)}\n'+
        ''.join(' '.join(map(str, row))+'\n' for row in sorted(excluded))).encode()
    freeze(out/'excluded-completed.txt', exclusion_raw)
    prefix = out/'native'/'sample'
    command = [str(bundle/'native-sampler'), '--input', str(bundle/'inputs/kernel_input.txt'),
               '--exclude', str(out/'excluded-completed.txt'), '--output', str(prefix),
               '--count', str(args.count), '--seed', str(args.seed), '--seconds', str(args.seconds),
               '--max-attempts', str(args.max_attempts), '--max-workload', str(args.max_workload),
               '--pool-factor', str(args.pool_factor)]
    freeze(out/'command.json', json_bytes(command))
    result = subprocess.run(command, capture_output=True, text=True, timeout=args.seconds+15)
    freeze(out/'sampler.stdout.log', result.stdout.encode()); freeze(out/'sampler.stderr.log', result.stderr.encode())
    if result.returncode:
        freeze(out/'summary.json', json_bytes(dict(status='ERROR', exit_code=result.returncode, search_dispatched=False)))
        return 2
    raw = Path(str(prefix)+'.quartets.txt').read_bytes(); stats = read_json(Path(str(prefix)+'.stats.json').read_bytes())
    freeze(out/'quartets.txt', raw); freeze(out/'native_sampler_stats.json', json_bytes(stats))
    # Streaming validation keeps only compact64-bit identities for the large
    # output. Independent Python histogram/workload checks use a64-row reservoir.
    stream = io.StringIO(raw.decode()); header = stream.readline().split()
    if header != ['MMKQUARTETS1', str(stats['selected'])]:
        raise ValueError('native sampler header/count mismatch')
    seen = set(); sample = []; rng = random.Random(args.seed ^ 0xA54)
    support_masks = [sum(1 << g for g in c['support']) for c in circuits]
    total = 0
    for line in stream:
        row = tuple(map(int, line.split()))
        if len(row) != 4 or not 0 <= row[0] < row[1] < row[2] < row[3] < len(circuits) or row in excluded:
            raise ValueError('invalid or previously completed sampled quartet')
        identity = sum(value << (16*(3-i)) for i, value in enumerate(row))
        if identity in seen:
            raise ValueError('duplicate sampled quartet')
        seen.add(identity)
        reached = 1
        for _ in range(3):
            for i in range(4):
                if reached >> i & 1:
                    for j in range(4):
                        if support_masks[row[i]] & support_masks[row[j]]:
                            reached |= 1 << j
        if reached != 15:
            raise ValueError('sampled quartet is disconnected')
        total += 1
        if len(sample) < 64:
            sample.append(row)
        else:
            j = rng.randrange(total)
            if j < 64: sample[j] = row
    if total != stats['selected']:
        raise ValueError('sampled row count mismatch')
    audits = []
    for row in sample:
        supports = [circuits[i]['support'] for i in row]
        counts = frequencies(system['baseline_vectors'], supports)
        gain = sum(max(c.values(), default=0)-c[0] for c in counts)
        work = basis_workload(system['baseline_vectors'], supports)
        if gain < 1 or (args.max_workload and work['exact_rhs_assignments'] > args.max_workload):
            raise ValueError('independent sampled bound/workload audit failed')
        audits.append(dict(indices=row, gain_upper=gain, **work))
    freeze(out/'independent-reservoir-audit.json', json_bytes(audits))
    manifest = dict(status=stats['status'], input_sha256=bindings['input_sha256'],
        binary_sha256=bindings['exact_worker_sha256'], catalog_sha256=sha(raw), sampler_sha256=bindings['files']['native-sampler'],
        source_preparation_bundle=str(bundle), excluded_catalog_sha256=sha(exclusion_raw), excluded_completed=len(excluded),
        baseline_rank=93, exact_entries_checked=15625, selected=total,
        selected_all_unique=True, selected_all_overlap_connected=True, selected_excludes_completed=True,
        native_bound_positive=True, independent_histogram_workload_reservoir=len(audits),
        all_unordered_quartets_covered=False, optimizer_search_dispatched=False,
        elapsed_seconds=time.monotonic()-started, child_cpu_seconds=resource.getrusage(resource.RUSAGE_CHILDREN).ru_utime+
            resource.getrusage(resource.RUSAGE_CHILDREN).ru_stime,
        scope='Finite seeded bound-positive connected star/path/cycle subset only; selections, work caps and omitted quartets are heuristic. '
              'No direction optimizer or target query was run during preparation. Exclusions bind the identical input W model.')
    freeze(out/'manifest.json', json_bytes(manifest)); freeze(out/'summary.json', json_bytes(manifest))
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
