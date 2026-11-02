"""Bounded exact flip walk followed by sparse rank-reducing SAT neighborhoods."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.sat import build_local_cnf, solve_local, write_problem
from mmsearch.search import decode_candidate, search
from mmsearch.verify import verify_candidate, write_standalone_verifier


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')


def emit_candidate(path, candidate):
    report = verify_candidate(candidate, random_trials=64)
    if not report['valid']:
        raise AssertionError('exact checkpoint failed independent verification')
    save(path, candidate)
    save(path.with_suffix('.verification.json'), report)
    write_standalone_verifier(path.with_suffix('.verify.py'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('artifacts/km95_f2.json'))
    parser.add_argument('--output-dir', type=Path, default=Path('artifacts/km-local-sat'))
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--flip-seconds', type=float, default=20)
    parser.add_argument('--sat-seconds', type=float, default=2)
    parser.add_argument('--conflicts', type=int, default=5000)
    args = parser.parse_args()
    started = time.monotonic()
    seed = json.loads(args.input.read_text())
    # Reject the float values 1.0 as well as all nonternary integer values.
    if any(type(v) is not int or v not in (-1, 0, 1)
           for t in seed['terms'] for axis in ('u', 'v', 'w') for v in t[axis]):
        raise ValueError('coefficients must be exact integers in {-1,0,1}')
    if seed.get('dimension') != 5 or seed.get('field') != 2 or len(seed['terms']) != 95:
        raise ValueError('this experiment requires an exact 5x5 F2 rank95 seed')
    if not verify_candidate(seed)['valid']:
        raise ValueError('input seed must be exact')
    seed = dict(seed, terms=[{a: [v % 2 for v in t[a]] for a in ('u','v','w')}
                            for t in seed['terms']])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    save(args.output_dir / 'seed.json', seed)
    checkpoint = search(rank=94, initial_terms=decode_candidate(seed),
                        steps=200000, seconds=args.flip_seconds, seed=args.seed)
    checkpoint['metadata']['source_metadata'] = seed.get('metadata', {})
    checkpoint['metadata']['source_sha256'] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    emit_candidate(args.output_dir / 'flip.json', checkpoint)
    # Alternate original and flipped representatives. Prefer deleting sparse
    # products; vary the active slot count, then try unrestricted factor support
    # on smaller patches. Neither partition covers all rank94 decompositions.
    plans = [(which, d, k, 'union') for which in (0, 1)
             for d in range(2) for k in (3, 4, 5)]
    plans += [(which, d, 2, 'full') for which in (0, 1) for d in range(2)]
    runs = []
    target = checkpoint if len(checkpoint['terms']) <= 94 else None
    if target is None:
        for number, (which, drop_order, active_count, support) in enumerate(plans):
            source = (seed, checkpoint)[which]
            sparse = sorted(range(95), key=lambda i:
                            (sum(source['terms'][i]['u']) * sum(source['terms'][i]['v'])
                             * sum(source['terms'][i]['w']), i))
            dropped = sparse[drop_order]
            problem = build_local_cnf(source, rank=94, drop_term=dropped,
                                      active_count=active_count, support_mode=support)
            prefix = args.output_dir / f'patch-{number:02d}'
            write_problem(problem, prefix)
            result = solve_local(problem, seconds=args.sat_seconds, conflicts=args.conflicts)
            candidate = result.pop('candidate', None)
            result.update(source='seed.json' if which == 0 else 'flip.json',
                          problem={k:v for k,v in problem['metadata'].items()
                                   if k != 'factor_variable_map'})
            save(prefix.with_suffix('.result.json'), result)
            runs.append(dict(patch=prefix.name, status=result['status'],
                             elapsed_seconds=result['elapsed_seconds'], source=result['source'],
                             drop_term=dropped, active_count=active_count, support=support,
                             variables=problem['nv'], clauses=len(problem['clauses']),
                             factor_variables=problem['metadata']['factor_variables'],
                             statistics=result.get('statistics', {})))
            print(json.dumps(runs[-1]), flush=True)
            if candidate is not None:
                emit_candidate(prefix.with_suffix('.candidate.json'), candidate)
                target = candidate
                break
            if result['status'] == 'ERROR':
                raise RuntimeError(result)
    summary = dict(input=str(args.input), input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
                   domain=[-1,0,1], canonical_representatives=[0,1],
                   flip=checkpoint['metadata'], runs=runs, target_rank=94,
                   exact_target_found=target is not None, elapsed_seconds=time.monotonic()-started,
                   solver='CaDiCaL 1.9.5 via python-sat 1.8.dev24',
                   solver_limits=dict(seconds_per_patch=args.sat_seconds, conflicts=args.conflicts),
                   scope='local frozen neighborhoods only; UNSAT is not a global rank bound')
    save(args.output_dir / 'summary.json', summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('flip','runs')}), flush=True)


if __name__ == '__main__':
    main()
