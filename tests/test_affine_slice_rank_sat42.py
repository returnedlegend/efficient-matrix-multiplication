import importlib.util
import itertools
import os
import time
import unittest
from unittest.mock import patch

from mmsearch.affine_slice_rank_sat42 import (build_matrix_problem,build_problem,control_assumptions,
    matrix_rank,solve,solve_rank_zero,validate_decode,validate_lift,witness_assignment)
from mmsearch.free_factor_kernel import pair_column
from mmsearch.kernel_quartet_block_wide import binary_rank
from mmsearch.search import encode_candidate

CMS=importlib.util.find_spec('pycryptosat') is not None
STRASSEN=[(9,9,9),(12,1,10),(1,10,12),(8,5,3),(3,8,5),(5,3,8),(10,12,1)]
MIXED=[(5,9,9),(12,8,9),(12,1,3),*STRASSEN[2:]]


def slow_worker(*args):time.sleep(.3)
def failed_worker(*args):os._exit(17)


class AffineSliceTests(unittest.TestCase):
    @unittest.skipUnless(CMS,'pycryptosat unavailable')
    def test_exhaustive_all_2x2_matrices_three_affine_families(self):
        checked=0
        for matrix in range(16):
            for columns in ([],[1],[1,2]):
                minimum=min(matrix_rank(matrix^sum((column if z else 0) for column,z in zip(columns,values)),2)
                            for values in itertools.product((False,True),repeat=len(columns)))
                # Columns1 and2 have disjoint bits, so this sum equals XOR.
                for rank in range(3):
                    problem=build_matrix_problem(matrix,columns,2,rank)
                    result=solve_rank_zero(problem) if rank==0 else solve(problem,seconds=1,memory_mb=256,options={'seed':'424501'})
                    self.assertEqual(result['status']=='SAT',minimum<=rank,(matrix,columns,rank,result))
                    if result['status']!='SAT':self.assertEqual(result['status'],'AFFINE_FAMILY_UNSAT')
                    checked+=1
        self.assertEqual(checked,144)

    @unittest.skipUnless(CMS,'pycryptosat unavailable')
    def test_full_MM_mandatory_mixing_all_free_axes_and_new_pairs(self):
        self.assertEqual(binary_rank([pair_column(t[:2],4) for t in MIXED]),8)
        for rotation in range(3):
            terms=[term[rotation:]+term[:rotation] for term in MIXED]
            axis=(2-rotation)%3;problem=build_problem(encode_candidate(terms,2),axis,9)
            self.assertEqual(problem['metadata']['unmixed_matrix_rank'],2)
            neutral=tuple((12,1,3)[rotation:]+(12,1,3)[:rotation])
            z=[tuple(t)==neutral for t in problem['neutral_terms']]
            rotated=(9,9,9)[rotation:]+(9,9,9)[:rotation]
            factors=[[rotated[a] for a in problem['other_axes']]]
            assignment=witness_assignment(problem,z,factors)
            _,report=validate_decode(problem,assignment)
            self.assertEqual((report['rank'],report['exact_entries_checked']),(7,64))
            result=solve(problem,seconds=2,memory_mb=256,options={'seed':'424501'})
            self.assertEqual(result['status'],'SAT',result)
            self.assertEqual((result['verification']['rank'],result['verification']['exact_entries_checked']),(7,64))
            self.assertTrue(any(result['candidate']['metadata']['neutral_bits']))
            old_pairs={tuple(term[a] for a in problem['other_axes']) for term in terms}
            self.assertTrue(any(tuple(pair) not in old_pairs for pair in result['candidate']['metadata']['new_rank_factors']))

    @unittest.skipUnless(CMS,'pycryptosat unavailable')
    def test_positive_rank_k_control_and_zero_factor_columns(self):
        problem=build_problem(encode_candidate(MIXED,2),2,9,rank_bound=2)
        assumptions=control_assumptions(problem)
        result=solve(problem,seconds=2,memory_mb=256,assumptions=assumptions,options={'seed':'424501'})
        self.assertEqual(result['status'],'SAT');self.assertEqual(result['verification']['rank'],8)
        zero=build_matrix_problem(0,[],2,2)
        assignment=witness_assignment(zero,[],[(0,0),(0,0)])
        witness,report=validate_decode(zero,assignment)
        self.assertEqual(report['matrix_rank'],0)
        self.assertEqual(solve(zero,seconds=1,memory_mb=256)['status'],'SAT')

    def test_corrupt_assignment_and_lift_rejected(self):
        problem=build_problem(encode_candidate(MIXED,2),2,9)
        z=[tuple(t)==(12,1,3) for t in problem['neutral_terms']]
        good=witness_assignment(problem,z,[(9,9)])
        bad=list(good);bad[problem['c_variables'][0][0]]=not bad[problem['c_variables'][0][0]]
        with self.assertRaises(AssertionError):validate_decode(problem,bad)
        bad=list(good);bad[1]=int(bad[1])
        with self.assertRaises(AssertionError):validate_decode(problem,bad)
        with self.assertRaises(ValueError):validate_lift(problem,z,[(8,9)])
        with self.assertRaises(ValueError):validate_lift(problem,[False]*len(z),[(9,9)])
        corrupt=encode_candidate(MIXED,2);corrupt['terms'][0]['u'][0]=2
        with self.assertRaises(ValueError):build_problem(corrupt,2,9)

    def test_timeout_resource_and_worker_error_lifecycle(self):
        problem=build_matrix_problem(0,[],2,1)
        with patch('mmsearch.local_eliminated42sat._worker',slow_worker):
            result=solve(problem,seconds=.01,memory_mb=256)
        self.assertEqual(result['status'],'UNKNOWN');self.assertTrue(result['worker_reaped'])
        with patch('mmsearch.local_eliminated42sat._worker',failed_worker):
            result=solve(problem,seconds=1,memory_mb=256)
        self.assertEqual(result['status'],'ERROR');self.assertEqual(result['worker_exitcode'],17);self.assertTrue(result['worker_reaped'])
        with self.assertRaises(ValueError):solve(problem,seconds=1,memory_mb=127)


if __name__=='__main__':unittest.main()
