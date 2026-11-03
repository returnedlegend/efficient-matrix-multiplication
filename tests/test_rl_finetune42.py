"""Continuation, phase scheduling, useful policy signal, and exact negative guards."""
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import tempfile
import unittest
from unittest import mock

import numpy as np

from mmsearch.rl_curriculum import ContextController, contextual_policy
from mmsearch.rl_finetune42 import (Finetune42Controller, phase_clock, phase_usage, recovery_due)
from mmsearch.rl_restart_curriculum import RecordSeeds, RestartRecordController
from mmsearch.rl_search import ACTIONS, TinyActorCritic, _write, term_hash
from mmsearch.search import encode_candidate, naive_terms, decode_candidate
from mmsearch.verify import verify_candidate
from scripts.train_finetune42 import read_schedule, main
from tests.test_rl_restart_curriculum import seeds_fixture

ROOT = Path(__file__).resolve().parents[1]


def context(clock=None):
    return {"clock": clock or phase_clock(0, 0), "curriculum_sha256": "test-frozen"}


def schedule(path, agent, **extra):
    value = {"format": "mmsearch-finetune-schedule-v42",
             "checkpoint_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
             "restart_context": copy.deepcopy(agent.restart_context),
             "finetune42": copy.deepcopy(agent.finetune_context), "record_cpu": 0, "recovery_cpu": 0}
    value.update(extra)
    _write(path.with_suffix(".schedule.json"), value)


class Finetune42Tests(unittest.TestCase):
    def test_phase_uses_new_cpu_and_does_not_inherit_old_twenty_percent_debt(self):
        clock = phase_clock(1000, 250, fraction=0.05, episode_origin=200, delayed_origin=40)
        self.assertFalse(recovery_due(clock, 1000, 250))
        self.assertTrue(recovery_due(clock, 1002, 250))
        self.assertFalse(recovery_due(clock, 1002, 250.2))
        self.assertTrue(recovery_due(clock, 1005, 250.2))
        self.assertEqual(phase_usage(clock, 1005, 250.2)[0], 5)
        with self.assertRaises(ValueError): phase_usage(clock, 999, 250)
        with self.assertRaises(ValueError): phase_clock(float("nan"), 0)

    def test_real_v4_migration_preserves_optimizer_rng_pending_and_exact_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seeds, _ = seeds_fixture(root)
            old = RestartRecordController(naive_terms(2), n=2, target_rank=1, seed=31,
                                          rollout=5, pool_context={"old_pool": "frozen"})
            old.bind_restarts(seeds, interval=300, record_cpu=0)
            old.restart_if_due(0)
            for _ in range(7): old.step(cost_seconds=0)
            path = root/"old.json"
            old.save(path)
            original = path.read_bytes()
            new = Finetune42Controller.load(path)
            self.assertEqual(original, path.read_bytes())
            for name in ("current", "best", "archive", "history", "action_counts", "steps", "total_reward"):
                self.assertEqual(getattr(new, name), getattr(old, name))
            self.assertEqual(new.policy.state(), old.policy.state())
            self.assertEqual(new.rng.getstate(), old.rng.getstate())
            self.assertEqual(new.ledger.state(), old.ledger.state())
            self.assertEqual(new.pending, json.loads(original)["pending"])
            new.finetune_context = context()
            checkpoint = root/"v42.json"
            new.save(checkpoint)
            schedule(checkpoint, new)
            read_schedule(checkpoint)
            restored = Finetune42Controller.load(checkpoint)
            restored.bind_restarts(seeds, interval=300, record_cpu=0)
            for _ in range(17):
                self.assertEqual(new.step(cost_seconds=0), restored.step(cost_seconds=0))
            self.assertEqual(new.policy.state(), restored.policy.state())
            self.assertEqual(new.rng.getstate(), restored.rng.getstate())
            self.assertEqual(new.current, restored.current)

    def test_twenty_feature_gradient_and_positive_negative_signal(self):
        policy = contextual_policy(TinyActorCritic(seed=4, hidden=3, entropy=0))
        x = np.linspace(-0.5, 0.8, 20)
        mask = [True]*len(ACTIONS)
        samples = [(x, mask, 10, 0.7, -0.3), (-x, mask, 11, -0.4, 0.8)]
        _, gradients = policy.loss_grad(samples)
        for key, values in policy.params.items():
            for index in np.ndindex(values.shape):
                original = values[index]
                values[index] = original+1e-6
                plus = policy.loss_grad(samples)[0]
                values[index] = original-1e-6
                minus = policy.loss_grad(samples)[0]
                values[index] = original
                self.assertAlmostEqual(gradients[key][index], (plus-minus)/2e-6, places=7)
        positive = contextual_policy(TinyActorCritic(seed=11, entropy=0))
        negative = contextual_policy(TinyActorCritic(seed=11, entropy=0))
        before = positive.forward(x, mask)[0][10]
        positive.learn([(x, mask, 10, positive.forward(x, mask)[1], 1.0)])
        negative.learn([(x, mask, 10, negative.forward(x, mask)[1], -1.0)])
        self.assertGreater(positive.forward(x, mask)[0][10], before)
        self.assertLess(negative.forward(x, mask)[0][10], before)

    def test_known_recovery_has_rank_signal_without_record_bonus_and_cannot_farm(self):
        base = set(naive_terms(2))
        a, b, c = min(base)
        d = 2 if c != 2 else 4
        planted = base-{(a, b, c)} | {(a, b, d), (a, b, c^d)}
        policy = contextual_policy(TinyActorCritic(seed=8, entropy=0))
        agent = ContextController(planted, n=2, target_rank=8, record_rank=7,
                                  task_kind="KNOWN_RECOVERY", policy=policy, seed=9)
        before = copy.deepcopy(policy.state())
        event = agent.step(5, cost_seconds=0)
        self.assertTrue(event["terminal"])
        self.assertFalse(event["record_target_reached"])
        self.assertGreater(event["reward"], 99)
        self.assertLess(event["reward"], 101)
        self.assertNotEqual(before["params"], policy.state()["params"])
        frozen = policy.state()
        self.assertEqual(agent.step(5, cost_seconds=0)["reward"], 0)
        self.assertEqual(policy.state(), frozen)

    def test_full_tensor_negative_guard_rejects_fake_rank92_before_reward_or_learning(self):
        path = ROOT/"artifacts/km93_f2.json"
        if not path.exists(): self.skipTest("verified rank93 fixture unavailable")
        seed = json.loads(path.read_text())
        terms = set(decode_candidate(seed, 5))
        bad = encode_candidate(terms-{min(terms)}, 5)
        self.assertFalse(verify_candidate(bad, random_trials=0)["valid"])
        class BadBridge:
            def run(self, *_args, **_kwargs):
                return {"status": "ok", "best_candidate": bad, "current_candidate": bad}
        agent = Finetune42Controller(terms, n=5, target_rank=92, native_bridge=BadBridge(),
                                     native_only=True, finetune_context=context())
        before = agent.policy.state()
        with self.assertRaises(ValueError): agent.step(10, cost_seconds=0)
        self.assertEqual(agent.steps, 0)
        self.assertEqual(agent.total_reward, 0)
        self.assertFalse(agent.terminal)
        self.assertEqual(agent.current, terms)
        self.assertEqual(before, agent.policy.state())
        bad["terms"][0]["u"][0] = 0.0
        with self.assertRaises(ValueError): decode_candidate(bad, 5)

    def test_schedule_phase_hash_and_code_tampering_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seeds, _ = seeds_fixture(root)
            agent = Finetune42Controller(naive_terms(2), n=2, target_rank=1, finetune_context=context())
            agent.bind_restarts(seeds, interval=300, record_cpu=0)
            path = root/"v42.json"
            agent.save(path)
            with self.assertRaisesRegex(ValueError, "sidecar"): read_schedule(path)
            schedule(path, agent)
            value = json.loads(path.with_suffix(".schedule.json").read_text())
            value["finetune42"]["clock"]["phase_id"] = "torn"
            _write(path.with_suffix(".schedule.json"), value)
            with self.assertRaisesRegex(ValueError, "phase"): read_schedule(path)
            schedule(path, agent)
            value = json.loads(path.read_text())
            value["code_hashes"]["rl_finetune42.py"] = "modified"
            _write(path, value)
            with self.assertRaisesRegex(ValueError, "source identity"): Finetune42Controller.load(path)
            with self.assertRaisesRegex(ValueError, "does not match"): read_schedule(path)

    def test_sigterm_during_bounded_action_writes_coherent_resumable_checkpoint(self):
        fixture = ROOT/"artifacts/km93_f2.json"
        if not fixture.exists(): self.skipTest("verified rank93 fixture unavailable")
        terms = decode_candidate(json.loads(fixture.read_text()), 5)
        class Bridge:
            def __init__(self, output_dir=None, *, archive_size=8, **_kwargs):
                self.output_dir, self.archive_size = output_dir, archive_size
                self.binary_sha256, self.source_sha256 = "testbinary", "testsource"
                self.binary, self.code_hashes = "/test/no-execution", {}
            def run(self, candidate, **_kwargs):
                os.kill(os.getpid(), signal.SIGTERM)
                return {"status": "ok", "best_candidate": candidate, "current_candidate": candidate,
                        "attempted_moves": 50000, "cpu_seconds": 0.01}
        class Pool:
            def __init__(self, directory):
                self.sha256, self.directory, self.heldout = "test-frozen", Path(directory), ["testheldout"]
                self.manifest = {"config": {"dimension": 5, "known_rank": 93, "probe_steps": 50000}, "small_pool": True}
        previous = {sig:signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        affinity = os.sched_getaffinity(0)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                seeds = RecordSeeds([fixture])
                old = RestartRecordController(terms, n=5, target_rank=92, native_bridge=Bridge(),
                                              native_only=True, pool_context={"old": "pool"})
                old.bind_restarts(seeds, interval=300, record_cpu=100)
                old.restart_if_due(100)
                old_path = root/"old.json"
                old.save(old_path)
                _write(old_path.with_suffix(".schedule.json"), {
                    "format": "mmsearch-restart-curriculum-schedule-v4",
                    "checkpoint_sha256": hashlib.sha256(old_path.read_bytes()).hexdigest(),
                    "restart_context": old.restart_context, "pool_context": old.pool_context,
                    "rng": random.Random(9).getstate(), "record_cpu": 100, "recovery_cpu": 25,
                    "recovery_episodes": 20, "recovery_successes": 10, "delayed_used": 4})
                out = root/"new/checkpoint.json"
                argv = ["--resume", str(old_path), "--cpu", str(min(affinity)), "--seconds", "60",
                        "--record-seed", str(fixture), "--recovery-pool", str(root/"pool"),
                        "--checkpoint", str(out), "--output", str(root/"new/best.json"),
                        "--events", str(root/"new/events.jsonl"), "--native-dir", str(root/"new/native")]
                with mock.patch("scripts.train_finetune42.NativeBridge", Bridge), mock.patch("scripts.train_finetune42.SourceRecoveryPool42", Pool):
                    self.assertEqual(main(argv), 0)
                state = read_schedule(out)
                self.assertEqual(state["finetune42"]["clock"]["record_origin"], 100)
                restored = Finetune42Controller.load(out, native_bridge=Bridge())
                self.assertEqual(restored.steps, 1)
                self.assertEqual(len(restored.pending), 1)
                self.assertEqual(restored.policy.updates, old.policy.updates)
                self.assertEqual(restored.best, set(terms))
                self.assertFalse(restored.terminal)
        finally:
            os.sched_setaffinity(0, affinity)
            for sig, handler in previous.items(): signal.signal(sig, handler)


if __name__ == "__main__":
    unittest.main()
