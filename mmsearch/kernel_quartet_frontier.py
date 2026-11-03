"""Strict frontier reconstruction, exact matrix-rank fingerprints and exports."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from .free_factor_kernel import decode_checked
from .free_factor_sat import satisfies
from .kernel_quartet_block_wide import apply_quartet, optimize_quartet
from .search import decode_candidate


def model_bytes(vectors):
    return ''.join(str(value)+'\n' for value in vectors).encode()


def matrix_rank(mask, dimension):
    rows = [(mask >> (i*dimension)) & ((1 << dimension)-1) for i in range(dimension)]
    rank = 0
    for bit in range(dimension):
        found = next((j for j in range(rank, dimension) if rows[j] >> bit & 1), None)
        if found is None: continue
        rows[rank], rows[found] = rows[found], rows[rank]
        for j in range(dimension):
            if j != rank and rows[j] >> bit & 1: rows[j] ^= rows[rank]
        rank += 1
    return rank


def fingerprint(system, vectors):
    dimension = system['metadata']['dimension']; permutation = system['metadata']['mode_permutation']
    counts = Counter()
    for pair, w in zip(system['pairs'], vectors):
        if not w: continue
        ranks = [0]*3
        for axis, value in zip(permutation, (*pair, w)):
            ranks[axis] = matrix_rank(value, dimension)
        counts[tuple(ranks)] += 1
    return {'/'.join(map(str, key)): value for key, value in sorted(counts.items())}


def reconstruct(system, circuits, catalog, raw, prefix, input_sha, catalog_sha, seed, completed):
    lines = raw.decode().splitlines(); header = lines[0].split()
    if len(header) != 5 or header[:3] != ['MMKFRONTIER1', input_sha, catalog_sha] or int(header[3]) != seed:
        raise ValueError('frontier binding mismatch')
    count = int(header[4])
    if not 0 <= count <= 128 or len(lines) != count+1:
        raise ValueError('frontier shortlist size mismatch')
    result, seen = [], set(); baseline = system['baseline_vectors']; width = system['metadata']['width']
    for index, line in enumerate(lines[1:]):
        values = list(map(int, line.split()))
        if len(values) != 12: raise ValueError('invalid frontier entry')
        row = values[0]; indices = tuple(values[1:5]); move = values[5:9]
        optimum_rank, rank, origin = values[9:12]
        if not 0 <= row < completed or row >= len(catalog) or indices != catalog[row]:
            raise ValueError('frontier entry lacks completed quartet provenance')
        if any(not 0 <= value < 1 << width for value in move) or origin not in (0, 1):
            raise ValueError('invalid frontier direction or origin')
        moved = apply_quartet(baseline, *(circuits[i]['support'] for i in indices), *move)
        if moved == baseline or not satisfies(system, moved):
            raise ValueError('unchanged or invalid frontier model')
        if (sum(bool(value) for value in moved) != rank or not optimum_rank <= rank <= optimum_rank+1 or
                rank > min(94, sum(bool(w) for w in baseline)+1)):
            raise ValueError('frontier objective/rank mismatch')
        stored = [int(value) for value in Path(str(prefix)+f'.frontier-{index}.w.txt').read_text().splitlines()]
        if stored != moved: raise ValueError('frontier checkpoint differs from its directions')
        raw_model = model_bytes(moved); digest = hashlib.sha256(raw_model).hexdigest()
        if digest in seen: raise ValueError('duplicate frontier model')
        seen.add(digest)
        result.append(dict(row=row, indices=indices, directions=move, block_optimum_rank=optimum_rank,
            rank=rank, gap=rank-optimum_rank, origin='xor-sampled' if origin else 'observed-basis-sampled',
            model_sha256=digest, vectors=moved, factor_rank_histogram=fingerprint(system, moved),
            active_support=sum(1 << i for i, value in enumerate(moved) if value)))
    return result


def select_diverse(records, limit=16):
    if not 0 <= limit <= 16: raise ValueError('frontier verified-export cap16 exceeded')
    pending = sorted(records, key=lambda record: record['model_sha256']); selected = []
    seen_histograms = set(); gap_counts = Counter()
    while pending and len(selected) < limit:
        def priority(record):
            histogram = record['factor_rank_histogram']; key = (record['rank'], tuple(histogram.items()))
            distance = min((sum(abs(histogram.get(k, 0)-other['factor_rank_histogram'].get(k, 0))
                                 for k in set(histogram) | set(other['factor_rank_histogram'])) for other in selected), default=0)
            support_distance = min(((record['active_support'] ^ other['active_support']).bit_count()
                                    for other in selected), default=0)
            return key not in seen_histograms, -gap_counts[record['gap']], distance, support_distance
        best = max(pending, key=priority); pending.remove(best); selected.append(best)
        seen_histograms.add((best['rank'], tuple(best['factor_rank_histogram'].items())))
        gap_counts[best['gap']] += 1
    return selected


def verify_export(system, circuits, record):
    if hashlib.sha256(model_bytes(record['vectors'])).hexdigest() != record['model_sha256']:
        raise ValueError('frontier raw model hash mismatch')
    supports = [circuits[i]['support'] for i in record['indices']]
    optimum = optimize_quartet(system['baseline_vectors'], *supports)
    exact_rank = sum(bool(w) for w in system['baseline_vectors'])+optimum['delta']
    if exact_rank != record['block_optimum_rank'] or record['rank'] not in (exact_rank, exact_rank+1):
        raise ValueError('frontier claimed optimum/gap failed independent exact oracle')
    candidate, report = decode_checked(system, record['vectors'], dict(method='sampled-exact-quartet-frontier',
        source_model_sha256=hashlib.sha256(model_bytes(system['baseline_vectors'])).hexdigest(),
        block_optimum_rank=exact_rank, gap=record['gap'], indices=record['indices'], directions=record['directions'],
        factor_rank_histogram=record['factor_rank_histogram'], record_claim=False))
    if report['rank'] != record['rank'] or fingerprint(system, record['vectors']) != record['factor_rank_histogram']:
        raise ValueError('frontier independent rank/histogram mismatch')
    term_bytes = json.dumps(sorted(decode_candidate(candidate, system['metadata']['dimension'])), separators=(',', ':')).encode()
    metadata = {key: value for key, value in record.items() if key not in ('vectors', 'active_support')}
    metadata.update(term_sha256=hashlib.sha256(term_bytes).hexdigest(), record_claim=False,
                    source_rank=sum(bool(w) for w in system['baseline_vectors']),
                    rank_improvement=record['rank'] < sum(bool(w) for w in system['baseline_vectors']),
                    frontier_coverage='bounded sampled frontier; no all-tie or all-near-optimum coverage claim')
    return candidate, report, metadata


def compress_export(candidate):
    """Existing exact pair/slice routines, alternated until a joint fixed point."""
    from .pair_column_compression import compress_candidate as pair_compress
    from .slice_compression import compress_candidate as slice_compress
    from .verify import verify_candidate
    current = candidate; steps = []
    while True:
        before = len(current['terms'])
        for method, function in (('active-pair-all-orientations', pair_compress),
                                 ('shared-factor-all-axes', slice_compress)):
            result = function(current, seconds=30, stop_at_record=True)
            current = result['candidate']
            steps.append(dict(method=method, **{key: value for key, value in result.items() if key != 'candidate'}))
            if result['winner_eligible']:
                report = verify_candidate(current, random_trials=0)
                if not report['valid'] or report['exact_entries_checked'] != current['dimension']**6:
                    raise ValueError('compressed winner failed full independent verification')
                return current, report, dict(steps=steps, fixed_point=False, winner=True,
                    stop_reason='verified target reached; stop before further compression',
                    scope='cross-orientation replacements outside fixed-pair quartet coverage')
            if not result['fixed_point']:
                raise ValueError('compression budget ended without the required fixed point')
        if len(current['terms']) == before:
            report = verify_candidate(current, random_trials=0)
            if not report['valid'] or report['exact_entries_checked'] != current['dimension']**6:
                raise ValueError('compressed frontier failed full independent verification')
            return current, report, dict(steps=steps, fixed_point=True, winner=False,
                scope='joint fixed point of these exact pair/slice routines only; no global minimality claim')
