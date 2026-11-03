"""Synthetic queue safety checks: no subprocess or research work is launched."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    'rl_campaign_queue', Path(__file__).resolve().parents[1]/'scripts/rl_campaign_queue.py')
QUEUE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUEUE)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='queue-test-')
        self.directory = Path(self.temp.name)
        self.clock = [1000.0]
        self.identities = {}
        self.launches = []
        self.write('campaign.json', dict(deadline_utc=QUEUE.utc(2000), field=2,
            target_rank=92, max_cpu_cores=4, max_ram_gib=8))

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value):
        path = self.directory/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def job(self, name='one', cpu=0, memory=768, enabled=True):
        return dict(id=name, cpu=cpu, memory_mb=memory, seconds=600,
                    command=['python3', 'synthetic-only.py', 'literal;not-shell'], enabled=enabled)

    def launch(self, command, prefix):
        self.launches.append((command, prefix))
        pid = 100+len(self.launches)
        self.identities[pid] = dict(start_ticks=pid, started_unix=self.clock[0])
        return pid

    def supervisor(self):
        return QUEUE.Supervisor(self.directory, now=lambda: self.clock[0],
            identity=lambda pid: self.identities.get(pid), launch=self.launch)

    def test_default_empty_and_duplicate_ids_fail_closed(self):
        supervisor = self.supervisor()
        self.assertTrue(supervisor.tick())
        self.assertEqual(self.launches, [])
        self.write('queue.json', {'jobs': [self.job(), self.job()]})
        self.assertTrue(supervisor.tick())
        self.assertIn('duplicate job id', supervisor.state['last_error'])
        self.assertEqual(self.launches, [])

    def test_core_collision_and_restart_never_duplicate(self):
        self.identities[5] = dict(start_ticks=5, started_unix=1000)
        self.write('external-job.running.json', dict(pid=5, started_utc=QUEUE.utc(1000),
                                                   cpu=0, memory_mb=768))
        self.write('queue.json', {'jobs': [self.job('blocked', 0), self.job('free', 1), self.job('samecore', 1)]})
        supervisor = self.supervisor()
        supervisor.tick()
        self.assertEqual(len(self.launches), 1)
        self.assertEqual(supervisor.state['jobs']['free']['spec']['cpu'], 1)
        self.assertEqual(self.launches[0][0][-1], 'literal;not-shell')
        self.supervisor().tick()
        self.assertEqual(len(self.launches), 1)
        self.write('free-job.result.json', dict(exit_code=0, timed_out=False))
        self.identities.pop(101)
        restarted = self.supervisor()
        restarted.tick()
        self.assertEqual(restarted.state['jobs']['free']['status'], 'completed')
        self.assertEqual(len(self.launches), 2)  # next samecore job, never free again
        self.assertEqual([prefix.name for _, prefix in self.launches], ['free-job', 'samecore-job'])
        record = restarted.state['jobs']['free']
        self.assertEqual(len(record['queue_sha256']), 64)
        self.assertEqual(len(record['code_sha256']), 64)

    def test_memory_cap_and_disabled_jobs(self):
        self.identities[5] = dict(start_ticks=5, started_unix=1000)
        self.write('external-job.running.json', dict(pid=5, started_utc=QUEUE.utc(1000), cpu=0, memory_mb=4096))
        self.write('queue.json', {'jobs': [self.job('large', 1, 3072), self.job('fits', 2, 2048), self.job('off', 3, enabled=False)]})
        supervisor = self.supervisor()
        supervisor.tick()
        self.assertEqual([prefix.name for _, prefix in self.launches], ['fits-job'])
        self.assertEqual(supervisor.state['requested_active_memory_mb'], 6144)

    def test_deadline_and_stop_reason_persist_without_killing(self):
        self.clock[0] = 2001
        self.write('queue.json', {'jobs': [self.job()]})
        supervisor = self.supervisor()
        self.assertFalse(supervisor.tick())
        reason = supervisor.state['stop_reason']
        self.clock[0] = 1000
        self.assertFalse(self.supervisor().tick())
        self.assertEqual(self.supervisor().state['stop_reason'], reason)
        self.assertEqual(self.launches, [])

    def test_winner_and_recovery_scope(self):
        self.write('queue.json', {'jobs': [self.job()]})
        self.write('recovery/best.json', dict(dimension=5, field=2, terms=[{}]*93,
            metadata=dict(rank=93, target_reached=True)))
        supervisor = self.supervisor()
        self.assertIsNone(supervisor.reported_target(92))
        self.write('branch/WINNER.json', {'unverified_report_only': True})
        self.assertFalse(supervisor.tick())
        self.assertIn('WINNER', supervisor.state['stop_reason'])
        self.assertEqual(self.launches, [])

    def test_crashed_intent_and_stale_registration_never_relaunch(self):
        self.write('queue.json', {'jobs': [self.job('intent'), self.job('stale', 1)]})
        supervisor = self.supervisor()
        supervisor.state['jobs']['intent'] = dict(status='launching',
            attempted_utc=QUEUE.utc(900), spec=self.job('intent'))
        supervisor.save()
        self.write('stale-job.running.json', dict(pid=99999, started_utc=QUEUE.utc(900), cpu=1, memory_mb=768))
        supervisor = self.supervisor()
        supervisor.tick()
        self.assertEqual(supervisor.state['jobs']['intent']['status'], 'held_ambiguous')
        self.assertEqual(supervisor.state['jobs']['stale']['status'], 'held_ambiguous')
        self.assertEqual(self.launches, [])

    def test_partial_metadata_and_invalid_cpu_block_launch(self):
        self.write('queue.json', {'jobs': [self.job()]})
        (self.directory/'partial-job.running.json').write_text('{')
        supervisor = self.supervisor()
        supervisor.tick()
        self.assertIsNotNone(supervisor.state['last_error'])
        (self.directory/'partial-job.running.json').unlink()
        self.write('queue.json', {'jobs': [self.job(cpu=4)]})
        supervisor.tick()
        self.assertIn('0..3', supervisor.state['last_error'])
        self.assertEqual(self.launches, [])


if __name__ == '__main__':
    unittest.main()
