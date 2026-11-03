import copy
import unittest

from mmsearch.dictionary43 import additional_kernel_evidence,validate_kernel_evidence
from mmsearch.free_factor_sat import packed_rref


def example():
    common=dict(width=1,orientation='wu',mode_permutation=[2,0,1])
    old_rows=[1,2,0];new_rows=[21,22,24]
    old=dict(pairs=[(1,1),(1,2)],baseline_vectors=[0,0],coefficients=old_rows,right_sides=[0,0,0],metadata=dict(common),
        reduced=packed_rref(old_rows,[0,0,0],2,1))
    new=dict(pairs=[(1,1),(1,2),(1,3),(2,1),(2,2)],baseline_vectors=[0]*5,coefficients=new_rows,right_sides=[0,0,0],metadata=dict(common),
        reduced=packed_rref(new_rows,[0,0,0],5,1))
    return old,new


class Dictionary43Tests(unittest.TestCase):
    def test_exact_embedding_and_independent_added_kernel_directions(self):
        old,new=example();proof=additional_kernel_evidence(old,new)
        self.assertEqual((proof['old_rank'],proof['new_rank']),(2,3))
        self.assertEqual(proof['added_kernel_dimensions'],2)
        self.assertTrue(validate_kernel_evidence(old,new,proof))

    def test_corrupted_witness_and_wrong_orientation_rejected(self):
        old,new=example();proof=additional_kernel_evidence(old,new)
        bad=copy.deepcopy(proof);bad['directions'][0]['full_kernel_mask_hex']='0x1'
        with self.assertRaises(AssertionError):validate_kernel_evidence(old,new,bad)
        bad=copy.deepcopy(proof);bad['directions'][1]=copy.deepcopy(bad['directions'][0])
        with self.assertRaises(AssertionError):validate_kernel_evidence(old,new,bad)
        wrong=copy.deepcopy(new);wrong['metadata']['orientation']='uv'
        with self.assertRaises(ValueError):additional_kernel_evidence(old,wrong)
        wrong=copy.deepcopy(new);wrong['coefficients'][0]^=1
        with self.assertRaises(AssertionError):additional_kernel_evidence(old,wrong)


if __name__=='__main__':unittest.main()
