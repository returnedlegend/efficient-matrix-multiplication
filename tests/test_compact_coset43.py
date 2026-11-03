import collections
import itertools
import unittest

from mmsearch.compact_coset43 import expand_products,solve_core


def brute_tiny():
    points=[]
    for term in itertools.product(range(1,4),repeat=3):
        # Independent eight-bit construction, not the production expansion.
        point=0
        for i,j,k in itertools.product(range(2),repeat=3):
            point^=((term[0]>>i&1)&(term[1]>>j&1)&(term[2]>>k&1))<<((i*2+j)*2+k)
        points.append(point)
    distance={0:0};queue=collections.deque([0])
    while queue:
        t=queue.popleft()
        for point in points:
            v=t^point
            if v not in distance:distance[v]=distance[t]+1;queue.append(v)
    return distance


class CompactCoset43Tests(unittest.TestCase):
    def test_all_256_tensors_against_independent_27_point_bfs(self):
        exact=brute_tiny();self.assertEqual(len(exact),256);checks=0;branches=collections.Counter()
        for packed in range(256):
            core=[packed>>i&1 for i in range(8)]
            for axis in range(3):
                d=solve_core(core,[2,2,2],0,axis=axis)['mode_rank']
                for target in range(d+2):
                    result=solve_core(core,[2,2,2],target,axis=axis)
                    self.assertEqual(result['status']=='SAT',exact[packed]<=target,(packed,axis,target,result))
                    self.assertTrue(result['complete']);branches[result['case']]+=1;checks+=1
                    if result['status']=='SAT':
                        self.assertEqual(expand_products(result['products'],[2,2,2]),core)
                        actual=0
                        for term in result['products']:
                            for i,j,k in itertools.product(range(2),repeat=3):actual^=((term[0]>>i&1)&(term[1]>>j&1)&(term[2]>>k&1))<<((i*2+j)*2+k)
                        self.assertEqual(actual,packed)
                self.assertEqual(solve_core(core,[2,2,2],d+2,axis=axis)['status'],'UNKNOWN')
        self.assertIn('single_nonzero_coset_star_differences_span',branches)
        print('tiny_coset_checks',checks,'branches',dict(branches))

    def test_one_dimensional_image_matrix_rank_three_excludes_two(self):
        # With free-axis dimension one CP rank is ordinary matrix rank.
        core=[1,0,0,0,1,0,0,0,1]
        result=solve_core(core,[1,3,3],2,axis=0)
        self.assertEqual(result['status'],'LOCAL_UNSAT');self.assertEqual(result['case'],'no_single_coset_spans')

    def test_cancellation_cap_and_corrupt_witness(self):
        core=[1,0,0,0,0,0,0,1]
        self.assertEqual(solve_core(core,[2,2,2],3,cancelled=lambda:True)['status'],'UNKNOWN')
        self.assertEqual(solve_core(core,[2,2,2],3,max_points=1)['status'],'UNKNOWN')
        result=solve_core(core,[2,2,2],2)
        self.assertEqual(result['status'],'SAT');result['products'][0][0]^=1
        self.assertNotEqual(expand_products(result['products'],[2,2,2]),core)


if __name__=='__main__':unittest.main()
