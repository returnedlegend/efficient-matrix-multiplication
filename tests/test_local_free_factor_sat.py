"""Exact local impossibility and planted 8-to-7 full-tensor SAT controls."""
import importlib.util
import unittest
from unittest.mock import patch
import time

from mmsearch.free_factor_sat import build_problem,build_system,solve
from mmsearch.local_free_factor_sat import checked_circuits,local_assumptions,local_bound,neighborhoods
from mmsearch.recombine import canonical_terms
from mmsearch.tensor import naive_candidate,strassen_candidate
from mmsearch.verify import verify_candidate

HAVE_SOLVER = bool(importlib.util.find_spec('pycryptosat') and importlib.util.find_spec('pysat'))


def planted_system():
    baseline = naive_candidate(2)
    planted = strassen_candidate(2)
    dictionary = sorted(set(canonical_terms(baseline)) | set(canonical_terms(planted)))
    system = build_system(dictionary,2,'wu',baseline)
    planted_vectors = build_system(dictionary,2,'wu',planted)['baseline_vectors']
    free = [g for g,(a,b) in enumerate(zip(system['baseline_vectors'],planted_vectors)) if a != b]
    return system,free


class LocalFreeFactorTests(unittest.TestCase):
    def test_forced_bound_proves_local_eight_cannot_reach_seven(self):
        baseline = naive_candidate(2)
        system = build_system(canonical_terms(baseline),2,'wu',baseline)
        # Every pair column is independent here; any selection of free vectors
        # remains forced by global tensor equality to its original nonzero value.
        for free in ([],[0],[1,3,5],list(range(8))):
            bound = local_bound(system,free,7)
            self.assertEqual(bound['status'],'LOCAL_UNSAT_BOUND')
            self.assertEqual(bound['lower_bound'],8)
            self.assertEqual(bound['local_nullity'],0)

    def test_circuits_checked_against_full_rows_and_connected_neighborhoods(self):
        system,_ = planted_system()
        pivots = {min(g for g in range(len(system['pairs'])) if coefficient >> g & 1)
                  for coefficient,_,_ in system['reduced']['rows']}
        records = []
        for free in range(len(system['pairs'])):
            if free in pivots:
                continue
            support = [free]
            for coefficient,_,_ in system['reduced']['rows']:
                if coefficient >> free & 1:
                    support.append((coefficient & -coefficient).bit_length()-1)
            records.append(dict(support=sorted(support)))
        supports = checked_circuits(system,records)
        plan = list(neighborhoods(system,supports,seed=17,families=4,max_groups=16))
        self.assertTrue(plan)
        for item in plan:
            union = set()
            for i in item['circuit_indices']:
                if union:
                    self.assertTrue(union & supports[i])
                union.update(supports[i])
            self.assertEqual(union,set(item['free_groups']))
            self.assertLessEqual(len(union),16)
            self.assertIn(item['circuit_count'],(1,2,4,8,16))
        with self.assertRaisesRegex(ValueError,'kernel'):
            checked_circuits(system,[dict(support=[0])])

    @unittest.skipUnless(HAVE_SOLVER,'optional XOR solver unavailable')
    def test_planted_local_eight_to_seven_with_all_outside_bits_fixed(self):
        system,free = planted_system()
        assumptions = local_assumptions(system,free)
        outside = set(range(len(system['pairs'])))-set(free)
        fixed_variables = {abs(lit) for lit in assumptions}
        width = system['metadata']['width']
        for g in outside:
            self.assertTrue(all(g*width+c+1 in fixed_variables for c in range(width)))
        for g in free:
            self.assertFalse(any(g*width+c+1 in fixed_variables for c in range(width)))
        control = solve(build_problem(system,8),seconds=2,memory_mb=512,assumptions=assumptions)
        self.assertEqual(control['status'],'SAT')
        result = solve(build_problem(system,7),seconds=2,memory_mb=512,assumptions=assumptions)
        self.assertEqual(result['status'],'SAT')
        self.assertEqual(result['verification']['rank'],7)
        self.assertTrue(result['worker_reaped'])
        self.assertTrue(verify_candidate(result['candidate'],random_trials=0)['valid'])
        self.assertEqual(result['verification']['exact_entries_checked'],64)
        self.assertLessEqual(local_bound(system,free,7)['lower_bound'],7)

    @unittest.skipUnless(HAVE_SOLVER,'optional XOR solver unavailable')
    def test_empty_free_neighborhood_cannot_improve_and_timeout_is_unknown(self):
        system,_ = planted_system()
        problem = build_problem(system,7)
        result = solve(problem,seconds=2,memory_mb=512,assumptions=local_assumptions(system,[]))
        self.assertEqual(result['status'],'UNSAT')
        self.assertEqual(local_bound(system,[],7)['status'],'LOCAL_UNSAT_BOUND')
        def stall(*args):
            time.sleep(.3)
        with patch('mmsearch.free_factor_sat._worker',stall):
            result = solve(problem,seconds=.02,memory_mb=512,assumptions=[])
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertTrue(result['worker_reaped'])
        self.assertLess(result['elapsed_seconds'],1)


if __name__ == '__main__':
    unittest.main()
