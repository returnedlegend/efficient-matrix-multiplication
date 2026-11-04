import itertools
import random
import unittest
from unittest.mock import patch

from mmsearch import conditional_surplus_three7 as subject
from mmsearch.kernel_projection_dominance7 import complete_kernel
from mmsearch.compact_coset43 import expand_products


def diagonal(mask,n):return sum((mask>>i&1)<<(i*n+i) for i in range(n))


def code_image(labels):
    kernel,_=complete_kernel(labels);n=len(labels)
    return [0]+[diagonal(v,n) for v in kernel]+[diagonal(kernel[0],n),0],n


class ConditionalSurplusThreeTests(unittest.TestCase):
    def witness(self,raw,n,result):
        self.assertEqual(result['status'],'SAT',result)
        self.assertLessEqual(len(result['support']),result['budget'])
        self.assertEqual(len(raw),len(result['target_coordinates']))
        for target,coordinates in zip(raw,result['target_coordinates']):
            value=0
            for i,p in enumerate(result['support']):
                if coordinates>>i&1:value^=p['column']
                self.assertEqual(p['column'],sum(((p['left']>>j&1)&(p['right']>>k&1))<<(j*n+k)
                    for j,k in itertools.product(range(n),repeat=2)))
                self.assertIn(p,result['factor_point_pool'])
            self.assertEqual(value,target)

    def test_true_c3_code_requires_new_parent_branch_and_all_raw_slices(self):
        raw,n=code_image([1,2,3,4,5,6,7,1])
        result=subject.solve_pair_image(raw,n,n,8)
        self.assertEqual(result['target_rank'],5)
        self.assertEqual(result['inside_rank'],0)
        self.assertEqual(result['case'],'conditional_repeated_pair_extension')
        self.assertTrue(result['conditional_pair_theorem_applies'])
        self.assertEqual(result['total_extensions'],3)
        self.witness(raw,n,result)
        core=[value>>i&1 for value in raw for i in range(n*n)]
        whole=subject.solve_core(core,[len(raw),n,n],8,axis=0)
        self.assertEqual(whole['status'],'SAT')
        self.assertEqual(expand_products(whole['products'],[len(raw),n,n]),core)
        self.assertEqual(whole['core_entries_checked'],len(core))

    def test_complete_negative_full_support_diagonal_code_lower_bound9(self):
        raw,n=code_image(list(range(1,10)))
        result=subject.solve_pair_image(raw,n,n,8)
        # Opposite unfolding has9 independent rows, each supported on its own
        # diagonal coordinate; the supplied kernel has full coordinate support.
        self.assertEqual(result['target_rank'],5)
        self.assertEqual(result['inside_rank'],0)
        self.assertEqual(result['status'],'LOCAL_UNSAT',result)
        self.assertTrue(result['complete'])
        self.assertEqual(result['total_extensions'],0)

    def test_actual_parent_child_caps_boundary_d11_b6_cp14(self):
        raw,_=code_image([1,2,3,4,5,6,7,1]);n=14
        embedded=[]
        for matrix in raw:
            mask=sum((matrix>>(i*8+i)&1)<<i for i in range(8))
            embedded.append(diagonal(mask,n))
        embedded.extend(diagonal(1<<i,n) for i in range(8,n))
        result=subject.solve_pair_image(embedded,n,n,14,timeout_seconds=10)
        self.assertEqual(result['target_rank'],11)
        self.assertEqual(result['inside_rank'],6)
        self.assertEqual(result['case'],'conditional_repeated_pair_extension')
        self.witness(embedded,n,result)

    def test_invertible_left_right_changes_keep_original_factor_witnesses(self):
        raw,n=code_image([1,2,3,4,5,6,7,1]);rng=random.Random(7993)
        for _ in range(10):
            left=[1<<i for i in range(n)];right=left[:]
            for basis in (left,right):
                for _ in range(32):
                    i,j=rng.sample(range(n),2);basis[i]^=basis[j]
            changed=[]
            for matrix in raw:
                output=0
                for i,j in itertools.product(range(n),repeat=2):
                    if matrix>>(i*n+j)&1:
                        output^=sum(((left[i]>>a&1)&(right[j]>>b&1))<<(a*n+b)
                            for a,b in itertools.product(range(n),repeat=2))
                changed.append(output)
            self.witness(changed,n,subject.solve_pair_image(changed,n,n,8))

    def test_missing_bound_unknown_and_lower_prior_still_exact(self):
        n=8;raw=[diagonal(3,n),diagonal(12,n),diagonal(48,n),diagonal(64,n),diagonal(128,n)]
        result=subject.solve_pair_image(raw,n,n,8)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(result['case'],'conditional_backbone_bound_not_met')
        self.assertEqual(result['inside_rank'],2)
        result=subject.solve_pair_image([1],1,1,4)
        self.assertEqual(result['status'],'SAT')
        self.assertEqual(result['case'],'surplus_two_cover')

    def test_caps_incomplete_prior_child_and_late_answers_unknown(self):
        raw,n=code_image([1,2,3,4,5,6,7,1])
        for kwargs in (dict(max_vectors=30),dict(max_extensions=0),dict(max_child_vectors=30),
                       dict(max_child_extensions=0),dict(timeout_seconds=0),dict(cancelled=lambda:True)):
            result=subject.solve_pair_image(raw,n,n,8,**kwargs)
            self.assertEqual(result['status'],'UNKNOWN',(kwargs,result));self.assertFalse(result['complete'])
        original=subject.solve_two
        for late_call in (1,2):
            calls=[0];flag=[False]
            def late(*args,**kwargs):
                result=original(*args,**kwargs);calls[0]+=1
                if calls[0]==late_call:flag[0]=True
                return result
            with patch.object(subject,'solve_two',late):
                result=subject.solve_pair_image(raw,n,n,8,cancelled=lambda:flag[0])
            self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete'])
            self.assertIn('last_prior_result' if late_call==1 else 'last_child_result',result)
            if late_call==2:self.assertEqual(result['last_child_result']['status'],'SAT')
        with patch.object(subject,'solve_two',return_value=dict(status='UNKNOWN',complete=False,case='synthetic')):
            self.assertEqual(subject.solve_pair_image(raw,n,n,8)['case'],'surplus_two_prior_incomplete')

    def test_strict_binary_core_and_caps(self):
        for core,shape in (([True],[1,1,1]),([1.0],[1,1,1]),([1],[True,1,1])):
            with self.assertRaises(ValueError):subject.solve_core(core,shape)
        with self.assertRaises(ValueError):subject.solve_pair_image([1],1,1,max_mode_rank=12)


if __name__=='__main__':unittest.main()
