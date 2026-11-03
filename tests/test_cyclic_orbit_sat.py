"""Exact cyclic identity, cube parity, local UNSAT, and model rejection."""
import importlib.util
import unittest

from mmsearch.cyclic_orbit_sat import (build_patch_problem,build_repair,nonfixed_orbits,
                                      solve_patch,validate_decode_global,validate_decode_patch)
from mmsearch.search import _rotations,encode_candidate,naive_terms
from mmsearch.verify import verify_candidate


AVAILABLE=importlib.util.find_spec('pycryptosat') is not None or importlib.util.find_spec('pysat') is not None


@unittest.skipUnless(AVAILABLE,'optional SAT solver unavailable')
class CyclicOrbitSATTests(unittest.TestCase):
    def test_planted_c3_plus_three_orbits_repair_to_two_and_global_exactness(self):
        # Apply the exact C3 plus identity to the two nonfixed naive orbits.
        # x=(1,2,4), y=(8,4,2) -> (9,2,4)+(8,2,6)+(8,6,2).
        source={(1,1,1),(8,8,8)}
        for term in ((9,2,4),(8,2,6),(8,6,2)):
            source.update(_rotations(term))
        self.assertEqual(len(source),11)
        self.assertTrue(verify_candidate(encode_candidate(source,2),random_trials=0)['valid'])
        self.assertEqual(len(nonfixed_orbits(source)),3)
        problem=build_repair(encode_candidate(source,2),[0,1,2],strict95=False)
        result=solve_patch(problem,seconds=3,conflicts=200000)
        self.assertEqual(result['status'],'SAT',result)
        candidate,report=validate_decode_global(problem,result['model'])
        self.assertTrue(report['valid'])
        self.assertEqual(report['exact_entries_checked'],64)
        self.assertLessEqual(len(candidate['terms']),8)
        # Mutating one shared AND gate must fail before decoding or handoff.
        mutated=list(result['model']);gate=problem['and_gate_variables'][0]
        mutated=[-lit if abs(lit)==gate else lit for lit in mutated]
        with self.assertRaises(AssertionError):
            validate_decode_global(problem,mutated)

    def test_one_dimensional_cube_three_copies_leave_odd_parity(self):
        problem=build_patch_problem([(1,1,1)],1,n=2)
        self.assertEqual(problem['metadata']['shared_dimension'],1)
        # The same q appears three times and must become one parity literal.
        self.assertTrue(any(len(variables)==1 and rhs for variables,rhs in problem['xors']))
        result=solve_patch(problem,seconds=1,conflicts=10000)
        self.assertEqual(result['status'],'SAT',result)
        self.assertEqual(validate_decode_patch(problem,result['model']),{(1,1,1)})

    def test_embedded_five_by_five_repair_checks_all_15625_coefficients(self):
        # The same planted identity embedded into the upper 2x2 block of n=5.
        source=set(naive_terms(5))
        for term in ((1,2,32),(64,32,2)):
            source.difference_update(_rotations(term))
        new=((65,2,32),(64,2,34),(64,34,2))
        for term in new:
            source.update(_rotations(term))
        reps=nonfixed_orbits(source)
        selected=sorted(reps.index(min(_rotations(term))) for term in new)
        problem=build_repair(encode_candidate(source,5),selected,strict95=False)
        result=solve_patch(problem,seconds=2,conflicts=100000)
        self.assertEqual(result['status'],'SAT',result)
        candidate,report=validate_decode_global(problem,result['model'])
        self.assertTrue(report['valid'])
        self.assertEqual(report['exact_entries_checked'],15625)
        self.assertLessEqual(len(candidate['terms']),125)

    def test_genuine_solver_unsat_for_nonzero_patch_with_zero_slots(self):
        problem=build_patch_problem([(1,1,1)],0,n=2,use_bounds=False)
        self.assertFalse(problem['metadata']['lower_bound_rejected'])
        self.assertIn([],problem['clauses'])
        result=solve_patch(problem,seconds=1,conflicts=10000)
        self.assertEqual(result['status'],'UNSAT',result)

    def test_flattening_bound_rejects_before_solver_and_zero_orbit_is_allowed(self):
        rejected=build_patch_problem([(1,1,1)],0,n=2)
        self.assertEqual(solve_patch(rejected)['status'],'LOWER_BOUND_REJECTED')
        empty=build_patch_problem([],1,n=2)
        result=solve_patch(empty,seconds=1,conflicts=10000)
        self.assertEqual(result['status'],'SAT',result)
        self.assertEqual(result['replacement_terms'],[])

    @unittest.skipUnless(importlib.util.find_spec('pysat') is not None,'CaDiCaL unavailable')
    def test_cadical_fallback_exact_cube_and_rank_zero_unsat(self):
        for slots,expected in ((1,'SAT'),(0,'UNSAT')):
            problem=build_patch_problem([(1,1,1)],slots,n=2,use_bounds=False)
            result=solve_patch(problem,seconds=1,conflicts=10000,backend='cadical')
            self.assertEqual(result['status'],expected,result)
            if expected=='SAT':
                self.assertEqual(validate_decode_patch(problem,result['model']),{(1,1,1)})


if __name__=='__main__':
    unittest.main()
