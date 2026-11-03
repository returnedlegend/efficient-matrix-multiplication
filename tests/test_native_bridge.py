"""Integration checks for bounded native macro actions and final-drain failures."""
import copy
import json
from pathlib import Path
import random
import tempfile
import unittest

from mmsearch.native_bridge import NativeBridge, canonical_terms, term_set_sha256
from mmsearch.search import encode_candidate, naive_terms
from mmsearch.tensor import strassen_candidate
from mmsearch.verify import verify_candidate


class NativeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.bridge = NativeBridge(self.directory, archive_size=8, archive_every=10)

    def tearDown(self):
        self.tmp.cleanup()

    def test_successful_fast_exit_is_drained_and_winner_frozen(self):
        result = self.bridge.run(strassen_candidate(2), seconds=.01, target_rank=7)
        self.assertEqual(result["attempted_moves"], 0)
        self.assertEqual(result["best_rank"], 7)
        self.assertEqual(result["current_rank"], 7)
        self.assertTrue(verify_candidate(result["best_candidate"])["valid"])
        winner = next((Path(result["run_dir"])/"winners").glob("*.json"))
        self.assertFalse(winner.stat().st_mode & 0o222)
        self.assertTrue(list(winner.parent.parent.glob("verified/*.sha256")))
        self.assertGreaterEqual(result["cpu_seconds"], 0)

    def test_bounded_steps_unique_runs_and_verified_archives(self):
        results = [self.bridge.run(encode_candidate(naive_terms(2),2), "explore", seconds=.1,
                                   target_rank=0, seed=19, step_limit=100) for _ in range(2)]
        self.assertNotEqual(results[0]["run_dir"], results[1]["run_dir"])
        self.assertEqual(results[0]["attempted_moves"], 100)
        self.assertEqual(results[1]["novelty"]["new_candidates"], 0)
        for item in results[0]["candidates"]:
            value = json.loads(Path(item["path"]).read_text())
            self.assertTrue(verify_candidate(value)["valid"])
            self.assertEqual(term_set_sha256(canonical_terms(value)), item["term_set_sha256"])

    def test_reject_inexact_input_and_invalid_limits(self):
        bad = strassen_candidate(2)
        bad["terms"].pop()
        with self.assertRaises(ValueError):
            self.bridge.run(bad, seconds=.01)
        for kwargs in (dict(seconds=6), dict(seconds=0), dict(seed=-1), dict(step_limit=-1)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.bridge.run(strassen_candidate(2), **kwargs)

    def test_canonical_rank_removes_zero_and_duplicate_terms(self):
        candidate = strassen_candidate(2)
        candidate["terms"] += [copy.deepcopy(candidate["terms"][0])]*2
        candidate["terms"].append(dict(u=[0]*4,v=[1]*4,w=[1]*4))
        self.assertEqual(len(canonical_terms(candidate)),7)
        result = self.bridge.run(candidate, seconds=.01,target_rank=7)
        self.assertEqual(result["best_essential_rank"],7)

    def test_noncyclic_action_is_skipped(self):
        from mmsearch.search import _plus, is_cyclic
        terms = set(canonical_terms(strassen_candidate(2)))
        rng = random.Random(31)
        for _ in range(100):
            proposed = _plus(terms,rng,False)
            if proposed is not None:
                terms = proposed
            if not is_cyclic(terms):
                break
        self.assertFalse(is_cyclic(terms))
        candidate = encode_candidate(terms,2)
        result = self.bridge.run(candidate,"cyclic",seconds=.01,target_rank=7)
        self.assertEqual(result["status"],"skipped")

    def test_malformed_final_metadata_is_rejected(self):
        result = self.bridge.run(strassen_candidate(2),seconds=.01,target_rank=7)
        folder = Path(result["run_dir"])
        stats = result["stats"].copy()
        meta = json.loads((folder/"manifest.json").read_text())
        for key, value in (("best_rank",99),("steps",True),("seed",123),("exact",False),("seconds_budget",float("nan"))):
            corrupt = dict(stats,**{key:value})
            with self.subTest(key=key),self.assertRaises(ValueError):
                NativeBridge._validate_stats(corrupt,meta)

    def test_corrupt_final_best_is_rejected(self):
        # A tiny executable simulates a native worker which lies after valid stats.
        worker = self.directory/"fake-worker"
        real = str(self.bridge.binary)
        worker.write_text("#!/usr/bin/env python3\nimport pathlib,subprocess,sys\n"
                          f"r=subprocess.run([{real!r},*sys.argv[1:]])\n"
                          "p=pathlib.Path(sys.argv[sys.argv.index('--output')+1]+'.best.txt')\n"
                          "p.write_text('1 1 1\\n')\nsys.exit(r.returncode)\n")
        worker.chmod(0o755)
        bridge = NativeBridge(self.directory/"fake",binary=worker)
        with self.assertRaises((ValueError,RuntimeError)):
            bridge.run(strassen_candidate(2),seconds=.01,target_rank=7)
        self.assertFalse(list((self.directory/"fake").glob("runs/*/winners/*.json")))


if __name__ == "__main__":
    unittest.main()
