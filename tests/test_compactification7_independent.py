"""Synthetic N4 controls; no production source reads or N5 decoder queries."""
import itertools
import json
from pathlib import Path
import tempfile
import unittest

from mmsearch.compact_eight43 import (bits, expand_core, factor_core,
                                     opposite_pair_ranks, packed_tensor,
                                     replace_and_verify)
from mmsearch.compact_coset43 import mode_slices
from mmsearch.compact_rank2_edges43 import solve_core as solve_one
from mmsearch.marathon7_modeclosure11 import factor_image_closure
from mmsearch.sat_neighborhoods import gf2_rank
from mmsearch.search import naive_terms, encode_candidate
from mmsearch.surplus_two7 import solve_core as solve_two
from scripts.verify_record42_independent import _check_all_basis_outputs


EXTRA_TRIPLES = [(0, 2, 2), (0, 3, 3), (1, 2, 3), (1, 3, 2), (2, 0, 2)]


def planted_n4(extra_count):
    """Seven naive N2 products plus 4/5 isolated coordinate products in N4.

    N2's omitted triple is (0,0,0). Extras have distinct factor coordinates
    in each mode, outside the four 2x2-block coordinates. This makes the
    compact residual a direct sum, although its whole source is naive N4.
    """
    if extra_count not in (4, 5):
        raise ValueError('only independently reviewed d8/d9 controls')
    triples = [point for point in itertools.product(range(2), repeat=3)
               if point != (0, 0, 0)] + EXTRA_TRIPLES[:extra_count]
    selected = [(1 << (i*4+j), 1 << (j*4+k), 1 << (k*4+i)) for i, j, k in triples]
    terms = list(naive_terms(4))
    indices = sorted(terms.index(term) for term in selected)
    source = encode_candidate(terms, 4)
    d = 4+extra_count
    case = dict(id='independent-n4-true-c2-d'+str(d), source_indices=indices,
                source_products=64, source_local_products=7+extra_count,
                target_local_products=6+extra_count, shape=[d]*3,
                mode_rank=d, free_axis=0)
    return source, terms, case


class CompactificationIndependentControls(unittest.TestCase):
    def test_mixed12_adapter_true_c2_n4_controls(self):
        from mmsearch.extend_eight_bulk43 import SourceCache
        from scripts.run_c3_mixed12_pilot7 import run_case
        from tests.test_run_c3_mixed9_pilot7 import Guard
        for extra in (4, 5):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); source, _, case = planted_n4(extra)
                (root/'source.json').write_text(json.dumps(source))
                case['source'] = 'source.json'
                result = run_case(SourceCache(root), case, root/'out', Guard(),
                                  control_expected_rank=63)
                self.assertEqual(result['status'], 'SMALL_CONTROL_PASSED', result)
                self.assertEqual(result['decoder_case'], 'repeated_coset_pair_extension')
                self.assertEqual(result['candidate_rank'], 63)
                self.assertEqual(result['primary']['exact_entries_checked'], 4096)
                self.assertEqual(result['independent']['exact_entries_checked'], 4096)
                self.assertEqual(len(list((root/'out/records').glob('*.json'))), 1)
                self.assertFalse((root/'out/WINNER.json').exists())

    def test_mixed12_adapter_late_true_c2_results_never_publish(self):
        from mmsearch.extend_eight_bulk43 import SourceCache
        from mmsearch.local_guard43 import CampaignHold
        from scripts.run_c3_mixed12_pilot7 import run_case
        from tests.test_run_c3_mixed9_pilot7 import Guard
        for barrier in ('post_solve', 'post_lift_full', 'post_persisted_primary_full',
                        'post_strict_independent_full', 'pre_canonical_rename',
                        'post_eligible_publication', 'post_result_publication'):
            with self.subTest(barrier=barrier), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); source, _, case = planted_n4(5)
                (root/'source.json').write_text(json.dumps(source)); case['source'] = 'source.json'
                class LateGuard(Guard):
                    def check(self, name):
                        if name == barrier:
                            raise CampaignHold('independent late barrier', name)
                result = run_case(SourceCache(root), case, root/'out', LateGuard(),
                                  control_expected_rank=63)
                self.assertEqual(result['status'], 'UNKNOWN', result)
                self.assertFalse(result['complete']); self.assertTrue(result['raw_retained'])
                self.assertFalse(list((root/'out/records').glob('*.json')))
                self.assertFalse((root/'out'/(case['id']+'.result.json')).exists())
                self.assertTrue(list((root/'out/.raw-returns').glob('*.raw')))

    def test_true_c2_d8_and_d9_full_n4_replacement(self):
        for extra in (4, 5):
            with self.subTest(extra=extra):
                source, terms, case = planted_n4(extra)
                indices = case['source_indices']; d = 4+extra; target = d+2
                self.assertEqual(opposite_pair_ranks(terms, 16), [64]*3)
                self.assertEqual(opposite_pair_ranks([terms[i] for i in indices], 16),
                                 [len(indices)]*3)
                bases, core, shape = factor_core(terms, indices)
                self.assertEqual(shape, [d]*3)
                self.assertEqual([gf2_rank(mode_slices(core, shape, a)[0])
                                  for a in range(3)], [d]*3)
                original = 0
                for i in indices:
                    original ^= packed_tensor(terms[i], 16)
                self.assertEqual(expand_core(core, shape, bases, 16), original)
                # This proves the added support cannot pass through only the
                # old CP(d+1) route. It is not a heuristic branch label.
                lower = solve_one(core, shape, d+1, axis=0, max_vectors=1023)
                self.assertEqual(lower['status'], 'LOCAL_UNSAT')
                self.assertTrue(lower['complete'])
                result = solve_two(core, shape, target, axis=0,
                                   max_vectors=1023, max_extensions=1533,
                                   timeout_seconds=8)
                self.assertEqual(result['status'], 'SAT')
                self.assertEqual(result['case'], 'repeated_coset_pair_extension')
                self.assertEqual(len(result['products']), target)
                lifted = []
                for term in result['products']:
                    factors = []
                    for mask, basis in zip(term, bases):
                        value = 0
                        for index in bits(mask):
                            value ^= basis[index]
                        factors.append(value)
                    lifted.append(tuple(factors))
                ambient = 0
                for term in lifted:
                    ambient ^= packed_tensor(term, 16)
                self.assertEqual(ambient, original)
                candidate, primary = replace_and_verify(source, indices, lifted)
                self.assertEqual(len(candidate['terms']), 63)
                self.assertTrue(primary['valid'])
                self.assertEqual(primary['exact_entries_checked'], 4096)
                strict = _check_all_basis_outputs(4, [tuple(tuple(t[a]) for a in ('u','v','w'))
                                                      for t in candidate['terms']])
                self.assertEqual(strict['mismatch_count'], 0)
                self.assertEqual(strict['output_bits_checked'], 4096)
                print('n4_positive', dict(d=d, source_local=len(indices), target=target,
                      pair_ranks=[len(indices)]*3, branch=result['case'], global_rank=63,
                      primary_entries=4096, independent_entries=4096))

    def test_finite_factor_image_closure_is_exact_and_idempotent(self):
        _, terms, case = planted_n4(5)
        result = factor_image_closure(terms, case['source_indices'])
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['shape'], [9]*3)
        allowed = [{terms[i][a] for i in case['source_indices']} for a in range(3)]
        expected = [i for i, term in enumerate(terms)
                    if all(term[a] in allowed[a] for a in range(3))]
        actual = [point['source_index'] for point in result['closure']]
        self.assertEqual(actual, expected)
        repeated = factor_image_closure(terms, actual)
        self.assertEqual([point['source_index'] for point in repeated['closure']], actual)
        bases, core, shape = factor_core(terms, actual)
        self.assertEqual(shape, [9]*3)
        self.assertEqual([gf2_rank(mode_slices(core, shape, a)[0]) for a in range(3)], [9]*3)
        for point in result['closure']:
            for axis, coordinates in enumerate(point['factor_coordinates']):
                rebuilt = 0
                for j in bits(coordinates):
                    rebuilt ^= result['basis_witnesses'][axis]['basis'][j]
                self.assertEqual(rebuilt, terms[point['source_index']][axis])
        self.assertEqual(factor_image_closure(terms, actual, cancelled=lambda:True)['status'], 'UNKNOWN')

    def test_pair_independence_is_needed_for_actual_image_claim(self):
        terms = [(1, 1, 1), (2, 1, 1)]
        self.assertEqual(opposite_pair_ranks(terms, 2), [1, 2, 2])
        _, core, shape = factor_core(terms, [0, 1])
        self.assertEqual(shape, [2, 1, 1])
        self.assertEqual(gf2_rank(mode_slices(core, shape, 0)[0]), 1)


if __name__ == '__main__':
    unittest.main()
