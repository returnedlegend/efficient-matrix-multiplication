import itertools
import random
import unittest
from mmsearch.forced_span43 import solve_span


def span(values):
    out={0}
    for v in values:out|={x^v for x in tuple(out)}
    return frozenset(out)


def brute(columns,targets,budget):
    target=span(targets)
    return any(target<=span([columns[i] for i in range(len(columns)) if mask>>i&1]) for mask in range(1<<len(columns)) if mask.bit_count()<=budget)


class ForcedSpanControls(unittest.TestCase):
    def check(self,columns,targets,budget):
        r=solve_span(columns,targets,budget);self.assertEqual(r['status']=='SAT',brute(columns,targets,budget),(columns,targets,budget,r))
        self.assertNotEqual(r['status'],'UNKNOWN')
        if r['status']=='SAT':
            self.assertLessEqual(len(r['support']),budget)
            for target,coefficients in zip(targets,r['target_coordinates']):
                value=0
                for j,i in enumerate(r['support']):
                    if coefficients>>j&1:value^=columns[i]
                self.assertEqual(value,target)
        return r

    def test_every_catalog_and_target_subspace_in_F2_cubed(self):
        spaces={span(g) for size in range(4) for g in itertools.combinations(range(1,8),size)};self.assertEqual(len(spaces),16);checks=0
        for mask in range(128):
            columns=[v for v in range(1,8) if mask>>(v-1)&1]
            for space in spaces:
                targets=sorted(space-{0});d=(len(space)).bit_length()-1
                for budget in range(d+3):self.check(columns,targets,budget);checks+=1
        print('exhaustive_catalog_subspace_bounds',checks)

    def test_random_F2_four_and_zero_duplicate_columns(self):
        rng=random.Random(432)
        for _ in range(150):
            columns=[rng.randrange(16) for _ in range(rng.randrange(0,9))];targets=[rng.randrange(16) for _ in range(rng.randrange(4))];d=len(span(targets)).bit_length()-1
            for budget in range(d,d+3):self.check(columns,targets,budget)

    def test_forcing_contraction_scalar_and_true_negative(self):
        r=self.check([1,2,4,8],[3,12],4);self.assertEqual(r['case'],'forced_same_coset_pair_then_one_surplus')
        r=self.check([3,4,8,16,32],[3,12,48],5);self.assertEqual(r['forced_rank'],1);self.assertEqual(r['case'],'forced_same_coset_pair_then_one_surplus')
        r=self.check([1,2,4],[7],3);self.assertEqual(r['case'],'forced_scalar_weight_three')
        r=self.check([1,2,4,8,16],[7,28],4);self.assertEqual(r['status'],'LOCAL_UNSAT')
        self.assertEqual(solve_span([1,2,4,8],[3,12],4,max_branches=0)['status'],'UNKNOWN')
        self.assertEqual(solve_span([1],[1],4)['status'],'UNKNOWN')
        self.assertEqual(solve_span([1,2],[3],3,cancelled=lambda:True)['status'],'UNKNOWN')

    def test_rankone_catalog_requires_two_cosets_for_four_products(self):
        columns=[]
        for a,b in itertools.product(range(1,16),repeat=2):
            value=0
            for i,j in itertools.product(range(4),repeat=2):value|=((a>>i&1)&(b>>j&1))<<(4*i+j)
            columns.append(value)
        targets=[(1<<0)|(1<<5),(1<<10)|(1<<15)]
        self.assertEqual(solve_span(columns,targets,3)['status'],'LOCAL_UNSAT')
        result=solve_span(columns,targets,4)
        self.assertEqual(result['status'],'SAT');self.assertEqual(len(result['support']),4)
        self.assertEqual(result['case'],'forced_same_coset_pair_then_one_surplus')


if __name__=='__main__':unittest.main()
