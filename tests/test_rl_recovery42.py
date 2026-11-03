"""Source-heldout isolation, deterministic declarations, and honest screening."""
import json
from pathlib import Path
import random
import tempfile
import unittest

from mmsearch.rl_recovery42 import source_partition, freeze_source_pool42, SourceRecoveryPool42
from mmsearch.rl_search import _write
from tests.test_rl_pool_curriculum import raw_fixture


def grouped_fixture(root):
    raw_fixture(root, count=28)
    value = json.loads((root/"manifest.json").read_text())
    partition = source_partition([f"source{index:02}" for index in range(16)])
    for index, entry in enumerate(value["entries"]):
        source = (partition["train"] if index % 3 else partition["heldout"])[index % (12 if index % 3 else 4)]
        entry["mixing"] = {"source_term_hash": source}
        template = entry["probes"][0]
        entry["probes"] = [dict(template, profile=profile) for profile in ("exploit", "explore", "long_walk")]
    _write(root/"manifest.json", value)
    return partition


class Recovery42Tests(unittest.TestCase):
    def test_partition_is_before_outcomes_and_independent_of_source_order(self):
        keys = [f"source{i}" for i in range(16)]
        first = source_partition(keys, ["old1", "old2"])
        self.assertEqual(first, source_partition(keys[::-1], ["old2", "old1"]))
        self.assertEqual(len(first["heldout"]), 4)
        self.assertNotIn("old1", first["heldout"])
        self.assertFalse(set(first["train"]) & set(first["heldout"]))
        with self.assertRaises(ValueError): source_partition(keys, [keys[0]])

    def test_frozen_group_split_and_sampler_never_use_heldout_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            partition = grouped_fixture(root/"raw")
            freeze_source_pool42(root/"raw", root/"frozen", partition)
            pool = SourceRecoveryPool42(root/"frozen")
            delayed = 0
            rng = random.Random(11)
            for episode in range(50):
                key, _, entry = pool.choose(rng, episode_index=episode, delayed_used=delayed)
                delayed += entry["task_bucket"] == "delayed_control"
                self.assertIn(entry["v42_source_hash"], partition["train"])
                self.assertNotIn(key, pool.heldout)
            path = root/"frozen/manifest.json"
            value = json.loads(path.read_text())
            key = value["split"]["train"][0]
            value["split"]["train"].remove(key)
            value["split"]["heldout"].append(key)
            _write(path, value)
            with self.assertRaisesRegex(ValueError, "leaks"): SourceRecoveryPool42(root/"frozen")

    def test_other_profile_easy_tasks_are_excluded_and_not_enough_data_never_publishes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            partition = grouped_fixture(root/"raw")
            path = root/"raw/manifest.json"
            value = json.loads(path.read_text())
            first = value["entries"][0]
            first["probes"][1].update(status="known_bound_recovered", attempted_moves=1, first_improvement_step=1)
            _write(path, value)
            frozen = freeze_source_pool42(root/"raw", root/"good", partition)
            self.assertNotIn(first["term_hash"], [entry["term_hash"] for entry in frozen["entries"]])
            self.assertTrue(frozen["v42_additional_screen_excluded"])
            with self.assertRaisesRegex(ValueError, "insufficient"):
                freeze_source_pool42(root/"raw", root/"notpublished", partition, min_train_hard=999)
            self.assertFalse((root/"notpublished").exists())


if __name__ == "__main__":
    unittest.main()

class Evaluation42Tests(unittest.TestCase):
    def test_source_equal_weighting_does_not_count_repeated_seeds_as_sources(self):
        from scripts.train_evaluate42 import source_comparisons
        rows = []
        for source, count, learned, warm in (("A", 100, True, False), ("B", 1, False, True)):
            for _ in range(count):
                for arm, success in (("learned", learned), ("frozenwarm", warm), ("random", False)):
                    rows.append({"source_hash": source, "arm": arm, "success": success})
        result = source_comparisons(rows)
        self.assertEqual(result["source_count"], 2)
        self.assertEqual(result["comparisons"]["learned_vs_frozenwarm"]["source_equal_weight_rate_difference"], 0)
        self.assertEqual(result["comparisons"]["learned_vs_random"]["source_equal_weight_rate_difference"], 0.5)
