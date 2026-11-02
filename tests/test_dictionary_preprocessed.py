import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from mmsearch.recombine import canonical_terms, save
from mmsearch.recombine_sat import build_system, satisfies, solve
from mmsearch.recombine_sat_preprocessed import build_problem, preprocess_rows, weighted_cardinality
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.verify import verify_candidate
from scripts.campaign_dictionary_preprocessed import main


def clause_satisfied(clause, selection):
    return any(bool(selection >> (abs(lit)-1) & 1) == (lit > 0) for lit in clause)


class DictionaryPreprocessedTests(unittest.TestCase):
    def test_all_small_assignments_preserve_affine_constraints_and_exact_cost(self):
        cases = [
            (5, [0b00011, 0b00110 | 32, 0b01000 | 32]),
            (4, [0b0011 | 16, 0b0101 | 16]),
            (2, [0b11 | 4]),
            (4, [0b0011, 0b1100, 0b1111]),
            (3, [0b011, 0b111 | 8]),
            (2, []),
            (2, [0b01, 0b01 | 4]),
            (3, [0b011, 0b110, 0b101 | 8]),
            (2, [4]),
        ]
        for variables, rows in cases:
            pre = preprocess_rows(rows, variables)
            for row, proof in zip(pre["rref_rows"], pre["rref_proofs"]):
                reconstructed = 0
                for i, original in enumerate(rows):
                    if proof >> i & 1:
                        reconstructed ^= original
                self.assertEqual(reconstructed, row)
            for selection in range(1 << variables):
                linked = all(clause_satisfied(c, selection) for c in pre["clauses"])
                xors = all(bool(sum(selection >> (v-1) & 1 for v in vs) % 2) == rhs
                           for vs, rhs in pre["xors"])
                self.assertEqual(linked and xors, satisfies(rows, selection, variables), (rows, selection))
                if linked:
                    cost = pre["constant_cost"]+sum(bool(selection >> (abs(lit)-1) & 1) == (lit > 0)
                                                    for lit in pre["cardinality_literals"])
                    self.assertEqual(cost, selection.bit_count(), (rows, selection))
        complement = preprocess_rows([0b0011 | 16, 0b0101 | 16], 4)
        self.assertIn(-1, complement["cardinality_literals"])
        balanced = preprocess_rows([0b11 | 4], 2)
        self.assertEqual(balanced["constant_cost"], 1)
        self.assertEqual(balanced["cardinality_literals"], [])

    def test_repeated_signed_literals_cardinality_exhaustive(self):
        from pysat.solvers import Solver
        for encoding in ("cardnetwrk", "totalizer", "seqcounter"):
            for literals in ([], [1, 1, -2, -2, -2, 3], [1, -1, 2, -2], [-1, -1, -2]):
                for bound in range(-1, len(literals)+1):
                    clauses, nv = weighted_cardinality(literals, bound, 3, encoding)
                    with Solver(name="g3", bootstrap_with=clauses) as solver:
                        for selection in range(8):
                            assumptions = [v if selection >> (v-1) & 1 else -v for v in range(1, 4)]
                            expected = sum(bool(selection >> (abs(lit)-1) & 1) == (lit > 0) for lit in literals) <= bound
                            self.assertEqual(solver.solve(assumptions=assumptions), expected,
                                             (encoding, literals, bound, selection))

    def test_bad_augmented_rows_rejected(self):
        for rows, variables in (([8], 2), ([-1], 2), ([True], 2), ([], 0)):
            with self.assertRaises(ValueError):
                preprocess_rows(rows, variables)

    @unittest.skipUnless(importlib.util.find_spec("pycryptosat"), "optional native XOR backend")
    def test_strassen_sat_and_naive_unsat_with_original_indicator_decode(self):
        naive, strassen = naive_candidate(2), strassen_candidate(2)
        dictionary = sorted(set(canonical_terms(naive)) | set(canonical_terms(strassen)))
        system = build_system(dictionary, 2, baseline=naive)
        problem = build_problem(system, 7)
        result = solve(problem, seconds=1, conflicts=10000)
        self.assertEqual(result["status"], "SAT")
        self.assertLessEqual(result["verification"]["rank"], 7)
        self.assertTrue(verify_candidate(result["candidate"])["valid"])
        self.assertIn("preprocessing", result["candidate"]["metadata"])
        self.assertEqual(solve(build_problem(build_system(canonical_terms(naive), 2), 7), seconds=1)["status"], "UNSAT")

    @unittest.skipUnless(importlib.util.find_spec("pycryptosat"), "optional native XOR backend")
    def test_driver_snapshots_extra_terms_and_passes_baseline_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            naive, strassen = naive_candidate(2), strassen_candidate(2)
            save(root/"dictionary.json", canonical_terms(naive))
            save(root/"baseline.json", naive)
            extra = root/"extra.txt"
            extra.write_text("".join(" ".join(map(str, t))+"\n" for t in canonical_terms(strassen)))
            self.assertEqual(main(["--dictionary", str(root/"dictionary.json"), "--baseline", str(root/"baseline.json"),
                "--extra-terms", str(extra), "--output-dir", str(root/"out"), "--dimension", "2", "--rank", "7", "--seconds", "2"]), 0)
            candidate = json.loads((root/"out/FOUND.json").read_text())
            self.assertTrue(verify_candidate(candidate)["valid"])
            self.assertEqual(json.loads((root/"out/control.result.json").read_text())["status"], "SAT")
            meta = json.loads((root/"out/manifest.json").read_text())
            self.assertIn("driver_code_sha256", meta["preprocessing"])
            self.assertTrue((root/"out/inputs/extra-terms-0.txt").exists())


if __name__ == "__main__":
    unittest.main()
