"""Independent tiny controls for exact backbone decoding and raw-slice lifting."""
from collections import deque
import itertools
import random
import unittest
from unittest.mock import patch

import mmsearch.backbone7 as decoder
from mmsearch.backbone7 import (HARD_DEADLINE, matrix_rank, rank_factorization,
                               solve_core, solve_pair_image)


def outer(left, right, rows, columns):
    return sum(((left >> i & 1) & (right >> j & 1)) << (i * columns + j)
               for i in range(rows) for j in range(columns))


def span(values):
    points = {0}
    for value in values:
        points |= {p ^ value for p in tuple(points)}
    return points


def independent(values):
    basis, points = [], {0}
    for value in values:
        if value not in points:
            basis.append(value)
            points |= {p ^ value for p in tuple(points)}
    return basis


def scalar_rank(value, rows, columns):
    # Exhaustively build the row span; independent of production elimination.
    raw = [(value >> (i * columns)) & ((1 << columns) - 1) for i in range(rows)]
    return len(span(raw)).bit_length() - 1


@patch("mmsearch.backbone7.time.time", return_value=HARD_DEADLINE - 60)
class BackboneControls(unittest.TestCase):
    def witness(self, targets, rows, columns, result):
        self.assertEqual(len(result["target_coordinates"]), len(targets))
        self.assertLessEqual(len(result["support"]), result["budget"])
        pool = result["factor_point_pool"]
        for point in result["support"]:
            self.assertIn(point, pool)
            self.assertTrue(point["left"] and point["right"])
            self.assertEqual(point["column"], outer(point["left"], point["right"], rows, columns))
        for target, mask in zip(targets, result["target_coordinates"]):
            rebuilt = 0
            for i, point in enumerate(result["support"]):
                if mask >> i & 1:
                    rebuilt ^= point["column"]
            self.assertEqual(rebuilt, target)

    def test_rank_factorization_all_small_matrices(self, _clock):
        for rows, columns in [(0, 3), (3, 0), (2, 3), (3, 2), (3, 3)]:
            for value in range(1 << (rows * columns)):
                points = rank_factorization(value, rows, columns)
                self.assertEqual(len(points), scalar_rank(value, rows, columns))
                self.assertEqual(matrix_rank(value, rows, columns), len(points))
                rebuilt = 0
                for point in points:
                    self.assertEqual(point["column"], outer(point["left"], point["right"], rows, columns))
                    rebuilt ^= point["column"]
                self.assertEqual(rebuilt, value)

    def test_arbitrary_surplus_corank_one_every_budget_and_raw_slice(self, _clock):
        # CP=5, while d+2=4.  This explicitly tests the new arbitrary-surplus case.
        e = 1
        diagonal = sum(1 << (i * 5 + i) for i in range(1, 5))
        raw = [0, diagonal ^ e, diagonal, e, diagonal, 0, diagonal ^ e]
        for budget in range(9):
            result = solve_pair_image(raw, 5, 5, budget)
            self.assertEqual(result["status"], "SAT" if budget >= 5 else "LOCAL_UNSAT")
            self.assertTrue(result["complete"])
            if budget >= 2:
                self.assertEqual(result["exact_cp_rank"], 5)
                self.assertEqual(result["inside_rank"], 1)
                self.assertEqual(result["quotient_dimension"], 1)
            if result["status"] == "SAT":
                self.witness(raw, 5, 5, result)

    def test_all_67_two_by_two_spaces_against_exhaustive_cover(self, _clock):
        # Every rank-one cover has a basis of <=4 of the nine rank-one points.
        rankones = [outer(x, y, 2, 2) for x in range(1, 4) for y in range(1, 4)]
        covers = []
        for count in range(5):
            covers.extend((count, span(subset)) for subset in itertools.combinations(rankones, count))
        spaces, queue = {frozenset({0})}, deque([frozenset({0})])
        while queue:
            old = queue.popleft()
            for value in range(1, 16):
                new = frozenset(set(old) | {p ^ value for p in old})
                if new not in spaces:
                    spaces.add(new)
                    queue.append(new)
        self.assertEqual(len(spaces), 67)
        checked = 0
        for space in spaces:
            basis = independent(sorted(space))
            raw = [0] + basis + basis[::-1] + [0]
            optimum = min(count for count, cover in covers if space <= cover)
            for budget in range(6):
                result = solve_pair_image(raw, 2, 2, budget)
                if result["status"] == "SAT":
                    self.assertLessEqual(optimum, budget)
                    self.witness(raw, 2, 2, result)
                elif result["status"] == "LOCAL_UNSAT":
                    self.assertGreater(optimum, budget)
                if result.get("quotient_dimension", 2) <= 1:
                    self.assertEqual(result["status"] == "SAT", optimum <= budget)
                    if result.get("exact_cp_rank") is not None:
                        self.assertEqual(result["exact_cp_rank"], optimum)
                    checked += 1
        self.assertGreater(checked, 100)

    def test_weighted_quotient_is_upper_bound_only(self, _clock):
        raw = [0, 33, 33792, 33 ^ 33792, 33]
        # Two disjoint rank-two diagonal blocks: d=2, B0=0, construction=4.
        hit = solve_pair_image(raw, 4, 4, 4)
        self.assertEqual(hit["status"], "SAT")
        self.assertEqual(hit["exact_scope"], "restricted_family_upper_bound")
        self.assertIsNone(hit["exact_cp_rank"])
        self.assertEqual(hit["restricted_family_optimum"], 4)
        self.witness(raw, 4, 4, hit)
        miss = solve_pair_image(raw, 4, 4, 3)
        self.assertEqual(miss["status"], "UNKNOWN")
        self.assertFalse(miss["complete"])
        # Here global CP=3 but the restricted family costs4: UNKNOWN is essential.
        pencil = solve_pair_image([9, 14], 2, 2, 3)
        self.assertEqual(pencil["cp_upper_bound"], 4)
        self.assertEqual(pencil["status"], "UNKNOWN")
        rankones = [outer(x, y, 2, 2) for x in range(1, 4) for y in range(1, 4)]
        self.assertTrue(any({9, 14} <= span(triple) for triple in itertools.combinations(rankones, 3)))

    def test_full_raw_core_all_axes_and_budgets(self, _clock):
        rows = [0, 256, 10, 256 ^ 10, 256, 0]
        original_shape = [len(rows), 3, 3]
        original = [value >> j & 1 for value in rows for j in range(9)]
        for axis in range(3):
            permutation = [1, 2]
            permutation.insert(axis, 0)
            shape = [original_shape[j] for j in permutation]
            core = []
            for xyz in itertools.product(*(range(v) for v in shape)):
                old = [0, 0, 0]
                for new, prior in enumerate(permutation):
                    old[prior] = xyz[new]
                core.append(original[(old[0] * 3 + old[1]) * 3 + old[2]])
            for budget in range(6):
                result = solve_core(core, shape, budget, axis=axis)
                self.assertEqual(result["status"] == "SAT", budget >= 3)
                if result["status"] == "SAT":
                    rebuilt = [0] * len(core)
                    for a, b, c in result["products"]:
                        for i, j, k in itertools.product(*(range(v) for v in shape)):
                            rebuilt[(i * shape[1] + j) * shape[2] + k] ^= (a >> i & 1) & (b >> j & 1) & (c >> k & 1)
                    self.assertEqual(rebuilt, core)
                    self.assertEqual(result["core_entries_checked"], len(core))

    def test_random_coordinate_changes_corank_one_controls(self, _clock):
        rng = random.Random(711)
        for _ in range(25):
            left = [1 << i for i in range(5)]
            right = [1 << i for i in range(5)]
            for basis in [left, right]:
                for _ in range(30):
                    i, j = rng.sample(range(5), 2)
                    basis[i] ^= basis[j]
            e = outer(left[0], right[0], 5, 5)
            diagonal = 0
            for i in range(1, 5):
                diagonal ^= outer(left[i], right[i], 5, 5)
            raw = [0, diagonal, e, diagonal ^ e, diagonal]
            result = solve_pair_image(raw, 5, 5, 5)
            self.assertEqual(result["exact_cp_rank"], 5)
            self.witness(raw, 5, 5, result)

    def test_guards_caps_timeout_deadline_are_unknown(self, _clock):
        for kwargs, case in [({"max_vectors": 2}, "subspace_enumeration_cap"),
                             ({"cancelled": lambda: True}, "cancelled"),
                             ({"timeout_seconds": 0}, "timeout"),
                             ({"deadline_utc": "2000-01-01T00:00:00Z"}, "deadline")]:
            result = solve_pair_image([9, 14, 0, 9], 2, 2, 3, **kwargs)
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["case"], case)
            self.assertFalse(result["complete"])
        calls = 0
        def cancelled():
            nonlocal calls
            calls += 1
            return calls > 3
        result = solve_pair_image([9, 14], 2, 2, 3, cancelled=cancelled)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["enumerated_vectors"], 2)
        self.assertEqual(solve_pair_image([], 0, 0, 0)["support"], [])

    def test_strict_input_validation(self, _clock):
        for targets, rows, columns, budget in [([-1], 2, 2, 1), ([16], 2, 2, 1),
                                               ([True], 2, 2, 1), ([1], -1, 2, 1),
                                               ([1], 2, 2, True)]:
            with self.assertRaises(ValueError):
                solve_pair_image(targets, rows, columns, budget)
        with self.assertRaises(ValueError):
            solve_pair_image([1], 2, 2, 1, timeout_seconds=float("nan"))

    def test_late_negative_and_core_postcall_are_unknown(self, _clock):
        # Independent reviewer repro: elimination can trigger a late cancel.
        original = decoder.BinaryBasis
        flag = [False]
        class DelayedBasis(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                flag[0] = True
        with patch.object(decoder, "BinaryBasis", DelayedBasis):
            result = solve_pair_image([1], 1, 1, 0, cancelled=lambda: flag[0])
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["case"], "cancelled")
        self.assertFalse(result["complete"])

        original_solve = decoder.solve_pair_image
        for target in [0, 1]:
            flag[0] = False
            def delayed_solve(*args, **kwargs):
                result = original_solve(*args, **kwargs)
                flag[0] = True
                return result
            with patch.object(decoder, "solve_pair_image", delayed_solve):
                result = decoder.solve_core([1], [1, 1, 1], target, axis=0,
                                            cancelled=lambda: flag[0])
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["case"], "cancelled")
            self.assertFalse(result["complete"])


if __name__ == "__main__":
    unittest.main()
