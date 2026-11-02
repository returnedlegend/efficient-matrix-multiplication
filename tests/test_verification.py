import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mmsearch.tensor import multiplication_tensor, naive_candidate, strassen_candidate, tensor_index
from mmsearch.verify import verify_candidate, verify_file, write_standalone_verifier


class VerificationTests(unittest.TestCase):
    def test_trace_tensor_coordinates(self):
        tensor = multiplication_tensor()
        self.assertEqual(len(tensor), 15625)
        self.assertEqual(sum(tensor), 125)
        self.assertEqual(tensor[tensor_index(1*5+2, 2*5+3, 3*5+1)], 1)
        self.assertEqual(tensor[tensor_index(1*5+2, 2*5+3, 1*5+3)], 0)

    def test_naive_f2_and_integer(self):
        for field in (0, 2):
            report = verify_candidate(naive_candidate(field=field))
            self.assertTrue(report["valid"], report)
            self.assertTrue(report["integer_valid"])
            self.assertEqual(report["rank"], 125)
            self.assertEqual(report["exact_entries_checked"], 15625)

    def test_strassen_baseline_and_signed_integer_lift(self):
        for field in (0, 2):
            report = verify_candidate(strassen_candidate(field=field))
            self.assertTrue(report["valid"], report)
            self.assertEqual(report["rank"], 110)
            self.assertEqual(report["integer_valid"], field == 0)

    def test_strassen_smaller_dimensions(self):
        for n, expected_rank in ((1, 1), (2, 7), (3, 26), (4, 49)):
            candidate = strassen_candidate(n, field=0)
            self.assertEqual(len(candidate["terms"]), expected_rank)
            self.assertTrue(verify_candidate(candidate)["valid"])

    def test_corrupted_and_transposed_coefficients_rejected(self):
        candidate = naive_candidate()
        candidate["terms"][0]["u"][0] = 0
        self.assertFalse(verify_candidate(candidate)["valid"])
        candidate = naive_candidate()
        for term in candidate["terms"]:
            term["w"] = [term["w"][j*5+i] for i in range(5) for j in range(5)]
        self.assertFalse(verify_candidate(candidate)["valid"])

    def test_exact_zeros_checked_even_without_random_trials(self):
        candidate = naive_candidate()
        candidate["terms"][0]["u"][1] = 1
        report = verify_candidate(candidate, random_trials=0)
        self.assertFalse(report["valid"])
        self.assertEqual(report["mismatch_count"], 1)
        self.assertEqual(report["exact_entries_checked"], 15625)

    def test_field_specificity_and_no_silent_integer_lift(self):
        candidate = naive_candidate()
        candidate["terms"][0]["u"][0] = 3
        report = verify_candidate(candidate)
        self.assertTrue(report["valid"])
        self.assertFalse(report["integer_valid"])
        candidate["field"] = 0
        self.assertFalse(verify_candidate(candidate)["valid"])
        candidate["field"] = 3
        self.assertFalse(verify_candidate(candidate)["valid"])

    def test_malformed_fails_closed(self):
        malformed = [None, [], {}, {"field": True, "dimension": 5, "terms": []}]
        base = naive_candidate()
        for mutate in (lambda c: c["terms"][0]["u"].pop(),
                       lambda c: c["terms"][0]["v"].__setitem__(0, True),
                       lambda c: c["terms"][0]["w"].__setitem__(0, 1.0),
                       lambda c: c.__setitem__("dimension", 5.0),
                       lambda c: c["terms"][0].__setitem__("extra", [])):
            bad = copy.deepcopy(base)
            mutate(bad)
            malformed.append(bad)
        for candidate in malformed:
            self.assertFalse(verify_candidate(candidate)["valid"])

    def test_standalone_verifier_and_invalid_exit_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            script = write_standalone_verifier(directory / "verify.py")
            certificate = directory / "candidate.json"
            candidate = naive_candidate()
            certificate.write_text(json.dumps(candidate), encoding="utf-8")
            result = subprocess.run([sys.executable, "-I", str(script), str(certificate)],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue(json.loads(result.stdout)["valid"])
            candidate["terms"][0]["u"][0] = 0
            certificate.write_text(json.dumps(candidate), encoding="utf-8")
            result = subprocess.run([sys.executable, "-I", str(script), str(certificate)],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertFalse(json.loads(result.stdout)["valid"])

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate.json"
            path.write_text('{"field":2,"field":0,"dimension":5,"terms":[]}', encoding="utf-8")
            report = verify_file(path)
            self.assertFalse(report["valid"])
            self.assertIn("duplicate JSON key", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
