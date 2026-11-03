"""Tiny weighted brute-force controls; no production inputs or tensor queries."""
import itertools
import random
import unittest
from unittest.mock import patch

import mmsearch.kernel_projection_dominance7 as subject


def xor_columns(columns, state):
    out = 0
    for i, column in enumerate(columns):
        if state >> i & 1:
            out ^= column
    return out


def cost(state, weights):
    return sum(weight for i, weight in enumerate(weights) if state >> i & 1)


def minimum(columns, target, weights):
    return min(cost(state, weights) for state in range(1 << len(columns))
               if xor_columns(columns, state) == target)


@patch("mmsearch.kernel_projection_dominance7.time.time", return_value=subject.HARD_DEADLINE - 60)
class ProjectionDominanceTests(unittest.TestCase):
    def assert_certificate(self, result, old, extended, weights):
        lifts = [int(value, 16) for value in result["projection_lifts_hex"]]
        margins = []
        for alpha in range(1 << len(lifts)):
            relation = 0
            for i, lift in enumerate(lifts):
                if alpha >> i & 1:
                    relation ^= lift
            self.assertEqual(xor_columns(extended, relation), 0)
            margins.append(cost(relation >> len(old), weights[len(old):]) -
                           cost(relation & ((1 << len(old)) - 1), weights[:len(old)]))
        self.assertEqual(result["minimum_margin"], min(margins))
        self.assertEqual(result["minimum_nonzero_margin"], min(margins[1:]) if len(margins) > 1 else None)
        self.assertEqual(result["enumerated_states"], len(margins))
        self.assertEqual(result["minimum_equality_certified"], min(margins) >= 0)

    def test_weighted_single_odd_cycle_is_dominated(self, _clock):
        old = [1, 2]
        extended = old + [4, 8, 1 ^ 2 ^ 4 ^ 8]
        weights = [1, 1, 3, 3, 1]
        result = subject.inspect_dominance(old, extended, 3, 3, extended_weights=weights,
                                           extended_kernel=[31])
        self.assertEqual(result["status"], "DOMINATED")
        self.assertEqual(result["projected_kernel_rank"], 1)
        self.assertEqual(result["minimum_margin"], 0)  # Include alpha=0 explicitly.
        self.assertEqual(result["minimum_nonzero_margin"], 5)  # New cost7 versus old cost2.
        self.assertEqual(result["nonzero_margin_minimizer_observed"]["old_cost"], 2)
        self.assertEqual(result["nonzero_margin_minimizer_observed"]["new_cost"], 7)
        self.assertEqual(minimum(old, 3, weights[:2]), 2)
        self.assertEqual(minimum(extended, 3, weights), 2)
        self.assert_certificate(result, old, extended, weights)

    def test_interacting_individually_safe_five_cycles_can_fail_joint_bound(self, _clock):
        old = [1, 2, 4, 8]
        extended = old + [16, 32, 16 ^ 32 ^ 1 ^ 2, 16 ^ 32 ^ 4 ^ 8]
        c1 = 0b0011 | (0b0111 << 4)
        c2 = 0b1100 | (0b1011 << 4)
        for cycle in [c1, c2]:
            self.assertEqual(cycle.bit_count(), 5)
            self.assertEqual(xor_columns(extended, cycle), 0)
            self.assertEqual((cycle >> 4).bit_count() - (cycle & 15).bit_count(), 1)
        result = subject.inspect_dominance(old, extended, 15, 15,
                                           extended_kernel=[c1, c2], projection_lifts=[c1, c2])
        self.assertEqual(result["status"], "POTENTIAL")
        self.assertFalse(result["minimum_equality_certified"])
        self.assertEqual(result["minimum_nonzero_margin"], -2)
        self.assertEqual(minimum(old, 15, [1] * 4), 4)
        self.assertEqual(minimum(extended, 15, [1] * 8), 2)  # Tiny known code only.
        self.assertNotIn("solution", result)
        self.assert_certificate(result, old, extended, [1] * 8)
        # Same negative bound, but zero target has equal zero minima. No converse.
        zero = subject.inspect_dominance(old, extended, 0, 0,
                                         extended_kernel=[c1, c2], projection_lifts=[c1, c2])
        self.assertEqual(zero["status"], "POTENTIAL")
        self.assertEqual(minimum(old, 0, [1] * 4), minimum(extended, 0, [1] * 8))

    def test_explicit_lift_choice_can_strengthen_certificate(self, _clock):
        old, extended = [1, 1], [1, 1, 1]
        kernel = [3, 5]
        automatic = subject.inspect_dominance(old, extended, 1, 1,
                    base_weights=[100, 1], extended_weights=[100, 1, 2], extended_kernel=kernel)
        chosen = subject.inspect_dominance(old, extended, 1, 1,
                    base_weights=[100, 1], extended_weights=[100, 1, 2], extended_kernel=kernel,
                    projection_lifts=[6])
        self.assertEqual(automatic["status"], "POTENTIAL")
        self.assertEqual(chosen["status"], "DOMINATED")
        self.assertEqual(minimum(old, 1, [100, 1]), minimum(extended, 1, [100, 1, 2]))

    def test_200_random_weighted_codes_against_literal_fiber_minima(self, _clock):
        rng = random.Random(798)
        dominated = potential = 0
        for _ in range(200):
            old_count, new_count = rng.randrange(5), rng.randrange(4)
            old = [rng.randrange(16) for _ in range(old_count)]
            extended = old + [rng.randrange(16) for _ in range(new_count)]
            state = rng.randrange(1 << old_count)
            target = xor_columns(old, state)
            weights = [rng.randrange(5) for _ in extended]
            result = subject.inspect_dominance(old, extended, target, state,
                        base_weights=weights[:old_count], extended_weights=weights)
            self.assertTrue(result["complete"])
            self.assert_certificate(result, old, extended, weights)
            base_min = minimum(old, target, weights[:old_count])
            extended_min = minimum(extended, target, weights)
            if result["status"] == "DOMINATED":
                self.assertEqual(base_min, extended_min)
                dominated += 1
            else:
                self.assertEqual(result["status"], "POTENTIAL")
                self.assertLess(result["negative_relation"]["margin"], 0)
                potential += 1
        self.assertGreater(dominated, 50)
        self.assertGreater(potential, 10)

    def test_complete_kernel_and_projection_coverage_are_required(self, _clock):
        old, extended = [1, 2], [1, 2, 1, 2]
        for kernel in [[], [5], [5, 5], [1, 10], [0, 5]]:
            with self.subTest(kernel=kernel), self.assertRaises(ValueError):
                subject.inspect_dominance(old, extended, 3, 3, extended_kernel=kernel)
        for lifts in [[], [5], [5, 5], [5, 1]]:
            with self.subTest(lifts=lifts), self.assertRaises(ValueError):
                subject.inspect_dominance(old, extended, 3, 3,
                    extended_kernel=[5, 10], projection_lifts=lifts)

    def test_empty_projection_zero_columns_and_zero_costs(self, _clock):
        for old, extended, target, state, weights in [([], [], 0, 0, []),
                ([1], [1], 1, 1, [0]), ([1], [1, 2], 1, 1, [2, 0]),
                ([], [0], 0, 0, [0]), ([0], [0, 0], 0, 1, [0, 0])]:
            result = subject.inspect_dominance(old, extended, target, state,
                base_weights=weights[:len(old)], extended_weights=weights)
            self.assertEqual(result["status"], "DOMINATED")
            self.assert_certificate(result, old, extended, weights)
        no_projection = subject.inspect_dominance([1], [1, 2], 1, 1)
        self.assertEqual(no_projection["projected_kernel_rank"], 0)
        self.assertEqual(no_projection["enumerated_states"], 1)
        self.assertIsNone(no_projection["minimum_nonzero_margin"])
        five = subject.inspect_dominance([], [0] * 5, 0, 0,
                                         extended_weights=[0, 1, 2, 3, 4])
        self.assertEqual(five["enumerated_states"], 32)
        self.assert_certificate(five, [], [0] * 5, [0, 1, 2, 3, 4])

    def test_caps_deadlines_and_partial_negative_are_unknown(self, _clock):
        for kwargs, case in [({"max_projection_rank": 0}, "projection_rank_cap"),
                             ({"max_states": 0}, "state_enumeration_cap"),
                             ({"max_states": 1}, "state_enumeration_cap"),
                             ({"timeout_seconds": 0}, "timeout"),
                             ({"cancelled": lambda: True}, "cancelled"),
                             ({"deadline_utc": "2000-01-01T00:00:00Z"}, "deadline")]:
            result = subject.inspect_dominance([1], [1, 1], 1, 1, **kwargs)
            self.assertEqual((result["status"], result["case"], result["complete"]),
                             ("UNKNOWN", case, False))
            self.assertFalse(result["minimum_equality_certified"])
        # The first nonzero Gray vector is already negative, but an unvisited
        # direction still makes the capped scan UNKNOWN, never a complete answer.
        result = subject.inspect_dominance([1, 2], [1, 2, 1, 2], 3, 3,
                    base_weights=[3, 3], extended_weights=[3, 3, 1, 1], max_states=2)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertLess(result["observed_negative_relation"]["margin"], 0)
        self.assertIsNone(result["minimum_margin"])
        rank21 = subject.inspect_dominance([], [0] * 21, 0, 0)
        self.assertEqual(rank21["projected_kernel_rank"], 21)
        self.assertEqual(rank21["status"], "UNKNOWN")
        self.assertEqual(rank21["case"], "projection_rank_cap")

    def test_late_completed_scan_is_unknown(self, _clock):
        actual = subject._cost
        flag = [False]
        def late_cost(*args):
            value = actual(*args)
            flag[0] = True
            return value
        with patch.object(subject, "_cost", late_cost):
            result = subject.inspect_dominance([], [], 0, 0, cancelled=lambda: flag[0])
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertFalse(result["complete"])
        self.assertFalse(result["minimum_equality_certified"])

    def test_strict_inputs_alignment_and_old_feasibility(self, _clock):
        for old, extended, target, state, kwargs in [([1], [2, 1], 1, 1, {}),
                ([1], [1], 0, 1, {}), ([1], [1], 1, 2, {}),
                ([True], [True], 1, 1, {}), ([1], [1.0], 1, 1, {}),
                ([1], [1], True, 1, {}), ([1], [1], 1, True, {}),
                ([1], [1], 1, 1, dict(base_weights=[-1])),
                ([1], [1], 1, 1, dict(extended_weights=[1.0])),
                ([1], [1], 1, 1, dict(base_weights=[1], extended_weights=[2])),
                ([1], [1], 1, 1, dict(max_projection_rank=21)),
                ([1], [1], 1, 1, dict(timeout_seconds=float("nan")))]:
            with self.subTest(old=old, kwargs=kwargs), self.assertRaises(ValueError):
                subject.inspect_dominance(old, extended, target, state, **kwargs)


if __name__ == "__main__":
    unittest.main()
