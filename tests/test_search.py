"""Exact identities and failure modes for the bounded research searches."""
import contextlib
import io
import json
import random
import tempfile
import unittest
from pathlib import Path

from mmsearch.search import (
    _flip, _outer, _plus, _reduction, _rotations, decode_candidate, flip_search,
    is_cyclic, main, naive_terms, residual, search,
)
from mmsearch.tensor import strassen_candidate
from mmsearch.verify import verify_candidate


class SearchTests(unittest.TestCase):
    def test_naive_trace_indexing(self):
        for dimension in (1,2,3,5):
            self.assertEqual(residual(naive_terms(dimension),dimension),0)

    def test_arbitrary_flip_and_plus_identities(self):
        rng = random.Random(391)
        terms = {(rng.randrange(1,512),rng.randrange(1,512),rng.randrange(1,512))
                 for _ in range(12)}
        # Force shared factors so both move kinds are exercised independently
        # of the matrix multiplication target.
        terms.update({(1,3,7),(1,9,11)})
        expected = residual(terms,3)
        flips = pluses = 0
        for step in range(120):
            if step % 5 == 0:
                proposed = _plus(terms,rng,False)
                pluses += proposed is not None
            else:
                proposed = _flip(terms,rng,False)
                flips += proposed is not None
            if proposed is not None:
                self.assertEqual(residual(proposed,3),expected)
                if len(proposed) < 65:
                    terms = proposed
        self.assertGreater(flips,0)
        self.assertGreater(pluses,0)

    def test_cyclic_moves_include_fixed_cube(self):
        rng = random.Random(17)
        terms = set(_rotations((1,2,4))) | set(_rotations((1,2,8))) | {(1,1,1)}
        expected = residual(terms,3)
        for step in range(120):
            proposed = (_plus if step % 7 == 0 else _flip)(terms,rng,True)
            if proposed is not None:
                self.assertTrue(is_cyclic(proposed))
                self.assertEqual(residual(proposed,3),expected)
                if len(proposed) < 70:
                    terms = proposed

    def test_reduction_identity_and_cyclic_closure(self):
        pair = {(1,2,4),(1,2,8)}
        self.assertEqual(_reduction(pair,False),{(1,2,12)})
        cyclic = set(_rotations((1,2,4))) | set(_rotations((1,2,8)))
        reduced = _reduction(cyclic,True)
        self.assertIsNotNone(reduced)
        self.assertEqual(len(reduced),3)
        self.assertTrue(is_cyclic(reduced))
        self.assertEqual(residual(cyclic,3),residual(reduced,3))

    def test_seeded_step_budget_is_reproducible(self):
        options = dict(n=2,rank=7,steps=200,seconds=100,seed=42,plus_every=10)
        first,second = search(**options),search(**options)
        self.assertEqual(first['terms'],second['terms'])
        self.assertEqual(first['metadata']['history'],second['metadata']['history'])
        self.assertTrue(verify_candidate(first)['valid'])

    def test_residual_incremental_check_and_honest_status(self):
        candidate = search(n=2,rank=7,engine='residual',steps=20,seconds=100,seed=4)
        weight = residual(decode_candidate(candidate,2),2).bit_count()
        self.assertEqual(candidate['metadata']['residual_weight'],weight)
        self.assertEqual(candidate['metadata']['exact'],weight == 0)
        self.assertEqual(verify_candidate(candidate)['valid'],weight == 0)
        if weight:
            self.assertFalse(candidate['metadata']['target_reached'])
            self.assertEqual(candidate['metadata']['status'],'research_checkpoint')

    def test_residual_pair_deletion_and_zero_padding(self):
        terms = decode_candidate(strassen_candidate(2,2),2)
        tensors = [_outer(term,4) for term in terms]
        expected = min((tensors[i] ^ tensors[j]).bit_count()
                       for i in range(len(terms)) for j in range(i+1,len(terms)))
        candidate = search(n=2,rank=5,engine='residual',initial_terms=terms,steps=0)
        self.assertEqual(candidate['metadata']['residual_weight'],expected)
        padded = search(n=2,rank=9,engine='residual',initial_terms=terms,steps=0)
        self.assertTrue(verify_candidate(padded)['valid'])

    def test_invalid_cyclic_seed_is_rejected(self):
        seed = _plus(set(naive_terms(2)),random.Random(0),False)
        self.assertFalse(is_cyclic(seed))
        with self.assertRaises(ValueError):
            flip_search(seed,n=2,cyclic=True,steps=0)
        with self.assertRaises(ValueError):
            search(n=2,engine='residual',cyclic=True,steps=0)
        with self.assertRaises(ValueError):
            flip_search([(1,1,1)],n=2,steps=0)

    def test_cli_emits_independent_verifier_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'checkpoint.json'
            with contextlib.redirect_stdout(io.StringIO()):
                result = main(['--dimension','2','--rank','8','--steps','0',
                               '--output',str(output),'--quiet'])
            self.assertEqual(result,0)
            report = json.loads(output.with_suffix('.verification.json').read_text())
            self.assertTrue(report['valid'])
            self.assertEqual(report['exact_entries_checked'],64)
            self.assertTrue(output.with_suffix('.verify.py').is_file())


if __name__ == '__main__':
    unittest.main()
