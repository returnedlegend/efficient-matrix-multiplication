import itertools
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

from mmsearch.free_factor_kernel_wide import native_input
from mmsearch.free_factor_kernel import pair_column
from mmsearch.free_factor_sat import build_system
from mmsearch.kernel_pair_block import optimize_pair, single_optimum
from mmsearch.kernel_triple_block_wide import (
    apply_triple, component_lower_bound, optimize_triple, validate_triple_solution)
from mmsearch.search import encode_candidate, naive_terms
from scripts.campaign_kernel_triple_block_wide import triple_catalog

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / 'native/free_factor_triple_block_worker_wide'


def planted_tensor():
    terms = list(naive_terms(2)) + [(3, b, 1) for b in (2, 3, 4, 5)]
    padding = [(5, b, 0) for b in (1, 2, 4, 8, 15)]
    system = build_system(terms + [(3, 6, 0), (3, 7, 0)] + padding,
                          2, 'uv', encode_candidate(terms, 2))
    ids = {tuple(pair): g for g, pair in enumerate(system['pairs'])}
    third = [ids[5, b] for b in (1, 2, 4, 8, 15)]
    shared = [ids[3, 6], ids[3, 7], *third]
    supports = [[ids[3, 2], ids[3, 3], *shared],
                [ids[3, 4], ids[3, 5], *shared], third]
    return system, [dict(class_id=2, support=s) for s in supports]


class TripleBlockTests(unittest.TestCase):
    def test_catalog_deterministic_connected_subset(self):
        circuits = [dict(support=[i, i+1, 20]) for i in range(12)]
        values = [0] * 24; values[20] = 1
        raw, info = triple_catalog(circuits, values, priority_first=2,
            local_anchors=5, neighbors_per_anchor=6, max_triples=30)
        self.assertEqual((raw, info), triple_catalog(circuits, values,
            priority_first=2, local_anchors=5, neighbors_per_anchor=6, max_triples=30))
        self.assertFalse(info['full_unordered_family'])
        self.assertEqual(info['selected'], 30)
        rows = [tuple(map(int, line.split())) for line in raw.decode().splitlines()[1:]]
        self.assertEqual(len(set(rows)), len(rows))
        self.assertTrue(all(set(circuits[i]['support']) & set(circuits[j]['support'])
                            for row in rows for i, j in itertools.combinations(row, 2)))

    def test_width3_exhaustive(self):
        rng = random.Random(83)
        for _ in range(35):
            values = [rng.randrange(8) for _ in range(18)]
            supports = [rng.sample(range(18), rng.randrange(1, 16)) for _ in range(3)]
            result = optimize_triple(values, *supports)
            optimum = min(sum(bool(w) for w in apply_triple(values, *supports, *move))
                          for move in itertools.product(range(8), repeat=3))
            self.assertEqual(sum(bool(w) for w in values) + result['delta'], optimum)
            self.assertLessEqual(component_lower_bound(values, supports), result['delta'])

    def test_joint_triple_barrier(self):
        classes = [6, 7, 3, 1, 7, 1, 1, 2, 4, 5, 6, 2, 6, 3, 4]
        values = [3, 3, 0, 7, 3, 6, 7, 1, 1, 0, 0, 6, 0, 5, 0]
        supports = [[g for g, s in enumerate(classes) if s >> i & 1] for i in range(3)]
        self.assertTrue(all(single_optimum(values, s)['delta'] == 0 for s in supports))
        self.assertTrue(all(optimize_pair(values, supports[i], supports[j])['delta'] == 0
                            for i, j in itertools.combinations(range(3), 2)))
        self.assertEqual(optimize_triple(values, *supports)['delta'], -1)

    @unittest.skipUnless(BINARY.exists(), 'native triple worker not built')
    def test_native_128_support_bag_capacity(self):
        system = build_system([(a, b, 0) for a in range(1, 16) for b in range(1, 16)],
                              2, 'uv', encode_candidate(naive_terms(2), 2))
        columns = [pair_column(pair, 4) for pair in system['pairs']]
        lookup = {column: g for g, column in enumerate(columns)}
        rng = random.Random(128)
        for _ in range(10000):
            support = rng.sample(range(len(columns)), 127)
            total = 0
            for g in support: total ^= columns[g]
            extra = lookup.get(total)
            if extra is not None and extra not in support:
                support.append(extra); break
        else:
            self.fail('could not plant wide128 kernel support')
        remaining = set(range(len(columns))) - set(support)
        short = []
        for i, j in itertools.combinations(sorted(remaining), 2):
            k = lookup.get(columns[i] ^ columns[j])
            if k in remaining and k > j:
                short.append([i, j, k])
                if len(short) == 2: break
        self.assertEqual(len(short), 2)
        circuits = [dict(class_id=2, support=support)] + [dict(class_id=0, support=s) for s in short]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'input'; source.write_bytes(native_input(system, circuits))
            catalog = root/'catalog'; catalog.write_text('MMKTRIPLES1 1\n0 1 2\n')
            prefix = root/'out'
            done = subprocess.run([str(BINARY), '--input', str(source), '--catalog', str(catalog),
                '--output', str(prefix), '--target', '0', '--seconds', '2'],
                capture_output=True, text=True, timeout=4)
            self.assertEqual(done.returncode, 0, done.stderr)
            stats = json.loads(prefix.with_suffix('.stats.json').read_text())
            self.assertEqual((stats['status'], stats['triples_considered']), ('NO_TARGET', 1))

    @unittest.skipUnless(BINARY.exists(), 'native triple worker not built')
    def test_native_random_feasible_objectives(self):
        rng = random.Random(1283)
        system = build_system(list(naive_terms(2)) + [(3, b, 0) for b in range(1, 16)],
                              2, 'uv', encode_candidate(naive_terms(2), 2))
        ids = {tuple(pair): g for g, pair in enumerate(system['pairs'])}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog = root/'catalog'
            catalog.write_text('MMKTRIPLES1 1\n0 1 2\n')
            tested = 0
            for _ in range(30):
                current = dict(system); values = list(system['baseline_vectors'])
                for b in range(1, 16):
                    if b not in (1, 2, 4, 8):
                        w = rng.randrange(16); values[ids[3, b]] ^= w
                        for bit in (1, 2, 4, 8):
                            if b & bit: values[ids[3, bit]] ^= w
                current['baseline_vectors'] = values
                supports = []
                while len(supports) < 3:
                    chosen = set(rng.sample(range(1, 16), rng.randint(2, 10)))
                    total = 0
                    for b in chosen: total ^= b
                    for bit in (1, 2, 4, 8):
                        if total & bit: chosen.symmetric_difference_update((bit,))
                    support = sorted(ids[3, b] for b in chosen)
                    if len(support) >= 3 and support not in supports: supports.append(support)
                circuits = [dict(class_id=2, support=s) for s in supports]
                optimum = optimize_triple(values, *supports)
                if optimum['delta'] == 0: continue
                target = sum(bool(w) for w in values) + optimum['delta']
                source = root/'input'; source.write_bytes(native_input(current, circuits))
                prefix = root/'out'
                done = subprocess.run([str(BINARY), '--input', str(source), '--catalog', str(catalog),
                    '--output', str(prefix), '--target', str(target), '--seconds', '2'],
                    capture_output=True, text=True, timeout=4)
                self.assertEqual(done.returncode, 0, done.stderr)
                proof = json.loads(prefix.with_suffix('.solution.json').read_text())
                moved, _, report = validate_triple_solution(current, circuits, proof)
                self.assertEqual(report['rank'], target); self.assertEqual(report['exact_entries_checked'], 64)
                tested += 1
            self.assertGreaterEqual(tested, 15)

    @unittest.skipUnless(BINARY.exists(), 'native triple worker not built')
    def test_native_full_tensor_and_rejections_and_cursor(self):
        system, circuits = planted_tensor()
        rng = random.Random(19)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / 'triples.txt'
            catalog.write_text('MMKTRIPLES1 1\n0 1 2\n')
            def run(raw, target=8, extra=()):
                source = root / 'input'; source.write_bytes(raw)
                prefix = root / 'out'
                done = subprocess.run([str(BINARY), '--input', str(source), '--catalog', str(catalog),
                                       '--output', str(prefix), '--target', str(target), '--seconds', '2', *extra],
                                      capture_output=True, text=True, timeout=4)
                return done, prefix
            for _ in range(6):
                current = dict(system)
                current['baseline_vectors'] = apply_triple(system['baseline_vectors'],
                    *(c['support'] for c in circuits), *(rng.randrange(16) for _ in range(3)))
                done, prefix = run(native_input(current, circuits))
                self.assertEqual(done.returncode, 0, done.stderr)
                proof = json.loads(prefix.with_suffix('.solution.json').read_text())
                moved, candidate, report = validate_triple_solution(current, circuits, proof)
                self.assertTrue(report['valid']); self.assertEqual(report['exact_entries_checked'], 64)
                self.assertEqual(report['rank'], 8)
            done, prefix = run(native_input(system, circuits), target=0)
            self.assertEqual(done.returncode, 0, done.stderr)
            stats = json.loads(prefix.with_suffix('.stats.json').read_text())
            self.assertEqual((stats['status'], stats['next_row']), ('NO_TARGET', 1))
            done, prefix = run(native_input(system, circuits), target=0, extra=('--start-row', '1'))
            self.assertEqual(json.loads(prefix.with_suffix('.stats.json').read_text())['triples_considered'], 0)
            done, prefix = run(native_input(system, circuits), target=0, extra=('--seconds', '0'))
            self.assertEqual(json.loads(prefix.with_suffix('.stats.json').read_text())['status'], 'UNKNOWN')
            lines = native_input(system, circuits).decode().splitlines()
            bad = lines.copy(); parts = bad[-1].split(); parts[-1] = parts[-2]; bad[-1] = ' '.join(parts)
            done, _ = run(('\n'.join(bad) + '\n').encode())
            self.assertNotEqual(done.returncode, 0)
            bad = lines.copy(); parts = bad[-1].split(); existing = set(map(int, parts[2:])); parts[-1] = str(next(g for g in range(len(system['pairs'])) if g not in existing)); bad[-1] = ' '.join(parts)
            done, _ = run(('\n'.join(bad) + '\n').encode())
            self.assertNotEqual(done.returncode, 0); self.assertIn('nonkernel', done.stderr)
            bad = lines.copy(); parts = bad[3].split(); parts[2] = str(int(parts[2]) ^ 1); bad[3] = ' '.join(parts)
            done, _ = run(('\n'.join(bad) + '\n').encode())
            self.assertNotEqual(done.returncode, 0); self.assertIn('PW=Y', done.stderr)
            bad = lines.copy(); bad[-1] = '2 129 ' + ' '.join(map(str, range(129)))
            done, _ = run(('\n'.join(bad) + '\n').encode())
            self.assertNotEqual(done.returncode, 0)


if __name__ == '__main__':
    unittest.main()
