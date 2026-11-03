"""Synthetic reports only: no workers or campaign state are touched."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1]/'scripts/rl_campaign_queue_v2.py'
SPEC = importlib.util.spec_from_file_location('queue_v2_test', SOURCE)
QUEUE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUEUE)


class QueueV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='queue-v2-test-')
        self.directory = Path(self.temp.name)
        self.supervisor = QUEUE.Supervisor(self.directory, now=lambda: 1000)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, path, value):
        path = self.directory/path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def candidate(self, rank=92, dimension=5):
        return dict(dimension=dimension, field=2,
                    terms=[[i+1, 1, 1] for i in range(rank)])

    def test_nested_found_and_scheduling_stop(self):
        self.write('dictionary-new1/solve/FOUND.json', self.candidate())
        self.write('campaign.json', dict(deadline_utc=QUEUE.base.utc(2000), field=2,
            target_rank=92, max_cpu_cores=4, max_ram_gib=8))
        self.assertFalse(self.supervisor.tick())
        reason = self.supervisor.state['stop_reason']
        self.assertIn('dictionary-new1/solve/FOUND.json', reason)
        self.assertIn('unverified by supervisor', reason)
        self.assertEqual(self.supervisor.state['jobs'], {})

    def test_hardpool_records_with_dense_terms(self):
        vector = [1]+[0]*24
        value = dict(dimension=5, field=2, terms=[dict(u=vector, v=vector, w=vector)])
        self.write('pool-hard/task/records/hash.json', value)
        self.assertIn('pool-hard/task/records/hash.json', self.supervisor.reported_target(92))

    def test_controls_and_invalid_reports_are_ignored(self):
        for path, value in [
            ('dictionary/control/FOUND.json', self.candidate(7, 2)),
            ('hardpool/records/rank93.json', self.candidate(93)),
            ('hardpool/records/empty.json', self.candidate(0)),
            ('hardpool/records/report.verification.json', {'valid': True, 'rank': 1}),
            ('bad/FOUND.json', dict(dimension=5, field=2, terms=[[True, 1, 1]])),
        ]:
            self.write(path, value)
        self.assertIsNone(self.supervisor.reported_target(92))

    def test_canonical_parity_and_zeros(self):
        value = self.candidate(93)
        value['terms'] += [[1, 1, 1], [0, 1, 1]]
        self.write('pool/records/reduced.json', value)
        self.assertIn('terms=92', self.supervisor.reported_target(92))
        self.write('pool/records/reduced.json', dict(dimension=5, field=2,
                                                   terms=[[1, 1, 1], [1, 1, 1]]))
        self.assertIsNone(self.supervisor.reported_target(92))

    def test_base_behavior_and_dependency_audit(self):
        self.write('WINNER.json', {})
        self.assertIn('WINNER file reported', self.supervisor.reported_target(92))
        self.supervisor.save()
        self.supervisor.record('synthetic_audit')
        state = json.loads((self.directory/'queue_state.json').read_text())
        event = json.loads((self.directory/'queue_events.jsonl').read_text())
        extension_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        base_hash = hashlib.sha256(SOURCE.with_name('rl_campaign_queue.py').read_bytes()).hexdigest()
        self.assertEqual(state['supervisor_code_sha256'], extension_hash)
        self.assertEqual(event['code_sha256'], extension_hash)
        self.assertEqual(state['base_dependency_sha256'], base_hash)
        self.assertEqual(event['base_dependency_sha256'], base_hash)
        restarted = QUEUE.Supervisor(self.directory)
        self.assertEqual(restarted.state['base_dependency_sha256'], base_hash)


if __name__ == '__main__':
    unittest.main()
