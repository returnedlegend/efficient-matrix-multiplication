import tempfile,unittest
from pathlib import Path
from mmsearch.surplus_two_large7 import solve_pair_image
from mmsearch.compact_coset43 import expand_products
from mmsearch.extend_eight_bulk43 import SourceCache
from scripts.run_c3_mixed15_largeS2_7 import PinnedCache,reviewed_solver,run_case
from tests.test_surplus_two_large7_planted import planted
from tests.test_run_c3_mixed9_pilot7 import Guard
class LargeS2AdapterControls(unittest.TestCase):
    def test_rank3_corank_one_at_actual_image_dimension12(self):
        n=14;raw=[sum(1<<(i*n+i) for i in range(3))]+[1<<(i*n+i) for i in range(3,14)]
        self.assertEqual(solve_pair_image(raw,n,n,13)['status'],'LOCAL_UNSAT')
        r=solve_pair_image(raw,n,n,14);self.assertEqual(r['status'],'SAT');self.assertEqual(r['case'],'exact_corank_one_backbone');self.assertEqual(r['inside_rank'],11);self.assertEqual(len(r['support']),14)
        for value,mask in zip(raw,r['target_coordinates']):
            actual=0
            for i,p in enumerate(r['support']):
                if mask>>i&1:actual^=p['column']
            self.assertEqual(actual,value)
    def test_true_c2_whole_n4_and_pinned_core_binding(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);_,_,case=planted(root);r=SourceCache(root).core(case);case.update(expected_core_math_sha256=r[4],expected_core_input_sha256=r[5]);result=run_case(PinnedCache(root),case,root/'out',Guard(),control_expected_rank=63)
            self.assertEqual(result['status'],'SMALL_CONTROL_PASSED');self.assertEqual(result['primary']['exact_entries_checked'],4096);self.assertEqual(result['independent']['exact_entries_checked'],4096)
            case['expected_core_input_sha256']='0'*64
            with self.assertRaises(ValueError):PinnedCache(root).core(case)
    def test_late_true_c2_is_hidden_unknown(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);_,_,case=planted(root);g=Guard()
            def late(*a,**kw):
                r=reviewed_solver(*a,**kw);g.now=21;return r
            result=run_case(SourceCache(root),case,root/'late',g,solver=late,control_expected_rank=63)
            self.assertEqual(result['status'],'UNKNOWN');self.assertFalse((root/'late/records').exists());self.assertTrue(list((root/'late/.raw-returns').glob('*.raw')))
if __name__=='__main__':unittest.main()
