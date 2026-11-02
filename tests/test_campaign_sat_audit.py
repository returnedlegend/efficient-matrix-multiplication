import json
from pathlib import Path
import tempfile
import unittest

from scripts.campaign_sat_audit import audit


def solve(status, support='union', **restrictions):
    return dict(event='solve', status=status,
        patch=dict(source_sha256='a'*64, active_terms=[0], drop_term=7,
                   active_count=1, patch_id='b'*64, support_mode=support),
        problem=dict(field=2, support_mode=support, **restrictions))


def worker(root, name, encoding, records):
    path = root/name
    path.mkdir()
    (path/'manifest.json').write_text(json.dumps(dict(identity=dict(dimension=2, target_rank=7),
                                                    encoding=encoding, attempts=len(records))))
    (path/'results.jsonl').write_text(''.join(json.dumps(record)+'\n' for record in records))
    return path


class SatAuditTests(unittest.TestCase):
    def test_uniform_union_full_image_merge_same_local_feasibility(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker(root, 'sat', None, [solve('UNKNOWN', 'union'), solve('UNSAT', 'full')])
            bound = dict(event='koszul_reject', status='LOCAL_UNSAT_BOUND',
                         patch=dict(solve('UNKNOWN')['patch'], support_mode='image', koszul=dict(field=2)))
            worker(root, 'compact', 'exact-multilinear-image-v1', [bound])
            report = audit(root)
            self.assertTrue(report['audit_valid'])
            self.assertEqual(report['uniform_summary']['neighborhoods'], 1)
            self.assertEqual(report['uniform_summary']['bound_and_solver_unsat'], 1)
            self.assertEqual(report['uniform_summary']['unknown_only'], 0)
            self.assertEqual(report['raw_record_counts'], dict(UNKNOWN=1, UNSAT=1, BOUND=1))

    def test_fixed_or_nonuniform_slot_constraints_split_conditional_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker(root, 'sat', None, [solve('UNKNOWN'), solve('UNSAT', fixed_factors={'slot0.u': [1, 0]})])
            report = audit(root)
            self.assertEqual(report['uniform_summary']['unknown_only'], 1)
            self.assertEqual(report['conditional_summary']['solver_unsat'], 1)
            self.assertEqual(len(report['neighborhoods']), 2)

    def test_unrecognized_dictionary_branch_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker(root, 'dictionary903', 'fixed-dictionary-v1', [solve('UNSAT')])
            report = audit(root)
            self.assertFalse(report['raw_record_counts'])
            self.assertEqual(len(report['excluded_workers']), 1)

    def test_contradictory_result_is_invalid_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker(root, 'sat', None, [solve('SAT'), solve('UNSAT')])
            report = audit(root)
            self.assertFalse(report['audit_valid'])
            self.assertEqual(report['uniform_summary']['contradictions'], 1)

    def test_live_partial_tail_visible_and_malformed_complete_line_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = worker(root, 'sat', None, [solve('UNKNOWN')])/'results.jsonl'
            with path.open('a') as handle:
                handle.write('{"event":')
            report = audit(root)
            self.assertTrue(report['audit_valid'])
            self.assertEqual(report['diagnostics'][0]['kind'], 'partial_live_tail')
            with path.open('a') as handle:
                handle.write('\n')
            self.assertFalse(audit(root)['audit_valid'])

    def test_replay_uses_verified_log_prefix_and_saved_manifest_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = worker(root, 'sat', None, [solve('UNKNOWN')])
            snapshot = audit(root)
            with (folder/'results.jsonl').open('a') as handle:
                handle.write(json.dumps(solve('SAT'))+'\n')
            manifest = json.loads((folder/'manifest.json').read_text())
            manifest['attempts'] = 2
            (folder/'manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(audit(root)['uniform_summary']['sat'], 1)
            replay = audit(root, replay=snapshot)
            self.assertEqual(replay['uniform_summary'], snapshot['uniform_summary'])
            self.assertEqual(replay['raw_record_counts'], snapshot['raw_record_counts'])
            self.assertEqual(replay['workers'][0]['manifest_attempts'], 1)
            text = (folder/'results.jsonl').read_text().replace('UNKNOWN', 'UNSAT')
            (folder/'results.jsonl').write_text(text)
            with self.assertRaises(ValueError):
                audit(root, replay=snapshot)


if __name__ == '__main__':
    unittest.main()
