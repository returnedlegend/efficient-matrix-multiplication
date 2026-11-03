"""V4 migration, external restart invariants, strict identity, and exact resume."""
import copy
import hashlib
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest import mock

from mmsearch.rl_pool_curriculum import PoolRecordController
from mmsearch.rl_restart_curriculum import (CHECKPOINT_FORMAT, SCHEDULE_FORMAT,
                                            RecordSeeds, RestartRecordController)
from mmsearch.rl_search import _write, gl_move, term_hash
from mmsearch.search import encode_candidate, naive_terms
from scripts.train_restart_tensor_agent import read_schedule


def seeds_fixture(directory):
    terms = set(naive_terms(2))
    alternate = gl_move(terms, 2, random.Random(41))
    paths = [directory/"first.json", directory/"second.json"]
    for path, value in zip(paths, (terms, alternate)):
        _write(path, encode_candidate(value, 2))
    return RecordSeeds(paths, n=2, known_rank=8), paths


def controller():
    return RestartRecordController(naive_terms(2), n=2, target_rank=1,
                                   seed=31, rollout=8, pool_context={"pool_sha256": "v3-frozen"})


def write_schedule(path, agent, record_cpu=0.0):
    _write(path.with_suffix(".schedule.json"), {
        "format": SCHEDULE_FORMAT, "checkpoint_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "restart_context": copy.deepcopy(agent.restart_context), "record_cpu": record_cpu})


class RestartCurriculumTests(unittest.TestCase):
    def test_flush_precedes_mutation_and_preserves_lifetime_state(self):
        with tempfile.TemporaryDirectory() as directory:
            seeds, _ = seeds_fixture(Path(directory))
            agent = controller()
            agent.step(7, cost_seconds=0)
            self.assertTrue(agent.pending)
            agent.bind_restarts(seeds, interval=300, record_cpu=12)
            old_current = agent.current.copy()
            old = {key: copy.deepcopy(getattr(agent, key)) for key in
                   ("best", "history", "total_reward", "novelty_paid", "segment_novelty_paid",
                    "action_counts", "steps", "archive", "stagnation")}
            rng = agent.rng.getstate()
            paid, seen = agent.ledger.paid, agent.ledger.seen.copy()
            policy = agent.policy
            original = agent._learn
            def flush():
                self.assertEqual(agent.current, old_current)
                self.assertTrue(agent.pending)
                original()
                self.assertFalse(agent.pending)
            with mock.patch.object(agent, "_learn", side_effect=flush):
                event = agent.restart_if_due(12)
            self.assertEqual(agent.current, seeds.terms[0])
            self.assertEqual(agent.rng.getstate(), rng)
            self.assertIs(agent.policy, policy)
            self.assertEqual(policy.updates, 1)
            self.assertEqual(agent.ledger.paid, paid)
            self.assertTrue(seen <= agent.ledger.seen)
            for key, value in old.items(): self.assertEqual(getattr(agent, key), value)
            self.assertEqual(event["reward"], 0)
            self.assertEqual(event["next_restart_cpu"], 312)
            self.assertIsNone(agent.restart_if_due(311.9))
            self.assertEqual(agent.restart_if_due(312)["restart_index"], 1)
            self.assertEqual(agent.restart_if_due(612)["restart_index"], 0)
            # A familiar supplied rank earns neither improvement nor novelty.
            agent.propose = lambda _action: seeds.terms[0].copy()
            event = agent.step(0, cost_seconds=0)
            self.assertEqual(event["improvement"], 0)
            self.assertEqual(event["novelty_bonus"], 0)
            self.assertLessEqual(event["reward"], 0)

    def test_v3_migration_keeps_model_optimizer_pending_rng_and_global_best(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seeds, _ = seeds_fixture(root)
            v3 = PoolRecordController(naive_terms(2), n=2, target_rank=1, seed=31,
                                      pool_context={"pool_sha256": "v3-frozen"})
            v3.step(7, cost_seconds=0)
            path = root/"v3.json"
            v3.save(path)
            _write(path.with_suffix(".schedule.json"), {
                "format": "mmsearch-pool-curriculum-schedule-v3",
                "checkpoint_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            self.assertEqual(read_schedule(path)["format"], "mmsearch-pool-curriculum-schedule-v3")
            agent = RestartRecordController.load(path)
            self.assertEqual(agent.policy.state(), v3.policy.state())
            self.assertEqual(agent.rng.getstate(), v3.rng.getstate())
            self.assertEqual(agent.pending, json.loads(path.read_text())["pending"])
            self.assertEqual(agent.best, v3.best)
            self.assertEqual(agent.ledger.state(), v3.ledger.state())
            self.assertEqual(agent.history, v3.history)
            self.assertEqual(agent.pool_context, v3.pool_context)
            agent.bind_restarts(seeds, interval=300, record_cpu=750)
            self.assertEqual(agent.restart_if_due(750)["restart_index"], 0)

    def test_v4_resume_preserves_partial_rollout_and_seed_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seeds, _ = seeds_fixture(root)
            agent = controller()
            agent.bind_restarts(seeds, interval=300, record_cpu=10)
            agent.restart_if_due(10)
            for _ in range(3): agent.step(7, cost_seconds=0)
            path = root/"v4.json"
            agent.save(path)
            write_schedule(path, agent, record_cpu=20)
            self.assertEqual(json.loads(path.read_text())["format"], CHECKPOINT_FORMAT)
            read_schedule(path)
            other = RestartRecordController.load(path)
            other.bind_restarts(seeds, interval=300, record_cpu=20)
            self.assertEqual(other.current, agent.current)
            self.assertEqual(other.pending, json.loads(path.read_text())["pending"])
            self.assertEqual(other.restart_context, agent.restart_context)
            for _ in range(10): self.assertEqual(agent.step(7, cost_seconds=0), other.step(7, cost_seconds=0))
            self.assertIsNone(other.restart_if_due(309.9))
            self.assertEqual(agent.restart_if_due(310), other.restart_if_due(310))
            self.assertEqual(agent.policy.state(), other.policy.state())
            self.assertEqual(agent.ledger.state(), other.ledger.state())

    def test_seed_order_bytes_interval_and_schedule_state_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seeds, paths = seeds_fixture(root)
            agent = controller()
            agent.bind_restarts(seeds, interval=300, record_cpu=0)
            reversed_seeds = RecordSeeds(paths[::-1], n=2, known_rank=8)
            with self.assertRaisesRegex(ValueError, "identity/order"):
                agent.bind_restarts(reversed_seeds, interval=300, record_cpu=0)
            with self.assertRaisesRegex(ValueError, "interval"):
                agent.bind_restarts(seeds, interval=301, record_cpu=0)
            paths[0].write_text(paths[0].read_text()+" ")
            changed = RecordSeeds(paths, n=2, known_rank=8)
            with self.assertRaisesRegex(ValueError, "identity/order"):
                agent.bind_restarts(changed, interval=300, record_cpu=0)
            path = root/"v4.json"
            agent.save(path)
            with self.assertRaisesRegex(ValueError, "sidecar"): read_schedule(path)
            write_schedule(path, agent)
            state = json.loads(path.with_suffix(".schedule.json").read_text())
            state["restart_context"]["next_index"] = 1
            _write(path.with_suffix(".schedule.json"), state)
            with self.assertRaisesRegex(ValueError, "restart state"): read_schedule(path)
            write_schedule(path, agent)
            agent.steps += 1
            agent.save(path)
            with self.assertRaisesRegex(ValueError, "does not match"): read_schedule(path)
            agent.restart_context["next_index"] = 90
            with self.assertRaisesRegex(ValueError, "schedule"):
                agent.bind_restarts(seeds, interval=300, record_cpu=0)

    def test_all_seed_inputs_require_exact_f2_dimension_and_essential_rank(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seeds, paths = seeds_fixture(root)
            for field, value in (("field", 3), ("dimension", 3)):
                candidate = encode_candidate(seeds.terms[0], 2)
                candidate[field] = value
                _write(paths[0], candidate)
                with self.assertRaises(ValueError): RecordSeeds([paths[0]], n=2, known_rank=8)
            _write(paths[0], encode_candidate(seeds.terms[0], 2))
            with self.assertRaisesRegex(ValueError, "essential rank"):
                RecordSeeds([paths[0]], n=2, known_rank=7)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                RecordSeeds([paths[0], paths[0]], n=2, known_rank=8)
            candidate = encode_candidate(seeds.terms[0]-{min(seeds.terms[0])}, 2)
            _write(paths[0], candidate)
            with self.assertRaisesRegex(ValueError, "independent exact"):
                RecordSeeds([paths[0]], n=2, known_rank=7)

    def test_terminal_global_best_blocks_restarts(self):
        with tempfile.TemporaryDirectory() as directory:
            seeds, _ = seeds_fixture(Path(directory))
            agent = controller()
            agent.bind_restarts(seeds, interval=300, record_cpu=0)
            agent.terminal = True
            before = copy.deepcopy(agent.restart_context)
            self.assertIsNone(agent.restart_if_due(900))
            self.assertEqual(agent.restart_context, before)

    def test_atomic_v4_publication_never_exposes_parent_format(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seeds, _ = seeds_fixture(root)
            agent = controller()
            agent.bind_restarts(seeds, interval=300, record_cpu=0)
            path = root/"agent.json"
            agent.save(path)
            original = path.read_bytes()
            with mock.patch("mmsearch.rl_restart_curriculum._write", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError): agent.save(path)
            self.assertEqual(path.read_bytes(), original)
            def publish_then_interrupt(destination, value):
                _write(destination, value)
                raise OSError("after publication")
            with mock.patch("mmsearch.rl_restart_curriculum._write", side_effect=publish_then_interrupt):
                with self.assertRaises(OSError): agent.save(path)
            self.assertEqual(json.loads(path.read_text())["format"], CHECKPOINT_FORMAT)
            self.assertFalse(list(root.glob(".*restart-private-*")))
            value = json.loads(path.read_text())
            value["code_hashes"]["rl_restart_curriculum.py"] = "changed"
            _write(path, value)
            with self.assertRaisesRegex(ValueError, "source identity"):
                RestartRecordController.load(path)

    def test_invalid_saved_cpu_and_index_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            seeds, _ = seeds_fixture(Path(directory))
            agent = controller()
            agent.bind_restarts(seeds, interval=300, record_cpu=0)
            original = copy.deepcopy(agent.restart_context)
            for key, value in (("next_cpu", float("nan")), ("next_cpu", 1000000),
                               ("next_index", -1), ("restarts", -1), ("next_index", 1)):
                agent.restart_context = copy.deepcopy(original)
                agent.restart_context[key] = value
                with self.assertRaisesRegex(ValueError, "saved restart"):
                    agent.bind_restarts(seeds, interval=300, record_cpu=0)


if __name__ == "__main__":
    unittest.main()
