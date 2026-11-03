"""Actual n2 lift/publication controls; production metadata tests use fake bytes."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mmsearch import binary_packet_adapter7 as subject
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.tensor_code7 import second_check
from scripts.campaign_operations_v3 import walk_files, canonical_candidate


def tiny():
    source = naive_candidate(2)
    terms = subject.literal_terms(source)
    core_mask = 0
    for term in terms:core_mask ^= subject.packed_tensor(term, 4)
    core = [core_mask >> i & 1 for i in range(64)]
    row = dict(id="tiny", source_indices=list(range(8)), shared_mode_basis=[1, 2, 4, 8],
        branch_metadata=dict(d=4, actual_core_sha256=subject.sha(bytes(core)),
                             ambient_sha256=subject.sha(core_mask.to_bytes(8, "little"))))
    data = subject.build_packet_data(source, row, production=False)
    products = [list(t) for t in subject.literal_terms(strassen_candidate(2))]
    observation = dict(status="RAW_EXACT_COMPACT", raw_compact=dict(products=products), best_loss=0)
    return source, row, data, observation


def independent_n2(raw):
    candidate = json.loads(raw)
    report = second_check(candidate)
    return dict(valid=report["valid"], exact_entries_checked=report["exact_entries_checked"],
                essential_rank=len(candidate["terms"]))


class BinaryPacketAdapterTests(unittest.TestCase):
    def test_shared_basis_core_pin_full_target_and_drop_minimum(self):
        source, row, data, observation = tiny()
        self.assertEqual(data["shape"], [4] * 3)
        self.assertEqual(data["removed_source_index"], 0)
        self.assertEqual(data["removed_compact_volume"], 1)
        self.assertEqual(data["initial_loss"], 1)
        self.assertTrue(data["full_target_unchanged"])
        self.assertEqual(len(data["original_compact_products"]), 8)
        self.assertEqual(len(data["initial_factors"]), 7)
        candidate = subject.lift_candidate(source, data, observation["raw_compact"]["products"])
        self.assertTrue(subject.verify_candidate(candidate)["valid"])
        self.assertEqual(len(candidate["terms"]), 7)
        wrong = copy.deepcopy(row); wrong["branch_metadata"]["actual_core_sha256"] = "0" * 64
        with self.assertRaises(ValueError):subject.build_packet_data(source, wrong, production=False)

    def test_positive_requires_both_checks_and_safe_publish(self):
        source, row, data, observation = tiny()
        barriers = []
        with tempfile.TemporaryDirectory() as directory:
            result = subject.verify_raw_and_publish(source, data, observation, directory,
                barriers.append, production=False, independent_checker=independent_n2)
            self.assertEqual(result["status"], "SMALL_CONTROL_PASSED")
            self.assertEqual(result["full"]["exact_entries_checked"], 64)
            self.assertEqual(result["independent"]["exact_entries_checked"], 64)
            self.assertIn("post_full_ambient", barriers)
            self.assertIn("post_independent_ambient", barriers)
            self.assertIn("premarker", barriers); self.assertIn("postmarker", barriers)
            self.assertTrue((Path(directory) / result["candidate_path"]).exists())

    def test_late_solve_full_independent_or_postmarker_remains_hidden_unknown(self):
        source, row, data, observation = tiny()
        for barrier in ["post_solve", "post_full_ambient", "post_independent_ambient", "postmarker"]:
            with self.subTest(barrier=barrier), tempfile.TemporaryDirectory() as directory:
                def guard(label):
                    if label == barrier:raise subject.Stop("synthetic late " + label)
                result = subject.verify_raw_and_publish(source, data, observation, directory, guard,
                    production=False, independent_checker=independent_n2)
                self.assertEqual(result["status"], "UNKNOWN")
                self.assertFalse(result["complete"])
                self.assertFalse((Path(directory) / "first-record-evidence").exists())
                for path in walk_files(directory):
                    if path.suffix == ".json":
                        with self.assertRaises((ValueError, TypeError, KeyError)):
                            canonical_candidate(json.loads(path.read_bytes()))
                self.assertTrue(list((Path(directory) / ".raw-candidates").rglob("*.json")))

    def test_bad_or_nonzero_compact_observation_cannot_promote(self):
        source, row, data, observation = tiny()
        for mutation in ["status", "products", "basis", "outside"]:
            with tempfile.TemporaryDirectory() as directory:
                obs, changed = copy.deepcopy(observation), copy.deepcopy(data)
                if mutation == "status":obs["status"] = "UNKNOWN"
                elif mutation == "products":obs["raw_compact"]["products"].pop()
                elif mutation == "basis":changed["image_bases"][0][0] ^= 2
                else:changed["outside_indices"] = [0]
                if mutation == "status":
                    result = subject.verify_raw_and_publish(source, changed, obs, directory, lambda _:None,
                        production=False, independent_checker=independent_n2)
                    self.assertEqual(result["status"], "UNKNOWN")
                else:
                    with self.assertRaises((ValueError, AssertionError)):
                        subject.verify_raw_and_publish(source, changed, obs, directory, lambda _:None,
                            production=False, independent_checker=independent_n2)
                self.assertFalse((Path(directory) / "first-record-evidence").exists())

    def test_plan_filters_only_nine_d11_and_rejects_scope_changes(self):
        rows = []
        for i in range(11):
            d = 11 if i < 9 else 13 + i % 2
            rows.append(dict(id=f"fake-{i}", source_indices=list(range(15)), shared_mode_basis=list(range(11)),
                branch_metadata=dict(d=d, local_products=15, target_local_products=14, outside_products=78,
                    target_global_products=92, mode_shape=[d] * 3, actual_core_mode_ranks=[d] * 3,
                    actual_unfolding_ranks_by_independent_pair_columns=[d] * 3,
                    actual_core_checked=True, branch="RETAIN_DEFER_HIGHER_SURPLUS")))
        def fixture():
            compressed = gzip.compress(json.dumps(dict(packets=rows)).encode())
            return {
                subject.PREP + "/catalog.json.gz": compressed,
                subject.PREP + "/manifest.json": subject.raw(dict(catalog_sha256=subject.sha(compressed),
                    source=dict(raw_sha256=subject.SOURCE_SHA, source_manifest_sha256=subject.ANCHORS,
                                root_eligibility_sha256=subject.ELIGIBILITY, essential_products=93))),
                subject.PREP + "/COMPLETE.json": subject.raw(dict(manifest_sha256=subject.PINS[subject.PREP + "/manifest.json"])),
                "tensor-code-source-anchors-v1/manifest.json": subject.raw(dict(anchors=[], known_input_train_states=[dict(
                    sha256=subject.SOURCE_SHA, heldout_excluded=True, evaluation_excluded=True, root_approved_train=True)])),
                "tensor-code-first120-proposal-v1/source-eligibility-root-approval.json": subject.raw(dict(
                    owner="root", approved_manifest_sha256=subject.ANCHORS, approved_groups=["anchors", "known_input_train_states"]))}
        values = fixture()
        with patch.object(subject, "pinned", side_effect=lambda relative, root=subject.C7:values[relative]):
            plan = subject.select_plan()
            self.assertEqual(len(plan["cases"]), 9)
            self.assertTrue(all(row["branch_metadata"]["d"] == 11 for row in plan["cases"]))
        rows[0]["branch_metadata"]["d"] = 12
        values = fixture()
        with patch.object(subject, "pinned", side_effect=lambda relative, root=subject.C7:values[relative]):
            with self.assertRaises(ValueError):subject.select_plan()


if __name__ == "__main__":unittest.main()
