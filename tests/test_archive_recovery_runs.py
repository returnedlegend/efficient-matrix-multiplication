"""Lossless round trips and fail-closed recovery-only archive removal."""
import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile
import time
import unittest
from unittest import mock

from scripts.archive_recovery_runs import (archive_runs, restore_runs, sha256_file,
                                           verify_bundle)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True)+"\n")
    path.chmod(0o444)


def completed(root, name="finished", rank=93):
    run = root/name
    run.mkdir(parents=True)
    value = {"field": 2, "dimension": 5, "terms": [{} for _ in range(rank)],
             "metadata": {"rank": rank}}
    write(run/"input.json", value)
    write(run/"verified/candidate.json", value)
    write(run/"verified/report.json", {"valid": True, "rank": rank})
    write(run/"winners/known.json", value)
    write(run/"manifest.json", {"target_rank": 93, "input_sha256": sha256_file(run/"input.json")})
    write(run/"result.json", {"status": "ok", "run_dir": str(run.resolve()), "best_rank": rank,
         "best_candidate": value, "current_candidate": value,
         "candidates": [{"path": str((run/"verified/candidate.json").resolve()),
                         "verification_path": str((run/"verified/report.json").resolve()),
                         "sha256": sha256_file(run/"verified/candidate.json"), "rank": rank}]})
    (run/"worker.log").write_bytes(b"opaque log\x00\xff\n")
    old = time.time()-120
    for path in run.rglob("*"):
        if path.is_file(): os.utime(path, (old, old))
    return run


class RecoveryArchiveTests(unittest.TestCase):
    def test_default_archive_is_lossless_readonly_and_retains_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root/"native/known-recovery/runs"
            run = completed(runs)
            original = {p.relative_to(runs).as_posix(): p.read_bytes() for p in run.rglob("*") if p.is_file()}
            result = archive_runs(runs, root/"archives")
            self.assertEqual(result["runs"], 1)
            self.assertEqual(result["removed_runs"], 0)
            self.assertTrue(run.exists())
            self.assertFalse(Path(result["archive"]).stat().st_mode & 0o222)
            self.assertFalse(Path(result["manifest"]).stat().st_mode & 0o222)
            destination = root/"restored/known-recovery/runs"
            restored = restore_runs(result["archive"], result["manifest"], destination)
            self.assertEqual(restored["restored_files"], len(original))
            for name, payload in original.items():
                self.assertEqual((destination/name).read_bytes(), payload)
            repeated = restore_runs(result["archive"], result["manifest"], destination)
            self.assertEqual(repeated["restored_files"], 0)
            self.assertEqual(repeated["existing_identical_files"], len(original))

    def test_remove_only_verified_completed_normal_known_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root/"known-recovery/runs"
            good = completed(runs, "ordinary")
            record = completed(runs, "genuine-record", rank=92)
            recent = completed(runs, "recent")
            os.utime(recent/"worker.log", None)
            active = runs/"active"
            active.mkdir()
            (active/"worker.log").write_text("still running")
            result = archive_runs(runs, root/"archives", remove_after_verify=True)
            self.assertEqual(result["removed_runs"], 1)
            self.assertFalse(good.exists())
            self.assertTrue(record.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(active.exists())
            restored = restore_runs(result["archive"], result["manifest"], runs)
            self.assertGreater(restored["restored_files"], 0)
            self.assertTrue(good.exists())

    def test_nonrecovery_directory_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root/"record/runs"
            completed(runs)
            with self.assertRaisesRegex(ValueError, "known-recovery/runs"):
                archive_runs(runs, root/"archives", remove_after_verify=True)

    def test_changed_native_hash_fails_before_archive_or_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root/"known-recovery/runs"
            run = completed(runs)
            candidate = run/"verified/candidate.json"
            candidate.chmod(0o644)
            candidate.write_text(candidate.read_text()+" ")
            old = time.time()-120
            os.utime(candidate, (old, old))
            with self.assertRaisesRegex(ValueError, "candidate hash mismatch"):
                archive_runs(runs, root/"archives", remove_after_verify=True)
            self.assertTrue(run.exists())

    def test_failed_archive_verification_never_deletes_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root/"known-recovery/runs"
            run = completed(runs)
            with mock.patch("scripts.archive_recovery_runs.verify_bundle", side_effect=ValueError("checksum mismatch")):
                with self.assertRaises(ValueError):
                    archive_runs(runs, root/"archives", remove_after_verify=True)
            self.assertTrue(run.exists())
            self.assertTrue((run/"result.json").exists())

    def test_restore_conflicting_existing_file_fails_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root/"known-recovery/runs"
            run = completed(runs)
            result = archive_runs(runs, root/"archives")
            conflicting = root/"restore/known-recovery/runs"/run.name/"worker.log"
            conflicting.parent.mkdir(parents=True)
            conflicting.write_bytes(b"different")
            with self.assertRaisesRegex(ValueError, "differs"):
                restore_runs(result["archive"], result["manifest"], conflicting.parent.parent)
            self.assertEqual(conflicting.read_bytes(), b"different")
            self.assertFalse((conflicting.parent/"input.json").exists())

    def test_unsafe_archive_path_rejected_before_restore(self):
        import io
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root/"bad.tar.gz"
            with tarfile.open(archive, "w:gz") as stream:
                member = tarfile.TarInfo("../escape")
                member.size = 1
                stream.addfile(member, io.BytesIO(b"x"))
            manifest = {"archive_sha256": sha256_file(archive),
                        "files": [{"path": "../escape", "size": 1, "sha256": hashlib.sha256(b"x").hexdigest()}]}
            with self.assertRaisesRegex(ValueError, "unsafe"):
                verify_bundle(archive, manifest)


if __name__ == "__main__":
    unittest.main()
