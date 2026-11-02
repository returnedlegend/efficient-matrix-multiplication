"""Independent coefficient checks for the native exact-identity walk."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from mmsearch.search import decode_candidate, encode_candidate, naive_terms
from mmsearch.verify import verify_candidate

ROOT = Path(__file__).resolve().parents[1]


def coefficients(terms, n):
    """Straight coefficient enumeration, independent of native indexing helpers."""
    result = set()
    for term in terms:
        bits = [[i for i in range(n*n) if value >> i & 1] for value in term]
        for i in bits[0]:
            for j in bits[1]:
                for k in bits[2]:
                    key = i, j, k
                    if key in result:
                        result.remove(key)
                    else:
                        result.add(key)
    return result


def read_terms(path):
    return [tuple(map(int, line.split())) for line in Path(path).read_text().splitlines()]


@unittest.skipUnless(shutil.which(os.environ.get('CXX', 'g++')), 'C++ compiler unavailable')
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.build.name) / 'flip_worker'
        subprocess.run(['bash', str(ROOT / 'scripts/build_native.sh'), str(cls.binary)],
                       check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def run_worker(self, terms, n, directory, *extra):
        source = Path(directory) / 'input.txt'
        source.write_text(''.join(' '.join(map(str, t))+'\n' for t in terms))
        prefix = Path(directory) / 'walk'
        args = [str(self.binary), '--input', str(source), '--output', str(prefix),
                '--n', str(n), '--target', '0', '--max-rank', '99',
                '--steps', '2000', '--seconds', '30', '--plus-every', '7',
                '--restart-every', '173', '--archive-every', '1',
                '--archive-size', '16', *extra]
        process = subprocess.run(args, capture_output=True, text=True, timeout=35)
        return process, prefix

    def test_all_move_types_preserve_arbitrary_tensor_every_step(self):
        # Includes a merge, multiple common factors, and free plus pairs.
        terms = [(1,2,4), (1,2,8), (1,3,7), (1,9,11), (6,5,13)]
        expected = coefficients(terms, 2)
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / 'trace.txt'
            process, prefix = self.run_worker(terms, 2, tmp, '--allow-arbitrary',
                                              '--trace', str(trace), '--seed', '391')
            self.assertEqual(process.returncode, 0, process.stderr)
            kinds = set()
            lines = trace.read_text().splitlines()
            self.assertEqual(len(lines), 2000)
            for line in lines:
                step, kind, accepted, *triples = line.split()
                current = [tuple(map(int, t.split(','))) for t in triples]
                self.assertEqual(coefficients(current, 2), expected, (step, kind))
                self.assertEqual(len(current), len(set(current)))
                self.assertTrue(all(all(t) for t in current))
                kinds.add(kind)
            self.assertEqual(kinds, {'f', 'p', 'r'})
            self.assertEqual(coefficients(read_terms(str(prefix)+'.best.txt'), 2), expected)

    def test_exact_small_dimension_walks_and_archive_are_verified(self):
        for n in (2, 3):
            with self.subTest(n=n), tempfile.TemporaryDirectory() as tmp:
                process, prefix = self.run_worker(naive_terms(n), n, tmp, '--seed', str(n))
                self.assertEqual(process.returncode, 0, process.stderr)
                stats = json.loads(Path(str(prefix)+'.stats.json').read_text())
                self.assertTrue(stats['exact'])
                for path in [Path(str(prefix)+'.best.txt'), Path(str(prefix)+'.current.txt'),
                             *Path(str(prefix)+'.archive').glob('*.txt')]:
                    self.assertTrue(verify_candidate(encode_candidate(read_terms(path), n))['valid'], path)

    def test_published_rank93_target5_walk_is_exact_and_reproducible(self):
        seed = decode_candidate(json.loads((ROOT/'artifacts/km93_f2.json').read_text()), 5)
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            results = []
            for directory in (first, second):
                process, prefix = self.run_worker(seed, 5, directory, '--seed', '1028',
                                                  '--max-rank', '99', '--steps', '12000')
                self.assertEqual(process.returncode, 0, process.stderr)
                best = read_terms(str(prefix)+'.best.txt')
                current = read_terms(str(prefix)+'.current.txt')
                self.assertTrue(verify_candidate(encode_candidate(best, 5))['valid'])
                self.assertTrue(verify_candidate(encode_candidate(current, 5))['valid'])
                results.append((best, current))
            self.assertEqual(*results)

    def test_inexact_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            process, _ = self.run_worker([(1,1,1)], 2, tmp)
            self.assertNotEqual(process.returncode, 0)
            self.assertIn('not an exact', process.stderr)

    def test_cyclic_every_step_preserves_tensor_and_orbits(self):
        base = [(1,2,4), (1,2,8), (1,1,1)]
        terms = set()
        for a, b, c in base:
            terms.update({(a,b,c), (b,c,a), (c,a,b)})
        expected = coefficients(terms, 2)
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / 'trace.txt'
            process, prefix = self.run_worker(terms, 2, tmp, '--allow-arbitrary',
                                              '--cyclic', '--trace', str(trace), '--seed', '13')
            self.assertEqual(process.returncode, 0, process.stderr)
            for line in trace.read_text().splitlines():
                step, kind, accepted, *triples = line.split()
                current = {tuple(map(int, t.split(','))) for t in triples}
                self.assertEqual(coefficients(current, 2), expected, (step, kind))
                for a, b, c in current:
                    self.assertIn((b,c,a), current)
            self.assertTrue(json.loads(Path(str(prefix)+'.stats.json').read_text())['cyclic'])

    def test_cyclic_rank93_target5_walk_is_exact(self):
        seed = decode_candidate(json.loads((ROOT/'artifacts/km93_f2.json').read_text()), 5)
        with tempfile.TemporaryDirectory() as tmp:
            process, prefix = self.run_worker(seed, 5, tmp, '--cyclic', '--seed', '32',
                                              '--steps', '12000')
            self.assertEqual(process.returncode, 0, process.stderr)
            for suffix in ('.best.txt', '.current.txt'):
                terms = read_terms(str(prefix)+suffix)
                self.assertTrue(verify_candidate(encode_candidate(terms, 5))['valid'])
                term_set = set(terms)
                self.assertTrue(all((b,c,a) in term_set for a,b,c in terms))

    def test_truncated_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'input.txt'
            source.write_text('1 2')
            result = subprocess.run([str(self.binary), '--input', str(source),
                                     '--output', str(Path(tmp)/'bad')], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('malformed', result.stderr)


if __name__ == '__main__':
    unittest.main()
