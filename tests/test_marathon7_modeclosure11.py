import unittest
from mmsearch.marathon7_modeclosure11 import factor_image_closure
from mmsearch.compact_eight43 import factor_core
from mmsearch.compact_coset43 import mode_slices,pair_column
from mmsearch.sat_neighborhoods import gf2_rank


class ModeClosureTests(unittest.TestCase):
    def test_all_three_factor_memberships_and_original_coordinates(self):
        terms=[(1,1,1),(2,2,2),(3,3,3),(4,1,1),(1,4,1),(1,1,4)];r=factor_image_closure(terms,[0,1])
        self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['shape'],[2,2,2]);self.assertEqual([e['source_index'] for e in r['closure']],[0,1,2]);self.assertEqual(r['other_products'],[dict(source_index=2,factor_coordinates=[3,3,3])]);self.assertEqual(r['raw_other_products_tested'],4)

    def test_basis_witnesses_and_fixed_actual_images_under_pair_independence(self):
        terms=[(1,1,1),(2,2,2),(3,3,3)];r=factor_image_closure(terms,[0,1])
        for axis in range(3):
            other=[j for j in range(3) if j!=axis];self.assertEqual(gf2_rank([pair_column(t[other[0]],t[other[1]],2) for t in terms]),3)
        _,core,shape=factor_core(terms,[0,1,2]);self.assertEqual(shape,r['shape']);self.assertEqual([gf2_rank(mode_slices(core,shape,a)[0]) for a in range(3)],shape)
        for w in r['basis_witnesses']:
            for basis,mask in zip(w['basis'],w['basis_from_original_coordinates']):
                v=0
                for j,i in enumerate(w['original_independent_indices']):
                    if mask>>j&1:v^=terms[i][w['axis']]
                self.assertEqual(v,basis)

    def test_closure_contains_dependent_parent_factors(self):
        r=factor_image_closure([(1,1,1),(2,2,2),(3,3,3)],[0,1,2]);self.assertEqual(r['shape'],[2,2,2]);self.assertEqual(len(r['closure']),3)

    def test_cancellation_is_incomplete_and_invalid_support_rejected(self):
        r=factor_image_closure([(1,1,1)],[0],cancelled=lambda:True);self.assertEqual(r['status'],'UNKNOWN');self.assertFalse(r['complete'])
        for parent in [[0,0],[-1],[True],[1]]:
            with self.assertRaises(ValueError):factor_image_closure([(1,1,1)],parent)


if __name__=='__main__':unittest.main()
