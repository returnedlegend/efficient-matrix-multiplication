import inspect
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from scripts import archive_native_runs_v4 as legacy
from scripts import archive_native_runs_v5 as archive
from scripts import native_maintenance_v5 as maintenance
from tests.test_archive_native_runs_v4 import completed, write
from tests.test_campaign_operations_v3 import policy, schoolbook


class NestedArchiveTests(unittest.TestCase):
    def test_legacy_roots_and_only_six_nested_forms_admitted_under_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for kind in ('native/runs', 'native/known-recovery/runs', 'native/record/runs'):
                self.assertEqual(archive.runs_root(root/kind), legacy.runs_root(root/kind))
            for arm in ('learned', 'frozenwarm', 'random'):
                for kind in ('known-recovery', 'record'):
                    path = root/'campaign'/'evaluation'/'native'/arm/kind/'runs'
                    self.assertEqual(archive.runs_root(path, allowed_campaigns=[root/'campaign']), path)
                    with self.assertRaises(ValueError):
                        archive.runs_root(path)
            for path in (root/'outside/eval/native/learned/known-recovery/runs',
                         root/'campaign/eval/native/policy/known-recovery/runs',
                         root/'campaign/eval/native/random/other/runs'):
                with self.assertRaises(ValueError):
                    archive.runs_root(path, allowed_campaigns=[root/'campaign'])
            real = root/'campaign/real'; real.mkdir(parents=True)
            (root/'campaign/link').symlink_to(real)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                archive.runs_root(root/'campaign/link/native/learned/record/runs', allowed_campaigns=[root/'campaign'])

    def test_archival_proof_and_record_code_identical_to_v4(self):
        for name in ('audit_candidates', 'completed_run', 'file_table', 'verify_bundle',
                     'checked_child', 'claims_record', 'file_identities', 'safe_relative'):
            self.assertEqual(inspect.getsource(getattr(archive, name)), inspect.getsource(getattr(legacy, name)))
        changed = inspect.getsource(archive.archive_runs).replace(', allowed_campaigns=()):', '):').replace(
            'runs_root(directory, allowed_campaigns=allowed_campaigns)', 'runs_root(directory)')
        self.assertEqual(changed, inspect.getsource(legacy.archive_runs))
        changed = inspect.getsource(archive.restore_runs).replace(', *, allowed_campaigns=()):', '):').replace(
            'runs_root(destination, allowed_campaigns=allowed_campaigns)', 'runs_root(destination)')
        self.assertEqual(changed, inspect.getsource(legacy.restore_runs))

    def test_nested_roundtrip_exact_and_persisted_proofs_precede_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); campaign = root/'campaign'
            runs = campaign/'evaluation/native/learned/known-recovery/runs'; run = completed(runs)
            originals = {p.relative_to(runs): p.read_bytes() for p in run.rglob('*') if p.is_file()}
            verified = []; original_verify = archive.verify_bundle; original_remove = archive.shutil.rmtree
            def verification(path, manifest):
                answer = original_verify(path, manifest); verified.append(Path(path)); return answer
            def remove(path):
                self.assertGreaterEqual(len(verified), 2)
                self.assertTrue(any(p.suffix == '.gz' and p.is_file() and not p.stat().st_mode & 0o222 for p in verified))
                manifests = list((root/'archives').glob('*.manifest.json'))
                self.assertEqual(len(manifests), 1)
                self.assertFalse(manifests[0].stat().st_mode & 0o222)
                return original_remove(path)
            with mock.patch.object(archive, 'verify_bundle', side_effect=verification), mock.patch.object(archive.shutil, 'rmtree', side_effect=remove):
                result = archive.archive_runs(runs, root/'archives', max_runs=1, remove_after_verify=True, allowed_campaigns=[campaign])
            self.assertEqual(result['removed_runs'], 1); self.assertFalse(run.exists())
            restored = campaign/'restored/native/random/record/runs'
            archive.restore_runs(result['archive'], result['manifest'], restored, allowed_campaigns=[campaign])
            self.assertEqual({p.relative_to(restored): p.read_bytes() for p in restored.rglob('*') if p.is_file()}, originals)

    def test_nested_active_recent_incomplete_and_explicit_winner_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); runs = root/'eval/native/frozenwarm/record/runs'
            active = runs/'active'; active.mkdir(parents=True)
            recent = completed(runs, 'recent'); os.utime(recent/'worker.log', None)
            winner = completed(runs, 'winner'); write(winner/'WINNER.json', schoolbook())
            old = time.time()-120; os.utime(winner/'WINNER.json', (old, old))
            result = archive.archive_runs(runs, root/'archives', remove_after_verify=True, allowed_campaigns=[root])
            self.assertEqual(result['runs'], 0)
            self.assertTrue(all(p.exists() for p in (active, recent, winner)))

    def test_eligible_record_retained_and_corrupt_unlisted_export_blocks_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); runs = root/'eval/native/random/known-recovery/runs'; run = completed(runs)
            fake = {'dimension': 5, 'field': 2, 'terms': [[1, 1, 1]]}
            write(run/'verified/record.json', fake); old = time.time()-120; os.utime(run/'verified/record.json', (old, old))
            # Control-flow fixture only: no actual <=92 identity is known.
            with mock.patch.object(archive, 'verify_candidate', return_value={'valid': True, 'exact_entries_checked': 15625}), mock.patch.object(
                    archive, 'verify_bytes', return_value={'record_eligible': True, 'exact_entries_checked': 15625}):
                result = archive.archive_runs(runs, root/'archives', remove_after_verify=True, allowed_campaigns=[root])
            self.assertEqual(result['status'], 'record_preserved'); self.assertTrue(run.exists()); self.assertFalse((root/'archives').exists())
            with self.assertRaisesRegex(ValueError, 'exhaustive candidate audit failed'):
                archive.archive_runs(runs, root/'archives', remove_after_verify=True, allowed_campaigns=[root])
            self.assertTrue(run.exists())

    def test_manual_explicit_maintenance_passes_only_policy_campaigns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); campaign = root/'campaign'; prior = root/'prior'; campaign.mkdir(); prior.mkdir(); policy(campaign)
            value = json.loads((campaign/'campaign.json').read_text()); value['prior_campaign'] = str(prior); write(campaign/'campaign.json', value)
            runs = campaign/'eval/native/learned/known-recovery/runs'; runs.mkdir(parents=True)
            callback = mock.Mock(return_value={'runs': 0, 'removed_runs': 0})
            result = maintenance.phase(campaign, {'discover_all_native': False, 'runs_directories': [str(runs)], 'max_runs': 500,
                                                  'archive_output_root': str(prior/'lossless-native-archives42')}, archiver=callback, free_bytes=15*1024**3)
            self.assertEqual(result['source'], str(runs)); self.assertEqual(callback.call_args.kwargs['allowed_campaigns'], [campaign, prior])
            self.assertEqual(callback.call_args.kwargs['max_runs'], 500)
            self.assertTrue(callback.call_args.args[1].is_relative_to(prior))
            self.assertTrue((campaign/'native-maintenance-v5/state.json').exists())
            self.assertFalse((campaign/'native-maintenance-v4/state.json').exists())

    def test_cli_arms_bounded_own_alarm_and_cancels_after_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); config = root/'config.json'; config.write_text('{}')
            with mock.patch.object(maintenance.os, 'sched_setaffinity'), mock.patch.object(maintenance.resource, 'setrlimit'), mock.patch.object(
                    maintenance.signal, 'signal'), mock.patch.object(maintenance.signal, 'alarm') as alarm, mock.patch.object(
                    maintenance, 'phase', return_value={'status': 'TEST_ONLY_NO_ARCHIVE'}) as phase:
                maintenance.main(['--campaign', str(root), '--config', str(config), '--seconds', '600'])
                self.assertEqual(alarm.call_args_list, [mock.call(600), mock.call(0)])
                phase.assert_called_once()
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                maintenance.main(['--campaign', str(root), '--config', str(config), '--seconds', '601'])


if __name__ == '__main__':
    unittest.main()
