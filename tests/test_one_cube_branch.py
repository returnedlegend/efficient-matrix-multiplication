"""Independent identity, C3 decoding, and frozen native flag controls."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from mmsearch.cube_polarization import orbit_inventory, polarize_cubes
from mmsearch.native_bridge import _read_terms
from mmsearch.search import _outer, _rotations, encode_candidate, naive_terms, orbit_counts
from mmsearch.verify import verify_candidate
from scripts.prepare_one_cube_seeds import factor_rank_profile, matrix_rank

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT/'artifacts/rl_campaign_20261102T210735Z/frozen/fixed-cubes-worker-v1/native/flip_worker_fixed_cubes'


class OneCubeBranchTests(unittest.TestCase):
    def test_small_polarization_and_orbit_expansion(self):
        for a in range(1, 16):
            for b in range(a+1, 16):
                old = {(a,a,a), (b,b,b)}
                terms = polarize_cubes(old, a, b)
                error = 0
                for term in old ^ terms:
                    error ^= _outer(term, 4)
                self.assertEqual(error, 0)
                inventory = orbit_inventory(terms)
                decoded = {(x,x,x) for x in inventory['fixed_cube_masks']}
                for representative in inventory['three_cycle_representatives']:
                    decoded.update(_rotations(tuple(representative)))
                self.assertEqual(decoded, terms)
                self.assertEqual(orbit_counts(terms), dict(fixed_cubes=1, three_cycles=2))

    def test_matrix_rank_profile(self):
        self.assertEqual(matrix_rank(0), 0)
        self.assertEqual(matrix_rank(sum(1 << (6*i) for i in range(5))), 5)
        self.assertEqual(matrix_rank(31), 1)
        self.assertEqual(factor_rank_profile([(1,3,33)]), (3,0,0,0,0))

    @unittest.skipUnless(BINARY.exists(), 'frozen worker unavailable')
    def test_zero_step_exact_one_cube_and_wrong_flag_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            terms = polarize_cubes(naive_terms(2), 1, 8)
            source = folder/'input.txt'
            source.write_text(''.join(f'{a} {b} {c}\n' for a,b,c in sorted(terms)))
            prefix = folder/'walk'
            command = [str(BINARY), '--input',str(source),'--output',str(prefix),
                '--n','2','--steps','0','--seconds','0','--target','7',
                '--max-rank','20','--cyclic','--fixed-cubes','1']
            result = subprocess.run(command, capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = verify_candidate(encode_candidate(_read_terms(prefix.with_suffix('.best.txt'),2),2),random_trials=0)
            self.assertTrue(report['valid'])
            self.assertEqual(report['exact_entries_checked'], 64)
            stats = json.loads(prefix.with_suffix('.stats.json').read_text())
            self.assertEqual(stats['steps'], 0)
            self.assertEqual(stats['required_fixed_cubes'], 1)
            for args, message in [(command[:-1]+['2'], 'initial fixed cube count'),
                                  ([x for x in command if x != '--cyclic'], 'requires --cyclic')]:
                result = subprocess.run(args, capture_output=True, text=True, timeout=3)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)


if __name__ == '__main__':
    unittest.main()
