import copy
import importlib.util
import itertools
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from mmsearch.free_factor_sat import (FormulaMemoryLimit, audit, baseline_assumptions,
    build_problem, build_system, canonical_pairs, decode_vectors, estimate_formula,
    packed_rref, satisfies, solve, validate_decode)
from mmsearch.recombine import canonical_terms, encode, save
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.verify import verify_candidate
from scripts.campaign_free_factor_sat import main


HAVE_SOLVER = bool(importlib.util.find_spec("pycryptosat") and importlib.util.find_spec("pysat"))


class FreeFactorSatTests(unittest.TestCase):
    def test_packed_rref_exact_equivalence_and_witnesses(self):
        coefficients, right_sides = [3, 2, 1], [5, 3, 6]
        result = packed_rref(coefficients, right_sides, 2, 3)
        self.assertEqual(result["rank"], 2)
        self.assertEqual(result["forced"], {0: 6, 1: 3})
        self.assertFalse(result["contradictions"])
        for vector in itertools.product(range(8), repeat=2):
            def holds(rows):
                return all((vector[0] if c & 1 else 0) ^ (vector[1] if c & 2 else 0) == r
                           for c, r in rows)
            self.assertEqual(holds(zip(coefficients, right_sides)),
                             holds((c, r) for c, r, _ in result["rows"]))
        bad = packed_rref(coefficients, [5, 3, 7], 2, 3)
        self.assertTrue(bad["contradictions"])
        self.assertTrue(bad["contradictions"][0][1])
        for row in result["rows"]+bad["contradictions"]:
            c = r = 0
            source_rhs = right_sides if row in result["rows"] else [5, 3, 7]
            for i in range(3):
                if row[2] >> i & 1:
                    c ^= coefficients[i]
                    r ^= source_rhs[i]
            self.assertEqual(row[:2], [c, r])

    def test_pair_dedup_zero_and_invalid_mask_canonicalization(self):
        self.assertEqual(canonical_pairs([(1, 2, 0), (1, 2, 3), (0, 2, 1)], 2), ((1, 2),))
        for bad in [[(True, 1, 1)], [(16, 1, 1)], [(-1, 1, 1)], [(1, 1)]]:
            with self.assertRaises(ValueError):
                canonical_pairs(bad, 2)
        with self.assertRaises(ValueError):
            canonical_pairs([], 0)
        with self.assertRaises(ValueError):
            canonical_pairs([], 2, "uw")

    def test_same_pair_xor_merge_cancels_zero_groups(self):
        source = strassen_candidate(2)
        terms = list(canonical_terms(source))+[(15, 15, 1), (15, 15, 2), (15, 15, 3)]
        baseline = encode(terms, 2)
        self.assertTrue(verify_candidate(baseline)["valid"])
        system = build_system(terms, 2, baseline=baseline)
        self.assertEqual(len(system["pairs"]), 8)
        self.assertEqual(system["metadata"]["baseline"]["supplied_rank"], 10)
        self.assertEqual(system["metadata"]["baseline"]["merged_rank"], 7)
        self.assertTrue(satisfies(system, system["baseline_vectors"]))
        self.assertTrue(verify_candidate(decode_vectors(system, system["baseline_vectors"]))["valid"])

    def test_three_mode_orientations_match_full_independent_tensor(self):
        baseline = strassen_candidate(2)
        terms = canonical_terms(baseline)
        for orientation in ("uv", "vw", "wu"):
            system = build_system(terms, 2, orientation, baseline)
            self.assertEqual(system["metadata"]["scalar_tensor_equations"], 64)
            self.assertTrue(satisfies(system, system["baseline_vectors"]))
            candidate = decode_vectors(system, system["baseline_vectors"])
            self.assertTrue(verify_candidate(candidate, random_trials=16)["valid"])
            corrupted = list(system["baseline_vectors"])
            corrupted[0] ^= 1
            self.assertFalse(satisfies(system, corrupted))
            self.assertFalse(verify_candidate(decode_vectors(system, corrupted), random_trials=0)["valid"])
            mapping = audit(system)
            self.assertEqual(len(mapping["original_rows_hex"]), 16)

    def test_linear_inconsistency_and_forced_group_bound(self):
        inconsistent = build_system([], 1)
        self.assertTrue(inconsistent["metadata"]["linear_inconsistent"])
        system = build_system(canonical_terms(naive_candidate(2)), 2)
        self.assertEqual(system["metadata"]["forced_active"], 8)
        self.assertEqual(system["metadata"]["linear_rank"], 8)
        self.assertEqual(system["metadata"]["linear_nullity"], 0)
        if HAVE_SOLVER:
            problem = build_problem(system, 7)
            self.assertIn([], problem["clauses"])
            self.assertEqual(problem["metadata"]["exact_preprocessing_unsat"], "forced active groups exceed rank bound")

    def test_baseline_validation_and_memory_guard(self):
        baseline = strassen_candidate(2)
        terms = canonical_terms(baseline)
        with self.assertRaisesRegex(ValueError, "absent"):
            build_system(terms[:-1], 2, baseline=baseline)
        bad = copy.deepcopy(baseline)
        bad["terms"][0]["w"][0] ^= 1
        with self.assertRaisesRegex(ValueError, "independently exact"):
            build_system(terms, 2, baseline=bad)
        system = build_system(terms, 2)
        self.assertGreater(estimate_formula(system)["estimated_python_formula_bytes"], 0)
        with self.assertRaises(FormulaMemoryLimit):
            build_problem(system, 7, max_formula_mb=0.0001)

    @unittest.skipUnless(HAVE_SOLVER, "optional native XOR backend")
    def test_free_factor_recovery_control_and_mutated_model_rejection(self):
        baseline = strassen_candidate(2)
        terms = canonical_terms(baseline)
        # Destroy every free dictionary factor. Exact recovery must be allowed
        # to choose vectors absent from the whole-triple dictionary.
        for orientation, free_axis in (("uv", 2), ("vw", 0), ("wu", 1)):
            dictionary = []
            for term in terms:
                altered = list(term)
                altered[free_axis] = 1
                dictionary.append(tuple(altered))
            self.assertFalse(verify_candidate(encode(dictionary, 2), random_trials=0)["valid"])
            system = build_system(dictionary, 2, orientation, baseline)
            problem = build_problem(system, 7)
            fixed = baseline_assumptions(problem)
            self.assertEqual(len(fixed), problem["metadata"]["base_variables"])
            control = solve(problem, seconds=1, memory_mb=512, assumptions=fixed)
            self.assertEqual(control["status"], "SAT")
            self.assertTrue(control["worker_reaped"])
            recovered = solve(problem, seconds=1, memory_mb=512)
            self.assertEqual(recovered["status"], "SAT")
            self.assertTrue(recovered["verification"]["valid"])
            self.assertLessEqual(recovered["verification"]["rank"], 7)
            model = recovered["complete_assignment"]
            mutated = list(model)
            mutated[1] = not mutated[1]
            with self.assertRaises(AssertionError):
                validate_decode(problem, mutated)
            with self.assertRaisesRegex(AssertionError, "incomplete"):
                validate_decode(problem, model[:-1])
            mutated = list(model)
            mutated[1] = None
            with self.assertRaisesRegex(AssertionError, "non-Boolean"):
                validate_decode(problem, mutated)

    @unittest.skipUnless(HAVE_SOLVER, "optional native XOR backend")
    def test_rank_zero_unsat_and_exact_inconsistency(self):
        system = build_system([(1, 1, 1)], 1, baseline=naive_candidate(1))
        self.assertEqual(solve(build_problem(system, 0), seconds=1, memory_mb=512)["status"], "UNSAT")
        self.assertEqual(solve(build_problem(build_system([], 1), 0), seconds=1, memory_mb=512)["status"], "UNSAT")

    @unittest.skipUnless(HAVE_SOLVER, "optional native XOR backend")
    def test_free_groups_cardinality_and_hard_timeout_cleanup(self):
        baseline = naive_candidate(2)
        dictionary = sorted(set(canonical_terms(baseline)) | set(canonical_terms(strassen_candidate(2))))
        system = build_system(dictionary, 2, baseline=baseline)
        self.assertGreater(system["metadata"]["linear_nullity"], 0)
        self.assertEqual(system["metadata"]["forced_active"], 0)
        problem = build_problem(system, 7)
        self.assertGreater(problem["nv"], problem["metadata"]["base_variables"])
        result = solve(problem, seconds=1, memory_mb=512)
        self.assertEqual(result["status"], "SAT")
        self.assertEqual(result["verification"]["rank"], 7)
        self.assertTrue(result["verification"]["valid"])
        model = list(result["complete_assignment"])
        first_y = system["metadata"]["width"]*len(system["pairs"])+1
        model[first_y] = not model[first_y]
        with self.assertRaises(AssertionError):
            validate_decode(problem, model)
        def stalled_worker(*_args):
            time.sleep(10)
        with patch("mmsearch.free_factor_sat._worker", stalled_worker):
            timed = solve(problem, seconds=0.02, memory_mb=512)
        self.assertEqual(timed["status"], "UNKNOWN")
        self.assertTrue(timed["worker_reaped"])
        self.assertLess(timed["elapsed_seconds"], 1)

    @unittest.skipUnless(HAVE_SOLVER, "optional native XOR backend")
    def test_cli_freezes_positive_control_and_exact_unsat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = naive_candidate(2)
            save(root/"dictionary.json", canonical_terms(baseline))
            save(root/"baseline.json", baseline)
            args = ["--dictionary", str(root/"dictionary.json"), "--baseline", str(root/"baseline.json"),
                "--dimension", "2", "--rank", "7", "--seconds", "4", "--memory-mb", "512",
                "--outdir", str(root/"out")]
            self.assertEqual(main(args), 0)
            result = json.loads((root/"out/result.json").read_text())
            self.assertEqual(result["status"], "UNSAT")
            self.assertEqual(result["control_status"], "SAT")
            self.assertTrue((root/"out/control.candidate.model.json").exists())
            self.assertTrue((root/"out/inputs/dictionary.json").exists())
            self.assertTrue((root/"out/code/mmsearch/free_factor_sat.py").exists())
            with self.assertRaises(FileExistsError):
                main(args)
            # Exercise the target SAT path with genuinely free groups and a
            # cardinality improvement over the fixed positive control.
            save(root/"dictionary.json", sorted(set(canonical_terms(baseline)) |
                set(canonical_terms(strassen_candidate(2)))))
            args[-1] = str(root/"target-sat")
            self.assertEqual(main(args), 0)
            winner = json.loads((root/"target-sat/WINNER.json").read_text())
            self.assertEqual(len(winner["terms"]), 7)
            self.assertTrue(verify_candidate(winner)["valid"])
            self.assertTrue((root/"target-sat/WINNER.model.json").exists())

    def test_cli_preflight_and_immediate_baseline_merge_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = strassen_candidate(2)
            save(root/"dictionary.json", canonical_terms(baseline))
            save(root/"baseline.json", baseline)
            args = ["--dictionary", str(root/"dictionary.json"), "--baseline", str(root/"baseline.json"),
                "--dimension", "2", "--rank", "7", "--outdir", str(root/"preflight"),
                "--orientation", "all", "--preflight"]
            self.assertEqual(main(args), 0)
            self.assertEqual(len(json.loads((root/"preflight/preflight.json").read_text())), 3)
            self.assertFalse((root/"preflight/control.problem.cnf").exists())
            self.assertTrue((root/"preflight/WINNER.json").exists())
            args = args[:args.index("--outdir")]+["--outdir", str(root/"winner")]
            self.assertEqual(main(args), 0)
            self.assertTrue((root/"winner/WINNER.json").exists())
            self.assertTrue(verify_candidate(json.loads((root/"winner/WINNER.json").read_text()))["valid"])


if __name__ == "__main__":
    unittest.main()
