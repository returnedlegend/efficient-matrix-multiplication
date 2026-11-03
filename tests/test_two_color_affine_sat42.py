import importlib.util
import itertools
from pathlib import Path
import unittest
from unittest.mock import patch

from mmsearch.affine_slice_rank_sat42 import build_problem as one_color,solve_rank_zero
from mmsearch.free_factor_kernel import pair_column
from mmsearch.kernel_quartet_block_wide import binary_rank
from mmsearch.search import encode_candidate
from mmsearch.two_color_affine_sat42 import (COORDINATES,build_coupled_problem,build_problem,control_assumptions,
    quotient_certificate,solve,validate_decode,validate_lift,witness_assignment)
from tests.test_affine_slice_rank_sat42 import slow_worker,failed_worker

CMS=importlib.util.find_spec('pycryptosat') is not None
CONTROL=[(13,1,10),(1,11,12),(1,1,6),(9,9,9),(8,5,3),(3,8,5),(5,3,8),(10,12,1)]
RESTORED=[(12,1,10),(1,10,12)]


def profiles(q):return [(a,b,q-a-b) for a in range(q+1) for b in range(q-a+1)]


@unittest.skipUnless(CMS,'pycryptosat unavailable')
class TwoColorTests(unittest.TestCase):
    def test_256mb_worker_does_not_inherit_large_parent_heap(self):
        import pycryptosat  # Match the broad runner's preloaded native extension.
        ballast=bytearray(280*1024**2)
        status=Path('/proc/self/status').read_text()
        virtual_kib=int(next(line.split()[1] for line in status.splitlines() if line.startswith('VmSize:')))
        self.assertGreater(virtual_kib,256*1024)
        result=solve(build_coupled_problem([0,0],[],1,(0,0,1)),seconds=2,memory_mb=256)
        self.assertEqual(result['status'],'SAT',result)
        self.assertEqual(result['memory_mb'],256);self.assertTrue(result['worker_reaped']);self.assertEqual(result['worker_exitcode'],0)
        self.assertEqual(len(ballast),280*1024**2)

    def test_exhaustive_width1_all_profiles_q0_q1_q2(self):
        checked=0
        for matrices in itertools.product(range(2),repeat=2):
            for columns in ([],[1]):
                for q in range(3):
                    for profile in profiles(q):
                        problem=build_coupled_problem(matrices,columns,1,profile);feasible=False
                        for neutral in itertools.product((False,True),repeat=2*len(columns)):
                            for factors in itertools.product(list(itertools.product(range(2),repeat=2)),repeat=q):
                                try:validate_lift(problem,list(neutral[:len(columns)]),list(neutral[len(columns):]),factors);feasible=True;break
                                except ValueError:pass
                            if feasible:break
                        result=solve(problem,seconds=1,memory_mb=256,options={'seed':'424601'})
                        self.assertEqual(result['status']=='SAT',feasible,(matrices,columns,profile,result))
                        checked+=1
        self.assertEqual(checked,80)

    def test_coupling_quotient_rank_bound_and_zero_padding(self):
        problem=build_coupled_problem([1,8],[],2,(1,0,1))
        self.assertEqual(solve(problem,seconds=1,memory_mb=256)['status'],'TWO_COLOR_PROFILE_UNSAT')
        self.assertEqual(problem['quotient_certificate']['quotient_syndrome_rank'],2)
        for profile in ((2,0,0),(0,2,0),(0,0,2)):
            mono=build_coupled_problem([1,8],[],2,profile)
            self.assertTrue(mono['quotient_certificate']['monochrome_profiles_excluded'])
            self.assertEqual(solve(mono,seconds=1,memory_mb=256)['status'],'TWO_COLOR_PROFILE_UNSAT')
        mono=build_coupled_problem([1,0],[],2,(2,0,0))
        self.assertFalse(mono['quotient_certificate']['monochrome_profiles_excluded'])
        self.assertEqual(solve(mono,seconds=1,memory_mb=256)['status'],'SAT')
        padding=build_coupled_problem([1,0],[],2,(1,1,0))
        assignment=witness_assignment(padding,[],[],[(1,1),(0,3)])
        _,report=validate_decode(padding,assignment);self.assertTrue(report['valid'])

    def test_full_MM_root_control_all_axes_and_one_color_exclusions(self):
        self.assertEqual(binary_rank([pair_column(term[:2],4) for term in CONTROL]),8)
        for rotation in range(3):
            terms=[term[rotation:]+term[:rotation] for term in CONTROL];axis=(2-rotation)%3;source=encode_candidate(terms,2)
            problem=build_problem(source,axis,10,12,(1,1,0));self.assertEqual(problem['metadata']['selected_color_counts'],[1,1,1])
            self.assertEqual(problem['quotient_certificate']['quotient_syndrome_rank'],2)
            restored=[term[rotation:]+term[:rotation] for term in RESTORED]
            factors=[[term[a] for a in problem['other_axes']] for term in restored]
            assignment=witness_assignment(problem,[False]*5,[False]*5,factors)
            _,report=validate_decode(problem,assignment)
            self.assertEqual((report['rank'],report['exact_entries_checked']),(7,64))
            result=solve(problem,seconds=2,memory_mb=256,options={'seed':'424601'})
            self.assertEqual(result['status'],'SAT',result);self.assertEqual(result['verification']['rank'],7)
            for delta in {term[axis] for term in terms}:
                single=one_color(source,axis,delta)
                self.assertEqual(single['metadata']['selected_count'],1)
                self.assertEqual(solve_rank_zero(single)['status'],'AFFINE_FAMILY_UNSAT')
            control=build_problem(source,axis,10,12,(1,1,1))
            checked=solve(control,seconds=2,memory_mb=256,assumptions=control_assumptions(control))
            self.assertEqual(checked['status'],'SAT');self.assertEqual(checked['verification']['rank'],8)

    def test_corruption_and_resource_lifecycle(self):
        problem=build_problem(encode_candidate(CONTROL,2),2,10,12,(1,1,0))
        assignment=witness_assignment(problem,[False]*5,[False]*5,[(12,1),(1,10)])
        assignment[problem['c_variables'][0][0]]=not assignment[problem['c_variables'][0][0]]
        with self.assertRaises(AssertionError):validate_decode(problem,assignment)
        with self.assertRaises(ValueError):validate_lift(problem,[False]*5,[False]*5,[(13,1),(1,10)])
        with self.assertRaises(ValueError):build_problem(encode_candidate(CONTROL,2),2,10,10,(1,1,0))
        with patch('mmsearch.local_eliminated42sat._worker',slow_worker):result=solve(problem,seconds=.01,memory_mb=256)
        self.assertEqual(result['status'],'UNKNOWN');self.assertTrue(result['worker_reaped'])
        with patch('mmsearch.local_eliminated42sat._worker',failed_worker):result=solve(problem,seconds=1,memory_mb=256)
        self.assertEqual(result['status'],'ERROR');self.assertTrue(result['worker_reaped'])


if __name__=='__main__':unittest.main()
