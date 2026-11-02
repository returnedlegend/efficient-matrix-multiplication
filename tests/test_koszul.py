import contextlib
import copy
import importlib.util
import io
import itertools
import json
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mmsearch.compact_sat import build_compact_cnf, compress_residual, image_bases
from mmsearch.koszul import koszul_bounds, koszul_p1_rows
from mmsearch.sat_neighborhoods import gf2_rank
from mmsearch.tensor import naive_candidate
from mmsearch.verify import verify_candidate
from scripts.campaign_compact_sat import CompactCampaign
from scripts.campaign_koszul_sat import CoreCache, KoszulCampaign, cached_encoder
from scripts import campaign_sat as base


def tensor(shape, products):
    values = [0]*(shape[0]*shape[1]*shape[2])
    for factors in products:
        for a, b, c in itertools.product(*(range(n) for n in shape)):
            values[(a*shape[1]+b)*shape[2]+c] ^= (factors[0] >> a) & (factors[1] >> b) & (factors[2] >> c) & 1
    return values


def dense_rank(matrix):
    rows = copy.deepcopy(matrix)
    rank = 0
    for column in range(len(rows[0]) if rows else 0):
        pivot = next((i for i in range(rank, len(rows)) if rows[i][column]), None)
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        for i in range(rank+1, len(rows)):
            if rows[i][column]:
                rows[i] = [a ^ b for a, b in zip(rows[i], rows[rank])]
        rank += 1
    return rank


class KoszulTests(unittest.TestCase):
    def test_rank_one_map_rank_exactly_a_minus_one(self):
        rng = random.Random(20)
        for a in range(2, 8):
            shape = [a, 4, 3]
            products = [tuple(rng.randrange(1, 1 << n) for n in shape)]
            core = tensor(shape, products)
            for mode in range(3):
                rows, _, _ = koszul_p1_rows(core, shape, mode)
                self.assertEqual(gf2_rank(rows), shape[mode]-1)

    def test_sum_k_products_bound_including_cancellation(self):
        rng = random.Random(51)
        shape = [5, 4, 3]
        for k in range(1, 7):
            products = [tuple(rng.randrange(1 << n) for n in shape) for _ in range(k)]
            duplicate = tuple(rng.randrange(1 << n) for n in shape)
            core = tensor(shape, products+[duplicate, duplicate])
            report = koszul_bounds(core, shape)
            self.assertLessEqual(report['tensor_rank_lower_bound'], k)
            for entry in report['bounds']:
                self.assertLessEqual(entry['matrix_rank'], k*entry['rank_one_contribution'])
                self.assertLessEqual(entry['tensor_rank_lower_bound'], k)

    def test_bitset_map_and_rank_match_independent_dense(self):
        rng = random.Random(4)
        shape = [3, 4, 2]
        core = [rng.randrange(2) for _ in range(24)]
        for mode in range(3):
            other = [x for x in range(3) if x != mode]
            a, b, c = shape[mode], shape[other[0]], shape[other[1]]
            dense = []
            for output, w in itertools.product(itertools.combinations(range(a), 2), range(c)):
                row = []
                for x, v in itertools.product(range(a), range(b)):
                    if x not in output:
                        row.append(0)
                        continue
                    position = [0]*3
                    position[mode] = next(y for y in output if y != x)
                    position[other[0]], position[other[1]] = v, w
                    i, j, k = position
                    row.append(core[(i*shape[1]+j)*shape[2]+k])
                dense.append(row)
            rows, columns, count = koszul_p1_rows(core, shape, mode)
            self.assertEqual(columns, a*b)
            self.assertEqual(count, len(dense))
            self.assertEqual(rows, [sum(value << i for i, value in enumerate(row)) for row in dense])
            self.assertEqual(gf2_rank(rows), dense_rank(dense))

    def test_flattening_passes_but_koszul_rejects(self):
        # Three diagonal products plus all-ones product: all mode ranks are3,
        # while each p1 map has rank8, proving local tensor rank at least4.
        core = tensor([3, 3, 3], [(1, 1, 1), (2, 2, 2), (4, 4, 4), (7, 7, 7)])
        self.assertEqual([len(b.vectors) for b in image_bases(core, 3)], [3, 3, 3])
        report = koszul_bounds(core, [3, 3, 3], target=3)
        self.assertTrue(report['rejected'])
        self.assertEqual([b['matrix_rank'] for b in report['bounds']], [8, 8, 8])
        self.assertEqual(report['tensor_rank_lower_bound'], 4)

    def test_feasible_naive_to_strassen7_passes(self):
        _, core, shape, _ = compress_residual(naive_candidate(2), range(8))
        self.assertFalse(koszul_bounds(core, shape, target=7)['rejected'])

    def test_core_cache_reused_by_private_encoder_without_module_mutation(self):
        source = naive_candidate(2)
        cache = CoreCache()
        cache.get(source, range(8))
        original = build_compact_cnf(source, rank=7, active_terms=list(range(7)), drop_term=7)
        built = cached_encoder(cache, 'cadical', 'none')(source, rank=7,
                    active_terms=list(range(7)), drop_term=7)
        self.assertEqual(cache.misses, 1)
        self.assertGreaterEqual(cache.hits, 2)
        self.assertEqual(built['clauses'], original['clauses'])
        self.assertEqual(built['metadata']['image_bases'], original['metadata']['image_bases'])

    def test_cached_native_xor_matches_existing_encoder(self):
        from mmsearch.xor_sat import build_xor_cnf
        source = naive_candidate(2)
        cache = CoreCache()
        actual = cached_encoder(cache, 'xor', 'u-lex')(source, rank=7,
                    active_terms=list(range(7)), drop_term=7)
        expected = build_xor_cnf(source, rank=7, active_terms=list(range(7)),
                                 drop_term=7, symmetry='u-lex')
        self.assertEqual(actual['clauses'], expected['clauses'])
        self.assertEqual(actual['xors'], expected['xors'])
        self.assertEqual(actual['nv'], expected['nv'])

    def test_wrapper_rejects_before_cnf_and_records_local_proof(self):
        source = naive_candidate(2)
        for mask in (1, 2, 4, 7):
            term = {a: [(mask >> j) & 1 for j in range(4)] for a in ('u', 'v', 'w')}
            source['terms'].extend([term, copy.deepcopy(term)])
        self.assertTrue(verify_candidate(source)['valid'])
        with tempfile.TemporaryDirectory() as directory:
            args = base.arguments(['--output-dir', directory, '--rank', '15', '--dimension', '2'])
            args.backend, args.compact_symmetry = 'cadical', 'u-lex'
            campaign = KoszulCampaign(args, CoreCache())
            candidate = dict(active_terms=[8, 10, 12], drop_term=14, active_count=3,
                             source_sha256='fixture', patch_id='fixture', level=0)
            campaign.state['sources']['fixture'] = dict(file_sha256='fixture')
            with patch.object(CompactCampaign, 'next_patch', side_effect=[candidate, None]), \
                    patch.object(campaign, 'stream', return_value=SimpleNamespace(source=source)), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(campaign.next_patch())
            self.assertEqual(campaign.state['counters']['koszul_rejected'], 1)
            event = json.loads((Path(directory)/'results.jsonl').read_text())
            self.assertEqual(event['status'], 'LOCAL_UNSAT_BOUND')
            self.assertEqual(event['patch']['koszul']['tensor_rank_lower_bound'], 4)

    @unittest.skipUnless(importlib.util.find_spec('pysat'), 'python-sat missing')
    def test_cached_filtered_encoder_nontrivial_exact_sat(self):
        from mmsearch.sat import solve_local
        source = naive_candidate(2)
        cache = CoreCache()
        problem = cached_encoder(cache, 'cadical', 'u-lex')(source, rank=7,
                    active_terms=list(range(7)), drop_term=7)
        result = solve_local(problem, seconds=4, conflicts=100000)
        self.assertEqual(result['status'], 'SAT')
        self.assertTrue(result['verification']['valid'])


if __name__ == '__main__':
    unittest.main()
