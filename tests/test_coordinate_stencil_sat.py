import copy
import importlib.util
import itertools
import json
import multiprocessing as mp
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from mmsearch.coordinate_stencil_sat import (FormulaMemoryLimit, VerifiedSources,
    audit, build_family, build_problem, decode_selection, estimate_formula,
    prune_stencils, selected_union, single_coordinate_scan, solve,
    source_assumptions, validate_decode, verify_selection)
from mmsearch.free_factor_sat import ORIENTATIONS
from mmsearch.recombine import canonical_terms, encode
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.verify import verify_candidate
from scripts.campaign_coordinate_stencil_sat import main, strict_json


HAVE_SOLVER = importlib.util.find_spec("pysat") is not None


def stalled_worker(*args):
    time.sleep(10)


def planted_sources(orientation):
    """Neither parent has rank seven; clean columns recombine to Strassen."""
    terms = list(canonical_terms(strassen_candidate(2)))
    permutation = ORIENTATIONS[orientation]
    parents = []
    for coordinate in (0, 1):
        extra = []
        for a in (1, 2, 3):
            triple = [0, 0, 0]
            for axis, value in zip(permutation, (a, 3, 1 << coordinate)):
                triple[axis] = value
            extra.append(tuple(triple))
        parents.append(encode(terms+extra, 2))
    return parents


class CoordinateStencilTests(unittest.TestCase):
    def test_exact_independent_coordinate_assembly_all_axes(self):
        sources = VerifiedSources([strassen_candidate(2), naive_candidate(2)], 2)
        for orientation in ORIENTATIONS:
            family = build_family(sources, orientation)
            for selection in itertools.product(*(range(len(row)) for row in family["choices"])):
                candidate, report = verify_selection(family, selection)
                self.assertTrue(report["valid"])
                self.assertEqual(report["exact_entries_checked"], 64)
                self.assertEqual(report["random_multiplication"]["trials"], 16)
                self.assertEqual(len(candidate["terms"]), selected_union(family, selection).bit_count())
            self.assertEqual(audit(family)["metadata"]["orientation"], orientation)

    def test_duplicate_and_strict_dominance_provenance(self):
        kept, mapping, originals = prune_stencils([3, 3, 7, 4, 12])
        self.assertEqual({item["mask"] for item in kept}, {3, 4})
        self.assertEqual(kept[mapping[0]]["sources"], [0, 1])
        for source, mask in enumerate((3, 3, 7, 4, 12)):
            self.assertEqual(kept[mapping[source]]["mask"] & mask, kept[mapping[source]]["mask"])
        self.assertEqual(sum(item["dominated"] for item in originals), 2)
        kept, mapping, _ = prune_stencils([0, 3, 5])
        self.assertEqual(kept, [dict(mask=0, sources=[0])])
        self.assertEqual(mapping, [0, 0, 0])
        for bad in ([True], [-1]):
            with self.assertRaises(ValueError):
                prune_stencils(bad)

    def test_source_validation_happens_before_dedupe_and_is_strict(self):
        good = strassen_candidate(2)
        with patch("mmsearch.coordinate_stencil_sat.verify_candidate", wraps=verify_candidate) as verify:
            sources = VerifiedSources([good, copy.deepcopy(good)], 2)
            self.assertEqual(verify.call_count, 2)
        self.assertEqual(len(sources.sources), 1)
        self.assertEqual(len(sources.input_sources), 2)
        for mutate in (lambda c: c.update(field=0), lambda c: c.update(dimension=5),
                       lambda c: c["terms"][0]["u"].__setitem__(0, True),
                       lambda c: c["terms"][0]["w"].__setitem__(0, 1-c["terms"][0]["w"][0])):
            bad = copy.deepcopy(good)
            mutate(bad)
            with self.assertRaises(ValueError):
                VerifiedSources([good, bad], 2)

    def test_same_pair_xor_merging_and_zero_groups(self):
        original = strassen_candidate(2)
        padded = encode(list(canonical_terms(original))+[(15, 15, 1), (15, 15, 2), (15, 15, 3)], 2)
        family = build_family(VerifiedSources([padded], 2))
        self.assertEqual(len(family["pairs"]), 8)
        self.assertEqual(family["metadata"]["merged_source_ranks"], [7])
        self.assertEqual(verify_selection(family, family["source_choices"][0])[1]["rank"], 7)

    def test_planted_parent_mix_dominance_baseline(self):
        for orientation in ORIENTATIONS:
            parents = planted_sources(orientation)
            sources = VerifiedSources(parents, 2)
            self.assertTrue(all(s["canonical_rank"] > 7 for s in sources.sources))
            family = build_family(sources, orientation)
            candidate, report = verify_selection(family, family["source_choices"][0])
            self.assertEqual(report["rank"], 7)
            self.assertEqual(canonical_terms(candidate), canonical_terms(strassen_candidate(2)))

    def test_single_coordinate_scan_matches_bruteforce(self):
        family = build_family(VerifiedSources([naive_candidate(2), strassen_candidate(2)], 2))
        best, tested = 1000, 0
        for source in family["source_choices"]:
            for c, row in enumerate(family["choices"]):
                for j in range(len(row)):
                    trial = list(source)
                    trial[c] = j
                    best = min(best, selected_union(family, trial).bit_count())
                    tested += 1
        retained = []
        result = single_coordinate_scan(family, seconds=1,
            on_improvement=lambda candidate, verification, selection: retained.append((candidate, verification)))
        self.assertEqual(result["status"], "SCAN_COMPLETE")
        self.assertEqual(result["rank"], best)
        self.assertEqual(result["tested_swaps"], tested)
        self.assertTrue(all(report["valid"] and report["random_multiplication"]["trials"] == 16
                            for candidate, report in retained))

    def test_preflight_estimate_caps(self):
        family = build_family(VerifiedSources([strassen_candidate(2)], 2))
        self.assertGreater(estimate_formula(family, 7)["estimated_python_formula_bytes"], 0)
        with self.assertRaises(FormulaMemoryLimit):
            build_problem(family, 7, max_formula_mb=0.00001)
        for bad in ([], [0], [-1]*4, [True]*4):
            with self.assertRaises(ValueError):
                decode_selection(family, bad)

    @unittest.skipUnless(HAVE_SOLVER, "PySAT optional")
    def test_pure_cnf_sat_controls_and_restricted_unsat(self):
        for orientation in ORIENTATIONS:
            family = build_family(VerifiedSources([strassen_candidate(2), naive_candidate(2)], 2), orientation)
            problem = build_problem(family, 7)
            self.assertEqual(problem["metadata"]["native_xors"], 0)
            control = solve(problem, seconds=1, memory_mb=512, assumptions=source_assumptions(problem))
            self.assertEqual(control["status"], "SAT")
            self.assertTrue(control["worker_reaped"])
            self.assertEqual(control["verification"]["rank"], 7)
            sat = solve(problem, seconds=1, memory_mb=512)
            self.assertEqual(sat["status"], "SAT")
            unsat = solve(build_problem(family, 6), seconds=1, memory_mb=512)
            self.assertEqual(unsat["status"], "UNSAT")
            self.assertIn("finite", unsat["scope"])

    @unittest.skipUnless(HAVE_SOLVER, "PySAT optional")
    def test_corrupt_and_incomplete_models_rejected(self):
        family = build_family(VerifiedSources([strassen_candidate(2), naive_candidate(2)], 2))
        problem = build_problem(family, 7)
        result = solve(problem, 1, memory_mb=512)
        model = result["complete_assignment"]
        for bad in (model[:-1], [None]+[int(x) for x in model[1:]]):
            with self.assertRaises(AssertionError):
                validate_decode(problem, bad)
        for variable in (problem["xs"][0][0], problem["ys"][0]):
            bad = list(model)
            bad[variable] = not bad[variable]
            with self.assertRaises(AssertionError):
                validate_decode(problem, bad)

    def test_timeout_worker_reaped(self):
        family = build_family(VerifiedSources([strassen_candidate(2)], 2))
        problem = build_problem(family, 7)
        before = {child.pid for child in mp.active_children()}
        started = time.monotonic()
        with patch("mmsearch.coordinate_stencil_sat._worker", stalled_worker):
            result = solve(problem, seconds=0.05, memory_mb=512)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertTrue(result["worker_reaped"])
        self.assertLess(time.monotonic()-started, 2)
        self.assertEqual({child.pid for child in mp.active_children()}, before)
        with self.assertRaises(ProcessLookupError):
            os.kill(result["worker_pid"], 0)

    def test_main_strict_dimension_and_json(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            strict_json('{"field":2,"field":0}')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/"tiny.json"
            path.write_text(json.dumps(strassen_candidate(2)))
            with self.assertRaisesRegex(ValueError, "dimension"):
                main(["--input", str(path), "--outdir", str(root/"output")])
            with self.assertRaises(SystemExit):
                main(["--input", str(path), "--rank", "93", "--outdir", str(root/"invalid")])


if __name__ == "__main__":
    unittest.main()
