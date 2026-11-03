import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mmsearch.marathon7_local12_runtime import compact_negative,select_plan
from mmsearch import surplus_two7
from scripts import marathon7_local12_campaign as worker
from tests import test_marathon7_local as helpers


class Local12RuntimeTests(unittest.TestCase):
    def test_real_small_positive_and_terminal_resume(self):
        with tempfile.TemporaryDirectory() as d,patch.object(helpers,'worker',worker):
            bundle=helpers.tiny_bundle(d);out=Path(d)/'out';_,r=helpers.invoke(bundle,out,'--small-control')
            self.assertEqual(r['status'],'SMALL_CONTROL_PASSED');self.assertEqual(json.loads((out/'SMALL_CONTROL.verification.json').read_text())['exact_entries_checked'],64)
            _,r=helpers.invoke(bundle,out,'--small-control','--resume');self.assertEqual(r['status'],'SMALL_CONTROL_PASSED')

    def test_late_surplus_child_is_open_then_resume(self):
        with tempfile.TemporaryDirectory() as d,patch.object(helpers,'worker',worker):
            bundle=helpers.tiny_bundle(d);out=Path(d)/'out';stop=Path(d)/'stop';actual=surplus_two7.solve_core
            def late(*a,**k):value=actual(*a,**k);stop.touch();return value
            with patch.object(surplus_two7,'solve_core',late):_,r=helpers.invoke(bundle,out,'--small-control','--stop-marker',str(stop))
            self.assertEqual((r['status'],r['queries_this_invocation']),('UNKNOWN',1));self.assertEqual(json.loads((out/'cursor.json').read_text())['next_case'],0)
            self.assertFalse((out/'WINNER.json').exists());self.assertTrue((out/'current/core.json').exists())
            stop.unlink();_,r=helpers.invoke(bundle,out,'--small-control','--stop-marker',str(stop),'--resume');self.assertEqual(r['status'],'SMALL_CONTROL_PASSED')

    def test_full_repeated_extension_negative_census(self):
        first=sum(1<<(i*6+i) for i in range(3));second=sum(1<<(i*6+i) for i in range(3,6));r=surplus_two7.solve_pair_image([first,second],6,6,4)
        self.assertEqual(r['status'],'LOCAL_UNSAT');c=compact_negative(r);self.assertNotIn('tested_extensions',c)
        with self.assertRaises(ValueError):compact_negative(dict(r,extension_cursor=1))
        with self.assertRaises(ValueError):compact_negative(dict(r,complete=False))

    def test_pilot_scope_rejects_old10_and_corrupt_mask(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);case=dict(mask_lo=(1<<12)-1,mask_hi=0,source_indices=list(range(12)),source_products=93,source_local_products=12,target_local_products=11,mode_rank=9,shape=[9,8,8],free_axis=0)
            (root/'plan.json').write_text(json.dumps(dict(cases=[case])));self.assertEqual(len(select_plan(root)['cases']),1)
            for change in [dict(source_local_products=10),dict(target_local_products=9),dict(mask_hi=1),dict(shape=[10,8,8])]:
                (root/'plan.json').write_text(json.dumps(dict(cases=[dict(case,**change)])))
                with self.assertRaises(ValueError):select_plan(root)


if __name__=='__main__':unittest.main()
