import itertools
import unittest
from scripts.analyze_cyclic_tensor_code7_affine import summarize

class AffineMetadataTests(unittest.TestCase):
    def test_locked_cube_triple_plus_even_kernel_proves_mod6(self):
        weights=[1,1,1,3,3,3];seed=7;kernel=[15,48]
        report=summarize(weights,seed,kernel)
        self.assertEqual(report['cube_projection_rank'],1);self.assertTrue(report['cube_all_together'])
        self.assertEqual(report['all_feasible_costs_mod6'],3);self.assertEqual(report['equivalent_bound_from_mod6'],87)
        for selected in itertools.product([False,True],repeat=2):
            state=seed
            for include,value in zip(selected,kernel):
                if include:state^=value
            cost=sum(weight for i,weight in enumerate(weights) if state>>i&1)
            self.assertEqual(cost%6,3)
            self.assertEqual(cost<=92,cost<=87)

    def test_individually_movable_cubes_do_not_imply_locked_triple(self):
        report=summarize([1,1,1,3,3,3],7,[9,18,36])
        self.assertEqual(report['cube_projection_rank'],3);self.assertFalse(report['cube_all_together'])
        self.assertIsNone(report['all_feasible_costs_mod6'])

    def test_odd_kernel_and_partial_cube_seed_do_not_get_mod6_claim(self):
        self.assertIsNone(summarize([1,1,1,3],7,[7])['all_feasible_costs_mod6'])
        self.assertIsNone(summarize([1,1,1,3],1,[15])['all_feasible_costs_mod6'])

if __name__=='__main__':unittest.main()
