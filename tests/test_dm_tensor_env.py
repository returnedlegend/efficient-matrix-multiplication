"""Meaningful dm_env interface, terminal verification, and policy reuse checks."""
import unittest

import numpy as np

from mmsearch.dm_tensor_env import DmTensorEnv
from mmsearch.rl_search import ACTIONS, FEATURES, OperatorController, TinyActorCritic
from mmsearch.search import decode_candidate, naive_terms
from mmsearch.tensor import strassen_candidate
from mmsearch.verify import verify_candidate


class DmTensorEnvTests(unittest.TestCase):
    def test_two_by_two_verified_last_retained_until_explicit_reset(self):
        def factory():
            controller = OperatorController(naive_terms(2),n=2,target_rank=7,seed=0)
            # Controlled exact target transition isolates adapter termination semantics.
            controller.propose = lambda action: set(decode_candidate(strassen_candidate(2),2))
            return controller
        env = DmTensorEnv(factory)
        first = env.reset()
        self.assertTrue(first.first())
        self.assertEqual(first.reward,0.0)
        last = env.step(0)
        self.assertTrue(last.last())
        self.assertEqual(last.discount,0.0)
        self.assertGreater(last.reward,1000)
        self.assertTrue(verify_candidate(env.terminal_artifacts[0]["candidate"])["valid"])
        self.assertEqual(env.last_transition["terminal_candidate_sha256"],env.terminal_artifacts[0]["candidate_sha256"])
        with self.assertRaises(RuntimeError):
            env.step(0)
        env.reset()
        self.assertEqual(len(env.terminal_artifacts),1)
        detached = env.terminal_artifacts
        detached[0]["candidate"]["terms"].clear()
        self.assertEqual(len(env.terminal_artifacts[0]["candidate"]["terms"]),7)

    def test_action_validation_and_detached_observation_spec(self):
        env = DmTensorEnv(lambda: OperatorController(naive_terms(2),n=2,target_rank=1,seed=3))
        with self.assertRaises(RuntimeError):
            env.step(0)
        first = env.reset()
        self.assertEqual(env.action_spec().num_values,len(ACTIONS))
        self.assertEqual(first.observation.shape,(FEATURES,))
        self.assertEqual(first.observation.dtype,np.float64)
        env.observation_spec().validate(first.observation)
        for action in (True,np.bool_(True),1.5,-1,len(ACTIONS),10):
            with self.subTest(action=action),self.assertRaises(ValueError):
                env.step(action)
        first.observation[:] = 999
        transition = env.step(np.int32(5))
        self.assertTrue(transition.mid())
        self.assertTrue(np.isfinite(transition.observation).all())
        self.assertFalse(np.any(transition.observation == 999))
        self.assertTrue(all(type(value) is int for term in env.controller.current for value in term))

    def test_reset_creates_search_state_and_preserves_shared_policy(self):
        policy = TinyActorCritic(seed=12)
        env = DmTensorEnv(lambda: OperatorController(naive_terms(2),n=2,target_rank=1,
                             seed=9,policy=policy,rollout=1))
        env.reset()
        previous = env.controller
        env.step(5)
        self.assertEqual(policy.updates,1)
        state = policy.state()
        first = env.reset()
        self.assertIsNot(env.controller,previous)
        self.assertIs(env.controller.policy,policy)
        self.assertEqual(policy.state(),state)
        self.assertEqual(env.controller.steps,0)
        self.assertEqual(len(env.controller.current),8)
        self.assertEqual(first.reward,0.0)
        self.assertIsNone(env.last_transition)


if __name__ == "__main__":
    unittest.main()
