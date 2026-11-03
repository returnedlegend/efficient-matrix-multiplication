import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.campaign_breadth_weight443 import (SOURCE_FILES,JOB_SPEC_KEYS,resume_terminal,
    validate_gap_selection,validate_job_spec)


class BreadthWeight443Tests(unittest.TestCase):
    def test_exact_six_gap_four_family_guard(self):
        labels=['b00','b01','b02','b03']
        plan=[dict(id=f'b01-{i}',source_case='b01') for i in range(3)]+[
            dict(id=f'b02-{i}',source_case='b02') for i in range(2)]+[dict(id='b03-0',source_case='b03')]
        self.assertTrue(validate_gap_selection(plan,labels))
        for changed in [plan[:-1],plan+[dict(id='extra',source_case='b01')],plan[:-1]+[plan[0]],
                plan[:-1]+[dict(id='other',source_case='old-model')]]:
            with self.assertRaises(AssertionError):validate_gap_selection(changed,labels)
        with self.assertRaises(AssertionError):validate_gap_selection(plan,labels[:-1])

    def test_strict_queue_schema(self):
        spec=dict(id='pilot',cpu=1,memory_mb=1024,seconds=315,command=['python','pilot.py'],enabled=False)
        self.assertEqual(set(spec),JOB_SPEC_KEYS);self.assertTrue(validate_job_spec(spec))
        with self.assertRaises(ValueError):validate_job_spec(dict(spec,note='not allowed'))

    def test_terminal_resume_and_local_source_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.assertEqual(resume_terminal(root,dict(last_status='ERROR')),'ERROR')
            self.assertIsNone(resume_terminal(root,dict(last_status='UNKNOWN')))
            (root/'WINNER.json').write_text('{}')
            with patch('scripts.campaign_observed_plane42.verify_candidate',return_value=dict(
                    valid=True,rank=92,exact_entries_checked=15625)):
                self.assertEqual(resume_terminal(root,dict(last_status='SAT')),'SAT')
        root=Path(__file__).resolve().parents[1]
        for relative in SOURCE_FILES:
            parts=list(Path(relative).with_suffix('').parts)
            for node in ast.walk(ast.parse((root/relative).read_text())):
                if not isinstance(node,ast.ImportFrom):continue
                module=(parts[:-node.level] if node.level else [])+(node.module.split('.') if node.module else [])
                if module and module[0] in ['mmsearch','scripts']:
                    self.assertIn('/'.join(module)+'.py',SOURCE_FILES)


if __name__=='__main__':unittest.main()
