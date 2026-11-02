import copy
import json
from pathlib import Path
import tempfile
import unittest

from mmsearch.recombine import Pool, canonical_terms, encode, search
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.verify import verify_candidate
from scripts.campaign_recombine import main, read_source


def planted():
    base = set(canonical_terms(naive_candidate(2)))
    a = {(1, 3, 3), (2, 3, 3), (3, 3, 3)}
    b = {(4, 5, 5), (8, 5, 5), (12, 5, 5)}
    return [encode(base ^ cycle, 2) for cycle in (a, b, a ^ b)]


class RecombineTests(unittest.TestCase):
    def test_xor_three_exact_algorithms_reduces_redundancy(self):
        pool = Pool(planted())
        self.assertEqual([s["rank"] for s in pool.sources], [11, 11, 14])
        self.assertEqual(pool.combine(7).bit_count(), 8)
        candidate, report, state = search(pool, target=8, seconds=1, neighbors=3)
        self.assertTrue(report["valid"])
        self.assertEqual(report["rank"], 8)
        self.assertEqual(report["exact_entries_checked"], 64)
        self.assertEqual(candidate["metadata"]["coefficients_hex"], "0x7")
        self.assertEqual(canonical_terms(candidate), canonical_terms(naive_candidate(2)))

    def test_local_pair_minimum_is_finite_pool_statement(self):
        pool = Pool(planted())
        candidate, report, state = search(pool, target=1, seconds=1, neighbors=3, walk_steps=25)
        self.assertTrue(report["valid"])
        self.assertEqual(report["rank"], 8)
        self.assertTrue(state["local_cycle_minimum"])
        self.assertEqual(state["local_pairs_checked"], 3)

    def test_all_odd_parity_and_odd_coefficients(self):
        pool = Pool([strassen_candidate(2)])
        self.assertEqual(pool.manifest()["source_rank_parities"], [1])
        self.assertIn("92 is unreachable", pool.manifest()["parity_limitation"])
        self.assertEqual(pool.combine(1).bit_count() % 2, 1)
        for mask in (0, 2, -1, True):
            with self.assertRaises(ValueError):
                pool.combine(mask)
        self.assertEqual(Pool(planted()).manifest()["source_rank_parities"], [0, 1])

    def test_reject_malformed_or_inexact_sources(self):
        for bad in (None, {}, dict(dimension=True, field=2, terms=[])):
            with self.assertRaises(ValueError):
                Pool([bad])
        source = naive_candidate(2)
        variants = []
        for value in (True, -1, 2):
            bad = copy.deepcopy(source)
            bad["terms"][0]["u"][0] = value
            variants.append(bad)
        bad = copy.deepcopy(source)
        bad["terms"][0]["u"] = [0]*4
        variants.append(bad)
        bad = copy.deepcopy(source)
        bad["terms"].pop()
        variants.append(bad)
        for bad in variants:
            with self.assertRaises(ValueError):
                Pool([bad])
        with self.assertRaises(ValueError):
            Pool([naive_candidate(2), naive_candidate(3)])

    def test_duplicate_terms_cancel_without_changing_parity(self):
        source = naive_candidate(2)
        source["terms"].extend([copy.deepcopy(source["terms"][0])]*2)
        pool = Pool([source, naive_candidate(2)])
        self.assertEqual(len(pool.sources), 1)
        self.assertEqual(pool.sources[0]["rank"], 8)

    def test_checkpoint_replay_and_tamper_rejection(self):
        pool = Pool(planted())
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/"a.json", Path(tmp)/"b.json"
            opts = dict(target=1, seconds=2, seed=9, neighbors=3, walk_steps=30)
            search(pool, checkpoint=a, max_steps=25, **opts)
            search(pool, checkpoint=b, max_steps=7, **opts)
            search(pool, checkpoint=b, max_steps=18, resume=True, **opts)
            self.assertEqual(json.loads(a.read_text()), json.loads(b.read_text()))
            with self.assertRaisesRegex(ValueError, "checkpoint"):
                search(pool, checkpoint=b, resume=True, seed=10, seconds=1)

    def test_cli_snapshots_native_even_source_and_independent_certificate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for i, candidate in enumerate(planted()):
                path = root/f"source{i}.json"
                path.write_text(json.dumps(candidate))
                paths.extend(["--input", str(path)])
            native = root/"walk.current.txt"
            native.write_text("".join(" ".join(map(str, t))+"\n" for t in canonical_terms(planted()[2])))
            candidate, record = read_source(native, 2)
            self.assertEqual(len(candidate["terms"]), 14)
            self.assertTrue(verify_candidate(candidate)["valid"])
            self.assertEqual(main(paths+["--raw-glob", str(native), "--output-dir", str(root/"out"),
                                        "--dimension", "2", "--target", "8", "--seconds", "1"]), 0)
            self.assertTrue((root/"out/FOUND.json").exists())
            self.assertTrue(verify_candidate(json.loads((root/"out/FOUND.json").read_text()))["valid"])
            manifest = json.loads((root/"out/pool.json").read_text())
            self.assertEqual(manifest["source_rank_parities"], [0, 1])
            self.assertTrue(all(Path(s["provenance"]["snapshot"]).exists() for s in manifest["sources"]))


if __name__ == "__main__":
    unittest.main()
