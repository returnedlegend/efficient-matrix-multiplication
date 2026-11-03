"""V3 immutable splits, fixed recovery budgets, sampler quotas, and resume."""
import hashlib
import json
from pathlib import Path
import random
import tempfile
import unittest
import contextlib
import io

from mmsearch.recovery_pool import bounded_mix, freeze_json
from mmsearch.rl_pool_curriculum import (FixedStepBridge, HardRecoveryPool, PoolRecordController,
                                         combine_raw_pools, freeze_pool)
from mmsearch.rl_search import _write, term_hash
from mmsearch.search import decode_candidate, encode_candidate, naive_terms
from mmsearch.tensor import strassen_candidate


def raw_fixture(path, count=12):
    entries = []
    source = decode_candidate(strassen_candidate(2), 2)
    for index in range(count):
        terms, _ = bounded_mix(source, n=2, rng=random.Random(941+index), known_rank=7,
                               record_rank=6, max_rank=10, steps=100)
        candidate = encode_candidate(terms, 2)
        hard = index < max(1, count-3)
        entries.append({"trial": index, "status": "retained_unknown" if hard else "retained_delayed_recovery",
                        "term_hash": term_hash(terms), "mix_seed": index,
                        "probes": [{"profile": "exploit", "status": "unknown_within_probe" if hard else "known_bound_recovered",
                                    "step_budget": 50000, "attempted_moves": 50000 if hard else 5000,
                                    "first_improvement_step": None if hard else 2000}],
                        **freeze_json(path/"tasks", candidate)})
    _write(path/"manifest.json", {"entries": entries, "sources": [], "attempted_candidates": count, "config": {
        "dimension": 2, "known_rank": 7, "record_rank": 6, "probe_steps": 50000, "max_extra": 3}})


class PoolCurriculumTests(unittest.TestCase):
    def test_fixed_step_wrapper_limits_recovery_but_preserves_record_bridge(self):
        class Stub:
            def __init__(self): self.calls = []
            def run(self, candidate, **kwargs):
                self.calls.append(kwargs)
                return kwargs
        original = Stub()
        recovery = FixedStepBridge(original, 50000)
        result = recovery.run({}, action="explore", seconds=2, target_rank=93, step_limit=10**12)
        self.assertEqual(result["step_limit"], 50000)
        self.assertEqual(original.run({}, action="explore", seconds=2)["seconds"], 2)
        self.assertNotIn("step_limit", original.calls[-1])

    def test_recovery_wrapper_preserves_separate_bridge_identity(self):
        class Stub:
            def __init__(self, archive_size, identity):
                self.archive_size, self.binary_sha256 = archive_size, identity
            def run(self, candidate, **kwargs): return kwargs
        record, raw_recovery = Stub(8, "record-sha"), Stub(1, "recovery-sha")
        recovery = FixedStepBridge(raw_recovery, 50000)
        self.assertIs(recovery.bridge, raw_recovery)
        self.assertEqual(recovery.archive_size, 1)
        self.assertEqual(recovery.binary_sha256, "recovery-sha")
        recovery.run({}, seconds=2)
        self.assertEqual(record.archive_size, 8)
        self.assertEqual(record.binary_sha256, "record-sha")

    def test_recovery_archive_cli_rejects_out_of_bounds_before_work(self):
        from scripts.train_pool_tensor_agent import main
        required = ["--resume", "/tmp/unused", "--cpu", "2", "--checkpoint", "/tmp/no-write",
                    "--output", "/tmp/no-write-best", "--events", "/tmp/no-write-events",
                    "--native-dir", "/tmp/no-write-native", "--recovery-pool", "/tmp/no-write-pool"]
        for value in ("0", "-1", "9", "10000"):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(required+["--recovery-archive-size", value])
            self.assertEqual(error.exception.code, 2)

    def test_predeclared_deterministic_split_has_minimum_holdout_and_no_leakage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_fixture(root/"raw")
            first = freeze_pool(root/"raw", root/"v1")
            second = freeze_pool(root/"raw", root/"v2")
            self.assertEqual(first["split"], second["split"])
            self.assertGreaterEqual(len(first["split"]["heldout"]), 2)
            hard_keys = {item["term_hash"] for item in first["entries"] if item["task_bucket"] == "hard_unknown"}
            self.assertGreaterEqual(len(set(first["split"]["heldout"]) & hard_keys), 1)
            self.assertFalse(set(first["split"]["train"]) & set(first["split"]["heldout"]))
            pool = HardRecoveryPool(root/"v1")
            delayed = 0
            rng = random.Random(1)
            for episode in range(50):
                key, _, entry = pool.choose(rng, episode_index=episode, delayed_used=delayed)
                self.assertNotIn(key, pool.heldout)
                delayed += entry["task_bucket"] == "delayed_control"
                self.assertLessEqual(delayed, (episode+1)//5)

    def test_ten_hard_tasks_reserve_at_least_two_hard_heldout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_fixture(root/"raw", 13)
            value = freeze_pool(root/"raw", root/"version")
            hard_keys = {item["term_hash"] for item in value["entries"] if item["task_bucket"] == "hard_unknown"}
            self.assertGreaterEqual(len(hard_keys), 10)
            self.assertGreaterEqual(len(set(value["split"]["heldout"]) & hard_keys), 2)
            self.assertGreaterEqual(len(set(value["split"]["train"]) & hard_keys), 1)

    def test_five_hard_tasks_prefer_two_hard_heldout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_fixture(root/"raw", 8)
            value = freeze_pool(root/"raw", root/"version")
            hard_keys = {item["term_hash"] for item in value["entries"] if item["task_bucket"] == "hard_unknown"}
            self.assertEqual(len(hard_keys), 5)
            self.assertEqual(len(set(value["split"]["heldout"]) & hard_keys), 2)
            self.assertEqual(len(set(value["split"]["train"]) & hard_keys), 3)

    def test_small_pool_preserves_one_hard_training_task_and_labels_small(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_fixture(root/"raw", 3)
            value = freeze_pool(root/"raw", root/"version")
            pool = HardRecoveryPool(root/"version")
            self.assertTrue(value["small_pool"])
            self.assertGreaterEqual(len(pool.training["hard_unknown"]), 1)

    def test_snapshot_checksum_and_version_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_fixture(root/"raw", 3)
            freeze_pool(root/"raw", root/"version")
            with self.assertRaisesRegex(ValueError, "version changed"):
                HardRecoveryPool(root/"version", expected_sha256="bad")
            value = json.loads((root/"version/manifest.json").read_text())
            task = root/"version"/value["entries"][0]["path"]
            task.chmod(0o644)
            task.write_text(task.read_text()+" ")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                HardRecoveryPool(root/"version")

    def test_combined_source_retains_trials_and_freezes_new_deduplicated_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_fixture(root/"wide", 12)
            raw_fixture(root/"tight", 3)
            combined = combine_raw_pools([root/"wide", root/"tight"], root/"combined")
            self.assertEqual(len(combined["entries"]), 15)
            self.assertEqual(len(combined["source_pools"]), 2)
            self.assertTrue(all("source_pool_sha256" in x for x in combined["entries"]))
            frozen = freeze_pool(root/"combined", root/"version")
            self.assertLessEqual(len(frozen["entries"]), 12)
            self.assertTrue(HardRecoveryPool(root/"version").training["hard_unknown"])

    def test_pool_controller_atomic_checkpoint_retains_censoring_identity(self):
        context = {"pool_sha256": "example", "recovery_step_limit": 50000}
        agent = PoolRecordController(naive_terms(3), n=3, target_rank=1, seed=11,
                                     pool_context=context)
        for _ in range(3): agent.step(cost_seconds=0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"agent.json"
            agent.save(path)
            restored = PoolRecordController.load(path)
            self.assertEqual(restored.pool_context, context)
            self.assertEqual(restored.candidate()["metadata"]["pool_curriculum"], context)
            for _ in range(10):
                self.assertEqual(agent.step(cost_seconds=0), restored.step(cost_seconds=0))


if __name__ == "__main__":
    unittest.main()
