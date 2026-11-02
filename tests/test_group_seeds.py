"""Exact elementary group actions and independently checked seed witnesses."""
import json
from pathlib import Path
import random
import tempfile
import unittest

from mmsearch.search import decode_candidate, encode_candidate, naive_terms
from mmsearch.verify import verify_candidate
from scripts.generate_group_seeds import (
    column_xor, forced_one_terms, generate, row_xor, transvection,
)

ROOT = Path(__file__).resolve().parents[1]


def matrix(mask, n):
    return [[mask >> (r*n+c) & 1 for c in range(n)] for r in range(n)]


def multiply(a, b):
    n = len(a)
    return [[sum(a[r][k]*b[k][c] for k in range(n)) % 2
             for c in range(n)] for r in range(n)]


def pack(a):
    return sum(value << (r*len(a)+c) for r,row in enumerate(a) for c,value in enumerate(row))


class GroupSeedTests(unittest.TestCase):
    def test_bit_operations_equal_independent_dense_matrix_multiplication(self):
        rng = random.Random(719)
        for n in (2, 5):
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    transpose = [[int(r==c) for c in range(n)] for r in range(n)]
                    transpose[j][i] ^= 1
                    for _ in range(5):
                        mask = rng.randrange(1 << (n*n))
                        dense = matrix(mask,n)
                        self.assertEqual(row_xor(mask,n,j,i),pack(multiply(transpose,dense)))
                        self.assertEqual(column_xor(mask,n,i,j),pack(multiply(dense,transpose)))

    def test_all_groups_are_involutions_and_preserve_all_target_coefficients(self):
        for n in (2,5):
            if n == 2:
                terms = naive_terms(n)
            else:
                terms = decode_candidate(json.loads((ROOT/'artifacts/km93_f2.json').read_text()),n)
            for group in 'PQR':
                for i in range(n):
                    for j in range(n):
                        if i == j:
                            continue
                        variant = transvection(terms,n,group,i,j)
                        self.assertEqual(transvection(variant,n,group,i,j),sorted(terms))
                        report = verify_candidate(encode_candidate(variant,n),random_trials=0)
                        self.assertTrue(report['valid'],(n,group,i,j))
                        self.assertEqual(report['exact_entries_checked'],n**6)
                        self.assertEqual(len(variant),len(terms))

    def test_full_back_elimination_finds_unit_equation(self):
        audit = dict(dictionary=[[1,1,1],[2,2,2],[4,4,4]],
                     independent_augmented_rows_hex=[hex(0b111|0b1000),hex(0b110)])
        forced, rank = forced_one_terms(audit)
        self.assertEqual(rank,2)
        self.assertEqual(forced,{(1,1,1)})

    def test_small_generation_records_exact_release_witnesses(self):
        terms = naive_terms(2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, audit, output = root/'source.json',root/'audit.json',root/'result'
            source.write_text(json.dumps(encode_candidate(terms,2)))
            audit.write_text(json.dumps(dict(dictionary=terms,
                independent_augmented_rows_hex=[hex((1<<i)|(1<<len(terms))) for i in range(len(terms))])))
            manifest = generate(source,audit,output)
            self.assertEqual(manifest['variants_generated'],6)
            self.assertEqual(manifest['forced_one_count'],8)
            union = {tuple(map(int,line.split())) for line in (output/'group_terms.txt').read_text().splitlines()}
            released = set()
            for selected in manifest['selected']:
                candidate = json.loads((output/(selected['id']+'.json')).read_text())
                self.assertTrue(verify_candidate(candidate,random_trials=0)['valid'])
                selected_terms = set(decode_candidate(candidate,2))
                self.assertLessEqual(selected_terms,union)
                omitted = {tuple(t) for t in selected['omitted_forced_terms']}
                self.assertTrue(omitted.isdisjoint(selected_terms))
                released |= omitted
            self.assertEqual(len(released),manifest['released_count'])
            self.assertLessEqual(manifest['selected_count'],8)
            self.assertLess(manifest['new_terms'],1000)
            self.assertTrue(manifest['known_equivalent'])
            self.assertFalse(manifest['novel'])


if __name__ == '__main__':
    unittest.main()
