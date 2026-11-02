import importlib.util
import itertools
from pathlib import Path
import tempfile
import unittest

from mmsearch.recombine import canonical_terms, save
from mmsearch.recombine_sat import (audit, build_problem, build_system, row_reduce,
                                    satisfies, solve, validate_decode)
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.verify import verify_candidate
from scripts.campaign_recombine_sat import load_extra, main


class RecombineSatTests(unittest.TestCase):
    def test_row_elimination_equivalent_for_every_small_assignment(self):
        for rows in ([0, 0b011, 0b110, 0b101], [0b011, 0b111], [0b001, 0b101], [0b100]):
            reduced, proofs = row_reduce(rows, 2)
            for row, proof in zip(reduced, proofs):
                reconstructed = 0
                for i in range(len(rows)):
                    if proof >> i & 1:
                        reconstructed ^= rows[i]
                self.assertEqual(reconstructed, row)
            for selection in range(4):
                self.assertEqual(satisfies(rows, selection, 2), satisfies(reduced, selection, 2))

    def test_tensor_rows_match_independent_verifier_for_all_small_selections(self):
        dictionary = [(1, 1, 1), (1, 1, 2), (2, 2, 2)]
        system = build_system(dictionary, 2)
        from mmsearch.recombine import encode
        for selection in range(8):
            candidate = encode([t for i, t in enumerate(dictionary) if selection >> i & 1], 2)
            report = verify_candidate(candidate, random_trials=0)
            self.assertEqual(satisfies(system["rows"], selection, 3), report["valid"])
            self.assertEqual(sum((row & selection).bit_count() % 2 != (row >> 3)
                                 for row in system["rows"]), report["mismatch_count"])
            self.assertEqual(satisfies(system["rows"], selection, 3), satisfies(system["reduced"], selection, 3))

    def test_baseline_and_dictionary_validation(self):
        baseline = naive_candidate(2)
        dictionary = canonical_terms(baseline)
        system = build_system(dictionary, 2, baseline=baseline)
        self.assertEqual(system["metadata"]["baseline"]["rank"], 8)
        self.assertEqual(len(audit(system)["original_augmented_rows_hex"]), 64)
        for bad in ([], [(0, 1, 1)], [(True, 1, 1)], [(16, 1, 1)], list(reversed(dictionary)), [dictionary[0]]*2):
            with self.assertRaises(ValueError):
                build_system(bad, 2)
        with self.assertRaisesRegex(ValueError, "absent"):
            build_system(dictionary[:-1], 2, baseline=baseline)

    def test_extra_terms_are_columns_without_full_source_algorithm_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"terms.txt"
            path.write_text("1 3 7\n1 3 7\n")
            terms, raw = load_extra(path, 2)
            self.assertEqual(terms, [(1, 3, 7)]*2)
            for line in ("0 1 1", "16 1 1", "1 1", "-1 1 1"):
                path.write_text(line)
                with self.assertRaises(ValueError):
                    load_extra(path, 2)

    @unittest.skipUnless(importlib.util.find_spec("pycryptosat"), "optional native XOR backend")
    def test_sat_strassen_union_and_unsat_naive_dictionary(self):
        naive, strassen = naive_candidate(2), strassen_candidate(2)
        dictionary = sorted(set(canonical_terms(naive)) | set(canonical_terms(strassen)))
        system = build_system(dictionary, 2, baseline=naive)
        for encoding in ("cardnetwrk", "totalizer", "seqcounter"):
            problem = build_problem(system, 7, encoding)
            result = solve(problem, seconds=1, conflicts=10000)
            self.assertEqual(result["status"], "SAT")
            self.assertLessEqual(result["verification"]["rank"], 7)
            self.assertTrue(verify_candidate(result["candidate"])["valid"])
        system = build_system(canonical_terms(naive), 2, baseline=naive)
        self.assertEqual(solve(build_problem(system, 7), seconds=1)["status"], "UNSAT")
        with self.assertRaises(AssertionError):
            validate_decode(build_problem(system, 7), [None]+[False]*1000)

    @unittest.skipUnless(importlib.util.find_spec("pycryptosat"), "optional native XOR backend")
    def test_cli_control_and_sat_subset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            naive, strassen = naive_candidate(2), strassen_candidate(2)
            save(root/"dictionary.json", canonical_terms(naive))
            save(root/"baseline.json", naive)
            extra = root/"extra.txt"
            extra.write_text("".join(" ".join(map(str, t))+"\n" for t in canonical_terms(strassen)))
            self.assertEqual(main(["--dictionary", str(root/"dictionary.json"), "--baseline", str(root/"baseline.json"),
                "--extra-terms", str(extra), "--output-dir", str(root/"out"), "--dimension", "2", "--rank", "7", "--seconds", "2"]), 0)
            self.assertTrue((root/"out/FOUND.json").exists())


if __name__ == "__main__":
    unittest.main()
