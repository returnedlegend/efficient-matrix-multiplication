"""Synthetic-only cached guard differential, mutation and late-I/O controls."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from mmsearch.marathon7_local import CampaignGuard as OriginalGuard
from mmsearch.marathon7_cached_guard import (CampaignGuard, CampaignHold,
                                           HARD_DEADLINE, StableJsonCache)
import mmsearch.marathon7_cached_guard as subject


def proc(pid):
    return Path("/proc", str(pid), "stat").read_text().rsplit(")", 1)[1].split()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, separators=(",", ":")))


class CachedGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="cached-guard-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.clock = [min(time.time(), HARD_DEADLINE - 3600)]
        self.mono = [10.0]
        self.state = self.root / "operations-v3/state.json"
        self.good = dict(updated_utc=datetime.fromtimestamp(self.clock[0], timezone.utc).isoformat(),
                         pid=os.getpid(), process_identity=dict(start_ticks=int(proc(os.getpid())[19])),
                         campaign_allocated_bytes=1024, stop_reason=None, nonce=1)
        write(self.state, self.good)
        write(self.root / "queue_state.json", {})
        # Existing FreshGuard uses the module clock; align only synthetic time.
        self.patch = patch("mmsearch.observed_rank3_lazy42.time.time", side_effect=lambda: self.clock[0])
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def guard(self, cls=CampaignGuard, **kwargs):
        return cls(1000, "2099-01-01T00:00:00Z", guard_state=self.state,
                   campaign_dir=self.root, monotonic=lambda: self.mono[0],
                   utc_clock=lambda: self.clock[0], **kwargs)

    def compare(self):
        old, new = self.guard(OriginalGuard), self.guard()
        a, b = old.reason(force=True), new.reason(force=True)
        self.assertEqual(a, b)
        return new, b

    def test_unchanged_cache_and_every_call_live_stat(self):
        guard, reason = self.compare()
        self.assertIsNone(reason)
        first = guard.cache.metrics()
        for _ in range(8):
            self.assertIsNone(guard.reason(force=False))
        later = guard.cache.metrics()
        self.assertEqual(later["parses"], first["parses"])
        self.assertGreater(later["signature_checks"], first["signature_checks"])
        self.assertGreater(later["hits"], first["hits"])
        write(self.state, dict(self.good, stop_reason="fresh stop"))
        self.assertIn("stop_reason", guard.reason(force=False))

    def test_large_synthetic_state_differential_and_fresh_stop(self):
        value = dict(self.good, padding="")
        raw = json.dumps(value, separators=(",", ":")).encode()
        value["padding"] = "x" * (1400000 - len(raw))
        write(self.state, value)
        self.assertEqual(self.state.stat().st_size, 1400000)
        old, new = self.guard(OriginalGuard), self.guard()
        for _ in range(3):
            self.assertEqual(old.reason(force=True), new.reason(force=True))
            self.assertIsNone(new.reason(force=False))
        self.assertEqual(new.cache.metrics()["parses"], 2)
        write(self.state, dict(value, stop_reason="large fresh stop"))
        self.assertEqual(old.reason(force=True), new.reason(force=False))

    def test_all_critical_markers_and_canonical_stops_differential(self):
        for relative, expected in [("guard_stopped.json", "global guard_stopped marker"),
                                   ("WINNER.json", "global WINNER marker"),
                                   ("child/WINNER.json", "immediate-child WINNER marker")]:
            path = self.root / relative
            write(path, {})
            _, reason = self.compare()
            self.assertEqual(reason, expected)
            path.unlink()
        for path in [self.root / "queue_state.json", self.state]:
            before = path.read_bytes()
            value = json.loads(before)
            value["stop_reason"] = "external hold"
            write(path, value)
            _, reason = self.compare()
            self.assertTrue(reason.startswith("global stop_reason:"))
            path.write_bytes(before)
        marker = self.root / "explicit.stop"
        guard = self.guard(stop_markers=[marker])
        self.assertIsNone(guard.reason())
        marker.touch()
        self.assertEqual(guard.reason(), "stop marker: " + str(marker))
        marker.unlink()
        guard.stop()
        self.assertEqual(guard.reason(), "stop signal")

    def test_typed_malformed_inputs_and_storage_differential(self):
        corruptions = [[], dict(self.good, updated_utc=4),
                       dict(self.good, updated_utc="2026-11-03T00:00:00"),
                       dict(self.good, pid=True), dict(self.good, pid=-1),
                       dict(self.good, process_identity=[]),
                       dict(self.good, process_identity=dict(start_ticks=1.0)),
                       dict(self.good, campaign_allocated_bytes=True),
                       dict(self.good, campaign_allocated_bytes=-1),
                       dict(self.good, campaign_allocated_bytes=5 * 1024**3)]
        for value in corruptions:
            with self.subTest(value=value):
                write(self.state, value)
                _, reason = self.compare()
                self.assertIsNotNone(reason)
        write(self.state, self.good)
        (self.root / "queue_state.json").write_text("not json")
        _, reason = self.compare()
        self.assertIsNotNone(reason)

    def test_cached_heartbeat_age_utc_rollback_pid_and_wall_checks(self):
        guard = self.guard()
        self.assertIsNone(guard.reason(force=True))
        parsed = guard.cache.metrics()["parses"]
        self.clock[0] += 61
        self.assertEqual(guard.reason(), "resource guard stale")
        self.assertEqual(self.guard(OriginalGuard).reason(force=True), "resource guard stale")
        self.assertEqual(guard.cache.metrics()["parses"], parsed)
        self.clock[0] -= 67
        self.assertEqual(guard.reason(), "resource guard stale")
        self.assertEqual(self.guard(OriginalGuard).reason(force=True), "resource guard stale")
        self.clock[0] += 6
        self.mono[0] += 1001
        self.assertEqual(guard.reason(), "invocation wall cutoff")
        new = self.guard()
        self.clock[0] = HARD_DEADLINE
        self.assertEqual(new.reason(), "absolute campaign deadline")
        self.assertEqual(new.deadline, HARD_DEADLINE)

    def test_pid_reuse_zombie_and_actual_child_death(self):
        guard = self.guard()
        self.assertIsNone(guard.reason())
        tail = proc(os.getpid())
        reused = list(tail)
        reused[19] = str(int(tail[19]) + 1)
        with patch.object(subject, "_proc_stat", return_value=reused):
            self.assertEqual(guard.reason(), "resource guard process identity changed")
        zombie = list(tail)
        zombie[0] = "Z"
        with patch.object(subject, "_proc_stat", return_value=zombie):
            self.assertEqual(guard.reason(), "resource process no longer live")
        child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
        try:
            start = int(proc(child.pid)[19])
            write(self.state, dict(self.good, pid=child.pid, process_identity=dict(start_ticks=start)))
            live = self.guard()
            self.assertIsNone(live.reason())
            child.terminate()
            child.wait(timeout=5)
            self.assertIsNotNone(live.reason())  # Unchanged cached JSON cannot hide death.
            self.assertIsNotNone(self.guard(OriginalGuard).reason(force=True))
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            child.stdin.close()

    def test_same_path_rewrite_preserved_mtime_and_atomic_replace(self):
        cache = StableJsonCache()
        self.assertEqual(cache.load(self.state)["nonce"], 1)
        before = self.state.stat()
        write(self.state, dict(self.good, nonce=2))
        os.utime(self.state, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(cache.load(self.state)["nonce"], 2)
        replacement = self.state.with_suffix(".replacement")
        write(replacement, dict(self.good, nonce=3))
        os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
        replacement.replace(self.state)
        self.assertEqual(cache.load(self.state)["nonce"], 3)
        self.assertEqual(cache.metrics()["parses"], 3)

    def test_open_and_parse_races_retry_or_fail_closed(self):
        cache = StableJsonCache()
        replacement = self.state.with_suffix(".replacement")
        write(replacement, dict(self.good, nonce=2))
        original_open = Path.open
        swapped = [False]
        def swap_after_open(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            if path == self.state and not swapped[0]:
                swapped[0] = True
                replacement.replace(self.state)
            return stream
        with patch.object(Path, "open", swap_after_open):
            self.assertEqual(cache.load(self.state)["nonce"], 2)
        self.assertGreater(cache.metrics()["retries"], 0)

        cache = StableJsonCache()
        actual_load = json.loads
        changed = [False]
        def change_after_parse(raw, *args, **kwargs):
            value = actual_load(raw, *args, **kwargs)
            if not changed[0]:
                changed[0] = True
                write(self.state, dict(self.good, nonce=3))
            return value
        with patch.object(subject.json, "loads", change_after_parse):
            self.assertEqual(cache.load(self.state)["nonce"], 3)
        self.assertGreater(cache.metrics()["retries"], 0)

        serial = [4]
        def always_change(raw, *args, **kwargs):
            value = actual_load(raw, *args, **kwargs)
            serial[0] += 1
            write(self.state, dict(self.good, nonce=serial[0]))
            return value
        write(self.state, dict(self.good, nonce=4))
        with patch.object(subject.json, "loads", always_change):
            with self.assertRaisesRegex(OSError, "changed"):
                cache.load(self.state)

    def test_symlinks_follow_old_policy_and_retarget_is_detected(self):
        link = self.root / "resource-link.json"
        link.symlink_to(self.state)
        old = OriginalGuard(100, "2099-01-01T00:00:00Z", guard_state=link,
                            utc_clock=lambda: self.clock[0], monotonic=lambda: self.mono[0])
        new = CampaignGuard(100, "2099-01-01T00:00:00Z", guard_state=link,
                            utc_clock=lambda: self.clock[0], monotonic=lambda: self.mono[0])
        self.assertIsNone(old.reason(force=True))
        self.assertIsNone(new.reason(force=True))
        other = self.root / "other.json"
        write(other, dict(self.good, stop_reason="retargeted stop"))
        link.unlink()
        link.symlink_to(other)
        self.assertIn("retargeted stop", new.reason(force=False))
        link.unlink()
        link.symlink_to(self.root / "missing.json")
        self.assertIsNotNone(new.reason())

    def test_late_json_proc_and_marker_io_cannot_allow(self):
        for step in ["json", "proc", "markers"]:
            with self.subTest(step=step):
                self.clock[0] = HARD_DEADLINE - 100
                write(self.state, dict(self.good, updated_utc=datetime.fromtimestamp(self.clock[0], timezone.utc).isoformat()))
                guard = self.guard()
                if step == "json":
                    actual = guard.cache.load
                    def late(path):
                        value = actual(path)
                        self.clock[0] = HARD_DEADLINE
                        return value
                    context = patch.object(guard.cache, "load", late)
                elif step == "proc":
                    actual = subject._proc_stat
                    def late(pid):
                        value = actual(pid)
                        self.clock[0] = HARD_DEADLINE
                        return value
                    context = patch.object(subject, "_proc_stat", late)
                else:
                    actual = subject._immediate_child_winner
                    def late(path):
                        value = actual(path)
                        self.clock[0] = HARD_DEADLINE
                        return value
                    context = patch.object(subject, "_immediate_child_winner", late)
                with context:
                    self.assertIsNotNone(guard.reason(force=True))

    def test_resource_replacement_during_marker_io_cannot_reuse_earlier_authority(self):
        guard = self.guard()
        self.assertIsNone(guard.reason())
        actual = subject._immediate_child_winner
        def replace_during_marker_check(path):
            value = actual(path)
            replacement = self.state.with_suffix(".new")
            write(replacement, dict(self.good, campaign_allocated_bytes=5 * 1024**3))
            replacement.replace(self.state)
            return value
        with patch.object(subject, "_immediate_child_winner", replace_during_marker_check):
            self.assertEqual(guard.reason(force=True), "resource guard working storage reached 5GiB")

    def test_canonical_stop_or_type_change_during_marker_io_is_observed(self):
        for value in [dict(stop_reason="late queue stop"), []]:
            with self.subTest(value=value):
                write(self.root / "queue_state.json", {})
                guard = self.guard()
                self.assertIsNone(guard.reason(force=True))
                actual = subject._immediate_child_winner
                def change_during_marker_check(path):
                    result = actual(path)
                    write(self.root / "queue_state.json", value)
                    return result
                with patch.object(subject, "_immediate_child_winner", change_during_marker_check):
                    reason = guard.reason(force=True)
                self.assertIsNotNone(reason)
                if isinstance(value, dict):
                    self.assertTrue(reason.startswith("global stop_reason:"))
                else:
                    self.assertEqual(reason, "invalid canonical state type")

    def test_many_child_files_are_never_enumerated_and_child_links_are_followed(self):
        for i in range(20):
            directory = self.root / f"child-{i:02d}"
            directory.mkdir()
            for j in range(48):
                (directory / f"payload-{j:03d}.json").touch()
        actual = os.scandir
        scanned = []
        def root_only(path):
            scanned.append(Path(path))
            self.assertEqual(Path(path), self.root, "enumerated child directory contents")
            return actual(path)
        with patch.object(subject.os, "scandir", root_only):
            self.assertFalse(subject._immediate_child_winner(self.root))
        self.assertEqual(scanned, [self.root])
        with tempfile.TemporaryDirectory(prefix="cached-guard-child-link-") as directory:
            external = Path(directory)
            (external / "WINNER.json").write_text("{}")
            (self.root / "linked-child").symlink_to(external, target_is_directory=True)
            self.assertTrue(subject._immediate_child_winner(self.root))
            old, new = self.guard(OriginalGuard), self.guard()
            self.assertEqual(old.reason(force=True), "immediate-child WINNER marker")
            self.assertEqual(new.reason(force=True), "immediate-child WINNER marker")

    def test_barrier_exception_and_frozen_sources_untouched(self):
        guard = self.guard()
        guard.stop()
        with self.assertRaises(CampaignHold) as error:
            guard.check("post_solve")
        self.assertEqual(error.exception.barrier, "post_solve")
        self.assertEqual(error.exception.reason, "stop signal")
        # Initial/final pins are compared by the standalone synthetic benchmark.
        for value in [float("nan"), float("inf"), -1, True]:
            with self.assertRaises(ValueError):
                CampaignGuard(value, "2099-01-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
