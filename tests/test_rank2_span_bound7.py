"""Independent finite-space controls for a necessary condition, never N5 search."""
import importlib.util
import itertools
from pathlib import Path
import unittest
from unittest.mock import patch

from mmsearch import rank2_span_bound7 as subject


def oracle_module():
    path = Path(__file__).parent/'fixtures/compact_rank2_edges43_oracle.py'
    spec = importlib.util.spec_from_file_location('rank2_span_independent_oracle', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def diagonal(indices, width):
    return sum(1 << (i*width+i) for i in indices)


class RankTwoSpanBoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = oracle_module()

    def witness(self, result):
        basis = [int(v, 16) for v in result['space_basis_hex']]
        matrices = []
        for point in result['low_rank_witness']:
            coordinates = int(point['space_coordinates_hex'], 16)
            rebuilt = 0
            for i, value in enumerate(basis):
                if coordinates >> i & 1:
                    rebuilt ^= value
            self.assertEqual(rebuilt, int(point['matrix_hex'], 16))
            self.assertEqual(self.oracle.matrix_rank(rebuilt, *result['shape']), point['matrix_rank'])
            self.assertIn(point['matrix_rank'], (1, 2))
            matrices.append(rebuilt)
        self.assertEqual(len(self.oracle.independent(matrices)), len(matrices))

    def test_bound_formula_all_surpluses_and_no_giant_power(self):
        for d, c in itertools.product(range(41), range(9)):
            self.assertEqual(subject.required_rank2_span(d, c), max(0, d+c-(2**c-1)))
        self.assertEqual([subject.required_rank2_span(12, c) for c in range(5)], [12, 12, 11, 8, 1])
        self.assertEqual(subject.required_rank2_span(12, 10**1000), 0)
        for bad in (True, -1, 1.0):
            with self.assertRaises(ValueError):
                subject.required_rank2_span(bad, 2)
            with self.assertRaises(ValueError):
                subject.required_rank2_span(2, bad)

    def test_c2_excludes_despite_an_existing_rank_two_direction(self):
        raw = [diagonal(range(2), 8), diagonal(range(2, 5), 8), diagonal(range(5, 8), 8)]
        self.assertEqual(self.oracle.matrix_rank(raw[0], 8, 8), 2)
        result = subject.classify_pair_image(raw, 8, 8, 5)
        self.assertEqual((result['status'], result['image_rank'], result['required_rank2_span'],
                          result['rank2_span_rank']), ('EXCLUDED', 3, 2, 1))
        self.assertTrue(result['complete']); self.assertTrue(result['enumeration_complete'])
        self.assertEqual(result['enumerated_vectors'], 7)
        self.witness(result)

    def test_c2_d_minus_one_is_tight_in_diagonal_cover(self):
        # The four coordinate rank-one points cover this two-dimensional image.
        # Its other mode flattening has rank4, so CP=4=d+2. Only E44 has rank<=2.
        raw = [diagonal(range(3), 4), diagonal([3], 4)]
        result = subject.classify_pair_image(raw, 4, 4, 4)
        self.assertEqual((result['status'], result['required_rank2_span'],
                          result['rank2_span_rank']), ('NOT_EXCLUDED', 1, 1))
        self.assertFalse(result['existence_claim'])
        self.witness(result)

    def test_not_excluded_does_not_claim_existence(self):
        result = subject.classify_pair_image([diagonal(range(2), 2)], 2, 2, 1)
        self.assertEqual(result['status'], 'NOT_EXCLUDED')
        self.assertEqual(self.oracle.matrix_rank(9, 2, 2), 2)  # This one-slice CP rank is2>1.
        self.assertFalse(result['existence_claim'])
        self.assertIn('not an existence', result['scope'])
        result = subject.classify_pair_image([33, 33792], 4, 4, 3)
        self.assertEqual(result['status'], 'NOT_EXCLUDED')  # Distinct cosets still obstruct CP<=3.

    def test_caps_and_cooperative_stops_are_unknown(self):
        raw = [diagonal(range(3), 4), diagonal([3], 4)]
        self.assertEqual(subject.classify_pair_image(raw, 4, 4, 4, max_vectors=2)['status'], 'UNKNOWN')
        self.assertEqual(subject.classify_pair_image(raw, 4, 4, 4, max_vectors=3)['status'], 'NOT_EXCLUDED')
        self.assertEqual(subject.classify_pair_image(raw, 4, 4, 4, seconds=0)['status'], 'UNKNOWN')
        self.assertEqual(subject.classify_pair_image(raw, 4, 4, 4, cancelled=lambda: True)['status'], 'UNKNOWN')
        now = [0.]
        actual = subject.matrix_rank_at_most_two
        def late(*args):
            answer = actual(*args); now[0] = 1.; return answer
        with patch.object(subject, 'matrix_rank_at_most_two', late):
            result = subject.classify_pair_image([1], 1, 1, 1, seconds=.5, clock=lambda: now[0])
        self.assertEqual(result['status'], 'UNKNOWN'); self.assertFalse(result['complete'])
        self.assertFalse(result['existence_claim'])

    def test_early_necessary_witness_and_raw_zero_dependent_slices(self):
        result = subject.classify_pair_image([0, 1, 8, 9, 1], 2, 2, 2, max_vectors=2)
        self.assertEqual(result['status'], 'NOT_EXCLUDED')
        self.assertTrue(result['complete']); self.assertFalse(result['enumeration_complete'])
        self.assertEqual(result['enumerated_vectors'], 2)
        self.assertIsNone(result['rank2_span_rank'])
        self.assertEqual(result['observed_rank2_span_rank'], 2)
        self.witness(result)
        self.assertNotEqual(result['raw_target_sha256'],
                            subject.classify_pair_image([1, 8], 2, 2, 2)['raw_target_sha256'])

    def test_zero_vacuous_and_flattening_cases(self):
        for a, b in ((0, 0), (0, 3), (3, 0), (2, 3)):
            result = subject.classify_pair_image([0, 0], a, b, 0, max_vectors=0)
            self.assertEqual(result['status'], 'NOT_EXCLUDED')
            self.assertTrue(result['enumeration_complete'])
        result = subject.classify_pair_image([1, 8], 2, 2, 1, max_vectors=0)
        self.assertEqual(result['status'], 'EXCLUDED')
        self.assertEqual(result['case'], 'flattening_rank_exceeds_budget')
        result = subject.classify_pair_image([diagonal(range(4), 4)], 4, 4, 3, max_vectors=0)
        self.assertEqual(result['status'], 'NOT_EXCLUDED')
        self.assertEqual(result['case'], 'vacuous_necessary_bound')

    def test_invalid_literal_input(self):
        for raw, a, b, budget, kwargs in [([True], 1, 1, 1, {}), ([-1], 2, 2, 1, {}),
                ([16], 2, 2, 1, {}), ([1], True, 1, 1, {}), ([1], 1, 1, True, {}),
                ([1], 1, 1, 1, {'max_vectors': True}), ([1], 1, 1, 1, {'seconds': float('inf')}),
                ([1], 1, 1, 1, {'seconds': True})]:
            with self.subTest(raw=raw, a=a, budget=budget, kwargs=kwargs), self.assertRaises(ValueError):
                subject.classify_pair_image(raw, a, b, budget, **kwargs)

    def test_all_2892_tiny_spaces_against_exact_cover_oracle(self):
        spaces_checked = checks = false_passes = 0
        for a, b in ((2, 2), (2, 3)):
            spaces = self.oracle.all_subspaces(a*b)
            rank_one = self.oracle.rankone_points(a, b)
            attainable = [(L.bit_count().bit_length()-1, L) for L in spaces
                          if self.oracle.span(p for p in rank_one if L >> p & 1)
                          == frozenset(self.oracle.points(L))]
            for encoded in spaces:
                points = list(self.oracle.points(encoded)); basis = self.oracle.independent(points)
                exact_cp = min(rank for rank, L in attainable if encoded & ~L == 0)
                low_rank = len(self.oracle.independent(p for p in points
                                if self.oracle.matrix_rank(p, a, b) <= 2))
                for budget in range(a*b+4):
                    result = subject.classify_pair_image([0, *basis, *basis[:1]], a, b, budget)
                    expected = (budget < len(basis) or low_rank <
                                subject.required_rank2_span(len(basis), budget-len(basis)))
                    self.assertEqual(result['status'] == 'EXCLUDED', expected)
                    if exact_cp <= budget:
                        self.assertNotEqual(result['status'], 'EXCLUDED', (a, b, basis, budget, exact_cp))
                    false_passes += result['status'] == 'NOT_EXCLUDED' and exact_cp > budget
                    checks += 1
                spaces_checked += 1
        self.assertEqual(spaces_checked, 2892); self.assertEqual(checks, 28786)
        self.assertGreater(false_passes, 0)
        print('exact_cover_oracle_spaces', spaces_checked, 'budgets', checks,
              'necessary_false_passes', false_passes)

    def test_all_2892_diagonal_spaces_against_exact_diagonal_cp(self):
        # On diagonal matrices, matrix rank is Hamming weight. The active
        # coordinate count is both a coordinate-point cover and a flattening LB.
        checks = exclusions = budget_checks = c2_exclusions = 0
        for width in (4, 6):
            for encoded in self.oracle.all_subspaces(width):
                points = list(self.oracle.points(encoded)); masks = self.oracle.independent(points)
                active = 0
                for point in points:
                    active |= point
                exact_cp = active.bit_count()
                low_rank = len(self.oracle.independent(p for p in points if p.bit_count() <= 2))
                raw = [diagonal([i for i in range(width) if mask >> i & 1], width) for mask in masks]
                d = len(masks)
                for budget in sorted({d, exact_cp, max(d, exact_cp-1), d+2}):
                    result = subject.classify_pair_image(raw, width, width, budget)
                    expected = low_rank < subject.required_rank2_span(d, budget-d)
                    self.assertEqual(result['status'] == 'EXCLUDED', expected)
                    if exact_cp <= budget:
                        self.assertNotEqual(result['status'], 'EXCLUDED')
                    exclusions += result['status'] == 'EXCLUDED'
                    c2_exclusions += budget == d+2 and result['status'] == 'EXCLUDED'
                    budget_checks += 1
                checks += 1
        self.assertEqual(checks, 2892); self.assertGreater(exclusions, 0)
        self.assertGreater(c2_exclusions, 0)
        print('diagonal_spaces', checks, 'budgets', budget_checks,
              'necessary_exclusion_decisions', exclusions, 'c2_excluded_spaces', c2_exclusions)


if __name__ == '__main__':
    unittest.main()
