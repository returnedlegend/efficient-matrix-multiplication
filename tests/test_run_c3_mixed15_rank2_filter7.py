import tempfile,unittest
from pathlib import Path
from scripts.run_c3_mixed15_rank2_filter7 import checked_bound,run_case
from tests.test_surplus_two_large7_planted import planted
from tests.test_run_c3_mixed9_pilot7 import Guard
from mmsearch.extend_eight_bulk43 import SourceCache
from mmsearch.compact_eight43 import factor_core
from mmsearch.compact_coset43 import mode_slices

def diagonal(indices,n):return sum(1<<(i*n+i) for i in indices)
class NecessaryFilterControls(unittest.TestCase):
    def test_true_c2_d12_pass_is_not_existence_or_exact_fullspan_claim(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source,terms,case=planted(root);r=run_case(SourceCache(root),case,root/'out',Guard());self.assertEqual(r['status'],'NOT_EXCLUDED');self.assertFalse(r['existence_claim']);self.assertEqual(r['cp_decoder_calls'],0);self.assertGreaterEqual(r['raw_filter']['observed_rank2_span_rank'],11)
            if not r['raw_filter']['enumeration_complete']:self.assertIsNone(r['raw_filter']['rank2_span_rank'])
    def test_necessary_pass_can_be_cp_infeasible_and_negative_is_full(self):
        # A single rank2 matrix needs CP2 but passes the CP1 necessary condition.
        r=checked_bound([9],2,2,1);self.assertEqual(r['status'],'NOT_EXCLUDED');self.assertFalse(r['existence_claim'])
        r=checked_bound([diagonal(range(2),8),diagonal(range(2,5),8),diagonal(range(5,8),8)],8,8,5);self.assertEqual(r['status'],'EXCLUDED');self.assertTrue(r['enumeration_complete']);self.assertEqual(r['enumerated_vectors'],7);self.assertEqual(r['rank2_span_rank'],1)
    def test_cancel_and_late_necessary_pass_are_unknown_hidden(self):
        self.assertEqual(checked_bound([1],1,1,1,cancelled=lambda:True)['status'],'UNKNOWN')
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);_,_,case=planted(root);g=Guard()
            def late(*a,**kw):
                r=checked_bound(*a,**kw);g.now=61;return r
            r=run_case(SourceCache(root),case,root/'out',g,classifier=late);self.assertEqual(r['status'],'UNKNOWN');self.assertFalse((root/'out'/(case['id']+'.result.json')).exists());self.assertTrue(list((root/'out/.raw-returns').glob('*.raw')))
if __name__=='__main__':unittest.main()
