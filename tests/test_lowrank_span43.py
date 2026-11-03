from collections import Counter
import random
import unittest
from mmsearch.lowrank_span43 import lowrank_span,matrix_rank
from mmsearch.compact_coset43 import pair_column
from mmsearch.sat_neighborhoods import gf2_rank


def core_from_matrices(matrices,b,c):
    return [(x>>j)&1 for x in matrices for j in range(b*c)]


class LowRankSpanTests(unittest.TestCase):
    def test_two_by_two_table_and_negative_identity(self):
        self.assertEqual(Counter(matrix_rank(x,2,2) for x in range(16)),{0:1,1:9,2:6})
        result=lowrank_span(core_from_matrices([0b100010001],3,3),[1,3,3],2,0)
        self.assertEqual((result['status'],result['lowrank_span_rank'],result['points_tested']),('LOWRANK_SPAN_EXCLUDES',0,1))

    def test_all_points_required_and_converse_false(self):
        identity=0b100010001;diagonal110=0b000010001
        r=lowrank_span(core_from_matrices([identity,diagonal110],3,3),[2,3,3],3,0)
        self.assertEqual((r['status'],r['lowrank_span_rank'],r['lowrank_points']),('BOUND_PASSED_NOT_EXISTENCE',2,2))
        blocks=[(1<<0)|(1<<5),(1<<10)|(1<<15)]
        r=lowrank_span(core_from_matrices(blocks,4,4),[2,4,4],3,0)
        self.assertEqual(r['status'],'BOUND_PASSED_NOT_EXISTENCE')
        self.assertEqual(matrix_rank(blocks[0]^blocks[1],4,4),4)

    def test_derived_positive_families_after_basis_mixing(self):
        rng=random.Random(4310255)
        for case in range(100):
            r=rng.randint(2,9);q=[]
            points=[pair_column(a,b,3) for a in range(1,8) for b in range(1,8)];rng.shuffle(points)
            for x in points:
                if gf2_rank(q+[x])>len(q):q.append(x)
                if len(q)==r:break
            self.assertEqual(len(q),r);n=rng.randrange(1,1<<r);pivot=(n&-n).bit_length()-1
            s=[q[j]^(q[pivot] if n>>j&1 else 0) for j in range(r) if j!=pivot]
            for step in range(30):
                if len(s)>1:
                    i,j=rng.sample(range(len(s)),2);s[i]^=s[j]
            result=lowrank_span(core_from_matrices(s,3,3),[len(s),3,3],len(s)+1,0)
            self.assertEqual(result['status'],'BOUND_PASSED_NOT_EXISTENCE')
            self.assertEqual(result['lowrank_span_rank'],len(s))
            for coordinate in result['lowrank_coordinate_basis']:
                matrix=0
                for bit,value in enumerate(result['space_basis']):
                    if coordinate>>bit&1:matrix^=value
                self.assertLessEqual(matrix_rank(matrix,3,3),2)

    def test_corruption_rejected(self):
        with self.assertRaises(ValueError):lowrank_span([2],[1,1,1],2,0)
        with self.assertRaises(ValueError):lowrank_span([1],[1,1,9],2,0)


if __name__=='__main__':unittest.main()
