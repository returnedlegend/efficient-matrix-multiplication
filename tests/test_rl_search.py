"""Exactness, policy gradients, bounded rewards, and reproducible RL resume."""
import json
import contextlib
import io
from pathlib import Path
import random
import tempfile
import unittest

import numpy as np

from mmsearch.rl_search import (ACTIONS, FEATURES, OperatorController, TinyActorCritic,
                                canonical_terms, gl_move)
from mmsearch.search import decode_candidate, encode_candidate, naive_terms, residual
from mmsearch.verify import verify_candidate


class ActorCriticTests(unittest.TestCase):
    def test_manual_gradient_matches_finite_difference(self):
        policy = TinyActorCritic(seed=4, hidden=4)
        mask = [True]*len(ACTIONS)
        mask[-1] = False
        samples = [(np.linspace(-0.5, 0.8, FEATURES), mask, 2, 0.7, -0.3),
                   (np.linspace(0.2, -0.3, FEATURES), mask, 4, -0.4, 0.8)]
        _, gradients = policy.loss_grad(samples)
        for key, value in policy.params.items():
            for index in np.ndindex(value.shape):
                original = value[index]
                value[index] = original+1e-6
                plus = policy.loss_grad(samples)[0]
                value[index] = original-1e-6
                minus = policy.loss_grad(samples)[0]
                value[index] = original
                self.assertAlmostEqual(gradients[key][index], (plus-minus)/2e-6, places=7)

    def test_policy_is_state_conditioned_and_training_changes_actor(self):
        policy = TinyActorCritic(seed=7)
        mask = [True]*len(ACTIONS)
        x = np.linspace(-1, 1, FEATURES)
        p = policy.forward(x, mask)[0]
        q = policy.forward(-x, mask)[0]
        self.assertGreater(np.max(np.abs(p-q)), 1e-4)
        for _ in range(5):
            policy.learn([(x, mask, 3, 0.5, 1.0)])
        self.assertGreater(policy.forward(x, mask)[0][3], p[3])
        self.assertEqual(policy.updates, 5)

    def test_checkpoint_restores_rng_adam_and_partial_rollout_exactly(self):
        agent = OperatorController(naive_terms(3), n=3, target_rank=1, seed=41, rollout=7)
        for _ in range(9):
            agent.step(cost_seconds=0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"agent.json"
            agent.save(path)
            other = OperatorController.load(path)
            for _ in range(17):
                self.assertEqual(agent.step(cost_seconds=0), other.step(cost_seconds=0))
            agent.save(path)
            second = Path(directory)/"other.json"
            other.save(second)
            self.assertEqual(json.loads(path.read_text()), json.loads(second.read_text()))

    def test_every_operator_is_exact_on_small_and_larger_tasks(self):
        for n in (2, 3, 5):
            agent = OperatorController(naive_terms(n), n=n, target_rank=1, seed=53)
            # Each operator gets the original cyclic seed before its attempt.
            original = agent.current.copy()
            for action in range(10):
                agent.current = original.copy()
                result = agent.propose(action)
                self.assertEqual(residual(result, n), 0, (n, ACTIONS[action]))
            rng = random.Random(9)
            current = original
            for _ in range(40):
                current = gl_move(current, n, rng)
                self.assertEqual(residual(current, n), 0)
                self.assertEqual(len(current), len(original))

    def test_zero_duplicate_products_cancel_before_counting(self):
        terms = naive_terms(2)+[(1, 1, 1), (1, 1, 1), (0, 3, 5)]
        self.assertEqual(canonical_terms(terms, 2), set(naive_terms(2)))
        agent = OperatorController(terms, n=2, target_rank=7)
        self.assertEqual(len(agent.best), 8)

    def test_invalid_initial_and_transition_are_rejected(self):
        with self.assertRaises(ValueError):
            OperatorController([(1, 1, 1)], n=2)
        agent = OperatorController(naive_terms(2), n=2, target_rank=1)
        before = agent.current.copy()
        agent.propose = lambda _action: {(1, 1, 1)}
        with self.assertRaises(ValueError):
            agent.step(0, cost_seconds=0)
        self.assertEqual(agent.current, before)
        self.assertEqual(agent.steps, 0)
        self.assertEqual(agent.total_reward, 0)

    def test_planted_reduction_reward_cannot_be_farmed(self):
        baseline = set(naive_terms(2))
        a, b, c = next(iter(sorted(baseline)))
        d = 2 if c != 2 else 4
        planted = baseline-{(a, b, c)} | {(a, b, d), (a, b, c^d)}
        agent = OperatorController(planted, n=2, target_rank=1, seed=2)
        first = agent.step(5, cost_seconds=0)
        self.assertEqual(first["improvement"], 1)
        self.assertGreater(first["reward"], 99)
        agent.propose = lambda _action: planted
        excursion = agent.step(0, cost_seconds=0)
        agent.propose = lambda _action: baseline
        revisit = agent.step(0, cost_seconds=0)
        self.assertEqual(revisit["improvement"], 0)
        self.assertLess(excursion["reward"]+revisit["reward"], 0.01)
        self.assertLessEqual(agent.novelty_paid, 0.25)
        # Force many exact distinct basis states; global novelty cap remains
        # smaller than 1% of one verified-product improvement reward.
        agent.propose = lambda _action: gl_move(agent.current, 2, agent.rng)
        for _ in range(350):
            agent.step(0, cost_seconds=0)
        self.assertLessEqual(agent.novelty_paid, 0.25+1e-12)
        self.assertGreater(first["reward"], 100*agent.novelty_paid)

    def test_naive_two_by_two_reaches_seven_and_freezes(self):
        agent = OperatorController(naive_terms(2), n=2, target_rank=7, seed=0)
        before = agent.policy.params["P"].copy()
        for _ in range(100):
            event = agent.step(cost_seconds=0)
            if agent.terminal:
                break
        self.assertTrue(agent.terminal)
        self.assertLessEqual(len(agent.best), 7)
        self.assertGreater(event["reward"], 1000)
        self.assertTrue(verify_candidate(agent.candidate())["valid"])
        self.assertGreater(np.max(np.abs(before-agent.policy.params["P"])), 0)
        steps, reward, best = agent.steps, agent.total_reward, agent.best.copy()
        self.assertEqual(agent.step()["reward"], 0)
        self.assertEqual((agent.steps, agent.total_reward, agent.best), (steps, reward, best))

    def test_native_results_are_verified_and_rank_reward_dominates(self):
        from mmsearch.tensor import strassen_candidate
        class Stub:
            def run(self, candidate, **kwargs):
                return {"status": "ok", "cpu_seconds": 0.1,
                        "best_candidate": strassen_candidate(2), "current_candidate": candidate}
        agent = OperatorController(naive_terms(2), n=2, target_rank=7, native_bridge=Stub())
        self.assertTrue(agent.mask()[10])
        event = agent.step(10)
        self.assertTrue(event["terminal"])
        self.assertGreater(event["reward"], 1000)
        self.assertEqual(len(decode_candidate(agent.candidate(), 2)), 7)

    def test_native_only_masks_all_python_actions(self):
        agent = OperatorController(naive_terms(2), n=2, target_rank=1,
                                   native_bridge=object(), native_only=True)
        self.assertEqual(agent.mask()[:10], [False]*10)
        self.assertEqual(sum(agent.mask()), 4)
        agent.current = gl_move(agent.current, 2, random.Random(8))
        # Use an unrestricted exact flip if this basis happens to stay cyclic.
        from mmsearch.search import _plus
        agent.current = _plus(agent.current, random.Random(3), False)
        self.assertEqual(agent.mask()[:10], [False]*10)
        self.assertEqual(sum(agent.mask()), 3)

    def test_native_archive_cli_rejects_unbounded_values(self):
        from scripts.train_tensor_agent import main
        for value in ("0", "-1", "65", "1000000"):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(["--native-archive-size", value, "--seconds", "0"])
            self.assertEqual(error.exception.code, 2)

    def test_frozen_and_random_controls_do_not_update_parameters(self):
        for control in ("policy", "random"):
            agent = OperatorController(naive_terms(3), n=3, target_rank=1, seed=3,
                                       train=False, control=control, rollout=2)
            before = agent.policy.state()
            for _ in range(5):
                agent.step(cost_seconds=0)
            self.assertEqual(agent.policy.state(), before)


if __name__ == "__main__":
    unittest.main()
