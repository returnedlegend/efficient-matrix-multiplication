import copy
import unittest
from mmsearch.sat_neighborhoods import gf2_rank,precompute_rows,flattening_bounds,select_patches,factor_masks
from mmsearch.tensor import naive_candidate,strassen_candidate

class NeighborhoodTests(unittest.TestCase):
    def test_binary_rank_dependency(self):
        self.assertEqual(gf2_rank([3,5,6]),2)
        self.assertEqual(gf2_rank([1,2,4,8]),4)
        self.assertEqual(gf2_rank([0,0]),0)

    def test_flattening_rejects_two_independent_products(self):
        source=naive_candidate(2)
        rows=precompute_rows(source)
        self.assertEqual(flattening_bounds(rows,[0,7]),[2,2,2])

    def test_passing_bound_does_not_imply_replacement_possible(self):
        source=strassen_candidate(2)
        self.assertEqual(flattening_bounds(precompute_rows(source),range(7)),[4,4,4])
        # These bounds pass a target6 test, but do not establish tensor rank6.

    def test_strict_source_and_budget_validation(self):
        source=naive_candidate(2)
        for value in (2,1.0,True):
            bad=copy.deepcopy(source)
            bad['terms'][0]['u'][0]=value
            with self.assertRaises(ValueError): factor_masks(bad)
        bad=copy.deepcopy(source)
        bad['terms'].pop()
        with self.assertRaises(ValueError): select_patches(bad)
        for seconds in (float('inf'),float('nan'),0,-1):
            with self.assertRaises(ValueError): select_patches(source,seconds=seconds)
        with self.assertRaises(ValueError): select_patches(source,attempts=-1)
        self.assertEqual(select_patches(source,attempts=0)['distinct_patches_checked'],0)

    def test_seed_reproducibility_and_small_source_support(self):
        source=naive_candidate(2)
        first=select_patches(source,attempts=50,seconds=1)
        second=select_patches(source,attempts=50,seconds=1)
        self.assertEqual(first['patches'],second['patches'])
        self.assertEqual(first['distinct_patches_checked'],second['distinct_patches_checked'])

if __name__=='__main__': unittest.main()
