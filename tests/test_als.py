"""Check algebra, objective measurements, and fail-closed search artifacts."""
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from mmsearch.als import (_coordinate_sweep, _encode, _residual, _target,
                          search, solve_gf2)
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.verify import verify_candidate


class ALSTests(unittest.TestCase):
    def test_simultaneous_rhs_satisfies_every_consistent_equation(self):
        rng = random.Random(10)
        for variables in range(1, 20):
            truth = [rng.randrange(32) for _ in range(variables)]
            rows = [rng.randrange(1 << variables) for _ in range(variables*3)]
            def product(row, solution):
                result = 0
                for index, value in enumerate(solution):
                    if row >> index & 1:
                        result ^= value
                return result
            rhs = [product(row, truth) for row in rows]
            actual, inconsistent = solve_gf2(rows, rhs, variables, rng)
            self.assertEqual(inconsistent, 0)
            self.assertEqual([product(row, actual) for row in rows], rhs)

    def test_inconsistent_system_is_not_claimed_exact(self):
        solution, inconsistent = solve_gf2([1, 1, 0], [1, 0, 2], 1)
        self.assertEqual(solution, [1])
        self.assertEqual(inconsistent, 2)
        self.assertNotEqual([solution[0], solution[0], 0], [1, 0, 2])

    def test_all_residual_orientations_match_independent_verifier(self):
        rng = random.Random(25)
        for n in (2, 3):
            width = n*n
            targets = [_target(n, axis) for axis in range(3)]
            for _ in range(10):
                factors = [[rng.randrange(1 << width) for _ in range(3)]
                           for _ in range(7)]
                expected = verify_candidate(_encode(factors, n, {}), random_trials=0)["mismatch_count"]
                for axis in range(3):
                    measured = sum(row.bit_count() for row in
                                   _residual(factors, targets[axis], width, axis))
                    self.assertEqual(measured, expected)
                for axis in range(3):
                    measured, _ = _coordinate_sweep(factors, targets[axis], width, axis, rng)
                    self.assertLessEqual(measured, expected)
                    exact = verify_candidate(_encode(factors, n, {}), random_trials=0)
                    self.assertEqual(measured, exact["mismatch_count"])
                    expected = measured

    def test_coordinate_search_recovers_small_corruption(self):
        candidate = naive_candidate(2)
        candidate["terms"][0]["u"][0] ^= 1
        self.assertFalse(verify_candidate(candidate)["valid"])
        found, report = search(candidate, rank=8, seconds=1, seed=4, progress=False)
        self.assertTrue(report["valid"], report)
        self.assertEqual(found["metadata"]["residual_weight"], 0)
        self.assertEqual(found["metadata"]["status"], "verified")

    def test_invalid_checkpoint_and_standalone_exit_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source = directory / "input.json"
            checkpoint = directory / "candidate.json"
            source.write_text(json.dumps(strassen_candidate(2)))
            result = subprocess.run(
                [sys.executable, "-m", "mmsearch.als", "--input", str(source),
                 "--output", str(checkpoint), "--rank", "6", "--seconds", "0"],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            candidate = json.loads(checkpoint.read_text())
            report = json.loads(checkpoint.with_suffix(".verification.json").read_text())
            self.assertFalse(report["valid"])
            self.assertGreater(report["mismatch_count"], 0)
            self.assertEqual(candidate["metadata"]["residual_weight"], report["mismatch_count"])
            self.assertEqual(candidate["metadata"]["status"], "failed_exact_verification")
            verifier = checkpoint.with_suffix(".verify.py")
            independent = subprocess.run([sys.executable, "-I", str(verifier), str(checkpoint)],
                                         cwd=directory, capture_output=True, text=True)
            self.assertEqual(independent.returncode, 1)
            self.assertEqual(json.loads(independent.stdout)["mismatch_count"], report["mismatch_count"])

    def test_unbounded_runtime_rejected(self):
        for seconds in (-1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                search(naive_candidate(1), rank=1, seconds=seconds, progress=False)


if __name__ == "__main__":
    unittest.main()
