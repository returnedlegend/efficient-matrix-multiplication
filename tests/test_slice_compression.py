import copy
import itertools
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from mmsearch.recombine import canonical_terms, encode, save
from mmsearch.slice_compression import (InvalidCertificate, canonical_masks,
    compress_candidate, factor_matrix, group_matrix, propose_group,
    verify_factorization, verify_proposal)
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.verify import verify_candidate
from scripts.scan_slice_compressions import (_freeze_first_winner, _winner_eligible,
    classify, main, strict_json)


def expanded_naive(dimension, axis):
    terms = list(canonical_terms(naive_candidate(dimension)))
    group = [term for term in terms if term[axis] == 1]
    first, second = group[:2]
    other = [a for a in range(3) if a != axis]
    a, b = (first[i] for i in other)
    c, d = (second[i] for i in other)
    assert a != c and b != d
    replacements = []
    for left, right in ((a, d), (c, b), (a ^ c, b ^ d)):
        term = [0, 0, 0]
        term[axis] = 1
        term[other[0]], term[other[1]] = left, right
        replacements.append(tuple(term))
    terms.remove(first)
    terms.remove(second)
    return encode(terms+replacements, dimension), replacements


class SliceCompressionTests(unittest.TestCase):
    def test_latent_three_to_two_every_axis_full_exact_source(self):
        for axis in range(3):
            source, three = expanded_naive(2, axis)
            self.assertEqual(len(source["terms"]), 9)
            self.assertTrue(verify_candidate(source)["valid"])
            other = [a for a in range(3) if a != axis]
            for free_axis in other:
                self.assertEqual(len({t[free_axis] for t in three}), 3)
            proposal = propose_group(three, axis, 1, 4)
            self.assertEqual(proposal["old_count"], 3)
            self.assertEqual(proposal["new_count"], 2)
            self.assertTrue(verify_proposal(proposal, 4))
            result = compress_candidate(source, seconds=1)
            self.assertEqual(result["final_rank"], 8)
            self.assertTrue(result["moves"])
            self.assertTrue(result["fixed_point"])
            self.assertTrue(result["source_verification"]["valid"])
            self.assertTrue(result["final_verification"]["valid"])
            self.assertFalse(result["winner_eligible"])
            self.assertTrue(all(m["verification"]["valid"] for m in result["moves"]))

    def test_random_matrix_factor_identity_and_exact_rank(self):
        rng = random.Random(123)
        for height, width in itertools.product(range(1, 5), repeat=2):
            for _ in range(8):
                rows = [rng.randrange(1 << width) for _ in range(height)]
                witness = factor_matrix(rows, width)
                self.assertTrue(verify_factorization(rows, width, witness))
                span = {0}
                for row in rows:
                    span |= {v ^ row for v in tuple(span)}
                self.assertEqual(len(span), 1 << witness["rank"])
                rebuilt = [0]*height
                for column, row in zip(witness["columns"], witness["row_basis"]):
                    for i in range(height):
                        if column >> i & 1:
                            rebuilt[i] ^= row
                self.assertEqual(rows, rebuilt)

    def test_zero_full_cancellation_and_canonical_source_noop(self):
        witness = factor_matrix([0, 0, 0], 3)
        self.assertEqual(witness["rank"], 0)
        self.assertEqual(witness["columns"], [])
        proposal = propose_group([(1, 2, 3), (1, 2, 3)], 0, 1, 4)
        self.assertEqual(proposal["new_count"], 0)
        self.assertEqual(group_matrix(proposal["old_terms"], 0, 4), [0]*4)
        source = naive_candidate(2)
        result = compress_candidate(source, seconds=1, stop_at_record=True)
        self.assertEqual(result["final_rank"], 8)
        self.assertEqual(result["moves"], [])
        padded = copy.deepcopy(source)
        padded["terms"].extend([copy.deepcopy(source["terms"][0])]*2)
        padded["terms"].append({"u": [0]*4, "v": [1, 0, 0, 0], "w": [1, 0, 0, 0]})
        result = compress_candidate(padded, seconds=1)
        self.assertEqual(result["final_rank"], 8)
        self.assertEqual(result["canonicalization"]["zero_products_removed"], 1)
        self.assertEqual(result["canonicalization"]["duplicate_pairs_cancelled"], 1)

    def test_corrupt_witness_rejected_and_no_false_refactor(self):
        rows = [3, 5, 6]
        witness = factor_matrix(rows, 3)
        for key in ("columns", "row_basis", "row_coordinates"):
            bad = copy.deepcopy(witness)
            bad[key][0] ^= 1
            with self.assertRaises(AssertionError):
                verify_factorization(rows, 3, bad)
        source, three = expanded_naive(2, 0)
        proposal = propose_group(three, 0, 1, 4)
        proposal["new_terms"][0][1] ^= 1
        with self.assertRaises(AssertionError):
            verify_proposal(proposal, 4)
        group = [t for t in canonical_terms(naive_candidate(2)) if t[0] == 1]
        self.assertIsNone(propose_group(group, 0, 1, 4))

    def test_strict_bits_duplicate_keys_and_bad_tensor_rejected(self):
        for value in (True, 1.0, -1, 2):
            bad = naive_candidate(2)
            bad["terms"][0]["u"][0] = value
            with self.assertRaises(InvalidCertificate):
                canonical_masks(bad)
        bad = naive_candidate(2)
        bad["terms"][0]["u"][0] ^= 1
        with self.assertRaises(InvalidCertificate) as caught:
            compress_candidate(bad)
        self.assertFalse(caught.exception.report["valid"])
        with self.assertRaises(ValueError):
            strict_json('{"field":2,"field":2}')
        self.assertEqual(classify([]), "NONCERTIFICATE")
        self.assertEqual(classify({"elapsed": 5}), "NONCERTIFICATE")
        self.assertEqual(classify(naive_candidate(2)), "UNSUPPORTED_CERTIFICATE")
        with self.assertRaises(InvalidCertificate):
            classify({"field": 2, "dimension": 5})

    def test_dimension5_full_entry_verification(self):
        source, _ = expanded_naive(5, 0)
        result = compress_candidate(source, seconds=1)
        self.assertEqual(result["source_rank"], 126)
        self.assertEqual(result["final_rank"], 125)
        self.assertFalse(result["winner_eligible"])
        self.assertEqual(result["source_verification"]["exact_entries_checked"], 15625)
        self.assertEqual(result["final_verification"]["exact_entries_checked"], 15625)
        self.assertTrue(all(m["verification"]["exact_entries_checked"] == 15625 for m in result["moves"]))

    def test_scanner_provenance_filters_error_and_persistent_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = root/"sources"
            source, _ = expanded_naive(5, 0)
            save(sources/"valid.json", source)
            save(sources/"duplicate.json", source)
            save(sources/"metadata.json", {"foo": 1})
            save(sources/"small.json", naive_candidate(2))
            malformed = naive_candidate(5)
            malformed["terms"][0]["v"][0] = -1
            save(sources/"malformed.json", malformed)
            args = ["--candidate-dir", str(sources), "--output-dir", str(root/"out"),
                    "--minimum-age", "0", "--seconds", "2", "--cache", str(root/"cache.json")]
            self.assertEqual(main(args), 2)
            result = json.loads((root/"out/result.json").read_text())
            self.assertEqual(result["status"], "ERROR")
            self.assertEqual(result["counts"]["ERROR"], 1)
            self.assertEqual(result["counts"]["VERIFIED"], 1)
            self.assertEqual(result["counts"]["DUPLICATE_RAW_INPUT"], 1)
            self.assertEqual(result["best_rank"], 125)
            self.assertFalse(result["winner"])
            records = json.loads((root/"out/source_records.json").read_text())
            verified = next(r for r in records if r["status"] == "VERIFIED")
            self.assertTrue(Path(verified["snapshot"]).exists())
            self.assertTrue(Path(verified["output_path"]).exists())
            args[args.index("--output-dir")+1] = str(root/"cached")
            self.assertEqual(main(args), 2)
            cached = json.loads((root/"cached/result.json").read_text())
            self.assertEqual(cached["fresh_sources"], 0)
            self.assertEqual(cached["counts"]["CACHED"], 4)
            self.assertEqual(cached["counts"]["CACHED_ERROR"], 1)
            self.assertFalse((root/"cached/WINNER.json").exists())
            self.assertTrue((root/"cached/artifact_checksums.json").exists())

    def test_scanner_age_and_source_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save(root/"input.json", naive_candidate(5))
            args = ["--input", str(root/"input.json"), "--output-dir", str(root/"young"), "--seconds", "1"]
            self.assertEqual(main(args), 0)
            summary = json.loads((root/"young/result.json").read_text())
            self.assertEqual(summary["counts"]["TOO_YOUNG"], 1)
            self.assertEqual(summary["fresh_sources"], 0)
            save(root/"another.json", expanded_naive(5, 0)[0])
            args = ["--input", str(root/"input.json"), "--input", str(root/"another.json"),
                "--output-dir", str(root/"limited"), "--seconds", "1", "--minimum-age", "0", "--max-sources", "1"]
            self.assertEqual(main(args), 0)
            summary = json.loads((root/"limited/result.json").read_text())
            self.assertEqual(summary["status"], "PARTIAL")
            self.assertEqual(summary["fresh_sources"], 1)
            self.assertEqual(summary["counts"]["DEFERRED"], 1)
            self.assertEqual(summary["recorded_paths"], 2)
        result = compress_candidate(naive_candidate(2), seconds=1e-9)
        self.assertFalse(result["fixed_point"])
        self.assertTrue(result["final_verification"]["valid"])

    def test_first_winner_exclusive_freeze_and_stop_control_flow_only(self):
        # Hypothetical campaign eligibility is mocked ONLY for this control
        # flow test. The certificates are known exact n2 rank8/rank7 examples,
        # never research records. The freezer still performs real full exact
        # verification, and production eligibility rejects both n2 results.
        first = compress_candidate(naive_candidate(2), seconds=1)
        second = compress_candidate(strassen_candidate(2), seconds=1)
        self.assertFalse(_winner_eligible(first["candidate"], first))
        self.assertFalse(_winner_eligible(second["candidate"], second))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save(root/"a.json", naive_candidate(5))
            save(root/"b.json", expanded_naive(5, 0)[0])
            args = ["--input", str(root/"a.json"), "--input", str(root/"b.json"),
                "--output-dir", str(root/"out"), "--minimum-age", "0", "--seconds", "2"]
            with patch("scripts.scan_slice_compressions.compress_candidate", side_effect=[copy.deepcopy(first), copy.deepcopy(second)]) as compress:
                with patch("scripts.scan_slice_compressions._winner_eligible", return_value=True):
                    self.assertEqual(main(args), 0)
                self.assertEqual(compress.call_count, 1)
                self.assertTrue(compress.call_args.kwargs["stop_at_record"])
            primary = root/"out/WINNER.json"
            original = primary.read_bytes()
            self.assertEqual(len(json.loads(original)["terms"]), 8)
            with self.assertRaises(FileExistsError):
                _freeze_first_winner(root/"out", second["candidate"])
            self.assertEqual(primary.read_bytes(), original)
            import hashlib
            expected = hashlib.sha256(original).hexdigest()
            self.assertEqual((root/"out/WINNER.sha256").read_text().split()[0], expected)
            self.assertEqual(json.loads((root/"out/WINNER.checksums.json").read_text())["WINNER.json"], expected)
            summary = json.loads((root/"out/result.json").read_text())
            self.assertEqual(summary["status"], "WINNER")
            self.assertEqual(summary["fresh_sources"], 1)
            self.assertEqual(summary["recorded_paths"], 1)
            self.assertEqual(summary["counts"]["VERIFIED"], 1)
            self.assertEqual(len(json.loads((root/"out/source_records.json").read_text())), 1)
            cache = json.loads((root/"out/cache.json").read_text())
            self.assertEqual(sum(len(entries) for entries in cache["implementations"].values()), 1)
            self.assertTrue((root/"out/WINNER.verify.py").exists())


if __name__ == "__main__":
    unittest.main()
