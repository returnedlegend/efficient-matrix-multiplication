"""Independent brute-force block optima and planted known n2 controls only."""
import itertools
import random
import unittest
from unittest.mock import patch

import mmsearch.binary_block_descent7 as subject
from mmsearch.tensor import strassen_candidate


def expand(factors, shape):
    values = []
    for a, b, c in itertools.product(*(range(d) for d in shape)):
        value = 0
        for u, v, w in factors:
            value ^= ((u >> a) & 1) * ((v >> b) & 1) * ((w >> c) & 1)
        values.append(value)
    return values


def literal_loss(core, shape, factors):
    return sum(a != b for a, b in zip(core, expand(factors, shape)))


def strassen():
    candidate = strassen_candidate(2)
    factors = [tuple(sum(x << i for i, x in enumerate(term[axis])) for axis in ("u", "v", "w"))
               for term in candidate["terms"]]
    shape = [4, 4, 4]
    return expand(factors, shape), shape, factors


@patch("mmsearch.binary_block_descent7.time.time", return_value=subject.HARD_DEADLINE - 60)
class BinaryBlockTests(unittest.TestCase):
    def test_all_axes_60_random_blocks_against_whole_block_bruteforce(self, _clock):
        rng = random.Random(714)
        for _ in range(20):
            shape = [rng.randrange(1, 4), rng.randrange(1, 3), rng.randrange(1, 3)]
            rank = rng.randrange(1, 4)
            factors = [tuple(rng.randrange(1 << d) for d in shape) for _ in range(rank)]
            core = [rng.randrange(2) for _ in range(__import__("math").prod(shape))]
            for axis in range(3):
                optimum = len(core)
                for vector in range(1 << (rank * shape[axis])):
                    possible = [list(term) for term in factors]
                    for t in range(rank):
                        possible[t][axis] = (vector >> (t * shape[axis])) & ((1 << shape[axis]) - 1)
                    optimum = min(optimum, literal_loss(core, shape, possible))
                result = subject.exact_block_update(core, shape, factors, axis)
                self.assertEqual(result["status"], "BLOCK_MINIMUM")
                self.assertEqual(result["loss_after"], optimum)
                self.assertEqual(literal_loss(core, shape, result["factors"]), optimum)
                self.assertLessEqual(optimum, literal_loss(core, shape, factors))
                self.assertEqual(result["enumerated_codewords"], 1 << rank)
                self.assertEqual(sum(result["row_distances"]), optimum)

    def test_84_planted_strassen7_single_factor_bit_repairs(self, _clock):
        core, shape, factors = strassen()
        self.assertEqual(len(factors), 7)
        checks = 0
        for axis, term, bit in itertools.product(range(3), range(7), range(4)):
            corrupted = [list(t) for t in factors]
            corrupted[term][axis] ^= 1 << bit
            self.assertGreater(literal_loss(core, shape, corrupted), 0)
            result = subject.exact_block_update(core, shape, corrupted, axis)
            self.assertEqual(result["loss_after"], 0)
            self.assertEqual(expand(result["factors"], shape), core)
            checks += 1
        self.assertEqual(checks, 84)

    def test_optimizer_raw_success_is_not_ambient_candidate(self, _clock):
        from scripts.campaign_operations_v3 import canonical_candidate
        core, shape, factors = strassen()
        for axis in range(3):
            corrupted = [list(t) for t in factors]
            corrupted[0][axis] ^= 1
            order = [axis] + [j for j in range(3) if j != axis]
            result = subject.optimize(core, shape, 7, initial_factors=corrupted, axis_order=order,
                        max_sweeps=1, max_restarts=0, max_perturbations=0)
            self.assertEqual(result["status"], "RAW_EXACT_COMPACT")
            self.assertEqual(result["best_loss"], 0)
            self.assertFalse(result["publication_eligible"])
            self.assertTrue(result["requires_ambient_verification"])
            self.assertFalse(result["raw_compact"]["ambient_verified"])
            self.assertEqual(expand(result["raw_compact"]["products"], shape), core)
            with self.assertRaises((ValueError, TypeError, KeyError)):
                canonical_candidate(result)

    def test_dependent_pair_code_ties_retain_current_factor_block(self, _clock):
        shape = [2, 2, 2]
        factors = [(3, 1, 1), (2, 1, 1), (0, 0, 2)]
        core = expand(factors, shape)
        result = subject.exact_block_update(core, shape, factors, 0)
        self.assertEqual(result["factors"], factors)
        self.assertEqual(result["changed_bits"], 0)
        self.assertEqual(result["loss_after"], 0)

    def test_bounded_failure_and_histories_never_claim_unsat(self, _clock):
        # Two diagonal entries have unfolding rank2, so one product cannot fit.
        core, shape = [1, 0, 0, 0, 0, 0, 0, 1], [2, 2, 2]
        result = subject.optimize(core, shape, 1, seed=72, max_sweeps=8,
                                  max_restarts=2, max_perturbations=2)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertFalse(result["complete"])
        self.assertGreater(result["best_loss"], 0)
        self.assertEqual(result["best_loss"], literal_loss(core, shape, result["best_factors"]))
        bests = [entry["best_loss"] for entry in result["history"]]
        self.assertTrue(all(a >= b for a, b in zip(bests, bests[1:])))
        for entry in result["history"]:
            if entry["action"] == "block":
                self.assertGreaterEqual(entry["loss_before"], entry["loss_after"])
        self.assertNotIn("UNSAT", repr(result))

    def test_fixed_seed_replay_with_discrete_perturbations(self, _clock):
        core, shape = [1, 0, 0, 0, 0, 0, 0, 1], [2, 2, 2]
        a = subject.optimize(core, shape, 1, seed=780, max_sweeps=10,
                             max_restarts=2, max_perturbations=3)
        b = subject.optimize(core, shape, 1, seed=780, max_sweeps=10,
                             max_restarts=2, max_perturbations=3)
        a.pop("elapsed_seconds")
        b.pop("elapsed_seconds")
        self.assertEqual(a, b)

    def test_zero_slots_zero_modes_and_binary_schema(self, _clock):
        result = subject.optimize([], [0, 2, 3], 0, max_sweeps=0)
        self.assertEqual(result["status"], "RAW_EXACT_COMPACT")
        self.assertEqual(result["best_loss"], 0)
        failed = subject.optimize([1], [1, 1, 1], 0, max_restarts=0, max_sweeps=1)
        self.assertEqual(failed["status"], "UNKNOWN")
        for core, shape, factors in [([True], [1, 1, 1], [(1, 1, 1)]),
                ([1.0], [1, 1, 1], [(1, 1, 1)]), ([2], [1, 1, 1], [(1, 1, 1)]),
                ([1], [True, 1, 1], [(1, 1, 1)]), ([1], [1, 1, 1], [(True, 1, 1)]),
                ([1], [1, 1, 1], [(2, 1, 1)])]:
            with self.assertRaises(ValueError):
                subject.exact_block_update(core, shape, factors, 0)
        for rank in [True, -1, 15]:
            with self.assertRaises(ValueError):
                subject.optimize([1], [1, 1, 1], rank)

    def test_timeouts_caps_and_late_blocks_are_unknown(self, _clock):
        for kwargs, expected in [(dict(timeout_seconds=0), "timeout"),
                (dict(cancelled=lambda: True), "cancelled"),
                (dict(deadline_utc="2000-01-01T00:00:00Z"), "deadline"),
                (dict(max_codewords=1), "codeword_cap")]:
            result = subject.exact_block_update([1], [1, 1, 1], [(1, 1, 1)], 0, **kwargs)
            self.assertEqual((result["status"], result["complete"], result["case"]),
                             ("UNKNOWN", False, expected))
        original = subject.scalar_loss
        flag = [False]
        def late(*args):
            loss = original(*args)
            flag[0] = True
            return loss
        with patch.object(subject, "scalar_loss", late):
            result = subject.exact_block_update([1], [1, 1, 1], [(1, 1, 1)], 0,
                                                cancelled=lambda: flag[0])
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertFalse(result["complete"])
        self.assertEqual(subject.optimize([1], [1, 1, 1], 1, timeout_seconds=0)["status"], "UNKNOWN")
        with self.assertRaises(ValueError):
            subject.optimize([1], [1, 1, 1], 1, timeout_seconds=121)


if __name__ == "__main__":
    unittest.main()
