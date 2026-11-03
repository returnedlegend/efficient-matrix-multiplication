import itertools
import unittest
from unittest.mock import patch

from mmsearch import binary_small_slot_repair7 as subject
from mmsearch.binary_block_descent7 import HARD_DEADLINE, residual_loss
from tests.test_binary_block_descent7 import expand,strassen


@patch('mmsearch.binary_block_descent7.time.time',return_value=HARD_DEADLINE-60)
class SmallSlotTests(unittest.TestCase):
    def test_all256_tiny_tensors_repaired_by_three_slots(self,_clock):
        factors=[(1,1,1),(2,2,2),(3,3,3)]
        for packed in range(256):
            core=[packed>>i&1 for i in range(8)]
            result=subject.repair_slots(core,[2,2,2],factors,[0,1,2])
            self.assertEqual(result['status'],'RAW_EXACT_COMPACT',(packed,result))
            self.assertLessEqual(len(result['factors']),3)
            self.assertEqual(expand(result['factors'],[2,2,2]),core)
            self.assertFalse(result['publication_eligible'])

    def test_fixed_outside_remains_literal_and_all_original_coefficients_match(self,_clock):
        exact=[(1,1,1),(2,2,2),(4,4,4),(8,8,8)]
        core=expand(exact,[4,4,4]);approx=[(3,1,1)]+exact[1:]
        result=subject.repair_slots(core,[4,4,4],approx,[0,1,2])
        self.assertEqual(result['status'],'RAW_EXACT_COMPACT')
        self.assertEqual(result['fixed_outside_factors'],[[8,8,8]])
        self.assertIn([8,8,8],result['factors'])
        self.assertEqual(result['full_compact_entries_checked'],64)
        self.assertEqual(residual_loss(core,[4,4,4],result['factors']),0)

    def test_rank_exclusion_is_conditional_not_global_unsat(self,_clock):
        core=expand([(1<<i,1<<i,1<<i) for i in range(4)],[4,4,4])
        result=subject.repair_slots(core,[4,4,4],[(1,1,1)]*3,[0,1,2])
        self.assertEqual(result['status'],'REPAIR_EXCLUDED')
        self.assertEqual(result['case'],'selected_residual_mode_rank_exceeds_slots')
        self.assertEqual(result['actual_mode_shape'],[4,4,4])
        self.assertTrue(result['no_global_cp_negative_claim'])

    def test_zero_residual_and_caps_or_late_decoder_are_unknown(self,_clock):
        zero=subject.repair_slots([0]*8,[2,2,2],[(1,1,1)]*3,[0,1,2])
        self.assertEqual(zero['status'],'RAW_EXACT_COMPACT')
        for kwargs in [dict(timeout_seconds=0),dict(cancelled=lambda:True),dict(max_vectors=0)]:
            result=subject.repair_slots([1,0,0,0,0,0,0,1],[2,2,2],[(1,1,1)]*3,[0,1,2],**kwargs)
            self.assertEqual(result['status'],'UNKNOWN')
            self.assertFalse(result['complete'])
        flag=[False];actual=subject.solve_one
        def late(*args,**kwargs):
            value=actual(*args,**kwargs);flag[0]=True;return value
        with patch.object(subject,'solve_one',late):
            result=subject.repair_slots([1,0,0,0,0,0,0,1],[2,2,2],[(1,1,1)]*3,[0,1,2],cancelled=lambda:flag[0])
        self.assertEqual(result['status'],'UNKNOWN')

    def test_slot_selection_is_metadata_only_and_bounded(self,_clock):
        core,shape,factors=strassen();factors=[list(t) for t in factors];factors[0][0]^=1
        result=subject.propose_slot_sets(core,shape,factors,limit=5)
        self.assertEqual(result['status'],'SLOT_PROPOSALS_ONLY')
        self.assertEqual(result['examined'],70)
        self.assertEqual(len(result['proposals']),5)
        self.assertEqual(result['decoder_calls'],0)
        capped=subject.propose_slot_sets(core,shape,factors,max_examined=1)
        self.assertEqual(capped['status'],'UNKNOWN')
        self.assertEqual(capped['decoder_calls'],0)

    def test_invalid_slot_indices_do_not_silently_change_the_problem(self,_clock):
        for selected in [[0,0,1],[0,1],[0,1,4],[False,1,2]]:
            with self.assertRaises(ValueError):subject.repair_slots([0]*8,[2,2,2],[(1,1,1)]*3,selected)


if __name__=='__main__':unittest.main()
