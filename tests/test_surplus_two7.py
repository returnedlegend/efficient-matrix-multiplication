"""Independent exhaustive small-space tests for the surplus-two decoder."""
import importlib.util
import itertools
from pathlib import Path
import random
import unittest
from unittest.mock import patch

import mmsearch.surplus_two7 as decoder
from mmsearch.backbone7 import HARD_DEADLINE
from mmsearch.surplus_two7 import solve_core, solve_pair_image


def oracle():
    path = Path(__file__).parent / "fixtures/compact_rank2_edges43_oracle.py"
    spec = importlib.util.spec_from_file_location("surplus_two_independent_oracle", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def outer(left, right, rows, columns):
    return sum(((left >> i & 1) & (right >> j & 1)) << (i * columns + j)
               for i in range(rows) for j in range(columns))


@patch("mmsearch.surplus_two7.time.time", return_value=HARD_DEADLINE - 60)
class SurplusTwoControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = oracle()

    def witness(self, raw, rows, columns, result):
        self.assertLessEqual(len(result["support"]), result["budget"])
        self.assertEqual(len(result["target_coordinates"]), len(raw))
        for point in result["support"]:
            self.assertIn(point, result["factor_point_pool"])
            self.assertEqual(point["column"], outer(point["left"], point["right"], rows, columns))
            self.assertTrue(point["left"] and point["right"])
        for value, mask in zip(raw, result["target_coordinates"]):
            actual = 0
            for j, point in enumerate(result["support"]):
                if mask >> j & 1:
                    actual ^= point["column"]
            self.assertEqual(actual, value)

    def test_all_2892_spaces_all_supported_budgets(self, _clock):
        cases = budgets = 0
        for rows, columns in [(2, 2), (2, 3)]:
            spaces = self.oracle.all_subspaces(rows * columns)
            points = self.oracle.rankone_points(rows, columns)
            attainable = [encoded for encoded in spaces
                          if self.oracle.span(p for p in points if encoded >> p & 1)
                          == frozenset(self.oracle.points(encoded))]
            for encoded in spaces:
                basis = self.oracle.independent(list(self.oracle.points(encoded)))
                d = len(basis)
                raw = [0] + basis + basis[::-1] + [0]
                optimum = min(cover.bit_count().bit_length() - 1 for cover in attainable
                              if not encoded & ~cover)
                for budget in range(d + 3):
                    result = solve_pair_image(raw, rows, columns, budget)
                    self.assertTrue(result["complete"], (rows, columns, basis, budget, result))
                    self.assertEqual(result["status"] == "SAT", optimum <= budget,
                                     (rows, columns, basis, budget, optimum, result))
                    if result["status"] == "SAT":
                        self.witness(raw, rows, columns, result)
                    budgets += 1
                cases += 1
        self.assertEqual(cases, 2892)
        self.assertEqual(budgets, 17285)

    def test_disjoint_rank_two_blocks_requires_new_branch(self, _clock):
        raw = [0, 33, 33792, 33 ^ 33792, 33, 0]
        self.assertEqual(solve_pair_image(raw, 4, 4, 3)["status"], "LOCAL_UNSAT")
        result = solve_pair_image(raw, 4, 4, 4)
        self.assertEqual(result["case"], "repeated_coset_pair_extension")
        self.assertEqual(result["inside_rank"], 0)
        self.assertEqual(result["backbone_codimension"], 2)
        self.assertEqual(result["unordered_rank_two_splits"], 6)
        self.assertGreater(result["total_extensions"], 0)
        self.witness(raw, 4, 4, result)

    def test_nonzero_backbone_new_branch_and_full_core(self, _clock):
        block1 = (1 << 0) ^ (1 << 6)
        block2 = (1 << 12) ^ (1 << 18)
        single = 1 << 24
        raw = [0, block1, single, block2, block1 ^ block2 ^ single, block1, 0]
        result = solve_pair_image(raw, 5, 5, 5)
        self.assertEqual(result["case"], "repeated_coset_pair_extension")
        self.assertEqual(result["inside_rank"], 1)
        self.witness(raw, 5, 5, result)
        shape = [len(raw), 5, 5]
        core = [value >> i & 1 for value in raw for i in range(25)]
        result = solve_core(core, shape, 5, axis=0)
        self.assertEqual(result["status"], "SAT")
        actual = [0] * len(core)
        for a, b, c in result["products"]:
            for i, j, k in itertools.product(*(range(v) for v in shape)):
                actual[(i * 5 + j) * 5 + k] ^= (a >> i & 1) & (b >> j & 1) & (c >> k & 1)
        self.assertEqual(actual, core)

    def test_dense_invertible_changes_preserve_new_branch(self, _clock):
        rng = random.Random(792)
        for _ in range(20):
            left = [1 << j for j in range(4)]
            right = [1 << j for j in range(4)]
            for basis in [left, right]:
                for _ in range(24):
                    i, j = rng.sample(range(4), 2)
                    basis[i] ^= basis[j]
            first = outer(left[0], right[0], 4, 4) ^ outer(left[1], right[1], 4, 4)
            second = outer(left[2], right[2], 4, 4) ^ outer(left[3], right[3], 4, 4)
            raw = [0, first ^ second, first, second, first]
            result = solve_pair_image(raw, 4, 4, 4)
            self.assertEqual(result["case"], "repeated_coset_pair_extension")
            self.witness(raw, 4, 4, result)

    def test_corank_one_exact_positive_negative_and_no_seed_negative(self, _clock):
        self.assertEqual(solve_pair_image([273, 0, 273], 3, 3, 3)["case"], "exact_corank_one_backbone")
        self.assertEqual(solve_pair_image([33825], 4, 4, 3)["status"], "LOCAL_UNSAT")
        # Two disjoint rank-three blocks: no rank-two difference exists in S.
        first = sum(1 << (i * 6 + i) for i in range(3))
        second = sum(1 << (i * 6 + i) for i in range(3, 6))
        result = solve_pair_image([0, first, second, first ^ second], 6, 6, 4)
        self.assertEqual(result["status"], "LOCAL_UNSAT")
        self.assertEqual(result["total_extensions"], 0)
        self.assertTrue(result["complete"])

    def test_caps_are_unknown_and_no_skipped_child_closes_negative(self, _clock):
        raw = [33, 33792]
        for kwargs, case in [({"max_extensions": 0}, "extension_cap"),
                             ({"max_vectors": 2}, "subspace_enumeration_cap"),
                             ({"max_mode_rank": 1}, "mode_rank_cap"),
                             ({"max_vectors": 3}, "extension_child_incomplete")]:
            result = solve_pair_image(raw, 4, 4, 4, **kwargs)
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["case"], case)
            self.assertFalse(result["complete"])
        self.assertEqual(solve_pair_image(raw, 4, 4, 5)["case"], "unsupported_surplus_gt_two")

    def test_guards_and_late_complete_answers_are_unknown(self, _clock):
        for kwargs, case in [({"timeout_seconds": 0}, "timeout"),
                             ({"cancelled": lambda: True}, "cancelled"),
                             ({"deadline_utc": "2000-01-01T00:00:00Z"}, "deadline")]:
            result = solve_pair_image([33, 33792], 4, 4, 4, **kwargs)
            self.assertEqual((result["status"], result["complete"], result["case"]),
                             ("UNKNOWN", False, case))
        original = decoder.solve_one
        flag = [False]
        def delayed(*args, **kwargs):
            result = original(*args, **kwargs)
            flag[0] = True
            return result
        with patch.object(decoder, "solve_one", delayed):
            result = solve_pair_image([1], 1, 1, 1, cancelled=lambda: flag[0])
        self.assertEqual(result["status"], "UNKNOWN")
        original_basis = decoder.BinaryBasis
        class DelayedBasis(original_basis):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                flag[0] = True
        flag[0] = False
        with patch.object(decoder, "BinaryBasis", DelayedBasis):
            result = solve_pair_image([1], 1, 1, 0, cancelled=lambda: flag[0])
        self.assertEqual(result["status"], "UNKNOWN")
        original_solve = decoder.solve_pair_image
        for target in [0, 1]:
            flag[0] = False
            def delayed_core(*args, **kwargs):
                result = original_solve(*args, **kwargs)
                flag[0] = True
                return result
            with patch.object(decoder, "solve_pair_image", delayed_core):
                result = solve_core([1], [1, 1, 1], target, axis=0, cancelled=lambda: flag[0])
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertFalse(result["complete"])

    def test_validation_zero_and_hard_deadline_clamp(self, _clock):
        for kwargs in [{"max_mode_rank": 10}, {"max_extensions": True},
                       {"timeout_seconds": float("inf")}, {"timeout_seconds": -1}]:
            with self.assertRaises(ValueError):
                solve_pair_image([1], 1, 1, 1, **kwargs)
        for value in [-1, True, 16]:
            with self.assertRaises(ValueError):
                solve_pair_image([value], 2, 2, 2)
        result = solve_pair_image([0, 0], 0, 0, 0, deadline_utc="2030-01-01T00:00:00Z")
        self.assertEqual(result["status"], "SAT")
        self.assertEqual(result["target_coordinates"], [0, 0])
        self.assertTrue(result["effective_deadline_utc"].startswith("2026-11-03T19:24:17"))


if __name__ == "__main__":
    unittest.main()
