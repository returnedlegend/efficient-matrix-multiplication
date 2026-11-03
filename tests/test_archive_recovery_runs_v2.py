"""V2 regression coverage for all original lossless archive safety checks."""
import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile
import time
import unittest
from unittest import mock

from scripts.archive_recovery_runs_v2 import (archive_runs, restore_runs, sha256_file,
                                           verify_bundle)
from scripts import archive_recovery_runs as old_archive
from scripts import archive_recovery_runs_v2 as archive_v2


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


class RecoveryArchiveV2Tests(unittest.TestCase):
    def test_batch_cap_never_opens_remaining_malformed_or_stale_run(self):
        for fault in ('malformed_result', 'stale_candidate'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                runs = root/'known-recovery/runs'
                first = completed(runs, 'a-selected')
                second = completed(runs, 'z-unscanned')
                target = second/('result.json' if fault == 'malformed_result'
                                 else 'verified/candidate.json')
                target.chmod(0o644)
                target.write_text('{bad json' if fault == 'malformed_result'
                                  else target.read_text()+' ')
                if fault == 'malformed_result':
                    target.chmod(0o444)
                old = time.time()-120
                os.utime(target, (old, old))
                original_open = Path.open

                def forbid_unscanned_open(path, *args, **kwargs):
                    if path.is_relative_to(second):
                        raise AssertionError(f'unselected run artifact opened: {path}')
                    return original_open(path, *args, **kwargs)

                with mock.patch.object(Path, 'open', forbid_unscanned_open), mock.patch.object(
                        archive_v2, 'completed_run', wraps=archive_v2.completed_run) as checked:
                    result = archive_runs(runs, root/'archives', max_runs=1)
                self.assertEqual([call.args[0] for call in checked.call_args_list], [first])
                self.assertEqual(result['runs'], 1)
                self.assertEqual(result['skipped'], {})
                self.assertTrue(result['selection_truncated'])
                self.assertEqual(result['scanned_entries'], 1)
                self.assertEqual(result['unscanned_entries'], 1)
                self.assertEqual(result['directory_entries'], 2)
                self.assertTrue(first.exists())
                self.assertTrue(second.exists())
                # Both old and new readers accept the same backward-compatible bundle.
                destination = root/'restored/known-recovery/runs'
                restored = old_archive.restore_runs(result['archive'], result['manifest'], destination)
                repeated = restore_runs(result['archive'], result['manifest'], destination)
                self.assertEqual(repeated['restored_files'], 0)
                self.assertEqual(repeated['existing_identical_files'], restored['restored_files'])
                for path in first.rglob('*'):
                    if path.is_file():
                        self.assertEqual(path.read_bytes(), (destination/path.relative_to(runs)).read_bytes())
                manifest = json.loads(Path(result['manifest']).read_text())
                self.assertEqual(manifest['utility_source_sha256'], sha256_file(archive_v2.__file__))
                self.assertEqual(manifest['base_source_sha256'], sha256_file(old_archive.__file__))
                self.assertEqual(manifest['selection']['unscanned_entries'], 1)
                self.assertEqual(manifest['skipped'], {})

    def test_only_scanned_skips_count_and_full_selection_is_not_truncated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root/'known-recovery/runs'
            completed(runs, 'b-selected')
            (runs/'a-incomplete').mkdir()
            (runs/'z-unclassified').write_bytes(b'not a directory')
            result = archive_runs(runs, root/'archives', max_runs=1)
            self.assertEqual(result['skipped'], {'active_or_incomplete': 1})
            self.assertTrue(result['selection_truncated'])
            self.assertEqual(result['scanned_entries'], 2)
            self.assertEqual(result['unscanned_entries'], 1)
            # Without the cap, every entry is classified; no truncation is claimed.
            result = archive_runs(runs, root/'archives', max_runs=2)
            self.assertEqual(result['skipped'], {'active_or_incomplete': 1, 'not_run_directory': 1})
            self.assertFalse(result['selection_truncated'])
            self.assertEqual(result['unscanned_entries'], 0)
            self.assertEqual(result['scanned_entries'], 3)

    def test_empty_selection_reports_scan_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root/'known-recovery/runs'
            runs.mkdir(parents=True)
            result = archive_runs(runs, root/'archives', max_runs=1)
            self.assertEqual(result, dict(runs=0, skipped={}, removed_runs=0,
                selection_truncated=False, scanned_entries=0, unscanned_entries=0,
                directory_entries=0))
            self.assertFalse((root/'archives').exists())

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
            with mock.patch("scripts.archive_recovery_runs_v2.verify_bundle", side_effect=ValueError("checksum mismatch")):
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
