"""Independent exact checks for discrete, nonlinear and restart semantics."""
import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from mmsearch.targeted_repair import (ResidualState, connected_proposals, decode,
    encode, search, shear_proposal, span_proposal)
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.verify import verify_candidate


class TargetedRepairTests(unittest.TestCase):
    def test_incremental_joint_moves_match_independent_exact_tensor(self):
        rng = random.Random(481)
        for n in (2, 3):
            width = n*n
            state = ResidualState([[rng.randrange(1 << width) for _ in range(3)]
                                   for _ in range(7)], n)
            for iteration in range(35):
                # Includes repeated coordinates and nonlinear same-slot flips.
                slot = rng.randrange(7)
                moves = [(slot, axis, rng.randrange(width)) for axis in range(3)]
                moves += [(rng.randrange(7), rng.randrange(3), rng.randrange(width))
                          for _ in range(iteration % 4)]
                predicted = state.residual ^ state.delta(moves)
                state.apply(moves)
                report = verify_candidate(encode(state.factors, n), random_trials=0)
                self.assertEqual(state.residual, predicted)
                self.assertEqual(state.weight, report["mismatch_count"])
                fresh = ResidualState(state.factors, n)
                self.assertEqual(state.residual, fresh.residual)

    def test_joint_move_recovers_two_axis_corruption(self):
        candidate = naive_candidate(2)
        # An annihilated product and a spurious factor bit require two flips.
        candidate["terms"][0]["u"][0] ^= 1
        candidate["terms"][0]["v"][1] ^= 1
        state = ResidualState(decode(candidate), 2)
        self.assertEqual(state.weight, 1)
        proposals = connected_proposals(state, random.Random(6))
        single_best = min(weight for weight, _, kind in proposals if kind == "single")
        self.assertGreater(single_best, 0)
        repairs = [moves for weight, moves, kind in proposals if weight == 0 and kind == "pair"]
        self.assertTrue(repairs)
        state.apply(repairs[0])
        self.assertTrue(verify_candidate(encode(state.factors, 2))["valid"])
        found, report = search(candidate, seconds=2, max_steps=40, seed=6, progress=False)
        self.assertTrue(report["valid"])
        self.assertEqual(found["metadata"]["residual_weight"], 0)

    def test_exact_span_repairs_multiple_corrupted_coordinates(self):
        candidate = strassen_candidate(2)
        for slot, coordinate in ((0, 0), (1, 2), (3, 1), (6, 3)):
            candidate["terms"][slot]["u"][coordinate] ^= 1
        state = ResidualState(decode(candidate), 2)
        self.assertGreater(state.weight, 1)
        moves, kind = span_proposal(state, 0, random.Random(8))
        self.assertEqual(kind, "span_repair")
        state.apply(moves)
        self.assertTrue(verify_candidate(encode(state.factors, 2))["valid"])

    def test_unrepresentable_span_does_not_claim_repair(self):
        state = ResidualState([[1, 1, 1]], 2)
        before = state.residual
        moves, kind = span_proposal(state, 0, random.Random(8))
        self.assertEqual(kind, "span_unrepresentable")
        self.assertEqual(moves, ())
        self.assertEqual(before, state.residual)

    def test_shear_preserves_tensor_and_strict_bits(self):
        state = ResidualState(decode(naive_candidate(2)), 2)
        before = state.residual
        rng = random.Random(81)
        changed = False
        for _ in range(40):
            moves = shear_proposal(state, rng)
            self.assertEqual(state.delta(moves), 0)
            state.apply(moves)
            changed |= bool(moves)
            self.assertEqual(state.residual, before)
        self.assertTrue(changed)
        result = encode(state.factors, 2)
        self.assertTrue(verify_candidate(result)["valid"])
        self.assertTrue(all(type(x) is int and x in (0, 1)
                            for t in result["terms"] for v in t.values() for x in v))

    def test_checkpoint_restart_replays_exact_state_and_rng(self):
        source = strassen_candidate(2)
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/"a.json", Path(tmp)/"b.json"
            search(source, rank=6, seconds=30, max_steps=17, seed=7,
                   checkpoint=a, progress=False)
            search(source, rank=6, seconds=30, max_steps=5, seed=7,
                   checkpoint=b, progress=False)
            search(source, rank=6, seconds=30, max_steps=12, seed=7,
                   checkpoint=b, resume=True, progress=False)
            self.assertEqual(json.loads(a.read_text()), json.loads(b.read_text()))
            checkpoint = json.loads(b.read_text())
            checkpoint["best_candidate"]["terms"].pop()
            b.write_text(json.dumps(checkpoint))
            with self.assertRaisesRegex(ValueError, "dimension or rank differs"):
                search(source, rank=6, seconds=0, seed=7,
                       checkpoint=b, resume=True, progress=False)
            b.write_text(a.read_text())
            checkpoint = json.loads(b.read_text())
            checkpoint["identity"]["code_sha256"]["targeted_repair.py"] = "changed"
            b.write_text(json.dumps(checkpoint))
            with self.assertRaisesRegex(ValueError, "hashes differ"):
                search(source, rank=6, seconds=0, seed=7,
                       checkpoint=b, resume=True, progress=False)

    def test_failed_candidate_has_independent_standalone_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/"best.json"
            candidate, report = search(strassen_candidate(2), rank=6, seconds=0,
                                      output=output, progress=False)
            self.assertFalse(report["valid"])
            self.assertEqual(candidate["metadata"]["status"], "failed_exact_verification")
            independent = subprocess.run([sys.executable, "-I", str(output.with_suffix(".verify.py")),
                str(output)], cwd=tmp, capture_output=True, text=True)
            self.assertEqual(independent.returncode, 1)
            self.assertEqual(json.loads(independent.stdout)["mismatch_count"],
                             report["mismatch_count"])

    def test_float_coefficients_and_invalid_budgets_are_rejected(self):
        for value in (1.0, True, -1, 2):
            source = naive_candidate(2)
            source["terms"][0]["u"][0] = value
            with self.assertRaises(ValueError):
                decode(source)
        for seconds in (-1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                search(naive_candidate(1), seconds=seconds, progress=False)


if __name__ == "__main__":
    unittest.main()
