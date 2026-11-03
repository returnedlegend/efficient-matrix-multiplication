"""Tests for v2 task labels, bounded novelty, actual dm_env, and migration."""
from pathlib import Path
import json
import random
import tempfile
import unittest
from unittest import mock

import numpy as np

from mmsearch.rl_curriculum import (ContextController, ContextDmEnv, NoveltyLedger,
                                    contextual_policy, make_recovery_seed)
from mmsearch.rl_search import ACTIONS, OperatorController, TinyActorCritic
from mmsearch.search import naive_terms, residual


def split_seed():
    baseline = set(naive_terms(2))
    a, b, c = min(baseline)
    d = 2 if c != 2 else 4
    return baseline, baseline-{(a,b,c)} | {(a,b,d), (a,b,c^d)}


class CurriculumTests(unittest.TestCase):
    def test_zero_weight_context_migration_preserves_probabilities_and_adam(self):
        base = TinyActorCritic(seed=7)
        x = np.linspace(-1, 1, 18)
        mask = [True]*len(ACTIONS)
        base.learn([(x, mask, 3, 0.5, 1.0)])
        before = base.forward(x, mask)[0].copy()
        moments = base.m["W"].copy()
        policy = contextual_policy(base)
        np.testing.assert_array_equal(policy.forward(list(x)+[0,1], mask)[0], before)
        np.testing.assert_array_equal(policy.m["W"][:18], moments)
        self.assertFalse(policy.params["W"][18:].any())

    def test_actual_dm_env_known_recovery_omits_record_terminal_bonus(self):
        baseline, planted = split_seed()
        controller = ContextController(planted, n=2, target_rank=8,
                                       task_kind="KNOWN_RECOVERY", seed=3)
        environment = ContextDmEnv(lambda: controller)
        first = environment.reset()
        self.assertTrue(first.first())
        self.assertEqual(first.observation.shape, (20,))
        terminal = environment.step(5)
        self.assertTrue(terminal.last())
        self.assertGreater(terminal.reward, 99)
        self.assertLess(terminal.reward, 101)
        event = environment.last_transition
        self.assertFalse(event["record_target_reached"])
        self.assertEqual(event["task_kind"], "KNOWN_RECOVERY")
        candidate = environment.terminal_artifacts[0]["candidate"]
        self.assertEqual(candidate["metadata"]["status"], "known_recovery_target")
        self.assertEqual(controller.policy.updates, 1)
        self.assertLess(controller.last_learning["loss"], 10)
        self.assertEqual(controller.pending, [])
        self.assertEqual(len(controller.best), len(baseline))
        self.assertEqual(residual(controller.best, 2), 0)

    def test_record_target_keeps_terminal_bonus_and_freezes(self):
        _, planted = split_seed()
        controller = ContextController(planted, n=2, target_rank=8, task_kind="RECORD_SEARCH")
        event = controller.step(5, cost_seconds=0)
        self.assertGreater(event["reward"], 1000)
        self.assertTrue(event["record_target_reached"])
        before = controller.policy.state()
        self.assertEqual(controller.step()["reward"], 0)
        self.assertEqual(controller.policy.state(), before)

    def test_recovery_jump_to_record_is_promoted_and_keeps_terminal_bonus(self):
        from mmsearch.search import decode_candidate
        from mmsearch.tensor import strassen_candidate
        _, planted = split_seed()
        agent = ContextController(planted, n=2, target_rank=8, record_rank=7,
                                  task_kind="KNOWN_RECOVERY")
        agent.propose = lambda _action: decode_candidate(strassen_candidate(2), 2)
        environment = ContextDmEnv(lambda: agent)
        environment.reset()
        terminal = environment.step(0)
        self.assertTrue(terminal.last())
        self.assertGreater(terminal.reward, 1199)
        self.assertTrue(environment.last_transition["record_target_reached"])
        candidate = environment.terminal_artifacts[0]["candidate"]
        self.assertEqual(candidate["metadata"]["status"], "verified_target")
        self.assertEqual(candidate["metadata"]["target_rank"], 7)
        self.assertEqual(candidate["metadata"]["recovery_target_rank"], 8)
        self.assertGreater(agent.last_learning["loss"], 10)
        self.assertEqual(agent.step()["reward"], 0)

    def test_global_novelty_dedup_and_cap_survive_segments_and_episodes(self):
        ledger = NoveltyLedger(cap=0.003)
        agent = ContextController(naive_terms(3), n=3, target_rank=1, ledger=ledger)
        paid = []
        for _ in range(40):
            event = agent.step(7, cost_seconds=0)
            paid.append(event["novelty_bonus"])
            agent.new_segment()
        self.assertAlmostEqual(sum(paid), ledger.paid)
        self.assertLessEqual(ledger.paid, 0.003+1e-12)
        other = ContextController(naive_terms(3), n=3, target_rank=1, ledger=ledger)
        self.assertIs(other.seen, agent.seen)
        event = other.step(7, cost_seconds=0)
        self.assertEqual(event["novelty_bonus"], 0)
        self.assertLess(ledger.paid, 100)

    def test_generated_recovery_tasks_are_exact_strictly_inflated(self):
        for n in (2, 3, 5):
            baseline = set(naive_terms(n))
            terms, provenance = make_recovery_seed([baseline], n, random.Random(83))
            self.assertEqual(residual(terms, n), 0)
            self.assertGreater(len(terms), len(baseline))
            self.assertLessEqual(len(terms), len(baseline)+7)
            self.assertEqual(provenance["kind"], "KNOWN_RECOVERY")

    def test_v2_resume_reproduces_context_rng_optimizer_and_rewards(self):
        agent = ContextController(naive_terms(3), n=3, target_rank=1, seed=13, rollout=5)
        for _ in range(7):
            agent.step(cost_seconds=0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"agent.json"
            agent.save(path)
            other = ContextController.load(path)
            for _ in range(15):
                self.assertEqual(agent.step(cost_seconds=0), other.step(cost_seconds=0))
            self.assertEqual(agent.policy.state(), other.policy.state())
            self.assertEqual(agent.ledger.state(), other.ledger.state())
            agent.save(path)
            other_path = Path(directory)/"other.json"
            other.save(other_path)
            self.assertEqual(json.loads(path.read_text()), json.loads(other_path.read_text()))

    def test_v1_checkpoint_migration_keeps_weights_rng_and_best(self):
        agent = OperatorController(naive_terms(3), n=3, target_rank=1, seed=5)
        agent.step(cost_seconds=0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"v1.json"
            agent.save(path)
            migrated = ContextController.load(path)
        self.assertEqual(migrated.best, agent.best)
        self.assertEqual(migrated.rng.getstate(), agent.rng.getstate())
        self.assertEqual(len(migrated.pending[0][0]), 20)
        np.testing.assert_array_equal(migrated.policy.params["W"][:18], agent.policy.params["W"])

    def test_interrupted_publication_keeps_old_or_final_v2_never_v1(self):
        from mmsearch.rl_search import _write
        agent = ContextController(naive_terms(3), n=3, target_rank=1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"agent.json"
            agent.save(path)
            original = path.read_bytes()
            agent.ledger.paid = 3.0
            with mock.patch("mmsearch.rl_curriculum._write", side_effect=OSError("interrupted before publication")):
                with self.assertRaises(OSError):
                    agent.save(path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(json.loads(path.read_text())["format"], "mmsearch-context-a2c-v2")
            def publish_then_interrupt(destination, value):
                _write(destination, value)
                raise OSError("interrupted after atomic publication")
            with mock.patch("mmsearch.rl_curriculum._write", side_effect=publish_then_interrupt):
                with self.assertRaises(OSError):
                    agent.save(path)
            final = json.loads(path.read_text())
            self.assertEqual(final["format"], "mmsearch-context-a2c-v2")
            self.assertEqual(final["context"]["ledger"]["paid"], 3.0)
            self.assertFalse(list(Path(directory).glob("*.private-*")))

    def test_scheduler_missing_or_mismatched_sidecar_fails_closed(self):
        import hashlib
        from scripts.train_tensor_curriculum import read_schedule
        from mmsearch.rl_search import _write
        agent = ContextController(naive_terms(3), n=3, target_rank=1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"agent.json"
            agent.save(path)
            with self.assertRaisesRegex(ValueError, "requires.*sidecar"):
                read_schedule(path)
            sidecar = path.with_suffix(".schedule.json")
            _write(sidecar, {"format": "mmsearch-curriculum-schedule-v2", "checkpoint_sha256": "bad"})
            with self.assertRaisesRegex(ValueError, "does not match"):
                read_schedule(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            _write(sidecar, {"format": "mmsearch-curriculum-schedule-v2", "checkpoint_sha256": digest})
            self.assertEqual(read_schedule(path)["checkpoint_sha256"], digest)
            agent.ledger.paid = 1.0
            agent.save(path)  # Simulate crash before the new sidecar publication.
            with self.assertRaisesRegex(ValueError, "does not match"):
                read_schedule(path)


if __name__ == "__main__":
    unittest.main()
