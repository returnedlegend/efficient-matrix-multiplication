"""Frozen record-reference entrypoint contracts and retained v4 state."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from mmsearch.rl_restart_curriculum import RestartRecordController, SCHEDULE_FORMAT
from mmsearch.rl_search import _write
from mmsearch.search import naive_terms
from scripts import train_record_reference as driver
from tests.test_rl_restart_curriculum import seeds_fixture


def write_schedule(path, agent, reference=False):
    value = {"format": SCHEDULE_FORMAT,
             "checkpoint_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
             "restart_context": agent.restart_context}
    if reference:
        identity = driver.driver_identity()
        value.update(record_reference=identity, code_hashes={identity["filename"]: identity["sha256"]})
    _write(path.with_suffix(".schedule.json"), value)


class ReferenceTests(unittest.TestCase):
    def test_zero_fraction_parses_and_policy_or_training_is_rejected_before_work(self):
        required = ["--resume", "/tmp/unused", "--cpu", "2", "--checkpoint", "/tmp/no-write",
                    "--output", "/tmp/no-write-best", "--events", "/tmp/no-write-events",
                    "--native-dir", "/tmp/no-write-native", "--recovery-pool", "/tmp/no-write-pool",
                    "--record-seed", "/tmp/no-write-seed", "--recovery-fraction", "0"]
        with mock.patch.object(driver, "read_schedule", side_effect=RuntimeError("parsed")):
            with self.assertRaisesRegex(RuntimeError, "parsed"):
                driver.main(required+["--control", "random", "--frozen"])
            for flags in (["--control", "policy", "--frozen"], ["--control", "random"],
                          ["--control", "random", "--frozen", "--recovery-fraction", ".2"]):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error: driver.main(required+flags)
                self.assertEqual(error.exception.code, 2)

    def test_v4_migration_and_reference_resume_preserve_model_rng_best_and_novelty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seeds, _ = seeds_fixture(root)
            agent = RestartRecordController(naive_terms(2), n=2, target_rank=1, seed=17,
                                            train=False, control="random", pool_context={"pool_sha256": "frozen"})
            agent.bind_restarts(seeds, interval=300, record_cpu=0)
            agent.step(7, cost_seconds=0)
            original = {key: copy.deepcopy(getattr(agent, key)) for key in ("best", "history", "total_reward")}
            policy = agent.policy.state(); rng = agent.rng.getstate(); paid = agent.ledger.paid
            path = root/"checkpoint.json"
            agent.save(path); write_schedule(path, agent)
            driver.read_schedule(path)  # Original v4 migration remains valid.
            driver.save_reference(agent, path); write_schedule(path, agent, reference=True)
            driver.read_schedule(path)
            value = json.loads(path.read_text())
            self.assertEqual(value["record_reference"]["sha256"], hashlib.sha256(Path(driver.__file__).read_bytes()).hexdigest())
            self.assertEqual(value["code_hashes"]["train_record_reference.py"], driver.driver_identity()["sha256"])
            restored = RestartRecordController.load(path)
            restored.bind_restarts(seeds, interval=300, record_cpu=0)
            with mock.patch.object(restored.policy, "learn", side_effect=AssertionError("must remain frozen")):
                event = restored.restart_if_due(0)
            self.assertEqual(event["reward"], 0)
            self.assertEqual(restored.policy.state(), policy)
            self.assertEqual(restored.rng.getstate(), rng)
            self.assertEqual(restored.ledger.paid, paid)
            for key, expected in original.items(): self.assertEqual(getattr(restored, key), expected)
            self.assertFalse(restored.train)
            self.assertEqual(restored.control, "random")

    def test_new_reference_driver_and_sidecar_identity_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); seeds, _ = seeds_fixture(root)
            agent = RestartRecordController(naive_terms(2), n=2, target_rank=1, train=False,
                                            control="random", pool_context={"pool_sha256": "frozen"})
            agent.bind_restarts(seeds, interval=300, record_cpu=0)
            path = root/"checkpoint.json"
            driver.save_reference(agent, path); write_schedule(path, agent, reference=True)
            changed = dict(driver.driver_identity(), sha256="another-version")
            with mock.patch.object(driver, "driver_identity", return_value=changed):
                with self.assertRaisesRegex(ValueError, "driver identity"): driver.read_schedule(path)
            schedule = json.loads(path.with_suffix(".schedule.json").read_text())
            schedule["record_reference"]["sha256"] = "changed"
            _write(path.with_suffix(".schedule.json"), schedule)
            with self.assertRaisesRegex(ValueError, "driver identity"): driver.read_schedule(path)

    def test_source_has_no_auxiliary_sampler_or_recovery_bridge(self):
        import ast
        tree = ast.parse(Path(driver.__file__).read_text())
        calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertFalse(any(isinstance(node, ast.Attribute) and node.attr == "choose" for node in calls))
        self.assertFalse(any(isinstance(node, ast.Name) and node.id in ("ContextController", "FixedStepBridge") for node in calls))
        self.assertTrue(any(isinstance(node, ast.Name) and node.id == "ContextDmEnv" for node in calls))


if __name__ == "__main__":
    unittest.main()
