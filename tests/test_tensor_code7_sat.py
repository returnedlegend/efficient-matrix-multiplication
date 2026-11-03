"""Tiny exact dictionary controls; no n5 solver calls or production preparation."""
import contextlib
import hashlib
import importlib.util
import io
import itertools
import json
from pathlib import Path
import random
import signal
import tempfile
import time
import unittest
from unittest import mock

from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.tensor_code7 import fundamental_kernel, prepare
from mmsearch import tensor_code7_sat as sat

HAVE_BACKEND = bool(importlib.util.find_spec("pycryptosat") and importlib.util.find_spec("pysat"))


def brute(columns, target, bound):
    answer = []
    for state in range(1 << len(columns)):
        observed = 0
        for index, column in enumerate(columns):
            if state >> index & 1:
                observed ^= column
        if observed == target and state.bit_count() <= bound:
            answer.append(state)
    return answer


class ExactEncodingTests(unittest.TestCase):
    def test_sparse_long_bit_encoding_hash_avoids_decimal_json_ceiling(self):
        # Synthetic one-variable code only: no matrix source or solver is read.
        column = 1 << 15000
        problem = sat.build_problem([column], column, 15001, 1)
        self.assertEqual(problem["xors"], [([1], True)])
        self.assertEqual(len(problem["metadata"]["formula_sha256"]), 64)
    def test_even_kernel_parity_tightening_is_scoped_to_the_exact_code(self):
        columns, seed = [1, 1, 2, 2], 0b0101
        cycles, _ = fundamental_kernel(columns)
        report = sat.kernel_diagnostics(columns, seed, cycles, bound=1)
        self.assertTrue(report["all_kernel_cycles_even"])
        self.assertEqual(report["feasible_weight_parity"], 0)
        self.assertEqual(report["parity_adjusted_bound"], 0)
        self.assertEqual(report["global_lower_bound"], 2)
        self.assertEqual(len(report["components"]), 2)
        odd = sat.kernel_diagnostics([1, 2, 3], 0b100, [0b111], bound=2)
        self.assertFalse(odd["all_kernel_cycles_even"])
        self.assertIsNone(odd["feasible_weight_parity"])
        self.assertEqual(odd["parity_adjusted_bound"], 2)

    def test_component_gray_minima_and_lower_bounds_match_bruteforce(self):
        rng = random.Random(731020)
        for _ in range(30):
            columns = [rng.randrange(16) for _ in range(rng.randrange(1, 9))]
            seed = rng.randrange(1 << len(columns))
            cycles, _ = fundamental_kernel(columns)
            target = 0
            for index in sat.bits(seed):
                target ^= columns[index]
            feasible = brute(columns, target, len(columns))
            exact = sat.kernel_diagnostics(columns, seed, cycles, max_component_nullity=20)
            self.assertTrue(exact["exact_dictionary_coset_minimum"])
            self.assertEqual(exact["global_lower_bound"], min(x.bit_count() for x in feasible))
            self.assertIn(int(exact["best_state_hex"], 16), feasible)
            lower = sat.kernel_diagnostics(columns, seed, cycles, max_component_nullity=0, max_combinations=0)
            self.assertLessEqual(lower["global_lower_bound"], min(x.bit_count() for x in feasible))
            self.assertEqual(lower["combinations_enumerated"], 0)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            sat.kernel_diagnostics([1, 1], 1, [])
        with self.assertRaisesRegex(ValueError, "dependent"):
            sat.kernel_diagnostics([1, 1], 1, [3, 3])

    def test_complete_rows_are_literal_transpose_including_zero_equations(self):
        columns, target = [0b10101, 0b00110, 0b11111], 0b11010
        rows = sat.full_rows(columns, target, 7)
        self.assertEqual(len(rows), 7)
        for row in range(7):
            self.assertEqual(rows[row], (sum(((c >> row) & 1) << i for i, c in enumerate(columns)),
                                         (target >> row) & 1))
        self.assertEqual(rows[-1], (0, 0))

    def test_independent_row_reduction_preserves_all_small_solutions(self):
        rng = random.Random(731003)
        for _ in range(30):
            columns = [rng.randrange(1 << 8) for _ in range(rng.randrange(8))]
            target = rng.randrange(1 << 8)
            rows = sat.full_rows(columns, target, 8)
            reduced = sat.reduce_rows(rows)
            for state in range(1 << len(columns)):
                original = all((state & mask).bit_count() % 2 == rhs for mask, rhs in rows)
                small = all((state & mask).bit_count() % 2 == rhs for mask, rhs, _ in reduced)
                self.assertEqual(original, small)
            for mask, rhs, witness in reduced:
                rebuilt = 0
                for index in sat.bits(witness):
                    rebuilt ^= (rows[index][0] << 1) | rows[index][1]
                self.assertEqual(rebuilt, (mask << 1) | rhs)

    def test_strict_inputs_and_original_model_validation(self):
        for columns, target, entries in [([True], 0, 1), ([1], True, 1), ([2], 0, 1), ([-1], 0, 4), ([1], 0, 1.0)]:
            with self.subTest(columns=columns, target=target, entries=entries), self.assertRaises(ValueError):
                sat.full_rows(columns, target, entries)
        problem = sat.build_problem([1, 2, 3], 3, 2, 1)
        self.assertTrue(sat.validate_state(problem, 4))
        for state in [True, -1, 8, 0, 3]:
            with self.assertRaises(ValueError):
                sat.validate_state(problem, state)

    def test_independent_tensor_columns_match_direct_literal_coefficients(self):
        atoms = [(1, 2, 4), (15, 7, 10)]
        columns, target = sat.independent_tensor_data(atoms, 2)
        for atom, column in zip(atoms, columns):
            for a, b, c in itertools.product(range(4), repeat=3):
                expected = (atom[0] >> a & 1) & (atom[1] >> b & 1) & (atom[2] >> c & 1)
                self.assertEqual(column >> ((a*4 + b)*4 + c) & 1, expected)
        for a, b, c in itertools.product(range(4), repeat=3):
            i, j = divmod(a, 2)
            jj, k = divmod(b, 2)
            kk, ii = divmod(c, 2)
            self.assertEqual(target >> ((a*4+b)*4+c) & 1, int(i == ii and j == jj and k == kk))

    def test_default_production_gate_and_cli_read_no_n5_inputs(self):
        with self.assertRaises(PermissionError):
            sat.solve_prepared({"dimension": 5})
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("must not read production")), contextlib.redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(sat.main([]), 0)
        result = json.loads(stream.getvalue())
        self.assertEqual(result["status"], "DISABLED_PENDING_ROOT_QA")
        self.assertFalse(result["production_inputs_read"])
        self.assertFalse(result["solver_called"])

    def test_prepared_raw_pin_is_checked_before_owner_loader_or_source_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"prepared.json"
            path.write_text('{"dimension":5}')
            with self.assertRaisesRegex(ValueError, "prepared raw hash"):
                sat.load_root_pinned_prepared(path, "0"*64, Path(tmp)/"missing-manifest", "0"*64,
                                             tmp, tmp, lambda phase: None)

    def test_changed_owner_code_pin_rejected_before_shared_source_checker(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, manifest = Path(tmp)/"prepared.json", Path(tmp)/"manifest.json"
            path.write_bytes(sat.raw_json({"dimension": 5, "dictionary_size": 1,
                                         "code_sha256": {"mmsearch/tensor_code7.py": "0"*64}}))
            manifest.write_bytes(b"{}")
            with self.assertRaisesRegex(ValueError, "owner code differs"):
                sat.load_root_pinned_prepared(path, hashlib.sha256(path.read_bytes()).hexdigest(),
                    manifest, hashlib.sha256(manifest.read_bytes()).hexdigest(), tmp, tmp, lambda phase: None)

    def test_resource_clamp_never_raises_inherited_soft_or_hard(self):
        with mock.patch.object(sat.resource, "getrlimit", return_value=(256, 512)), mock.patch.object(sat.resource, "setrlimit") as setter:
            self.assertEqual(sat._clamp_limit(sat.resource.RLIMIT_AS, 1024), 256)
        setter.assert_called_once_with(sat.resource.RLIMIT_AS, (256, 512))


@unittest.skipUnless(HAVE_BACKEND, "real pycryptosat and PySAT controls require optional XOR dependencies")
class RealSolverTests(unittest.TestCase):
    def test_planted_schoolbook8_to_known_strassen7_and_exact_freeze(self):
        document = prepare([naive_candidate(2), strassen_candidate(2)])
        result = sat.solve_prepared(document, bound=7, seconds=3)
        self.assertEqual(result["status"], "SAT", result)
        self.assertEqual(result["essential_rank"], 7)
        self.assertTrue(result["worker_reaped"])
        self.assertEqual(result["solver_threads"], 1)
        self.assertEqual(result["cpu_affinity"], [1])
        self.assertGreaterEqual(result["nice"], 10)
        self.assertLessEqual(result["effective_memory_limit_bytes"], 1024*1024**2)
        for report in result["checks"].values():
            self.assertTrue(report["valid"])
            self.assertEqual(report["exact_entries_checked"], 64)
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)/"planted-control"
            sat.freeze_solution(destination, result)
            self.assertTrue((destination/"CONTROL.json").is_file())
            self.assertFalse((destination/"WINNER.json").exists())
            for name, digest in json.loads((destination/"checksums.json").read_bytes()).items():
                self.assertEqual(hashlib.sha256((destination/name).read_bytes()).hexdigest(), digest)
                self.assertFalse((destination/name).stat().st_mode & 0o222)
        result = sat.solve_prepared(document, bound=6, seconds=3)
        self.assertEqual(result["status"], "DICTIONARY_UNSAT", result)
        self.assertIn("no global", result["scope"])

    def test_schoolbook_only_dictionary_cannot_reach7(self):
        result = sat.solve_prepared(prepare([naive_candidate(2)]), bound=7, seconds=3)
        self.assertEqual(result["status"], "DICTIONARY_UNSAT", result)

    def test_random_small_linear_codes_match_bruteforce_full_and_reduced(self):
        rng = random.Random(731092)
        for number in range(24):
            count = rng.randrange(0, 8)
            entries = rng.randrange(1, 10)
            columns = [rng.randrange(1 << entries) for _ in range(count)]
            target, bound = rng.randrange(1 << entries), rng.randrange(count + 1)
            expected = brute(columns, target, bound)
            for compress in [False, True]:
                with self.subTest(number=number, compress=compress):
                    problem = sat.build_problem(columns, target, entries, bound, compress=compress)
                    result = sat.solve_linear(problem, seconds=2)
                    self.assertEqual(result["status"], "SAT" if expected else "DICTIONARY_UNSAT", result)
                    if expected:
                        self.assertIn(int(result["state_hex"], 16), expected)


class LifecycleTests(unittest.TestCase):
    def test_hard_timeout_unknown_kills_ignoring_child_and_reaps(self):
        def stalled(problem, deadline, conflicts, memory_mib, sender):
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            time.sleep(5)
        problem = sat.build_problem([1], 1, 1, 1)
        started = time.monotonic()
        with mock.patch.object(sat, "_worker", stalled):
            result = sat.solve_linear(problem, seconds=.04)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertTrue(result["worker_reaped"])
        self.assertLess(time.monotonic() - started, 1)

    def test_prelaunch_cancel_does_not_spawn_and_is_not_unsat(self):
        problem = sat.build_problem([1], 1, 1, 1)
        with mock.patch.object(sat.mp, "get_context", side_effect=AssertionError("no process")):
            result = sat.solve_linear(problem, seconds=1, cancelled=lambda: True)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertFalse(result["solver_called"])

    def test_invalid_native_sat_witness_rejected_against_original_rows(self):
        def bad(problem, deadline, conflicts, memory_mib, sender):
            sender.send({"status": "SAT", "state_hex": "0x0"})
            sender.close()
        problem = sat.build_problem([1], 1, 1, 1)
        with mock.patch.object(sat, "_worker", bad), self.assertRaisesRegex(ValueError, "original tensor"):
            sat.solve_linear(problem, seconds=1)

    def test_postcall_stop_discards_even_valid_sat_status(self):
        document = prepare([naive_candidate(2), strassen_candidate(2)])
        def guard(phase):
            if phase == "post_native_result":
                raise sat.Stopped("planted postcall stop")
        with mock.patch.object(sat, "solve_linear", return_value={"status": "SAT", "state_hex": document["seed_states_hex"][1]}):
            result = sat.solve_prepared(document, bound=7, seconds=2, guard=guard)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertNotIn("candidate", result)
        self.assertEqual(result["raw_witness"]["state_hex"], document["seed_states_hex"][1])
        self.assertFalse(result["raw_witness"]["within_budget"])

    def test_canonical_owner_stop_preserves_raw_sat_without_publication(self):
        from scripts.tensor_code7 import Stop
        document = prepare([naive_candidate(2), strassen_candidate(2)])
        def guard(phase):
            if phase == "post_native_result":
                raise Stop("canonical planted stop")
        raw = {"status": "SAT", "state_hex": document["seed_states_hex"][1], "worker_reaped": True}
        with mock.patch.object(sat, "solve_linear", return_value=raw):
            result = sat.solve_prepared(document, bound=7, seconds=2, guard=guard)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertTrue(result["worker_reaped"])
        self.assertEqual(result["raw_native_result"]["status"], "SAT")
        self.assertFalse(result["raw_witness"]["within_budget"])
        self.assertNotIn("candidate", result)
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            sat.freeze_solution(Path(tmp)/"no-late-marker", result)

    def test_late_negative_retained_only_as_diagnostic_unknown(self):
        result = sat.unknown_with_raw({"status": "DICTIONARY_UNSAT", "worker_reaped": True}, "late")
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertFalse(result["complete"])
        self.assertEqual(result["raw_native_result"]["status"], "DICTIONARY_UNSAT")
        self.assertNotIn("raw_witness", result)

    def test_false_primary_pass_cannot_bypass_independent_check(self):
        candidate = naive_candidate(2)
        candidate["terms"].pop()
        with mock.patch.object(sat, "verify_candidate", return_value={"valid": True, "exact_entries_checked": 64}), self.assertRaisesRegex(ValueError, "independent"):
            sat.verify_solution(candidate, 7)

    def test_no_marker_before_stop_or_after_postmarker_rollback(self):
        result = dict(status="SAT", candidate=strassen_candidate(2), support_bound=7, state_hex="0x1")
        for stop_phase in ["premarker", "postmarker"]:
            def guard(phase):
                if phase == stop_phase:
                    raise sat.Stopped("planted freeze stop")
            with self.subTest(stop_phase=stop_phase), tempfile.TemporaryDirectory() as tmp:
                destination = Path(tmp)/"control"
                with self.assertRaises(sat.Stopped):
                    sat.freeze_solution(destination, result, guard)
                self.assertFalse(destination.exists())

    def test_corrupt_prepared_rows_fail_before_solver(self):
        document = prepare([naive_candidate(2)])
        document["columns_hex"][0] = "0x0"
        with mock.patch.object(sat, "solve_linear", side_effect=AssertionError("no native query")), self.assertRaises(ValueError):
            sat.solve_prepared(document, bound=7, seconds=2)


if __name__ == "__main__":
    unittest.main()
