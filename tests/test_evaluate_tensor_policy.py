"""Mock-native tests: actual dm_env evaluation, no fitting, explicit censoring."""
import unittest

from mmsearch.rl_curriculum import contextual_policy
from mmsearch.rl_search import TinyActorCritic
from mmsearch.search import encode_candidate, naive_terms
from mmsearch.tensor import strassen_candidate
from scripts.evaluate_tensor_policy import (EvaluationBridge, evaluate_episode,
                                            policy_weight_sha256)


def start_candidate():
    terms = set(naive_terms(2))
    a,b,c = min(terms)
    return encode_candidate(terms-{(a,b,c)} | {(a,b,2), (a,b,c^2)}, 2)


class Stub:
    def __init__(self, output, moves=50000):
        self.output, self.moves, self.calls = output, moves, []
    def run(self, candidate, **kwargs):
        self.calls.append(kwargs)
        return {"status": "ok", "best_candidate": self.output, "current_candidate": self.output,
                "attempted_moves": self.moves, "cpu_seconds": 0.01, "candidates": []}


class EvaluationTests(unittest.TestCase):
    def test_known_recovery_uses_actual_dm_env_and_never_fits(self):
        policy = contextual_policy(TinyActorCritic(seed=9))
        before, updates = policy_weight_sha256(policy), policy.updates
        stub = Stub(encode_candidate(naive_terms(2), 2), moves=1300)
        bridge = EvaluationBridge(stub, 50000)
        events = []
        result, record = evaluate_episode(start_candidate(), policy, bridge, arm="learned", seed=27,
                                          known_rank=8, record_rank=7, event_sink=events.append)
        self.assertTrue(result["success"])
        self.assertFalse(result["record_target_reached"])
        self.assertEqual(result["status"], "KNOWN_BOUND_RECOVERED")
        self.assertEqual(result["dm_env_steps"], 1)
        self.assertEqual(events[0]["dm_step_type"], "2")
        self.assertIsNone(record)
        self.assertEqual(stub.calls[0]["step_limit"], 50000)
        self.assertEqual(policy_weight_sha256(policy), before)
        self.assertEqual(policy.updates, updates)

    def test_unsolved_fixed_budget_is_censored_and_random_does_not_fit(self):
        source = start_candidate()
        policy = contextual_policy(TinyActorCritic(seed=4))
        before = policy_weight_sha256(policy)
        bridge = EvaluationBridge(Stub(source), 50000)
        result, record = evaluate_episode(source, policy, bridge, arm="random", seed=27,
                                          known_rank=8, record_rank=7, max_actions=2)
        self.assertEqual(result["status"], "UNKNOWN_WITHIN_LIMITS")
        self.assertFalse(result["success"])
        self.assertEqual(result["attempted_moves"], 100000)
        self.assertEqual(result["stop_reason"], "action_budget")
        self.assertIsNone(record)
        self.assertEqual(policy_weight_sha256(policy), before)

    def test_genuine_record_is_preserved_and_reported_separately(self):
        winner = strassen_candidate(2)
        bridge = EvaluationBridge(Stub(winner, moves=3000), 50000)
        result, record = evaluate_episode(start_candidate(), contextual_policy(), bridge,
                                          arm="frozenwarm", seed=27, known_rank=8, record_rank=7)
        self.assertEqual(record, winner)
        self.assertTrue(result["record_target_reached"])
        self.assertEqual(result["status"], "VERIFIED_RECORD")
        self.assertEqual(result["best_rank"], 7)

    def test_same_seed_same_start_produces_same_initial_native_seed(self):
        source = start_candidate()
        native_seeds = []
        for arm in ("learned", "frozenwarm", "random"):
            stub = Stub(source)
            bridge = EvaluationBridge(stub, 50000)
            evaluate_episode(source, contextual_policy(TinyActorCritic(seed=4)), bridge,
                             arm=arm, seed=27, known_rank=8, record_rank=7, max_actions=1)
            native_seeds.append(stub.calls[0]["seed"])
        self.assertEqual(len(set(native_seeds)), 1)

    def test_invalid_output_fails_independent_exact_check(self):
        bad = encode_candidate([(1,1,1)], 2)
        with self.assertRaises(ValueError):
            evaluate_episode(start_candidate(), contextual_policy(), EvaluationBridge(Stub(bad), 50000),
                             arm="learned", seed=27, known_rank=8, record_rank=7)


if __name__ == "__main__":
    unittest.main()
