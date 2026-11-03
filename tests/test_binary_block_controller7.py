import json
import unittest
from unittest.mock import patch

from mmsearch import binary_block_controller7 as subject
from mmsearch.binary_block_descent7 import HARD_DEADLINE, scalar_loss
from tests.test_binary_block_descent7 import strassen


@patch("mmsearch.binary_block_descent7.time.time", return_value=HARD_DEADLINE - 60)
class ControllerTests(unittest.TestCase):
    def test_incorrect_low_rank_never_receives_terminal_credit(self, _clock):
        reward = subject.exact_reward(8, 1, 64, True, product_count=1, source_product_count=8)
        self.assertEqual(reward["terminal"], 0)
        self.assertEqual(reward["verified_product_benefit"], 0)
        with self.assertRaises(ValueError):
            subject.exact_reward(8, 1, 64, True, verified_exact=True, product_count=1, source_product_count=8)
        exact = subject.exact_reward(1, 0, 64, True, verified_exact=True, product_count=7, source_product_count=8)
        self.assertEqual(exact["verified_product_benefit"], 1)
        self.assertGreater(exact["terminal"], 0)

    def test_policy_checkpoint_rng_and_frozen_selection(self, _clock):
        policy = subject.Bandit(71)
        for i in range(30):
            action = policy.select("L0:S0:A0", training=True)
            policy.update("L0:S0:A0", action, i - 5)
        restored = subject.Bandit.restore(json.loads(json.dumps(policy.checkpoint())))
        self.assertEqual(policy.checkpoint(), restored.checkpoint())
        for _ in range(20):
            self.assertEqual(policy.select("L0:S0:A0", True), restored.select("L0:S0:A0", True))
        before = json.dumps(policy.checkpoint(), sort_keys=True)
        for _ in range(10):
            policy.select("L0:S0:A0", training=False)
        self.assertEqual(before, json.dumps(policy.checkpoint(), sort_keys=True))
        broken = policy.checkpoint(); broken["updates"] += 1
        with self.assertRaises(ValueError):subject.Bandit.restore(broken)

    def test_fixed_rank_until_zero_and_exact_reward_only_after_scalar_check(self, _clock):
        core, shape, factors = strassen()
        factors = [list(t) for t in factors]; factors[0][0] ^= 1
        result = subject.run_controller(core, shape, 7, initial_factors=factors,
                                       source_product_count=8, mode="fixed", max_actions=2)
        self.assertEqual(result["status"], "RAW_EXACT_COMPACT")
        self.assertEqual(scalar_loss(core, shape, result["best_factors"]), 0)
        self.assertGreater(result["terminal_reward_total"], 0)
        self.assertTrue(all(entry["fixed_rank"] == 7 for entry in result["history"]))
        self.assertFalse(result["publication_eligible"])

    def test_already_known_zero_observation_has_no_controller_credit(self, _clock):
        core, shape, factors = strassen()
        result = subject.run_controller(core, shape, 7, initial_factors=factors,
                                       source_product_count=8, max_actions=2)
        self.assertEqual(result["status"], "RAW_EXACT_COMPACT")
        self.assertEqual(result["terminal_reward_total"], 0)
        self.assertEqual(result["actions"], 0)

    def test_bad_approximations_timeout_and_failed_actions_remain_unknown(self, _clock):
        diag = [1, 0, 0, 0, 0, 0, 0, 1]
        policy = subject.Bandit(8)
        result = subject.run_controller(diag, [2, 2, 2], 1, policy=policy, mode="bandit",
            training=True, source_product_count=2, max_actions=12)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertGreater(result["best_loss"], 0)
        self.assertEqual(result["terminal_reward_total"], 0)
        self.assertTrue(all(entry["reward"]["terminal"] == 0 for entry in result["history"]))
        timed = subject.run_controller(diag, [2, 2, 2], 1, timeout_seconds=0)
        self.assertEqual(timed["status"], "UNKNOWN")


if __name__ == "__main__":unittest.main()
