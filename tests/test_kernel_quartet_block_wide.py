from collections import Counter
import itertools
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

from mmsearch.free_factor_kernel_wide import native_input
from mmsearch.free_factor_sat import build_system
from mmsearch.kernel_quartet_block_wide import (
    apply_quartet, basis_workload, optimize_quartet, validate_quartet_solution)
from mmsearch.search import encode_candidate

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT/'native/free_factor_quartet_block_worker_wide'
MATH = ROOT/'native/kernel_quartet_math_driver'


def planted_tensor():
    strassen = [(9, 9, 9), (12, 1, 10), (1, 10, 12), (8, 5, 3),
                (3, 8, 5), (5, 3, 8), (10, 12, 1)]
    unary, a, b, c = [1, 8, 9], [2, 4, 6], [3, 12, 15], [10, 13, 7]
    terms = strassen[1:] + [(9, 1, 9), (9, 8, 9)]
    dictionary = terms + [(9, v, 0) for v in [9, *a, *b, *c]]
    system = build_system(dictionary, 2, 'uv', encode_candidate(terms, 2))
    ids = {tuple(pair): i for i, pair in enumerate(system['pairs'])}
    supports = [[ids[9, v] for v in values] for values in (unary+a, a+b, b+c, c)]
    return system, [dict(class_id=2, support=s) for s in supports]


def bags_to_values(bags):
    values, classes = [], []
    for s, bag in bags.items():
        for value, frequency in bag.items():
            values += [value]*frequency; classes += [s]*frequency
    supports = [[g for g, s in enumerate(classes) if s >> bit & 1] for bit in range(4)]
    return values, classes, supports


class QuartetTests(unittest.TestCase):
    def native_math(self, values, classes, width):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'input'
            source.write_text(f'MMKQUARTETMATH1 {width} {len(values)}\n'+
                              ''.join(f'{s} {value}\n' for s, value in zip(classes, values)))
            result = subprocess.run([str(MATH), str(source)], capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    @unittest.skipUnless(MATH.exists(), 'native math driver not built')
    def test_exhaustive_random_bag_oracle(self):
        rng = random.Random(4242)
        for trial in range(25):
            width = 3 if trial < 4 else 2
            values = [rng.randrange(1 << width) for _ in range(18)]
            classes = [rng.randrange(1, 16) for _ in values]
            supports = [[g for g, s in enumerate(classes) if s >> bit & 1] for bit in range(4)]
            counts = [Counter(values[g] for g, s in enumerate(classes) if s == k) for k in range(16)]
            best = 0
            for move in itertools.product(range(1 << width), repeat=4):
                score = sum(counts[s][(move[0] if s&1 else 0) ^ (move[1] if s&2 else 0) ^
                                      (move[2] if s&4 else 0) ^ (move[3] if s&8 else 0)] for s in range(1, 16))
                best = max(best, score)
            python = optimize_quartet(values, *supports); native = self.native_math(values, classes, width)
            self.assertEqual(python['score'], best); self.assertEqual(native['score'], best)
            self.assertEqual(native['basis_count'], python['basis_count'])
            self.assertEqual(native['exact_rhs_assignments'], python['exact_rhs_assignments'])

    @unittest.skipUnless(MATH.exists(), 'native math driver not built')
    def test_zero_nonmodal_and_xor_rhs_counterexamples(self):
        controls = [({1: {1: 5}, 2: {0: 3, 2: 2}, 3: {2: 3, 3: 2}}, 9),
                    ({1: {0: 1}, 2: {1: 1}}, 2),
                    ({3: {1: 1}, 2: {2: 1}}, 2)]
        for bags, score in controls:
            values, classes, supports = bags_to_values(bags)
            self.assertEqual(optimize_quartet(values, *supports)['score'], score)
            self.assertEqual(self.native_math(values, classes, 2)['score'], score)
        values = [0]*15; classes = list(range(1, 16))
        result = self.native_math(values, classes, 1)
        self.assertEqual((result['rank'], result['basis_count'], result['exact_rhs_assignments']), (4, 840, 840))

    @unittest.skipUnless(MATH.exists(), 'native math driver not built')
    def test_math_union512_bag128_and_25bit_masks(self):
        result = self.native_math([0]*512, [s for s in (1,2,4,8) for _ in range(128)], 25)
        self.assertEqual((result['score'], result['delta']), (512, 0))
        result = self.native_math([(1 << 25)-1, 1 << 24], [3, 2], 25)
        self.assertEqual(result['score'], 2)
        self.assertEqual((result['d'], result['e']), ((1 << 24)-1, 1 << 24))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'bad'
            source.write_text('MMKQUARTETMATH1 1 129\n'+'1 0\n'*129)
            result = subprocess.run([str(MATH), str(source)], capture_output=True, text=True, timeout=3)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('128', result.stderr)

    def test_full_tensor_four_only_barrier(self):
        system, circuits = planted_tensor(); values = system['baseline_vectors']
        supports = [c['support'] for c in circuits]
        classes = [sum(1 << bit for bit, support in enumerate(supports) if g in support)
                   for g in range(len(values))]
        counts = [Counter(values[g] for g, s in enumerate(classes) if s == k) for k in range(16)]
        minimum = [100]*5
        # All16^4 exact vector assignments, including arbitrary non-scalar moves.
        for move in itertools.product(range(16), repeat=4):
            score = sum(counts[s][(move[0] if s&1 else 0) ^ (move[1] if s&2 else 0) ^
                                  (move[2] if s&4 else 0) ^ (move[3] if s&8 else 0)] for s in range(1, 16))
            rank = sum(bool(w) for w in values) + sum(c[0] for c in counts[1:])-score
            nonzero = sum(bool(v) for v in move)
            minimum[nonzero] = min(minimum[nonzero], rank)
        self.assertEqual(minimum, [8, 10, 10, 10, 7])
        self.assertEqual(optimize_quartet(values, *supports)['delta'], -1)

    @unittest.skipUnless(BINARY.exists(), 'native quartet worker not built')
    def test_native_full_tensor_positive_invalid_and_cursor(self):
        system, circuits = planted_tensor(); supports = [c['support'] for c in circuits]
        rng = random.Random(449)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'input'; catalog = root/'catalog'; prefix = root/'out'
            catalog.write_text('MMKQUARTETS1 1\n0 1 2 3\n')
            def run(raw, target=7, extra=()):
                source.write_bytes(raw)
                result = subprocess.run([str(BINARY), '--input', str(source), '--catalog', str(catalog),
                    '--output', str(prefix), '--target', str(target), '--seconds', '2', *extra],
                    capture_output=True, text=True, timeout=4)
                return result
            for _ in range(6):
                current = dict(system)
                current['baseline_vectors'] = apply_quartet(system['baseline_vectors'], *supports,
                                                           *(rng.randrange(16) for _ in range(4)))
                result = run(native_input(current, circuits))
                self.assertEqual(result.returncode, 0, result.stderr)
                record = json.loads(prefix.with_suffix('.solution.json').read_text())
                _, _, report = validate_quartet_solution(current, circuits, record)
                self.assertEqual((report['valid'], report['rank'], report['exact_entries_checked']), (True, 7, 64))
            result = run(native_input(system, circuits), target=0)
            stats = json.loads(prefix.with_suffix('.stats.json').read_text())
            self.assertEqual((stats['status'], stats['next_row']), ('NO_TARGET', 1))
            result = run(native_input(system, circuits), target=0, extra=('--start-row', '1'))
            self.assertEqual(json.loads(prefix.with_suffix('.stats.json').read_text())['quartets_considered'], 0)
            result = run(native_input(system, circuits), extra=('--seconds', '0'))
            self.assertEqual(json.loads(prefix.with_suffix('.stats.json').read_text())['status'], 'UNKNOWN')
            raw = native_input(system, circuits).decode().splitlines()
            bad = raw.copy(); parts = bad[-1].split(); parts[-1] = str(next(i for i in range(len(system['pairs'])) if str(i) not in parts[2:])); bad[-1] = ' '.join(parts)
            result = run(('\n'.join(bad)+'\n').encode())
            self.assertNotEqual(result.returncode, 0); self.assertIn('nonkernel', result.stderr)
            bad = raw.copy(); parts = bad[3].split(); parts[2] = str(int(parts[2])^1); bad[3] = ' '.join(parts)
            result = run(('\n'.join(bad)+'\n').encode())
            self.assertNotEqual(result.returncode, 0); self.assertIn('PW=Y', result.stderr)
            bad = raw.copy(); bad[-1] = '2 129 '+' '.join(map(str, range(129)))
            self.assertNotEqual(run(('\n'.join(bad)+'\n').encode()).returncode, 0)


if __name__ == '__main__':
    unittest.main()
