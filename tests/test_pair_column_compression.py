import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mmsearch.free_factor_sat import build_system, satisfies
from mmsearch.pair_column_compression import (compress_candidate, orientation_proposal,
    pair_merge, pivot_solution, validate_rref)
from mmsearch.recombine import canonical_terms, encode, save
from mmsearch.slice_compression import compress_candidate as slice_compress
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.verify import verify_candidate
from scripts.scan_pair_compressions import main
from tests.test_slice_compression import expanded_naive


NONLOCAL = [(1,10,13), (3,8,4), (5,3,8), (8,5,3), (9,9,9),
            (10,12,1), (12,1,10), (2,10,1), (3,2,1)]


class PairColumnCompressionTests(unittest.TestCase):
    def test_existing_latent_slice_examples_all_axes(self):
        for axis in range(3):
            source, _ = expanded_naive(2, axis)
            result = compress_candidate(source, seconds=1)
            self.assertEqual(result["source_rank"], 9)
            self.assertEqual(result["final_rank"], 8)
            self.assertTrue(result["moves"])
            self.assertTrue(result["fixed_point"])
            self.assertTrue(all(move["verification"]["valid"] for move in result["moves"]))
            self.assertTrue(result["final_verification"]["valid"])

    def test_nonlocal_four_circuit_missed_by_all_shared_factor_slices(self):
        original = list(canonical_terms(strassen_candidate(2)))
        a, b = original[0], original[1]
        self.assertNotEqual(a[0], b[0])
        self.assertNotEqual(a[1], b[1])
        d = 1
        self.assertNotIn(d, (a[2], b[2]))
        changed = list(original)
        changed[0] = a[0], a[1], a[2] ^ d
        changed[1] = b[0], b[1], b[2] ^ d
        changed += [(a[0] ^ b[0], a[1], d), (b[0], a[1] ^ b[1], d)]
        self.assertEqual(changed, NONLOCAL)
        source = encode(changed, 2)
        self.assertTrue(verify_candidate(source)["valid"])
        self.assertEqual(slice_compress(source, seconds=1)["final_rank"], 9)
        proposal, summary = orientation_proposal(tuple(sorted(changed)), 2, "uv")
        self.assertEqual(summary["active_columns"], 9)
        self.assertEqual(summary["pair_column_rank"], 8)
        self.assertLessEqual(len(proposal["candidate"]["terms"]), 8)
        self.assertTrue(verify_candidate(proposal["candidate"])["valid"])
        result = compress_candidate(source, seconds=1)
        self.assertLessEqual(result["final_rank"], 8)
        self.assertTrue(result["final_verification"]["valid"])

    def test_zero_free_column_solution_and_corrupt_rref_proof_rejection(self):
        system = build_system(sorted(NONLOCAL), 2, "uv", baseline=None)
        self.assertTrue(validate_rref(system))
        vectors = pivot_solution(system)
        self.assertTrue(satisfies(system, vectors))
        self.assertLessEqual(sum(bool(v) for v in vectors), system["reduced"]["rank"])
        pivots = {(row[0] & -row[0]).bit_length()-1 for row in system["reduced"]["rows"]}
        self.assertTrue(all(v == 0 for i, v in enumerate(vectors) if i not in pivots))
        corrupt = copy.deepcopy(system)
        corrupt["reduced"]["rows"][0][2] ^= 1
        with self.assertRaises(ValueError):
            validate_rref(corrupt)
        corrupt = copy.deepcopy(system)
        corrupt["reduced"]["rows"].pop()
        with self.assertRaises(ValueError):
            pivot_solution(corrupt)

    def test_pair_merges_precede_active_only_factorization(self):
        source = naive_candidate(2)
        terms = list(canonical_terms(source))+[(15,15,1), (15,15,2), (15,15,3)]
        merged, proof = pair_merge(terms, 2, "uv")
        self.assertEqual(len(merged), 8)
        self.assertEqual(proof["old_count"], 11)
        result = compress_candidate(encode(terms, 2), seconds=1)
        self.assertEqual(result["final_rank"], 8)
        self.assertEqual(result["moves"][0]["method"], "same-pair-XOR-merge")
        self.assertTrue(all(check["active_columns"] <= 8 for check in result["orientation_checks"]))

    def test_noop_full_rank_not_global_minimality_claim(self):
        result = compress_candidate(naive_candidate(2), seconds=1)
        self.assertEqual(result["final_rank"], 8)
        self.assertEqual(result["moves"], [])
        self.assertEqual(len(result["orientation_checks"]), 3)
        self.assertTrue(all(check["pair_column_rank"] == 8 for check in result["orientation_checks"]))
        self.assertIn("no global", result["scope"])

    def test_n5_exact_full_entries_and_explicit_helper_cap_override(self):
        source, _ = expanded_naive(5, 0)
        with self.assertRaisesRegex(ValueError, "column cap"):
            compress_candidate(source)
        result = compress_candidate(source, seconds=2, max_active=126)
        self.assertEqual(result["final_rank"], 125)
        self.assertEqual(result["source_verification"]["exact_entries_checked"], 15625)
        self.assertEqual(result["final_verification"]["exact_entries_checked"], 15625)
        self.assertTrue(all(move["verification"]["exact_entries_checked"] == 15625 for move in result["moves"]))

    def test_scanner_filters_inactive_dictionary_and_first_record_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save(root/"large.json", naive_candidate(5))
            args = ["--input", str(root/"large.json"), "--output-dir", str(root/"skip"), "--minimum-age", "0", "--seconds", "2"]
            self.assertEqual(main(args), 0)
            result = json.loads((root/"skip/result.json").read_text())
            self.assertEqual(result["counts"]["TOO_MANY_ACTIVE_COLUMNS"], 1)
            self.assertEqual(result["fresh_sources"], 0)
            # Hypothetical control-flow test only: exact n2 rank8/rank7
            # certificates do not represent campaign research records.
            first = compress_candidate(naive_candidate(2), seconds=1)
            second = compress_candidate(strassen_candidate(2), seconds=1)
            save(root/"a.json", dict(dimension=5,field=2,terms=[]))
            save(root/"b.json", dict(dimension=5,field=2,terms=[{"u":[0]*25,"v":[0]*25,"w":[0]*25}]))
            args = ["--input", str(root/"a.json"), "--input", str(root/"b.json"),
                "--output-dir", str(root/"hypothetical"), "--minimum-age", "0", "--seconds", "2"]
            with patch("scripts.scan_pair_compressions.compress_candidate", side_effect=[copy.deepcopy(first),copy.deepcopy(second)]) as compress:
                with patch("scripts.scan_pair_compressions._winner_eligible", return_value=True):
                    self.assertEqual(main(args), 0)
                self.assertEqual(compress.call_count, 1)
            record = json.loads((root/"hypothetical/result.json").read_text())
            self.assertEqual(record["status"], "WINNER")
            self.assertEqual(record["recorded_paths"], 1)
            self.assertTrue((root/"hypothetical/WINNER.sha256").exists())


if __name__ == "__main__":
    unittest.main()
