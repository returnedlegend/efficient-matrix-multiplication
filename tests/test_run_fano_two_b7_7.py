import tempfile
from pathlib import Path
import unittest
from mmsearch.extend_eight_bulk43 import SourceCache
from scripts.run_fano_two_b7_7 import run_branch,publish_receipt
from scripts.run_c3_mixed12_pilot7 import reviewed_solver
from tests.test_run_c3_mixed12_pilot7 import planted
from tests.test_run_c3_mixed9_pilot7 import Guard


class FanoRunnerControls(unittest.TestCase):
    def test_branch_negative_is_not_complete_CP14_negative(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);case=planted(root,8,9)
            solver=lambda *a,**k:dict(status='FANO_BRANCH_UNSAT',complete=True,fano_branch_complete=True,assumptions=[])
            result=run_branch(SourceCache(root),case,root/'out',Guard(),solver=solver)
            self.assertEqual(result['status'],'FANO_BRANCH_UNSAT');self.assertTrue(result['fano_branch_complete'])
            self.assertFalse(result['full_CP14_negative']);self.assertFalse((root/'out/records').exists())

    def test_assumed_negative_and_late_negative_remain_unknown(self):
        for late in (False,True):
            with self.subTest(late=late),tempfile.TemporaryDirectory() as t:
                root=Path(t);case=planted(root,8,9);guard=Guard()
                def solver(*a,**k):
                    if late:guard.now=76
                    return dict(status='FANO_BRANCH_UNSAT' if late else 'FANO_ASSUMPTIONS_UNSAT',complete=True,fano_branch_complete=late,assumptions=[] if late else [1])
                result=run_branch(SourceCache(root),case,root/'out',guard,solver=solver)
                self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['fano_branch_complete'])

    def test_existing_whole_tensor_primary_and_independent_positive_gates(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);case=planted(root,8,9)
            result=run_branch(SourceCache(root),case,root/'out',Guard(),solver=reviewed_solver,control_expected_rank=27)
            self.assertEqual(result['status'],'SMALL_CONTROL_PASSED',result)
            self.assertEqual(result['legacy_result']['primary']['exact_entries_checked'],729)
            self.assertEqual(result['legacy_result']['independent']['exact_entries_checked'],729)

    def test_error_and_after_receipt_hold_preserve_distinct_status(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);case=planted(root,8,9)
            result=run_branch(SourceCache(root),case,root/'error',Guard(),solver=lambda *a,**k:dict(status='ERROR'))
            self.assertEqual(result['status'],'ERROR')
            class Late(Guard):
                def check(self,stage):
                    if stage=='post_fano_branch_receipt':self.signal_stop=True
                    return super().check(stage)
            from mmsearch.marathon7_cached_guard import CampaignHold
            with self.assertRaises(CampaignHold):publish_receipt(root/'late',dict(status='FANO_BRANCH_UNSAT'),Late())
            self.assertFalse((root/'late/branch-receipt.json').exists())
            self.assertTrue((root/'late/.raw-returns/late-branch-receipt.raw').exists())


if __name__=='__main__':unittest.main()
