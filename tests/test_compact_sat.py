import copy
import importlib.util
import itertools
import random
import unittest

from mmsearch.compact_sat import BinaryBasis, build_compact_cnf, compress_residual, image_bases, lex_nondecreasing
from mmsearch.sat import CNF, build_local_cnf, solve_local
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.verify import verify_candidate


class CompactBasisTests(unittest.TestCase):
    def test_lex_comparator_exhaustively(self):
        cnf = CNF()
        left = [cnf.variable() for _ in range(2)]
        right = [cnf.variable() for _ in range(2)]
        lex_nondecreasing(cnf, left, right)
        for values in itertools.product((False, True), repeat=4):
            possible = False
            for extra in itertools.product((False, True), repeat=cnf.nv-4):
                assignment = dict(zip(range(1, cnf.nv+1), values+extra))
                if all(any(assignment[abs(lit)] == (lit > 0) for lit in clause) for clause in cnf.clauses):
                    possible = True
                    break
            self.assertEqual(possible, values[:2] <= values[2:])

    def test_basis_coordinates_roundtrip_and_linear_projection(self):
        rng = random.Random(193)
        for _ in range(30):
            basis = BinaryBasis([rng.randrange(1 << 9) for _ in range(5)])
            for coordinates in range(1 << len(basis.vectors)):
                vector = basis.expand(coordinates)
                self.assertEqual(basis.coordinates(vector, require_member=True), coordinates)
            for _ in range(10):
                a, b = rng.randrange(1 << 9), rng.randrange(1 << 9)
                self.assertEqual(basis.coordinates(a ^ b), basis.coordinates(a) ^ basis.coordinates(b))
        with self.assertRaises(ValueError):
            BinaryBasis([1]).coordinates(2, require_member=True)

    def test_known_residual_image_and_exact_expansion(self):
        source = naive_candidate(2)
        bases, core, shape, _ = compress_residual(source, [0, 7])
        self.assertEqual(shape, [2, 2, 2])
        self.assertEqual(sum(core), 2)
        self.assertEqual([len(b.vectors) for b in image_bases([0]*64, 4)], [0, 0, 0])

    def test_strict_exact_source_and_dimensions(self):
        source = naive_candidate(2)
        for value in (1.0, True, 2):
            corrupt = copy.deepcopy(source)
            corrupt['terms'][0]['u'][0] = value
            with self.assertRaises(ValueError):
                build_compact_cnf(corrupt, rank=7, drop_term=7, active_terms=[0])
        invalid = copy.deepcopy(source)
        invalid['terms'][0]['u'][0] = 0
        with self.assertRaises(ValueError):
            build_compact_cnf(invalid, rank=7, drop_term=7, active_terms=[0])
        with self.assertRaises(ValueError):
            build_compact_cnf(source, rank=6)


@unittest.skipUnless(importlib.util.find_spec('pysat'), 'python-sat missing')
class CompactSolverTests(unittest.TestCase):
    def compare(self, source, active, dropped, expected):
        rank = len(source['terms'])-1
        original = build_local_cnf(source, rank=rank, active_terms=active,
                                   drop_term=dropped, support_mode='full')
        compact = build_compact_cnf(source, rank=rank, active_terms=active, drop_term=dropped)
        for problem in (original, compact):
            result = solve_local(problem, seconds=5, conflicts=100000)
            self.assertEqual(result['status'], expected)
            if expected == 'SAT':
                self.assertTrue(verify_candidate(result['candidate'])['valid'])
                self.assertEqual(result['verification']['exact_entries_checked'], 64)
        self.assertEqual(compact['metadata']['preprocessing_exact_entries_checked'], 64)
        self.assertLessEqual(compact['metadata']['compressed_tensor_equations'], 64)

    def test_full_compact_unsat_agree_two_independent_terms(self):
        self.compare(naive_candidate(2), [0], 7, 'UNSAT')

    def test_full_compact_sat_agree_with_dense_strassen_factor(self):
        source = strassen_candidate(2)
        source['terms'].append({a: [0]*4 for a in ('u', 'v', 'w')})
        self.compare(source, [0], 7, 'SAT')

    def test_nontrivial_naive8_to_strassen7_control(self):
        self.compare(naive_candidate(2), list(range(7)), 7, 'SAT')

    def test_nontrivial_symmetry_control_preserves_sat(self):
        problem = build_compact_cnf(naive_candidate(2), rank=7, active_terms=list(range(7)),
                                    drop_term=7, symmetry='u-lex')
        result = solve_local(problem, seconds=5, conflicts=100000)
        self.assertEqual(result['status'], 'SAT')
        self.assertTrue(result['verification']['valid'])

    def test_cancelling_patch_zero_core(self):
        source = naive_candidate(2)
        source['terms'].extend([copy.deepcopy(source['terms'][0]), copy.deepcopy(source['terms'][0])])
        problem = build_compact_cnf(source, rank=9, active_terms=[8], drop_term=9)
        self.assertEqual(problem['metadata']['image_shape'], [0, 0, 0])
        result = solve_local(problem, seconds=2, conflicts=100)
        self.assertEqual(result['status'], 'SAT')
        self.assertTrue(result['verification']['valid'])


if __name__ == '__main__':
    unittest.main()
