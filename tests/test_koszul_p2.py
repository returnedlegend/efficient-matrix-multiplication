import itertools
import contextlib
import io
import json
from pathlib import Path
import random
import tempfile
import unittest

from mmsearch.koszul import koszul_bounds
from mmsearch.koszul_p2 import koszul_p2_bounds, koszul_p2_rows
from mmsearch.sat_neighborhoods import gf2_rank
from mmsearch.tensor import naive_candidate
from mmsearch.compact_sat import compress_residual
from scripts.campaign_koszul_p2_sat import HigherCoreCache, HigherCampaign
from scripts import campaign_sat as base
from tests.test_koszul import dense_rank, tensor


class KoszulP2Tests(unittest.TestCase):
    def test_rankone_exact_binomial_a_minus_one_choose_two(self):
        import math
        rng = random.Random(923)
        for a in range(3, 9):
            shape = [a, 4, 3]
            core = tensor(shape, [tuple(rng.randrange(1, 1 << n) for n in shape)])
            for mode in range(3):
                rows, _, _ = koszul_p2_rows(core, shape, mode)
                self.assertEqual(gf2_rank(rows), math.comb(shape[mode]-1, 2))

    def test_dense_independent_exterior_map_and_elimination(self):
        rng = random.Random(32)
        shape = [4, 3, 3]
        core = [rng.randrange(2) for _ in range(36)]
        for mode in range(3):
            other = [axis for axis in range(3) if axis != mode]
            a, b, c = shape[mode], shape[other[0]], shape[other[1]]
            dense = []
            for output, w in itertools.product(itertools.combinations(range(a), 3), range(c)):
                row = []
                for source, v in itertools.product(itertools.combinations(range(a), 2), range(b)):
                    difference = set(output)-set(source)
                    if not set(source) <= set(output) or len(difference) != 1:
                        row.append(0)
                        continue
                    position = [0, 0, 0]
                    position[mode] = next(iter(difference))
                    position[other[0]], position[other[1]] = v, w
                    i, j, k = position
                    row.append(core[(i*shape[1]+j)*shape[2]+k])
                dense.append(row)
            rows, columns, count = koszul_p2_rows(core, shape, mode)
            self.assertEqual(count, len(dense))
            self.assertEqual(columns, len(dense[0]))
            self.assertEqual(rows, [sum(value << i for i, value in enumerate(row)) for row in dense])
            self.assertEqual(gf2_rank(rows), dense_rank(dense))

    def test_planted_k_sums_and_cancellations_never_rejected(self):
        rng = random.Random(730)
        shape = [6, 5, 4]
        for k in range(1, 8):
            products = [tuple(rng.randrange(1 << size) for size in shape) for _ in range(k)]
            repeat = tuple(rng.randrange(1 << size) for size in shape)
            report = koszul_p2_bounds(tensor(shape, products+[repeat, repeat]), shape, target=k)
            self.assertFalse(report['rejected'])
            self.assertLessEqual(report['tensor_rank_lower_bound'], k)

    def test_p1_passing_fixture_is_rejected_by_p2(self):
        # Exact 8x8x7 core from a ten-product local patch of km93. Packing
        # removes dependence on campaign artifacts or mutable source ordering.
        packed = int('81200000120048080400000300014b210924ba91484b218004be18480124a830058b490124003000c1c901a000001a104808040120808100', 16)
        core = [(packed >> i) & 1 for i in range(8*8*7)]
        self.assertFalse(koszul_bounds(core, [8, 8, 7], target=9)['rejected'])
        report = koszul_p2_bounds(core, [8, 8, 7], target=9)
        self.assertTrue(report['rejected'])
        self.assertEqual(report['tensor_rank_lower_bound'], 10)
        self.assertFalse(koszul_p2_bounds(core, [8, 8, 7], target=10)['rejected'])

    def test_caps_skip_explicitly_and_do_not_reject(self):
        core = tensor([6, 5, 4], [(63, 31, 15)])
        for caps in (dict(max_dimension=0), dict(max_rows=0), dict(max_columns=0)):
            report = koszul_p2_bounds(core, [6, 5, 4], target=1, **caps)
            self.assertEqual(report['computed_modes'], 0)
            self.assertEqual(report['skipped_modes'], 3)
            self.assertFalse(report['rejected'])
            self.assertTrue(all(entry['status'] == 'SKIPPED' for entry in report['bounds']))

    def test_feasible_nontrivial_strassen7_passes_both_filters(self):
        source = naive_candidate(2)
        cache = HigherCoreCache()
        _, report = cache.get(source, range(8))
        self.assertLessEqual(report['tensor_rank_lower_bound'], 7)
        self.assertFalse(report['p2']['rejected'])
        self.assertEqual(cache.metrics['p2_evaluations'], 1)
        cache.get(source, range(8))
        self.assertEqual(cache.metrics['p2_evaluations'], 1)

    def test_p2_rejection_record_names_p2_proof_and_caps_guard_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            args = base.arguments(['--output-dir', directory])
            args.backend, args.compact_symmetry = 'cadical', 'u-lex'
            campaign = HigherCampaign(args, HigherCoreCache())
            event = dict(event='koszul_reject', patch=dict(koszul=dict(p2=dict(rejected=True))))
            with contextlib.redirect_stdout(io.StringIO()):
                campaign.emit(event)
            record = json.loads((Path(directory)/'results.jsonl').read_text())
            self.assertEqual(record['exterior_degree'], 2)
            self.assertIn('Koszul_p2', record['proof'])
            base.save(campaign.path, campaign.state)
            HigherCampaign(args, HigherCoreCache())
            with self.assertRaises(ValueError):
                HigherCampaign(args, HigherCoreCache(max_dimension=10))


if __name__ == '__main__':
    unittest.main()
