import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mmsearch.cyclic_orbit_large import (choose_large_neighbor_orbits,encoding_estimate,
                                       guarded_patch_problem)
from mmsearch.cyclic_orbit_sat import solve_patch,validate_decode_global
from mmsearch.search import _rotations,naive_terms


def planted_patch():
    return {item for term in ((9,2,4),(8,2,6),(8,6,2)) for item in _rotations(term)}


class LargeOrbitTests(unittest.TestCase):
    def test_estimates_bound_actual_encoder_and_grow_with_dimension(self):
        problem=guarded_patch_problem(planted_patch(),2,n=2)
        estimate=problem['metadata']['encoding_estimate']
        self.assertFalse(problem['metadata']['skipped_too_large'])
        self.assertGreaterEqual(estimate['variables'],problem['nv'])
        self.assertGreaterEqual(estimate['cnf_clauses'],len(problem['clauses']))
        self.assertGreaterEqual(estimate['native_xors'],len(problem['xors']))
        largest=encoding_estimate(25,9)
        self.assertEqual(largest['variables'],142182)
        self.assertEqual(largest['cnf_clauses'],564246)
        self.assertGreater(largest['estimated_memory_mb'],estimate['estimated_memory_mb'])

    def test_size_guard_skips_before_any_nonlinear_encoding_without_unsat_claim(self):
        problem=guarded_patch_problem(planted_patch(),2,n=2,max_variables=1,max_clauses=1,
                                      max_estimated_memory_mb=128)
        self.assertTrue(problem['metadata']['skipped_too_large'])
        self.assertFalse(problem['metadata']['lower_bound_rejected'])
        self.assertEqual(problem['metadata']['encoding_status'],'NOT_ENCODED_SIZE_GUARD')
        self.assertEqual(problem['nv'],0)
        self.assertEqual(problem['clauses'],[])
        self.assertIsNone(problem['metadata']['formula_sha256'])

    @unittest.skipUnless(importlib.util.find_spec('pycryptosat') is not None,'native XOR solver unavailable')
    def test_guarded_planted_control_reuses_exact_encoder_and_global_verification(self):
        problem=guarded_patch_problem(planted_patch(),2,n=2)
        problem['outside_terms']=[(1,1,1),(8,8,8)]
        problem['metadata']['global_nominal_rank_cap']=8
        result=solve_patch(problem,seconds=1,conflicts=100000,backend='cryptominisat')
        self.assertEqual(result['status'],'SAT',result)
        candidate,report=validate_decode_global(problem,result['model'])
        self.assertTrue(report['valid']);self.assertEqual(report['exact_entries_checked'],64)
        self.assertLessEqual(len(candidate['terms']),8)

    def test_large_configuration_accepts_only_new_k_range_and_rejects_old_cli_range(self):
        terms=naive_terms(5)
        for k in (8,9,10):
            first=choose_large_neighbor_orbits(terms,k,seed=11,anchor=0)
            self.assertEqual(len(set(first)),k)
            self.assertEqual(first,choose_large_neighbor_orbits(terms,k,seed=11,anchor=0))
        for k in (7,11):
            with self.assertRaises(ValueError):
                choose_large_neighbor_orbits(terms,k)
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'must-not-exist'
            result=subprocess.run([sys.executable,str(root/'scripts/campaign_cyclic_orbit_sat_large.py'),
                                   '--output-dir',str(output),'--k-min','7'],
                                  capture_output=True,text=True,timeout=3)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(output.exists())


if __name__=='__main__':
    unittest.main()
