"""Exact coefficient identities and cyclic profile-changing seed controls."""
import json
from pathlib import Path
import unittest

from mmsearch.cube_polarization import conjugate_terms, polarize_cubes, polarized_seeds
from mmsearch.search import _outer, decode_candidate, encode_candidate, is_cyclic, naive_terms, orbit_counts
from mmsearch.verify import verify_candidate


class CubePolarizationTests(unittest.TestCase):
    def test_two_cube_identity_every_small_pair(self):
        for a in range(1,16):
            for b in range(a+1,16):
                old = {(a,a,a),(b,b,b)}
                new = polarize_cubes(old,a,b)
                error = 0
                for term in old ^ new:
                    error ^= _outer(term,4)
                self.assertEqual(error,0,(a,b))
                self.assertTrue(is_cyclic(new))
                self.assertEqual(orbit_counts(new),dict(fixed_cubes=1,three_cycles=2))

    def test_km93_has_exact_rank98_two_fixed_cube_seeds(self):
        path = Path(__file__).resolve().parents[1]/"artifacts/km93_f2.json"
        original = decode_candidate(json.loads(path.read_text()),5)
        seeds = list(polarized_seeds(original,5))
        self.assertEqual(len(seeds),3)
        for terms,meta in seeds:
            self.assertEqual(len(terms),98)
            self.assertEqual(orbit_counts(terms),dict(fixed_cubes=2,three_cycles=32))
            self.assertTrue(verify_candidate(encode_candidate(terms,5),random_trials=0)["valid"])
            self.assertEqual(meta["polarized_rank"],98)

    def test_simultaneous_gl_is_exact_cyclic_and_involutory(self):
        original = set(naive_terms(3))
        for i in range(3):
            for j in range(3):
                if i == j:
                    continue
                transformed = conjugate_terms(original,3,i,j)
                self.assertEqual(conjugate_terms(transformed,3,i,j),original)
                self.assertEqual(len(transformed),len(original))
                self.assertEqual(orbit_counts(transformed),orbit_counts(original))
                self.assertTrue(is_cyclic(transformed))
                self.assertTrue(verify_candidate(encode_candidate(transformed,3),random_trials=0)["valid"])


if __name__ == "__main__":
    unittest.main()
