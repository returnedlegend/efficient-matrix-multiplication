"""Freeze exact rank-100, one-fixed-cube seeds from rank-95 two-cube states."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.cube_polarization import orbit_inventory, polarize_cubes
from mmsearch.native_bridge import _freeze, _json_bytes, canonical_terms, term_set_sha256
from mmsearch.search import encode_candidate, is_cyclic, orbit_counts
from mmsearch.verify import verify_candidate


def matrix_rank(mask, n=5):
    rows = [(mask >> (i*n)) & ((1 << n)-1) for i in range(n)]
    rank = 0
    for col in range(n):
        pivot = next((i for i in range(rank, n) if rows[i] >> col & 1), None)
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        for i in range(n):
            if i != rank and rows[i] >> col & 1:
                rows[i] ^= rows[rank]
        rank += 1
    return rank


def factor_rank_profile(terms, n=5):
    counts = Counter(matrix_rank(x, n) for term in terms for x in term)
    return tuple(counts[i] for i in range(1, n+1))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources', type=Path, nargs='+', required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--limit', type=int, default=6)
    args = p.parse_args()
    if not 1 <= args.limit <= 32:
        p.error('limit must be in 1..32')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    profiles, records, scanned = set(), [], 0
    code = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in
            (Path(__file__).resolve(), Path(__file__).resolve().parents[1]/'mmsearch/cube_polarization.py',
             Path(__file__).resolve().parents[1]/'mmsearch/verify.py')}
    for folder in args.sources:
        for source in sorted(folder.glob('*.json')):
            raw = source.read_bytes()
            value = json.loads(raw)
            terms = canonical_terms(value)
            if value['dimension'] != 5 or len(terms) != 95:
                continue
            if not is_cyclic(terms) or orbit_counts(terms)['fixed_cubes'] != 2:
                continue
            scanned += 1
            cubes = orbit_inventory(terms)['fixed_cube_masks']
            result = polarize_cubes(terms, *cubes)
            profile = factor_rank_profile(result)
            if profile in profiles:
                continue
            source_report = verify_candidate(value, random_trials=0)
            if not source_report['valid'] or source_report['exact_entries_checked'] != 15625:
                raise ValueError(f'invalid exact source: {source}')
            if len(result) != 100 or orbit_counts(result) != dict(fixed_cubes=1, three_cycles=33):
                raise ValueError('unexpected one-cube seed profile')
            h = term_set_sha256(result)
            source_sha = hashlib.sha256(raw).hexdigest()
            frozen_source = _freeze(args.output_dir/'sources'/(source_sha+'.json'), raw)
            candidate = encode_candidate(result, 5, method='two-cube-to-one-cube-polarization',
                source=str(source.resolve()), frozen_source=str(frozen_source.resolve()),
                source_sha256=source_sha, code_sha256=code, cube_pair=cubes,
                source_cube_matrix_ranks=[matrix_rank(a) for a in cubes],
                fixed_cube_matrix_rank=matrix_rank(cubes[0]^cubes[1]),
                factor_matrix_rank_counts=list(profile), term_set_sha256=h,
                orbit_profile=orbit_counts(result), orbit_inventory=orbit_inventory(result))
            report = verify_candidate(candidate, random_trials=0)
            if not report['valid'] or report['exact_entries_checked'] != 15625:
                raise RuntimeError('independent full tensor verification rejected polarization')
            payload = _json_bytes(candidate)
            path = _freeze(args.output_dir/'seeds'/(h+'.json'), payload)
            _freeze(args.output_dir/'verification'/(h+'.verification.json'), _json_bytes(report))
            _freeze(args.output_dir/'verification'/(source_sha+'.source.verification.json'), _json_bytes(source_report))
            digest = hashlib.sha256(payload).hexdigest()
            _freeze(args.output_dir/'verification'/(h+'.sha256'), (digest+'  '+path.name+'\n').encode())
            profiles.add(profile)
            records.append(dict(path=str(path.resolve()), sha256=digest, term_set_sha256=h,
                source=str(source.resolve()), source_sha256=source_sha, rank=100,
                orbit_profile=orbit_counts(result), factor_matrix_rank_counts=list(profile),
                source_cube_matrix_ranks=[matrix_rank(a) for a in cubes],
                fixed_cube_matrix_rank=matrix_rank(cubes[0]^cubes[1])))
            if len(records) >= args.limit:
                break
        if len(records) >= args.limit:
            break
    if not records:
        raise ValueError('no eligible exact sources')
    _freeze(args.output_dir/'manifest.json', _json_bytes(dict(candidates=records, scanned=scanned,
        code_sha256=code, note='Different factor-rank histograms only; no inequivalence claim.')))
    _freeze(args.output_dir/'verify.py', (Path(__file__).resolve().parents[1]/'mmsearch/verify.py').read_bytes())
    print(json.dumps(dict(seeds=len(records), scanned=scanned, output_dir=str(args.output_dir))))


if __name__ == '__main__':
    main()
