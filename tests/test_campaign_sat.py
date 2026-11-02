import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from mmsearch.tensor import naive_candidate
from mmsearch.verify import verify_candidate
from scripts.campaign_sat import Campaign, PatchStream, arguments, load_source, retain_problems, save


class CampaignTests(unittest.TestCase):
    def test_strict_canonical_sources_and_permutation_dedup(self):
        source = naive_candidate(1)
        source['terms'].append({'u': [0], 'v': [0], 'w': [0]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.json'
            save(path, source)
            first = load_source(path, 1, 1)
            source['terms'].reverse()
            source['terms'][1]['u'][0] = -1
            save(path, source)
            second = load_source(path, 1, 1)
            self.assertEqual(first[1], second[1])
            self.assertNotEqual(first[2], second[2])
            for value in (1.0, True, 3):
                corrupt = copy.deepcopy(source)
                corrupt['terms'][1]['u'][0] = value
                save(path, corrupt)
                with self.assertRaises(ValueError):
                    load_source(path, 1, 1)
            path.write_text('{"field":2,"field":2}')
            with self.assertRaises(ValueError):
                load_source(path, 1, 1)

    def test_patch_stream_restart_reproducible(self):
        source = naive_candidate(2)
        a, b = PatchStream(source, 19, 1, 7), PatchStream(source, 19, 1, 7)
        self.assertEqual([a.proposal(i) for i in range(40)], [b.proposal(i) for i in range(40)])
        for i in range(40):
            proposal = a.proposal(i)
            if proposal:
                self.assertLessEqual(max(proposal['flattening_ranks']), proposal['active_count'])

    def test_unknown_escalation_finite_and_unsat_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign = Campaign(arguments(['--output-dir', directory]))
            campaign.state['attempts'] = 5
            campaign.state['patches'] = {
                'a': dict(status='UNSAT', level=0, last_attempt=0),
                'b': dict(status='UNKNOWN', level=0, last_attempt=1),
            }
            self.assertEqual(campaign.next_patch()['level'], 1)
            self.assertEqual(campaign.next_patch()['level'], 2)
            self.assertIsNone(campaign.next_patch())
            self.assertEqual(campaign.state['patches']['a']['level'], 0)

    def test_recursive_snapshot_ingestion_and_restart(self):
        source = naive_candidate(1)
        source['terms'].append({'u': [0], 'v': [0], 'w': [0]})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'native' / 'nested' / 'exact.json'
            save(path, source)
            args = arguments(['--input', str(path), '--seed-dir', str(root / 'native'),
                              '--output-dir', str(root / 'out'), '--rank', '1', '--dimension', '1'])
            campaign = Campaign(args)
            campaign.scan(force=True)
            self.assertEqual(len(campaign.state['sources']), 1)
            campaign.state['source_cursor'] = 19
            save(campaign.path, campaign.state)
            restarted = Campaign(args)
            self.assertEqual(restarted.state['source_cursor'], 19)
            self.assertEqual(len(restarted.state['sources']), 1)

    def test_cnf_count_and_byte_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(3):
                (root / f'{index}.cnf').write_text('x'*10)
                (root / f'{index}.map.json').write_text('{}')
            retain_problems(root, 2, 100)
            self.assertEqual(len(list(root.glob('*.cnf'))), 2)
            retain_problems(root, 2, 11)
            self.assertFalse(list(root.glob('*.cnf')))
            self.assertFalse(list(root.glob('*.map.json')))

    @unittest.skipUnless(importlib.util.find_spec('pysat'), 'python-sat missing')
    def test_planted_exact_solution_frozen_with_provenance(self):
        source = naive_candidate(1)
        source['terms'].append({'u': [0], 'v': [0], 'w': [0]})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'source.json'
            save(path, source)
            args = arguments(['--input', str(path), '--output-dir', str(root / 'out'),
                '--rank', '1', '--dimension', '1', '--k-min', '1', '--k-max', '1',
                '--max-runs', '1', '--seconds', '4', '--patch-seconds', '2'])
            campaign = Campaign(args)
            summary = campaign.run()
            self.assertEqual(summary['counters']['SAT'], 1)
            candidate = json.loads((root / 'out' / 'FOUND.json').read_text())
            self.assertTrue(verify_candidate(candidate)['valid'])
            self.assertIn('cnf_sha256', candidate['metadata']['campaign_provenance'])
            attempts = Campaign(args).run()['attempts']
            self.assertEqual(attempts, 1)


if __name__ == '__main__':
    unittest.main()
