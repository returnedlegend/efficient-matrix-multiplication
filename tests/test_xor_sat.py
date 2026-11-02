import copy
import importlib.util
import itertools
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from mmsearch.compact_sat import build_compact_cnf
from mmsearch.sat import CNF
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.verify import verify_candidate
from mmsearch.xor_sat import XorCNF, build_xor_cnf, solve_local, validate_model, write_problem


class NativeXorEncodingTests(unittest.TestCase):
    def test_parity_semantics_exhaustive_with_constants_duplicates(self):
        for inputs in ([], [0], [1], [1, 1], [1, 2], [0, 1, 2, 1, 3], [1, 2, 3]):
            for required in (0, 1):
                cnf, xor = CNF(), XorCNF()
                for _ in range(3):
                    cnf.variable()
                    xor.variable()
                cnf.parity(inputs, required)
                xor.parity(inputs, required)
                for values in itertools.product((False, True), repeat=3):
                    expected = sum(values[x-1] for x in inputs if x) % 2 == required
                    found = False
                    for extra in itertools.product((False, True), repeat=cnf.nv-3):
                        assignment = (False,)+values+extra
                        if all(any(assignment[abs(x)] == (x > 0) for x in clause) for clause in cnf.clauses):
                            found = True
                            break
                    self.assertEqual(found, expected)
                    model = [i if value else -i for i, value in enumerate(values, 1)]
                    if expected:
                        validate_model(dict(clauses=xor.clauses, xors=xor.xors), model)
                    else:
                        with self.assertRaises(AssertionError):
                            validate_model(dict(clauses=xor.clauses, xors=xor.xors), model)

    def test_and_gate_cnf_exhaustively(self):
        for factors in ([1, 2, 3], [1, 1, 2], [0, 1, 2]):
            cnf = XorCNF()
            for _ in range(3):
                cnf.variable()
            output = cnf.conjunction(factors)
            for values in itertools.product((False, True), repeat=cnf.nv):
                assignment = (False,)+values
                actual = all(any(assignment[abs(x)] == (x > 0) for x in clause) for clause in cnf.clauses)
                expected = assignment[output] == all(assignment[x] for x in factors)
                self.assertEqual(actual, expected)

    def test_signed_literals_cancel_correctly(self):
        xor = XorCNF()
        xor.parity([-1, 1, -2, 0], 1)
        self.assertEqual(xor.xors, [([2], True)])

    def test_native_encoder_preserves_original_module_and_reduces_auxiliaries(self):
        source = naive_candidate(2)
        before = build_compact_cnf(source, rank=7, active_terms=list(range(7)), drop_term=7)
        native = build_xor_cnf(source, rank=7, active_terms=list(range(7)), drop_term=7)
        after = build_compact_cnf(source, rank=7, active_terms=list(range(7)), drop_term=7)
        self.assertEqual(before, after)
        self.assertLess(native['nv'], before['nv'])
        self.assertLess(len(native['clauses']), len(before['clauses']))
        self.assertGreater(len(native['xors']), 0)
        self.assertEqual(native['metadata']['image_bases'], before['metadata']['image_bases'])

    def test_extended_dimacs_records_rhs_and_all_equations(self):
        problem = dict(nv=3, clauses=[[1], [-2]], xors=[([1, 2], False), ([2, 3], True)], metadata={})
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)/'problem'
            write_problem(problem, prefix)
            self.assertEqual(prefix.with_suffix('.cnf').read_text(),
                             'p cnf 3 4\n1 0\n-2 0\nx-1 2 0\nx2 3 0\n')


@unittest.skipUnless(importlib.util.find_spec('pycryptosat'), 'optional pycryptosat missing')
class NativeXorSolverTests(unittest.TestCase):
    def solve(self, source, active, drop=7, symmetry='none'):
        problem = build_xor_cnf(source, rank=len(source['terms'])-1,
                                active_terms=active, drop_term=drop, symmetry=symmetry)
        return problem, solve_local(problem, seconds=5, conflicts=100000)

    def test_exact_unsat_two_independent_terms(self):
        _, result = self.solve(naive_candidate(2), [0])
        self.assertEqual(result['status'], 'UNSAT')
        self.assertNotIn('candidate', result)

    def test_full_naive8_to_strassen7(self):
        for symmetry in ('none', 'u-lex'):
            _, result = self.solve(naive_candidate(2), list(range(7)), symmetry=symmetry)
            self.assertEqual(result['status'], 'SAT')
            self.assertTrue(verify_candidate(result['candidate'], random_trials=64)['valid'])
            self.assertEqual(result['verification']['exact_entries_checked'], 64)

    def test_planted_full_rank7_and_original_coordinate_decoding(self):
        source = strassen_candidate(2)
        source['terms'].append({axis: [0]*4 for axis in ('u', 'v', 'w')})
        for active in ([0], list(range(7))):
            _, result = self.solve(source, active)
            self.assertEqual(result['status'], 'SAT')
            self.assertTrue(verify_candidate(result['candidate'])['valid'])
            self.assertEqual(result['verification']['exact_entries_checked'], 64)

    def test_all_15625_ambient_entries_checked_before_acceptance(self):
        source = naive_candidate(5)
        source['terms'].append({axis: [0]*25 for axis in ('u', 'v', 'w')})
        _, result = self.solve(source, [0], drop=125)
        self.assertEqual(result['status'], 'SAT')
        self.assertEqual(result['verification']['exact_entries_checked'], 15625)
        self.assertTrue(verify_candidate(result['candidate'])['valid'])

    def test_zero_image_core_decodes_all_zero_mutable_slot(self):
        source = naive_candidate(2)
        source['terms'].extend([copy.deepcopy(source['terms'][0]), copy.deepcopy(source['terms'][0])])
        problem, result = self.solve(source, [8], drop=9)
        self.assertEqual(problem['metadata']['image_shape'], [0, 0, 0])
        self.assertEqual(result['status'], 'SAT')
        self.assertTrue(verify_candidate(result['candidate'])['valid'])

    def test_hard_wall_reports_unknown(self):
        problem = build_xor_cnf(naive_candidate(2), rank=7, active_terms=[0], drop_term=7)
        def blocked_worker(*args):
            time.sleep(1)
        started = time.monotonic()
        with patch('mmsearch.xor_sat._worker', blocked_worker):
            result = solve_local(problem, seconds=0.02, conflicts=1)
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertLess(time.monotonic()-started, 0.5)
        self.assertNotIn('candidate', result)

    def test_independent_verifier_rejects_corrupt_decoding(self):
        source = strassen_candidate(2)
        source['terms'].append({axis: [0]*4 for axis in ('u', 'v', 'w')})
        corrupt = strassen_candidate(2)
        corrupt['terms'][0]['u'] = [0]*4
        problem = build_xor_cnf(source, rank=7, active_terms=[0], drop_term=7)
        with patch('mmsearch.xor_sat.decode_model', return_value=corrupt):
            with self.assertRaises(AssertionError):
                solve_local(problem, seconds=5, conflicts=100000)


if __name__ == '__main__':
    unittest.main()
