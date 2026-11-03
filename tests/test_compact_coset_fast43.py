import itertools
import unittest
from mmsearch.compact_coset43 import pair_column
from mmsearch.compact_coset_fast43 import rankone_matrix_factors,solve_core
from tests.test_compact_coset43 import brute_tiny


class FastCosetControls(unittest.TestCase):
    def test_every_small_binary_matrix_rankone_test(self):
        for a,b in [(1,3),(2,3),(3,2),(3,3)]:
            points={pair_column(x,y,b):(x,y) for x in range(1,1<<a) for y in range(1,1<<b)}
            for q in range(1<<(a*b)):self.assertEqual(rankone_matrix_factors(q,a,b),points.get(q))

    def test_all_tiny_tensors_and_original_witnesses(self):
        exact=brute_tiny();checks=0;fast=0
        for packed in range(256):
            core=[packed>>i&1 for i in range(8)]
            for axis in range(3):
                d=solve_core(core,[2,2,2],0,axis=axis)['mode_rank']
                for target in range(d+2):
                    r=solve_core(core,[2,2,2],target,axis=axis)
                    self.assertEqual(r['status']=='SAT',exact[packed]<=target,(packed,axis,target,r));checks+=1
                    if r['algorithm']=='enumerate_mode_subspace_rankone_test':
                        fast+=1;self.assertEqual(r['tested_span_vectors'],(1<<d)-1)
                    if r['status']=='SAT':
                        actual=0
                        for term in r['products']:
                            for i,j,k in itertools.product(range(2),repeat=3):actual^=((term[0]>>i&1)&(term[1]>>j&1)&(term[2]>>k&1))<<((i*2+j)*2+k)
                        self.assertEqual(actual,packed)
        self.assertEqual(checks,2931);self.assertEqual(fast,765)

    def test_cancel_and_fast_resource_scope(self):
        core=[1,0,0,0,0,0,0,1]
        self.assertEqual(solve_core(core,[2,2,2],2,cancelled=lambda:True)['status'],'UNKNOWN')
        self.assertEqual(solve_core(core,[2,2,2],2,max_points=2)['status'],'UNKNOWN')
        self.assertEqual(solve_core(core,[2,2,2],4)['status'],'UNKNOWN')


if __name__=='__main__':unittest.main()
