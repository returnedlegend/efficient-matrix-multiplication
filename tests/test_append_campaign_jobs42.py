import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import append_campaign_jobs42 as helper


class AppendJobsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.queue = self.root / 'queue.json'
        self.proposal = self.root / 'proposal.json'
        self.receipt = self.root / 'receipt.json'
        self.job = {'id': 'example-1', 'cpu': 2, 'memory_mb': 768, 'seconds': 30,
                    'command': ['env', 'PYTHONDONTWRITEBYTECODE=1', 'python3', '-B', 'worker.py'], 'enabled': False}
        self.write(self.queue, {'jobs': []})

    def write(self, path, value):
        path.write_text(json.dumps(value) + '\n')

    def run_helper(self, proposal=None, **kwargs):
        self.write(self.proposal, self.job if proposal is None else proposal)
        return helper.append_jobs(self.queue, self.proposal,
                                  hashlib.sha256(self.proposal.read_bytes()).hexdigest(), self.receipt, **kwargs)

    def test_preview_never_opens_lock_or_writes_receipt_or_queue(self):
        before = self.queue.read_bytes()
        report = self.run_helper(enable=True)
        self.assertEqual(report['status'], 'PREVIEW_ONLY')
        self.assertEqual(self.queue.read_bytes(), before)
        self.assertFalse(self.receipt.exists())
        self.assertFalse((self.root / 'queue_append.lock').exists())

    def test_real_validator_rejects_shell_string_extra_key_and_nul_before_writes(self):
        for update in ({'command': 'python worker.py'}, {'note': 'extra'}, {'command': ['python3', 'bad\0arg']}):
            with self.subTest(update=update):
                bad = {**self.job, **update}
                with self.assertRaises(ValueError):
                    self.run_helper(bad, apply=True)
                self.assertEqual(json.loads(self.queue.read_text()), {'jobs': []})
                self.assertFalse(self.receipt.exists())

    def test_invalid_existing_queue_and_duplicate_proposal_reject(self):
        bad = {**self.job, 'command': 'shell string'}
        self.write(self.queue, {'jobs': [bad]})
        with self.assertRaisesRegex(ValueError, 'argv'):
            self.run_helper(apply=True)
        self.write(self.queue, {'jobs': []})
        with self.assertRaisesRegex(ValueError, 'duplicate proposal'):
            self.run_helper({'jobs': [self.job, self.job]}, apply=True)
        self.assertFalse(self.receipt.exists())

    def test_append_receipt_and_idempotent_same_job_preserve_bytes(self):
        report = self.run_helper({'jobs': [self.job]}, apply=True)
        self.assertEqual(report['status'], 'COMMITTED')
        self.assertEqual(report['effective_jobs'], [self.job])
        self.assertEqual(report['queue_after_sha256'], hashlib.sha256(self.queue.read_bytes()).hexdigest())
        self.assertEqual(report['helper_sha256'], hashlib.sha256(Path(helper.__file__).read_bytes()).hexdigest())
        self.assertEqual(report['validator_sha256'], hashlib.sha256(Path(helper.coordinator.__file__).read_bytes()).hexdigest())
        before = self.queue.read_bytes()
        replay = self.run_helper({'jobs': [self.job]}, apply=True)
        self.assertTrue(replay['idempotent_receipt_replay'])
        self.assertEqual(self.queue.read_bytes(), before)
        self.receipt = self.root / 'second-receipt.json'
        self.assertFalse(self.run_helper(apply=True)['queue_changed'])
        self.assertEqual(self.queue.read_bytes(), before)

    def test_mutated_duplicate_and_disable_cannot_change_queue(self):
        self.write(self.queue, {'jobs': [self.job]})
        before = self.queue.read_bytes()
        with self.assertRaisesRegex(ValueError, 'duplicate id mutation'):
            self.run_helper({**self.job, 'seconds': 31}, apply=True, enable=True)
        self.assertEqual(self.queue.read_bytes(), before)
        self.write(self.queue, {'jobs': [{**self.job, 'enabled': True}]})
        with self.assertRaisesRegex(ValueError, 'mutation'):
            self.run_helper(apply=True)

    def test_enable_requires_flag_and_only_changes_enabled(self):
        self.write(self.queue, {'jobs': [self.job]})
        with self.assertRaisesRegex(ValueError, 'mutation'):
            self.run_helper({**self.job, 'enabled': True}, apply=True)
        report = self.run_helper(apply=True, enable=True)
        self.assertEqual(report['actions'], [{'id': self.job['id'], 'action': 'enable'}])
        self.assertEqual(json.loads(self.queue.read_text())['jobs'], [{**self.job, 'enabled': True}])
        self.write(self.queue, {'jobs': []}); self.receipt = self.root / 'other.json'
        with self.assertRaisesRegex(ValueError, 'explicit --enable'):
            self.run_helper({**self.job, 'enabled': True}, apply=True)

    def test_changed_proposal_hash_or_receipt_binding_fails_closed(self):
        self.write(self.proposal, self.job)
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            helper.append_jobs(self.queue, self.proposal, '0' * 64, self.receipt, apply=True)
        self.run_helper(apply=True)
        with self.assertRaisesRegex(ValueError, 'receipt request binding'):
            self.run_helper({**self.job, 'id': 'other'}, apply=True)
        self.assertEqual(len(json.loads(self.queue.read_text())['jobs']), 1)

    def test_intent_survives_queue_write_failure_and_retry_recovers(self):
        original = helper.atomic
        def fail_queue(path, value):
            if path == self.queue:
                raise OSError('injected write failure')
            return original(path, value)
        with mock.patch.object(helper, 'atomic', side_effect=fail_queue):
            with self.assertRaises(OSError):
                self.run_helper(apply=True)
        self.assertEqual(json.loads(self.receipt.read_text())['status'], 'INTENT')
        self.assertEqual(json.loads(self.queue.read_text()), {'jobs': []})
        self.assertEqual(self.run_helper(apply=True)['status'], 'COMMITTED')

    def test_committed_queue_pending_receipt_retry_preserves_original_intent(self):
        original = helper.atomic
        def fail_commit(path, value):
            if path == self.receipt and value['status'] == 'COMMITTED':
                raise OSError('injected receipt commit failure')
            return original(path, value)
        with mock.patch.object(helper, 'atomic', side_effect=fail_commit):
            with self.assertRaises(OSError):
                self.run_helper(apply=True)
        before = self.queue.read_bytes()
        intent = json.loads(self.receipt.read_text())
        result = self.run_helper(apply=True)
        self.assertEqual(self.queue.read_bytes(), before)
        self.assertEqual(result['recovered_intent']['queue_before_sha256'], intent['queue_before_sha256'])
        self.assertEqual(result['recovered_intent']['actions'], [{'id': self.job['id'], 'action': 'append'}])
        self.assertEqual(result['actions'], [{'id': self.job['id'], 'action': 'unchanged'}])

    def test_locked_reread_revalidates_whole_queue_and_fsyncs(self):
        real = helper.coordinator.queue_value
        calls = []
        def changed(path):
            calls.append(path)
            if len(calls) == 2:
                self.write(path, {'jobs': [{**self.job, 'command': 'invalid changed while locking'}]})
            return real(path)
        with mock.patch.object(helper.coordinator, 'queue_value', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'argv'):
                self.run_helper(apply=True)
        self.assertFalse(self.receipt.exists())
        self.write(self.queue, {'jobs': []})
        with mock.patch.object(helper.os, 'fsync', wraps=helper.os.fsync) as sync:
            self.run_helper(apply=True)
        self.assertGreaterEqual(sync.call_count, 6)  # Intent, queue, receipt: file and directory.


if __name__ == '__main__':
    unittest.main()
