import importlib.util
import itertools
import json
from pathlib import Path
import tempfile
import unittest

from mmsearch.free_factor_sat import (ORIENTATIONS, baseline_assumptions,
    build_problem, build_system, canonical_pairs, satisfies, solve)
from mmsearch.recombine import canonical_terms, save
from mmsearch.tensor import naive_candidate
from scripts.augment_factor_pairs import (augment_pairs, augmented_dictionary,
    gf2_column_rank, main, outer_mask)


class AugmentFactorPairsTests(unittest.TestCase):
    def test_exact_witnesses_rank_and_one_round_parents(self):
        old = [(1, 1), (2, 1), (1, 2), (1, 4), (4, 2)]
        result = augment_pairs(old, 4, max_pairs=9, seed=7)
        self.assertTrue(result["metadata"]["target_reached"])
        self.assertEqual(len(result["pairs"]), 9)
        self.assertLessEqual(abs(result["metadata"]["shared_first_additions"]-
                                 result["metadata"]["shared_second_additions"]), 1)
        for witness in result["witnesses"]:
            parents = [result["old_pairs"][i] for i in witness["parent_pair_indices"]]
            self.assertEqual([list(p) for p in parents], witness["parent_pairs"])
            self.assertEqual(parents[0][witness["shared_fixed_axis"]], parents[1][witness["shared_fixed_axis"]])
            self.assertEqual(outer_mask(witness["pair"], 4),
                             outer_mask(parents[0], 4) ^ outer_mask(parents[1], 4))
        self.assertEqual(result["metadata"]["old_column_rank"], result["metadata"]["new_column_rank"])
        self.assertEqual(gf2_column_rank(outer_mask(p, 4) for p in result["pairs"]), 5)

    def test_deterministic_seed_balanced_cap_and_exhaustion(self):
        pairs = list(itertools.product((1, 2, 4, 8), repeat=2))
        first = augment_pairs(pairs, 4, 24, 20261102)
        self.assertEqual(first, augment_pairs(list(reversed(pairs)), 4, 24, 20261102))
        self.assertNotEqual(first["witnesses"], augment_pairs(pairs, 4, 24, 20261103)["witnesses"])
        self.assertEqual(first["metadata"]["shared_first_additions"], 4)
        self.assertEqual(first["metadata"]["shared_second_additions"], 4)
        exhausted = augment_pairs([(1, 1), (2, 1)], 2, 20)
        self.assertFalse(exhausted["metadata"]["target_reached"])
        self.assertEqual(exhausted["pairs"], ((1, 1), (2, 1), (3, 1)))
        with self.assertRaises(ValueError):
            augment_pairs(pairs, 4, 15)

    def test_zero_duplicate_canonicalization_and_validation(self):
        result = augment_pairs([(1, 1), (1, 1), (2, 1), (0, 1), (1, 0)], 2, 3)
        self.assertEqual(result["old_pairs"], ((1, 1), (2, 1)))
        self.assertEqual(result["pairs"], ((1, 1), (2, 1), (3, 1)))
        self.assertTrue(all(a and b for a, b in result["pairs"]))
        for bad in [[(True, 1)], [(-1, 1)], [(4, 1)], [(1, 1, 1)]]:
            with self.assertRaises(ValueError):
                augment_pairs(bad, 2)
        # XOR results already present in the original pair set are removed.
        self.assertEqual(augment_pairs([(1, 1), (2, 1), (3, 1)], 2, 10)["witnesses"], [])

    def test_outer_coordinates_and_every_orientation_dummy_mapping(self):
        self.assertEqual(outer_mask((5, 10), 4), sum(1 << (a*4+b) for a in (0, 2) for b in (1, 3)))
        for orientation, permutation in ORIENTATIONS.items():
            dictionary = []
            for pair in ((1, 1), (2, 1)):
                triple = [1, 1, 1]
                triple[permutation[0]], triple[permutation[1]] = pair
                dictionary.append(triple)
            closure = augment_pairs(canonical_pairs(dictionary, 2, orientation), 4, 3, orientation=orientation)
            emitted = augmented_dictionary(dictionary, closure, orientation)
            self.assertEqual(emitted[:len(dictionary)], dictionary)
            self.assertEqual(emitted[-1][permutation[2]], 1)
            self.assertEqual(canonical_pairs(emitted, 2, orientation), closure["pairs"])

    def test_tiny_baseline_remains_exact_positive_control(self):
        baseline = naive_candidate(2)
        dictionary = list(canonical_terms(baseline))
        for orientation in ORIENTATIONS:
            old = build_system(dictionary, 2, orientation, baseline)
            closure = augment_pairs(old["pairs"], 4, len(old["pairs"])+2, orientation=orientation)
            emitted = augmented_dictionary(dictionary, closure, orientation)
            new = build_system(emitted, 2, orientation, baseline)
            self.assertEqual(old["metadata"]["linear_rank"], new["metadata"]["linear_rank"])
            self.assertEqual(new["metadata"]["baseline"]["merged_rank"], 8)
            self.assertTrue(satisfies(new, new["baseline_vectors"]))
            if importlib.util.find_spec("pycryptosat") and importlib.util.find_spec("pysat"):
                problem = build_problem(new, 8)
                control = solve(problem, seconds=1, memory_mb=512, assumptions=baseline_assumptions(problem))
                self.assertEqual(control["status"], "SAT")
                self.assertTrue(control["verification"]["valid"])

    def test_cli_separate_orientation_files_and_frozen_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = naive_candidate(2)
            dictionary = canonical_terms(baseline)
            save(root/"input.json", dictionary)
            save(root/"baseline.json", baseline)
            args = ["--dictionary", str(root/"input.json"), "--baseline", str(root/"baseline.json"),
                "--orientation", "all", "--max-pairs", "10", "--outdir", str(root/"out")]
            self.assertEqual(main(args), 0)
            result = json.loads((root/"out/result.json").read_text())
            self.assertFalse(result["solver_called"])
            self.assertEqual(result["status"], "READY")
            for orientation in ORIENTATIONS:
                emitted = json.loads((root/f"out/{orientation}/dictionary.json").read_text())
                self.assertEqual(len(emitted), len(dictionary)+2)
                self.assertEqual(len(canonical_pairs(emitted, 2, orientation)), 10)
                self.assertEqual(json.loads((root/f"out/{orientation}/manifest.json").read_text())["old"]["baseline_merged_rank"], 8)
            self.assertTrue((root/"out/inputs/baseline.json").exists())
            self.assertTrue((root/"out/code/scripts/augment_factor_pairs.py").exists())
            with self.assertRaises(FileExistsError):
                main(args)


if __name__ == "__main__":
    unittest.main()
