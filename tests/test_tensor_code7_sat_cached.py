"""Guard-only adapter and actual-native-entry telemetry; tiny controls only."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from mmsearch import tensor_code7_sat as sat
from mmsearch import tensor_code7_sat_cached as adapter
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.tensor_code7 import prepare
from scripts import tensor_code7 as owner


class CachedSatAdapterTests(unittest.TestCase):
    def fixture(self, root):
        (root / "operations-v3").mkdir()
        config = {"deadline_utc": "2026-11-03T19:24:17Z"}
        raw = json.dumps(config).encode()
        (root / "campaign.json").write_bytes(raw)
        ticks = int(Path(f"/proc/{os.getpid()}/stat").read_text().rsplit(")", 1)[1].split()[19])
        state = dict(pid=os.getpid(), process_identity={"start_ticks": ticks},
            updated_utc=datetime.now(timezone.utc).isoformat(), campaign_allocated_bytes=0, stop_reason=None)
        resource = root / "operations-v3/state.json"
        resource.write_text(json.dumps(state))
        (root / "queue_state.json").write_text("{}")
        return hashlib.sha256(raw).hexdigest(), resource, state

    def test_install_restores_originals_and_disabled_cli_reads_no_input(self):
        before = owner.Guard, sat._worker, sat.solve_linear
        with adapter.installed() as profile:
            self.assertIs(owner.Guard, adapter.CachedTensorGuard)
            self.assertIs(sat._worker, adapter.profiled_worker)
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("disabled input read")), redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(sat.main([]), 0)
            self.assertFalse(json.loads(stream.getvalue())["solver_called"])
            self.assertFalse(profile.observation()["native_solve_called"])
        self.assertEqual((owner.Guard, sat._worker, sat.solve_linear), before)

    def test_cached_component_preserves_hash_deadline_signal_and_live_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pin, resource, state = self.fixture(root)
            with mock.patch.object(owner.signal, "signal"), adapter.installed(root, owns_output=True):
                guard = owner.Guard("2099-01-01T00:00:00Z", 10, root, resource, pin)
                self.assertIsInstance(guard.canonical, CampaignGuard)
                self.assertEqual(guard.hard.isoformat(), "2026-11-03T19:24:17+00:00")
                guard("prepared_validation")
                for _ in range(25):
                    guard("prepared_validation")
                self.assertLessEqual(guard.canonical.cache.metrics()["parses"], 2)
                (root / "queue_state.json").write_text('{"stop_reason":"new stop"}')
                with self.assertRaises(owner.Stop):
                    guard("post_independent_verification")
                self.assertFalse(json.loads((root / "profiler-parent.json").read_bytes())["native_solve_called"])
                with self.assertRaisesRegex(ValueError, "config hash"):
                    owner.Guard("2099-01-01T00:00:00Z", 10, root, resource, "0" * 64)

    def test_native_proxy_records_actual_solve_and_unchanged_tiny_witness(self):
        document = prepare([naive_candidate(2), strassen_candidate(2)])
        with tempfile.TemporaryDirectory() as directory, adapter.installed(directory, owns_output=True) as profile:
            result = sat.solve_prepared(document, bound=7, seconds=3)
            self.assertEqual(result["status"], "SAT", result)
            self.assertEqual(result["essential_rank"], 7)
            observation = profile.observation()
            self.assertTrue(observation["solve_linear_entered"])
            self.assertTrue(observation["native_solve_called"])
            self.assertEqual(sum(w["native_solve_calls"] for w in observation["workers"]), 1)
            self.assertTrue(result["worker_reaped"])
            self.assertEqual(result["cpu_affinity"], [1])

    def test_preprocessing_stop_records_no_native_call_and_preserves_raw_late_sat(self):
        document = prepare([naive_candidate(2), strassen_candidate(2)])
        with tempfile.TemporaryDirectory() as directory, adapter.installed(directory, owns_output=True) as profile:
            def early(phase):
                if phase == "pre_prepared_validation":
                    profile.mark("prepared_validation", force=True)
                    raise sat.Stopped("before native")
            result = sat.solve_prepared(document, bound=7, seconds=2, guard=early)
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertFalse(profile.observation()["solve_linear_entered"])
            self.assertFalse(profile.observation()["native_solve_called"])
            def late(phase):
                if phase == "post_native_result":
                    raise owner.Stop("after native")
            result = sat.solve_prepared(document, bound=7, seconds=2, guard=late)
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["raw_native_result"]["status"], "SAT")
            self.assertFalse(result["raw_witness"]["within_budget"])
            self.assertTrue(profile.observation()["native_solve_called"])

    def test_fresh_heartbeat_age_pid_and_marker_checks_survive_cache_hits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pin, resource, state = self.fixture(root)
            with mock.patch.object(owner.signal, "signal"), adapter.installed(root, owns_output=True):
                guard = owner.Guard("2099-01-01T00:00:00Z", 10, root, resource, pin)
                guard("pre_source")
                state["process_identity"]["start_ticks"] += 1
                resource.write_text(json.dumps(state))
                with self.assertRaises(owner.Stop):
                    guard("pre_dispatch")

    def test_disabled_adapter_existing_output_reads_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = root / "result.json"
            original = b'{"status":"SAT","immutable":true}\n'
            result.write_bytes(original)
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("disabled read")), mock.patch.object(adapter.StageProfile, "_write", side_effect=AssertionError("disabled write")), redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(adapter.main(["--outdir=" + str(root)]), 0)
            self.assertEqual(json.loads(stream.getvalue())["status"], "DISABLED_PENDING_ROOT_QA")
            self.assertEqual(result.read_bytes(), original)
            self.assertEqual({p.name for p in root.iterdir()}, {"result.json"})

    def test_authorized_existing_output_rejected_without_read_or_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = b'{"status":"UNKNOWN","preserve":true}\n'
            (root / "result.json").write_bytes(original)
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("existing read")), mock.patch.object(adapter.StageProfile, "_write", side_effect=AssertionError("existing write")), self.assertRaises(FileExistsError):
                adapter.main(["--authorize-search", "--qa-approval", "root-reviewed", "--outdir", str(root)])
            self.assertEqual((root / "result.json").read_bytes(), original)
            self.assertEqual({p.name for p in root.iterdir()}, {"result.json"})

    def test_failed_exclusive_creation_race_never_claims_someone_elses_output(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "raced-output"
            def raced(argv):
                target.mkdir()
                (target / "result.json").write_bytes(b'{"owner":"other"}\n')
                raise FileExistsError("another creator won")
            with mock.patch.object(adapter.base, "main", side_effect=raced), self.assertRaises(FileExistsError):
                adapter.main(["--authorize-search", "--qa-approval", "root-reviewed", "--outdir", str(target)])
            self.assertEqual((target / "result.json").read_bytes(), b'{"owner":"other"}\n')
            self.assertEqual({p.name for p in target.iterdir()}, {"result.json"})


if __name__ == "__main__":
    unittest.main()
