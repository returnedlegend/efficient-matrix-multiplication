"""Tiny partialtensor-only positive/negative/late protocol controls."""
import unittest
from mmsearch.compact_eight43 import expand_core
from mmsearch.marathon7_cached_guard import CampaignHold
from scripts.query_c3_wedge_kernel63_7 import partial_case


def tiny(target=4):
    core=[(value>>i)&1 for value in (33,33792) for i in range(16)]
    shape=[2,4,4];bases=[[1<<i for i in range(d)] for d in shape]
    return dict(id='tiny-partial',mode_rank=2,target=target,old_weight=5,
                old_orbit_indices=[],core=core,shape=shape,image_bases=bases,
                ambient_tensor_hex=hex(expand_core(core,shape,bases,25)))


class KernelPartialQueryControls(unittest.TestCase):
    def test_true_surplus2_positive_is_only_exact_partial_witness(self):
        result=partial_case(tiny(),lambda *_:None,lambda:False)
        self.assertEqual(result['status'],'PARTIAL_TENSOR_SAT')
        self.assertEqual(result['raw_decoder']['case'],'repeated_coset_pair_extension')
        witness=result['partial_witness']
        self.assertEqual(witness['exact_ambient_entries_checked'],15625)
        self.assertEqual(len(witness['products_in_original_25d_modes']),4)
        self.assertFalse(witness['global_matrix_tensor_verified'])
        self.assertFalse(result['publication_eligible'])

    def test_late_positive_preserves_raw_without_acceptance(self):
        for barrier in ('post_partial_decode','post_partial_scalar_core','post_partial_ambient_verification','pre_partial_result'):
            with self.subTest(barrier=barrier):
                def check(name):
                    if name==barrier:raise CampaignHold('tiny cutoff',name)
                result=partial_case(tiny(),check,lambda:False)
                self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete'])
                self.assertEqual(result['raw_decoder']['status'],'SAT');self.assertFalse(result['publication_eligible'])

    def test_complete_local_negative_and_cancelled_unknown_differ(self):
        result=partial_case(tiny(3),lambda *_:None,lambda:False)
        self.assertEqual(result['status'],'LOCAL_UNSAT');self.assertTrue(result['complete'])
        result=partial_case(tiny(),lambda *_:None,lambda:True)
        self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete'])


if __name__=='__main__':unittest.main()
