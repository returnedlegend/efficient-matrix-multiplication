"""Restartable, bounded, single-process local F2 rank-reduction SAT campaign.

UNSAT here concerns one frozen local patch, never global tensor rank. The
encoder enforces all tensor entries; union and full supports are separate
branches. No support conditioning or integer lifting is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.sat import build_local_cnf, solve_local, write_problem
from mmsearch.sat_neighborhoods import factor_masks, flattening_bounds, precompute_rows
from mmsearch.verify import verify_candidate, write_standalone_verifier

SCOPE = 'local frozen neighborhood only; UNSAT is not a global rank lower bound'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')
    temporary.replace(path)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def load_source(path, target_rank, dimension=None):
    raw = Path(path).read_bytes()
    source = json.loads(raw, object_pairs_hook=unique_object)
    report = verify_candidate(source, random_trials=0)
    if (not report['valid'] or source.get('field') != 2 or
            len(source['terms']) != target_rank + 1 or
            (dimension is not None and source['dimension'] != dimension)):
        raise ValueError('source must be an exact F2 certificate with target_rank+1 terms')
    if any(type(x) is not int or x not in (-1, 0, 1)
           for term in source['terms'] for axis in ('u', 'v', 'w') for x in term[axis]):
        raise ValueError('source coefficients must be exact ternary integers')
    # Stable ordering removes term-permutation-only native snapshots.
    terms = [{axis: [x % 2 for x in term[axis]] for axis in ('u', 'v', 'w')}
             for term in source['terms']]
    terms.sort(key=lambda term: tuple(x for axis in ('u', 'v', 'w') for x in term[axis]))
    canonical = dict(dimension=source['dimension'], field=2, terms=terms)
    return canonical, digest(canonical), hashlib.sha256(raw).hexdigest(), report


class PatchStream:
    """Reproducible graph/random patch proposals, with exact necessary bounds."""
    def __init__(self, source, seed, minimum=5, maximum=12):
        self.source = source
        self.seed = seed
        self.masks = factor_masks(source)
        self.rows = precompute_rows(source)
        self.sizes = list(range(min(minimum, len(self.masks)-1),
                                min(maximum, len(self.masks)-1)+1))
        if not self.sizes or self.sizes[0] < 1:
            raise ValueError('source needs at least two terms and a nonempty K range')
        self.neighbors = []
        for i, factors in enumerate(self.masks):
            def distance(j):
                other = self.masks[j]
                shared = sum(x == y for x, y in zip(factors, other))
                overlap = sum((x & y).bit_count() for x, y in zip(factors, other))
                difference = sum((x ^ y).bit_count() for x, y in zip(factors, other))
                return (-100*shared-overlap, difference, j)
            self.neighbors.append(sorted((j for j in range(len(self.masks)) if j != i), key=distance))

    def proposal(self, number):
        # Per-proposal PRNG means restart requires only the integer cursor.
        rng = random.Random((self.seed << 40) ^ number)
        count = len(self.masks)
        k = self.sizes[number % len(self.sizes)]
        anchor = rng.randrange(count)
        strategy = (number // len(self.sizes)) % 5
        if strategy == 0:
            selected = [anchor] + self.neighbors[anchor][:k]
        elif strategy in (1, 2):
            selected = [anchor] + rng.sample(self.neighbors[anchor][:min(count-1, (2 if strategy == 1 else 4)*k)], k)
        elif strategy == 3:
            start = rng.randrange(count-k)
            selected = list(range(start, start+k+1))
        else:
            selected = rng.sample(range(count), k+1)
        selected.sort()
        bounds = flattening_bounds(self.rows, selected)
        if max(bounds) > k:
            return None
        # Different deletions only relabel mutable slots; keep one canonical
        # deleted slot per subset to avoid effectively identical CNFs.
        drop = min(selected, key=lambda i: (math.prod(x.bit_count() for x in self.masks[i]), i))
        return dict(drop_term=drop, active_terms=[i for i in selected if i != drop],
                    flattening_ranks=bounds, active_count=k, strategy=strategy,
                    proposal=number, proposal_seed=(self.seed << 40) ^ number)


def cnf_digest(problem):
    value = hashlib.sha256()
    value.update(f"{problem['nv']}\n".encode())
    for clause in problem['clauses']:
        value.update((' '.join(map(str, clause)) + ' 0\n').encode())
    return value.hexdigest()


def retain_problems(directory, keep, byte_limit):
    prefixes = sorted(Path(directory).glob('*.cnf'), key=lambda p: p.stat().st_mtime, reverse=True)
    total = 0
    for index, path in enumerate(prefixes):
        mapping = path.with_suffix('.map.json')
        size = path.stat().st_size + (mapping.stat().st_size if mapping.exists() else 0)
        if index >= keep or total + size > byte_limit:
            path.unlink()
            mapping.unlink(missing_ok=True)
        else:
            total += size


class Campaign:
    def __init__(self, args):
        self.args = args
        self.root = args.output_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'manifest.json'
        identity = dict(target_rank=args.rank, dimension=args.dimension, seed=args.seed,
                        k_min=args.k_min, k_max=args.k_max)
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            if self.state['identity'] != identity:
                raise ValueError('restart parameters differ from manifest identity')
        else:
            self.state = dict(version=1, identity=identity, scope=SCOPE, sources={}, files={},
                              patches={}, cnf_hashes={}, counters={}, attempts=0, source_cursor=0)
        self.streams = {}
        self.last_scan = 0

    def increment(self, name, amount=1):
        self.state['counters'][name] = self.state['counters'].get(name, 0) + amount

    def emit(self, event):
        event['utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        with (self.root / 'results.jsonl').open('a') as handle:
            handle.write(json.dumps(event, sort_keys=True) + '\n')
        print(json.dumps(event, sort_keys=True), flush=True)

    def scan(self, force=False):
        if not force and time.monotonic()-self.last_scan < self.args.scan_seconds:
            return
        self.last_scan = time.monotonic()
        paths = list(self.args.input)
        for directory in self.args.seed_dir:
            paths.extend(sorted(directory.rglob('*.json')))
        for path in paths:
            fingerprint = None
            try:
                stat = path.stat()
                fingerprint = [stat.st_mtime_ns, stat.st_size]
                if self.state['files'].get(str(path), {}).get('fingerprint') == fingerprint:
                    continue
                source, key, raw_sha, report = load_source(path, self.args.rank, self.args.dimension)
            except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
                if fingerprint is not None:
                    self.state['files'][str(path)] = dict(fingerprint=fingerprint, status='REJECTED', reason=str(exc))
                continue
            self.state['files'][str(path)] = dict(fingerprint=fingerprint, status='EXACT',
                                                  source_sha256=key, file_sha256=raw_sha)
            if key not in self.state['sources']:
                save(self.root / 'sources' / f'{key}.json', source)
                self.state['sources'][key] = dict(path=str(path), file_sha256=raw_sha,
                        cursor=0, patches=0, verification=report)
                self.emit(dict(event='source', source_sha256=key, path=str(path), rank=self.args.rank+1))
        save(self.path, self.state)

    def stream(self, key):
        if key not in self.streams:
            source = json.loads((self.root / 'sources' / f'{key}.json').read_text())
            self.streams[key] = PatchStream(source, self.args.seed ^ int(key[:12], 16),
                                            self.args.k_min, self.args.k_max)
        return self.streams[key]

    def next_patch(self):
        # At most one escalation per five fresh solver attempts. Every patch
        # has finitely many levels and UNSAT patches are never retried.
        if self.state['attempts'] % 6 == 5:
            eligible = [p for p in self.state['patches'].values()
                        if p.get('status') == 'UNKNOWN' and p['level']+1 < self.args.levels]
            if eligible:
                # More slack in the necessary flattening bound is a modest
                # heuristic for an easier replacement; never a SAT guarantee.
                chosen = min(eligible, key=lambda p: (p['level'],
                    -sum(p.get('active_count', 0)-r for r in p.get('flattening_ranks', [])),
                    p['last_attempt']))
                chosen['level'] += 1
                return chosen
        keys = list(self.state['sources'])
        if not keys:
            return None
        # Bounded proposal work leaves time for periodic native-source scans.
        for _ in range(self.args.proposals_per_round):
            key = keys[self.state['source_cursor'] % len(keys)]
            self.state['source_cursor'] += 1
            entry = self.state['sources'][key]
            number = entry['cursor']
            entry['cursor'] += 1
            patch = self.stream(key).proposal(number)
            self.increment('proposals')
            if patch is None:
                self.increment('flattening_rejected')
                continue
            # Deterministic alternation over accepted patches includes both
            # unrestricted support and support-union branches.
            support = 'full' if entry['patches'] % 3 == 2 else 'union'
            entry['patches'] += 1
            patch.update(source_sha256=key, support_mode=support, level=0)
            patch_id = digest(dict(source=key, selected=sorted(patch['active_terms']+[patch['drop_term']]), support=support))
            if patch_id in self.state['patches']:
                self.increment('duplicate_patches')
                continue
            patch['patch_id'] = patch_id
            self.state['patches'][patch_id] = patch
            return patch
        return None

    def run(self):
        started = time.monotonic()
        deadline = started + self.args.seconds
        self.scan(force=True)
        if not self.state['sources']:
            raise ValueError('no exact source of target_rank+1 terms found')
        new_attempts = 0
        while not self.state.get('found') and time.monotonic() < deadline and (not self.args.max_runs or new_attempts < self.args.max_runs):
            self.scan()
            patch = self.next_patch()
            if patch is None:
                save(self.path, self.state)
                continue
            source = self.stream(patch['source_sha256']).source
            encoded_at = time.monotonic()
            problem = build_local_cnf(source, rank=self.args.rank, drop_term=patch['drop_term'],
                        active_terms=patch['active_terms'], support_mode=patch['support_mode'])
            problem['metadata']['scope'] = SCOPE
            encoding_seconds = time.monotonic()-encoded_at
            cnf_sha = cnf_digest(problem)
            previous = self.state['cnf_hashes'].get(cnf_sha)
            if previous is not None and previous != patch['patch_id']:
                patch.update(status='DUPLICATE', duplicate_of=previous, cnf_sha256=cnf_sha)
                self.increment('duplicate_cnfs')
                save(self.path, self.state)
                continue
            self.state['cnf_hashes'][cnf_sha] = patch['patch_id']
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                break
            seconds = min(self.args.patch_seconds * 2**patch['level'], remaining)
            conflicts = self.args.conflicts * 3**patch['level']
            prefix = self.root / 'problems' / patch['patch_id']
            write_problem(problem, prefix)
            retain_problems(prefix.parent, self.args.keep_cnf, self.args.cnf_mb*1024*1024)
            result = solve_local(problem, seconds=seconds, conflicts=conflicts)
            candidate = result.pop('candidate', None)
            patch.update(status=result['status'], cnf_sha256=cnf_sha, last_attempt=self.state['attempts'])
            self.state['attempts'] += 1
            new_attempts += 1
            self.increment(result['status'])
            result.update(event='solve', attempt=self.state['attempts'], patch=dict(patch), scope=SCOPE,
                encoding_seconds=encoding_seconds, source_file_sha256=self.state['sources'][patch['source_sha256']]['file_sha256'],
                python_version=sys.version, python_sat_version=importlib.metadata.version('python-sat'),
                phase_sha256=digest(problem['phases']),
                problem={k: v for k, v in problem['metadata'].items() if k != 'factor_variable_map'})
            # Fix legacy encoder scope text without changing existing modules.
            result['problem']['scope'] = SCOPE
            self.emit(result)
            if candidate is not None:
                report = verify_candidate(candidate, random_trials=64, seed=self.args.seed)
                if not report['valid'] or report['rank'] != self.args.rank:
                    raise AssertionError('SAT candidate failed independent exact verification')
                candidate['metadata']['campaign_provenance'] = dict(patch=patch, cnf_sha256=cnf_sha,
                    source_sha256=patch['source_sha256'], source_file_sha256=result['source_file_sha256'])
                destination = self.root / 'FOUND.json'
                save(destination, candidate)
                save(self.root / 'FOUND.verification.json', report)
                write_standalone_verifier(self.root / 'FOUND.verify.py')
                self.state['found'] = str(destination)
                self.emit(dict(event='FOUND_EXACT', path=str(destination), verification=report))
            save(self.path, self.state)
            if candidate is not None or result['status'] == 'ERROR':
                break
        summary = dict(event='summary', scope=SCOPE, attempts=self.state['attempts'],
                       counters=self.state['counters'], sources=len(self.state['sources']),
                       elapsed_seconds=time.monotonic()-started, found=self.state.get('found'))
        save(self.path, self.state)
        save(self.root / 'summary.json', summary)
        self.emit(summary)
        return summary


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, action='append', default=[])
    parser.add_argument('--seed-dir', type=Path, action='append', default=[])
    parser.add_argument('--output-dir', type=Path, default=Path('research/campaign/sat'))
    parser.add_argument('--rank', type=int, default=92)
    parser.add_argument('--dimension', type=int, default=5)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--seconds', type=float, default=6600)
    parser.add_argument('--patch-seconds', type=float, default=30)
    parser.add_argument('--conflicts', type=int, default=100000)
    parser.add_argument('--levels', type=int, default=3)
    parser.add_argument('--k-min', type=int, default=5)
    parser.add_argument('--k-max', type=int, default=12)
    parser.add_argument('--scan-seconds', type=float, default=30)
    parser.add_argument('--proposals-per-round', type=int, default=300)
    parser.add_argument('--max-runs', type=int, default=0)
    parser.add_argument('--keep-cnf', type=int, default=2)
    parser.add_argument('--cnf-mb', type=int, default=256)
    args = parser.parse_args(argv)
    if not args.input:
        args.input = [Path('artifacts/km93_f2.json')]
    if any(not math.isfinite(x) or x <= 0 for x in (args.seconds, args.patch_seconds, args.scan_seconds)):
        parser.error('time budgets must be positive and finite')
    if min(args.rank, args.dimension, args.k_min, args.levels, args.conflicts,
           args.proposals_per_round) < 1 or args.k_max < args.k_min or min(args.max_runs, args.keep_cnf, args.cnf_mb) < 0:
        parser.error('invalid integer bounds')
    return args


if __name__ == '__main__':
    Campaign(arguments()).run()
