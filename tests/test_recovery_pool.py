"""Exact bounded mixing, censored difficulty, early credit, and record capture."""
import random
import tempfile
from pathlib import Path
import unittest

from mmsearch.recovery_pool import bounded_mix, freeze_json, probe_candidate
from mmsearch.search import decode_candidate, encode_candidate, naive_terms, residual
from mmsearch.tensor import strassen_candidate


class ProbeStub:
    def __init__(self, best, attempts, history):
        self.best, self.attempts, self.history = best, attempts, history
        self.calls = []
    def run(self, candidate, **kwargs):
        self.calls.append(kwargs)
        return {"status": "ok", "best_candidate": self.best,
                "attempted_moves": self.attempts, "cpu_seconds": 0.01,
                "stats": {"history": self.history}}


class RecoveryPoolTests(unittest.TestCase):
    def test_bounded_mixing_remains_exact_and_above_known_rank(self):
        source = decode_candidate(strassen_candidate(2), 2)
        for reduction_every in (0, 11):
            terms, metadata = bounded_mix(source, n=2, rng=random.Random(31),
                                          known_rank=7, record_rank=6, steps=1000,
                                          max_rank=11, reduction_every=reduction_every)
            self.assertEqual(residual(terms, 2), 0)
            self.assertGreater(len(terms), 7)
            self.assertLessEqual(len(terms), 11)
            self.assertEqual(metadata["steps"], 1000)
            self.assertTrue(all(8 <= rank <= 11 for rank in metadata["rank_histogram"]))

    def test_probe_failure_requires_complete_fixed_attempt_budget(self):
        candidate = encode_candidate(naive_terms(2), 2)
        for attempts, expected in ((49999, "incomplete_probe"), (50000, "unknown_within_probe")):
            stub = ProbeStub(candidate, attempts, [{"step": 0, "rank": 8}])
            result = probe_candidate(candidate, stub, known_rank=7, record_rank=6, steps=50000)
            self.assertEqual(result["status"], expected)
            self.assertIsNone(result["first_improvement_step"])
            self.assertEqual(result["initial_rank"], 8)
            self.assertEqual(stub.calls[0]["step_limit"], 50000)

    def test_early_progress_is_recorded_and_known_recovery_not_record(self):
        baseline = set(naive_terms(2))
        a,b,c = min(baseline)
        planted = baseline-{(a,b,c)} | {(a,b,2), (a,b,c^2)}
        start = encode_candidate(planted, 2)
        stub = ProbeStub(encode_candidate(baseline, 2), 13,
                         [{"step": 0, "rank": 9}, {"step": 13, "rank": 8}])
        result = probe_candidate(start, stub, known_rank=8, record_rank=7)
        self.assertEqual(result["status"], "known_bound_recovered")
        self.assertEqual(result["first_improvement_step"], 13)
        self.assertEqual(result["rank_reduction"], 1)
        self.assertIsNone(result["record"])

    def test_probe_preserves_genuine_record_jump(self):
        start = encode_candidate(naive_terms(2), 2)
        winner = strassen_candidate(2)
        stub = ProbeStub(winner, 3, [{"step": 0, "rank": 8}, {"step": 3, "rank": 7}])
        result = probe_candidate(start, stub, known_rank=8, record_rank=7)
        self.assertEqual(result["status"], "verified_record")
        self.assertEqual(result["record"], winner)

    def test_invalid_probe_candidate_fails_before_native_execution(self):
        stub = ProbeStub({}, 0, [])
        with self.assertRaises(ValueError):
            probe_candidate(encode_candidate([(1,1,1)], 2), stub, known_rank=8, record_rank=7)
        self.assertEqual(stub.calls, [])

    def test_immutable_pool_objects_are_content_addressed(self):
        with tempfile.TemporaryDirectory() as directory:
            first = freeze_json(directory, {"task": 1})
            repeated = freeze_json(directory, {"task": 1})
            second = freeze_json(directory, {"task": 2})
            self.assertEqual(first, repeated)
            self.assertNotEqual(first["path"], second["path"])
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
