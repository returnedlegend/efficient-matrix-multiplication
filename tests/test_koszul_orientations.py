import itertools
import math
import unittest

from mmsearch.compact_sat import compress_residual
from mmsearch.koszul import koszul_bounds, koszul_p1_rows
from mmsearch.koszul_p2 import koszul_p2_bounds, koszul_p2_rows
from mmsearch.koszul_orientations import orientation_bounds, transpose_tensor
from mmsearch.sat import solve_local
from mmsearch.sat_neighborhoods import gf2_rank
from mmsearch.tensor import naive_candidate
from scripts.campaign_koszul_sat import cached_encoder
from scripts.campaign_oriented_sat import OrientedCoreCache
from tests.test_koszul import dense_rank, tensor


class OrderedModeTests(unittest.TestCase):
    def test_all_permutations_match_independent_dense_maps(self):
        shape = [3, 4, 2]
        core = tensor(shape, [(7, 9, 3), (2, 7, 2), (3, 12, 1)])
        original = {(a, b, c): core[(a*shape[1]+b)*shape[2]+c]
                    for a, b, c in itertools.product(*(range(n) for n in shape))}
        for permutation in itertools.permutations(range(3)):
            permuted, dimensions = transpose_tensor(core, shape, permutation)
            a, b, c = dimensions
            for degree, constructor in ((1, koszul_p1_rows), (2, koszul_p2_rows)):
                dense = []
                for output, w in itertools.product(itertools.combinations(range(a), degree+1), range(c)):
                    row = []
                    for source, v in itertools.product(itertools.combinations(range(a), degree), range(b)):
                        if not set(source) <= set(output):
                            row.append(0)
                        else:
                            remaining = set(output)-set(source)
                            position = [0, 0, 0]
                            position[permutation[0]] = next(iter(remaining))
                            position[permutation[1]], position[permutation[2]] = v, w
                            row.append(original[tuple(position)])
                    dense.append(row)
                rows, columns, count = constructor(permuted, dimensions, 0)
                self.assertEqual(columns, math.comb(a, degree)*b)
                self.assertEqual(count, len(dense))
                self.assertEqual(rows, [sum(x << i for i, x in enumerate(row)) for row in dense])
                self.assertEqual(gf2_rank(rows), dense_rank(dense))

    def test_new_orientation_rejects_original_order_survivor(self):
        # A nine-product local source core. All original p1/p2 axis choices
        # pass K8, but transposing the dualized B/C modes proves local rank9.
        packed = int('540000000000000000140000001400001400060012000014080609105400140800081454200088000954', 16)
        core = [(packed >> i) & 1 for i in range(6*7*8)]
        shape = [6, 7, 8]
        self.assertFalse(koszul_bounds(core, shape, target=8)['rejected'])
        self.assertFalse(koszul_p2_bounds(core, shape, target=8)['rejected'])
        report = orientation_bounds(core, shape, target=8)
        self.assertTrue(report['rejected'])
        decisive = report['decisive']
        self.assertGreater(decisive['matrix_rank'], 8*decisive['rank_one_contribution'])
        self.assertFalse(orientation_bounds(core, shape, target=9)['rejected'])

    def test_positive_k_product_sums_all_six_orientations(self):
        shape = [5, 4, 3]
        products = [(31, 15, 7), (7, 9, 2), (19, 3, 5), (28, 5, 3)]
        for k in range(1, 5):
            self.assertFalse(orientation_bounds(tensor(shape, products[:k]), shape, target=k)['rejected'])

    def test_caps_are_explicit_and_no_false_rejection(self):
        core = tensor([5, 4, 3], [(31, 15, 7)])
        report = orientation_bounds(core, [5, 4, 3], target=1, max_dimension=0)
        self.assertFalse(report['rejected'])
        p2 = [entry for entry in report['bounds'] if entry['exterior_degree'] == 2]
        self.assertEqual(len(p2), 6)
        self.assertTrue(all(entry['status'] == 'SKIPPED' for entry in p2))

    def test_planted_5x5_exact_positive_survives_filter_and_decode(self):
        source = naive_candidate(5)
        source['terms'].append({axis: [0]*25 for axis in ('u', 'v', 'w')})
        cache = OrientedCoreCache()
        problem = cached_encoder(cache, 'cadical', 'u-lex')(source, rank=125,
                    active_terms=[0], drop_term=125)
        self.assertLessEqual(problem['metadata']['koszul']['tensor_rank_lower_bound'], 1)
        result = solve_local(problem, seconds=2, conflicts=1000)
        self.assertEqual(result['status'], 'SAT')
        self.assertEqual(result['verification']['exact_entries_checked'], 15625)
        self.assertTrue(result['verification']['valid'])
        self.assertEqual(cache.metrics['orientation_evaluations'], 1)


if __name__ == '__main__':
    unittest.main()
