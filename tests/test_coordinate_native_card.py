import copy
import hashlib
import importlib.util
import itertools
import json
import multiprocessing as mp
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mmsearch.coordinate_native_card import (FormulaMemoryLimit, VerifiedSources,
    build_family, build_problem, estimate_formula, formula_audit, selected_union,
    solve, source_assumptions, validate_decode)
from mmsearch.coordinate_stencil_sat import build_problem as build_cnf_problem
from mmsearch.free_factor_sat import ORIENTATIONS
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.verify import verify_candidate
from scripts.campaign_coordinate_native_card import main, run_sat, save_record


HAVE_PYSAT = importlib.util.find_spec("pysat") is not None
REPO = Path(__file__).resolve().parents[1]


def stalled_worker(*args):
    time.sleep(10)


def selection_assignment(problem, selection):
    assignment = [None]+[False]*problem["nv"]
    for c, j in enumerate(selection):
        assignment[problem["xs"][c][j]] = True
    union = selected_union(problem["family"], selection)
    for g, variable in enumerate(problem["ys"]):
        assignment[variable] = bool(union >> g & 1)
    return assignment


class CoordinateNativeCardTests(unittest.TestCase):
    def setUp(self):
        self.sources = VerifiedSources([strassen_candidate(2), naive_candidate(2)], 2)

    def test_frozen_predecessor_hashes_unchanged(self):
        expected = {
            "mmsearch/coordinate_stencil_sat.py": "b0d28733827aba1ad9b8ecb230f13127cc4c3a273128cb2a10e236181604b588",
            "scripts/campaign_coordinate_stencil_sat.py": "9ec9cd33ae73d3e99a24762144c5fedc7e53007dbbf2892531714cd614f9938e"}
        for path, sha in expected.items():
            self.assertEqual(hashlib.sha256((REPO/path).read_bytes()).hexdigest(), sha)

    def test_only_xy_variables_and_full_native_description(self):
        family = build_family(self.sources)
        problem = build_problem(family, 7)
        count = sum(len(row) for row in family["choices"])+len(family["pairs"])
        self.assertEqual(problem["nv"], count)
        self.assertEqual(problem["metadata"]["auxiliary_variables"], 0)
        self.assertEqual(len(problem["atmosts"]), 5)
        self.assertEqual(problem["atmosts"][-1]["literals"], problem["ys"])
        self.assertEqual(problem["atmosts"][-1]["bound"], 7)
        self.assertEqual(formula_audit(problem)["atmosts"], problem["atmosts"])
        self.assertNotEqual(build_problem(family, 8)["metadata"]["formula_sha256"],
                            problem["metadata"]["formula_sha256"])
        self.assertEqual(estimate_formula(family, 7)["variables"], count)
        with self.assertRaises(FormulaMemoryLimit):
            build_problem(family, 7, max_formula_mb=0.00001)

    def test_native_atmost_mutations_and_onehot_rejected(self):
        family = build_family(self.sources)
        problem = build_problem(family, 7)
        naive = family["source_choices"][1]
        model = selection_assignment(problem, naive)
        # The rank-eight source satisfies every clause and exactly-one choice;
        # only the native total-group bound rejects it.
        self.assertTrue(all(any(model[abs(lit)] == (lit > 0) for lit in clause) for clause in problem["clauses"]))
        with self.assertRaisesRegex(AssertionError, "native at-most: active pair"):
            validate_decode(problem, model)
        loose = build_problem(family, 100)
        model = [None]+[True]*loose["nv"]
        self.assertTrue(all(any(model[abs(lit)] == (lit > 0) for lit in clause) for clause in loose["clauses"]))
        with self.assertRaisesRegex(AssertionError, "native at-most: coordinate"):
            validate_decode(loose, model)
        model = selection_assignment(problem, family["source_choices"][0])
        for variable in problem["xs"][0]:
            model[variable] = False
        with self.assertRaisesRegex(AssertionError, "CNF"):
            validate_decode(problem, model)

    def test_corrupt_models_and_original_union_rank_rejected(self):
        family = build_family(self.sources)
        problem = build_problem(family, 7)
        good = selection_assignment(problem, family["source_choices"][0])
        for bad in (good[:-1], [None]+[int(x) for x in good[1:]]):
            with self.assertRaisesRegex(AssertionError, "incomplete or non-Boolean"):
                validate_decode(problem, bad)
        bad = list(good)
        bad[problem["ys"][0]] = not bad[problem["ys"][0]]
        with self.assertRaises(AssertionError):
            validate_decode(problem, bad)
        # Even a corrupted native count description cannot bypass the separately
        # recomputed actual union bound.
        corrupted = copy.deepcopy(problem)
        corrupted["atmosts"][-1]["bound"] = 100
        with self.assertRaisesRegex(AssertionError, "actual union rank"):
            validate_decode(corrupted, selection_assignment(corrupted, family["source_choices"][1]))

    @unittest.skipUnless(HAVE_PYSAT, "PySAT optional")
    def test_all_axes_native_source_controls_and_restricted_unsat(self):
        for orientation in ORIENTATIONS:
            family = build_family(self.sources, orientation)
            for source, rank in ((0, 7), (1, 8)):
                problem = build_problem(family, rank)
                result = solve(problem, 1, memory_mb=512, assumptions=source_assumptions(problem, source))
                self.assertEqual(result["status"], "SAT")
                self.assertTrue(result["worker_reaped"])
                self.assertTrue(result["verification"]["valid"])
                self.assertEqual(result["verification"]["rank"], rank)
                self.assertEqual(result["verification"]["exact_entries_checked"], 64)
                self.assertEqual(result["verification"]["random_multiplication"]["trials"], 16)
                self.assertEqual(result["candidate"]["metadata"]["orientation"], orientation)
            unsat = solve(build_problem(family, 6), 1, memory_mb=512)
            self.assertEqual(unsat["status"], "UNSAT")
            self.assertIn("finite", unsat["scope"])

    @unittest.skipUnless(HAVE_PYSAT, "PySAT optional")
    def test_exhaustive_tiny_choice_equivalence_to_old_cnf(self):
        from pysat.solvers import Solver
        for orientation in ORIENTATIONS:
            family = build_family(self.sources, orientation)
            for rank in (0, 6, 7, 8, 12):
                native = build_problem(family, rank)
                cnf = build_cnf_problem(family, rank)
                self.assertEqual(native["xs"], cnf["xs"])
                self.assertEqual(native["ys"], cnf["ys"])
                with Solver(name="minicard", bootstrap_with=native["clauses"]) as ns, Solver(
                        name="cadical195", bootstrap_with=cnf["clauses"]) as cs:
                    for constraint in native["atmosts"]:
                        ns.add_atmost(constraint["literals"], constraint["bound"])
                    for selection in itertools.product(*(range(len(row)) for row in family["choices"])):
                        model = selection_assignment(native, selection)
                        fixed = [i if model[i] else -i for i in range(1, len(model))]
                        expected = selected_union(family, selection).bit_count() <= rank
                        self.assertEqual(ns.solve(assumptions=fixed), expected)
                        self.assertEqual(cs.solve(assumptions=fixed), expected)
                        if expected:
                            _, verification, recovered = validate_decode(native, model)
                            self.assertTrue(verification["valid"])
                            self.assertEqual(recovered, list(selection))

    @unittest.skipUnless(HAVE_PYSAT, "PySAT optional")
    def test_reverse_links_optional(self):
        family = build_family(self.sources)
        result = solve(build_problem(family, 7, reverse_links=False), 1, memory_mb=512)
        self.assertEqual(result["status"], "SAT")
        self.assertEqual(result["verification"]["rank"], 7)

    @unittest.skipUnless(HAVE_PYSAT, "PySAT optional")
    def test_missing_backend_is_error_never_unsat(self):
        problem = build_problem(build_family(self.sources), 7)
        with patch.dict("sys.modules", {"pysat.solvers": None}):
            result = solve(problem, 1, memory_mb=512)
        self.assertEqual(result["status"], "ERROR")
        self.assertTrue(result["worker_reaped"])

    def test_timeout_cleanup_reaps_child(self):
        problem = build_problem(build_family(self.sources), 7)
        before = {child.pid for child in mp.active_children()}
        started = time.monotonic()
        with patch("mmsearch.coordinate_native_card._worker", stalled_worker):
            result = solve(problem, 0.03, memory_mb=512)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertTrue(result["worker_reaped"])
        self.assertLess(time.monotonic()-started, 2)
        self.assertEqual({child.pid for child in mp.active_children()}, before)
        with self.assertRaises(ProcessLookupError):
            os.kill(result["worker_pid"], 0)

    @unittest.skipUnless(HAVE_PYSAT, "PySAT optional")
    def test_runner_control_uses_native_93_and_exports_full_problem(self):
        family = build_family(self.sources)
        args = SimpleNamespace(rank=6, max_formula_mb=384, no_reverse_links=False,
            control_seconds=1, memory_mb=512)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = []
            def retain(candidate, verification):
                record, winner = save_record(root, f"record{len(records)}", candidate, verification)
                records.append(record)
                return winner
            result = run_sat(family, args, root, time.monotonic()+3, 0, retain)
            self.assertEqual(result["status"], "UNSAT")
            self.assertEqual(result["control_status"], "SAT")
            control = json.loads((root/"control.problem.json").read_text())
            self.assertEqual(control["atmosts"][-1]["bound"], 93)
            self.assertEqual(control["metadata"]["auxiliary_variables"], 0)
            self.assertTrue((root/"control.model.json").exists())
            self.assertFalse((root/"WINNER.json").exists())

    def test_cli_strict_n5_and_export_reverification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = strassen_candidate(2)
            path = root/"tiny.json"
            path.write_text(json.dumps(candidate))
            with self.assertRaisesRegex(ValueError, "dimension"):
                main(["--input", str(path), "--outdir", str(root/"output")])
            bad = copy.deepcopy(candidate)
            bad["terms"][0]["w"][0] ^= 1
            with self.assertRaisesRegex(AssertionError, "exported candidate"):
                save_record(root, "bad", bad, verify_candidate(candidate))
            self.assertFalse((root/"bad.json").exists())


if __name__ == "__main__":
    unittest.main()
