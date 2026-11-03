"""Independent checker adversarial and mathematical controls; no search imports."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("independent42", ROOT / "scripts/verify_record42_independent.py")
V = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V)


def schoolbook(n):
    terms = []
    for i in range(n):
        for j in range(n):
            for k in range(n):
                u, v, w = ([0] * (n*n) for _ in range(3))
                u[i*n+j] = v[j*n+k] = w[k*n+i] = 1
                terms.append((tuple(u), tuple(v), tuple(w)))
    return terms


class IndependentRecord42Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.km = json.loads((ROOT / "artifacts/km93_f2.json").read_text())

    def verify(self, data):
        return V.verify_bytes(json.dumps(data))

    def test_published_km93_full_zero_and_one_coverage(self):
        report = self.verify(self.km)
        self.assertTrue(report["valid"])
        self.assertFalse(report["record_eligible"])
        self.assertEqual(report["canonical_essential_products"], 93)
        self.assertEqual(report["output_bits_checked"], 15625)
        self.assertEqual(report["expected_one_bits"], 125)
        self.assertEqual(report["observed_one_bits"], 125)

    def test_published_alphaevolve93(self):
        path = ROOT / "artifacts/rl_campaign_20261102T210735Z/public/alphaevolve93_f2.json"
        self.assertTrue(path.is_file(), "published AE93 fixture must be available")
        report = V.verify_file(path)
        self.assertTrue(report["valid"])
        self.assertFalse(report["record_eligible"])
        self.assertEqual(report["canonical_essential_products"], 93)
        self.assertEqual(report["output_bits_checked"], 15625)

    def test_single_coefficient_corruption(self):
        data = copy.deepcopy(self.km)
        data["terms"][0]["u"][0] ^= 1
        report = self.verify(data)
        self.assertFalse(report["valid"])
        self.assertGreater(report["mismatch_count"], 0)
        self.assertEqual(report["output_bits_checked"], 15625)

    def test_strict_type_ring_and_dimension_guards(self):
        for field, value in (("dimension", 2), ("dimension", 5.0), ("field", 3),
                             ("field", 2.0), ("field", True)):
            with self.subTest(field=field, value=value):
                data = copy.deepcopy(self.km)
                data[field] = value
                self.assertFalse(self.verify(data)["valid"])

    def test_float_bool_coefficient_and_wrong_lengths(self):
        for value in (True, False, 0.0, 1.0, 2, -1, "1", None):
            with self.subTest(value=value):
                data = copy.deepcopy(self.km)
                data["terms"][0]["u"][0] = value
                self.assertFalse(self.verify(data)["valid"])
        for length in (24, 26):
            data = copy.deepcopy(self.km)
            data["terms"][0]["w"] = [0] * length
            self.assertFalse(self.verify(data)["valid"])

    def test_duplicate_keys_at_top_and_nested(self):
        for raw in ('{"dimension":5,"dimension":5,"field":2,"terms":[]}',
                    '{"dimension":5,"field":2,"terms":[{"u":[],"u":[]}]}'):
            report = V.verify_bytes(raw)
            self.assertFalse(report["valid"])
            self.assertIn("duplicate JSON key", report["errors"][0])

    def test_nonjson_constants(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            report = V.verify_bytes('{"dimension":5,"field":2,"terms":[],"meta":'+value+'}')
            self.assertFalse(report["valid"])

    def test_nominal_rank_untrusted_and_duplicate_zero_cancellation(self):
        data = copy.deepcopy(self.km)
        data["rank"] = data["essential_rank"] = 92
        data["terms"].extend(copy.deepcopy([data["terms"][0], data["terms"][0]]))
        data["terms"].append({"u": [0]*25, "v": [1]*25, "w": [1]*25})
        report = self.verify(data)
        self.assertTrue(report["valid"])
        self.assertFalse(report["record_eligible"])
        self.assertEqual(report["canonical_essential_products"], 93)
        self.assertEqual(report["nominal_input_products"], 96)
        self.assertEqual(report["zero_input_products"], 1)
        self.assertEqual(report["duplicate_products_cancelled"], 2)

    def test_fake92_and_empty_are_not_records(self):
        data = copy.deepcopy(self.km)
        data["terms"].pop()
        self.assertFalse(self.verify(data)["record_eligible"])
        data["terms"] = []
        report = self.verify(data)
        self.assertFalse(report["valid"])
        self.assertEqual(report["mismatch_count"], 125)

    def test_n2_generic_core_and_strict_campaign_guard(self):
        terms = schoolbook(2)
        report = V._check_all_basis_outputs(2, terms)
        self.assertEqual(report["mismatch_count"], 0)
        self.assertEqual(report["output_bits_checked"], 64)
        data = {"dimension": 2, "field": 2, "rank": 7,
                "terms": [dict(zip(("u","v","w"), map(list, t))) for t in terms]}
        self.assertFalse(self.verify(data)["record_eligible"])
        # Planted canceling pair proves canonical reduction without a search.
        canonical, _ = V.canonical_terms(terms + [terms[0], terms[0]])
        self.assertEqual(len(canonical), 8)
        self.assertEqual(V._check_all_basis_outputs(2, canonical)["mismatch_count"], 0)

    def test_strassen7_planted_cancellation_and_n2_record_rejection(self):
        path = ROOT / "artifacts/campaign_20261102T164324Z/control-strassen7.candidate.json"
        data = json.loads(path.read_text())
        terms = [tuple(tuple(t[a]) for a in ("u", "v", "w")) for t in data["terms"]]
        self.assertEqual(len(terms), 7)
        self.assertEqual(V._check_all_basis_outputs(2, terms)["mismatch_count"], 0)
        planted = terms + [terms[0], terms[0]]
        canonical, _ = V.canonical_terms(planted)
        self.assertEqual(len(canonical), 7)
        self.assertEqual(V._check_all_basis_outputs(2, canonical)["mismatch_count"], 0)
        self.assertFalse(self.verify(data)["record_eligible"])

    def test_transpose_convention_is_required(self):
        terms = schoolbook(2)
        wrong = [(u, v, tuple(w[j*2+i] for i in range(2) for j in range(2))) for u,v,w in terms]
        self.assertGreater(V._check_all_basis_outputs(2, wrong)["mismatch_count"], 0)
        data = copy.deepcopy(self.km)
        for term in data["terms"]:
            w = term["w"]
            term["w"] = [w[j*5+i] for i in range(5) for j in range(5)]
        self.assertFalse(self.verify(data)["valid"])

    def test_canonical_hash_ignores_order_zero_and_even_duplicates(self):
        original = self.verify(self.km)
        data = copy.deepcopy(self.km)
        data["terms"].reverse()
        data["terms"] += copy.deepcopy([data["terms"][0], data["terms"][0]])
        self.assertEqual(original["canonical_certificate_sha256"], self.verify(data)["canonical_certificate_sha256"])


if __name__ == "__main__":
    unittest.main()
