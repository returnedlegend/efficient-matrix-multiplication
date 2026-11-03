"""Planted positive and deliberate corruption controls for tensor_code7.

The n2 8->7 example puts known Strassen atoms in the dictionary; it is a
planted solver check, never evidence for a new matrix multiplication result.
"""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.tensor_code7 import (Walk, atom_column, atom_from_term, checked_candidate,
    choose_move, cycle_delta, fundamental_kernel, prepare, rng_restore, second_check,
    target_tensor, validate_kernel, validate_prepared, xor_columns)

REPO = Path(__file__).resolve().parents[1]


class TensorCode7Tests(unittest.TestCase):
    def fixture(self):
        return prepare([naive_candidate(2), strassen_candidate(2)])

    def test_planted_n2_eight_to_known_strassen_seven(self):
        document = self.fixture()
        atoms, columns, seeds, cycles = validate_prepared(document)
        self.assertEqual(document["tensor_entries"], 64)
        self.assertEqual(document["seed_weights"], [8, 7])
        self.assertEqual(document["rank"]+document["nullity"], len(atoms))
        self.assertGreater(document["nullity"], 0)
        # This planted dictionary has exactly one cycle, the known 8 XOR 7.
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0], seeds[0]^seeds[1])
        move, reason = choose_move(seeds[0], cycles, random.Random(7), ceiling=10)
        self.assertEqual(reason, "steepest_negative")
        result = seeds[0]^move
        self.assertEqual(result.bit_count(), 7)
        candidate, report = checked_candidate(atoms, result, 2)
        self.assertTrue(report["standard"]["valid"])
        self.assertTrue(report["scalar"]["valid"])
        self.assertEqual(report["standard"]["exact_entries_checked"], 64)
        self.assertFalse(candidate["metadata"]["novelty_claim"])

    def test_corrupted_full_column_rejected_even_before_linear_search(self):
        document = self.fixture()
        document["columns_hex"][0] = hex(int(document["columns_hex"][0], 16)^1)
        with self.assertRaisesRegex(ValueError, "corrupted column"):
            validate_prepared(document)

    def test_nonzero_nullbasis_control(self):
        document = self.fixture()
        document["kernel_hex"][0] = "0x1"
        with self.assertRaisesRegex(ValueError, "kernel"):
            validate_prepared(document)

    def test_incomplete_nullbasis_is_rejected(self):
        document = self.fixture()
        document["kernel_hex"] = []
        document["nullity"] = 0
        with self.assertRaisesRegex(ValueError, "completeness"):
            validate_prepared(document)

    def test_duplicate_and_dependent_nullbasis_rejected(self):
        with self.assertRaises(ValueError):
            validate_kernel([1, 1], [3, 3])
        with self.assertRaises(ValueError):
            validate_kernel([1, 1, 1], [3, 5, 6])

    def test_prepared_literal_integer_metadata_required(self):
        for key in ("field", "dimension", "rank", "nullity", "dictionary_size", "tensor_entries"):
            document = self.fixture()
            document[key] = float(document[key])
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_prepared(document)

    def test_seed_corruption_fails_closed(self):
        document = self.fixture()
        document["seed_states_hex"][0] = "0x0"
        with self.assertRaisesRegex(ValueError, "nonexact seed"):
            validate_prepared(document)

    def test_literal_binary_only_no_float_bool_or_reduction(self):
        for bad in (True, 1.0, 2, -1):
            candidate = naive_candidate(2)
            candidate["terms"][0]["u"][0] = bad
            with self.assertRaises(ValueError):
                prepare([candidate])
        with self.assertRaises(ValueError):
            atom_column((-1, 1, 1), 2)
        with self.assertRaises(ValueError):
            xor_columns([1], -1)

    def test_cap_never_truncates_a_seed(self):
        with self.assertRaisesRegex(ValueError, "truncate"):
            prepare([naive_candidate(2), strassen_candidate(2)], cap=8)

    def test_reordered_basis_full_and_all_moves_exact_bounded(self):
        document = self.fixture()
        atoms, columns, seeds, _ = validate_prepared(document)
        rng = random.Random(83)
        state = seeds[0]
        for _ in range(20):
            order = list(range(len(columns)))
            rng.shuffle(order)
            cycles, rank = fundamental_kernel(columns, order)
            self.assertEqual(rank, document["rank"])
            move, _ = choose_move(state, cycles, rng, ceiling=8, samples=8)
            if move is not None:
                self.assertEqual(xor_columns(columns, move), 0)
                self.assertEqual(cycle_delta(state, move), (state^move).bit_count()-state.bit_count())
                state ^= move
            self.assertLessEqual(state.bit_count(), 8)
            self.assertEqual(xor_columns(columns, state), target_tensor(2))

    def test_random_small_kernel_rank_nullity_and_exhaustive_membership(self):
        rng = random.Random(92)
        for _ in range(30):
            columns = [rng.randrange(32) for _ in range(7)]
            cycles, rank = fundamental_kernel(columns)
            span = {0}
            for z in cycles:
                span |= {x^z for x in list(span)}
            exact = {x for x in range(1 << len(columns)) if xor_columns(columns, x) == 0}
            self.assertEqual(span, exact)
            self.assertEqual(rank+len(cycles), len(columns))

    def test_rng_and_cursor_roundtrip_replays_identical_moves(self):
        document = self.fixture()
        _atoms, _columns, seeds, cycles = validate_prepared(document)
        rng = random.Random(739)
        walk = Walk(seeds[0], seeds[0], restart=3, step=90, moves=43)
        checkpoint = json.loads(json.dumps({"cursor": walk.to_json(), "rng_state": rng.getstate()}))
        restored = Walk.from_json(checkpoint["cursor"])
        restored_rng = rng_restore(checkpoint["rng_state"])
        self.assertEqual(walk, restored)
        for _ in range(20):
            self.assertEqual(choose_move(walk.state, cycles, rng, 10), choose_move(restored.state, cycles, restored_rng, 10))

    def test_both_checkers_reject_bad_tensor(self):
        candidate = strassen_candidate(2)
        candidate["terms"].pop()
        self.assertFalse(second_check(candidate)["valid"])
        with self.assertRaisesRegex(ValueError, "verification failed"):
            document = self.fixture()
            atoms, _columns, seeds, _cycles = validate_prepared(document)
            checked_candidate(atoms, seeds[1]^1, 2)

    def test_guard_disabled_modes_never_read_missing_production_inputs(self):
        with tempfile.TemporaryDirectory(prefix="tensor_code7-test-") as directory:
            for mode in ("prepare", "search"):
                outdir = Path(directory)/mode
                command = [sys.executable, str(REPO/"scripts/tensor_code7.py"), mode,
                           "--outdir", str(outdir), "--hard-utc", "2030-01-01T00:00:00Z",
                           "--manifest", "/nonexistent/DO_NOT_READ", "--prepared", "/nonexistent/DO_NOT_READ"]
                completed = subprocess.run(command, capture_output=True, text=True, check=True)
                report = json.loads(completed.stdout)
                self.assertEqual(report["status"], "DISABLED_PENDING_ROOT_QA")
                self.assertFalse(report["production_inputs_read"])
                self.assertFalse(report["search_called"])
                self.assertFalse(outdir.exists())

    def test_expired_authorized_preparation_stops_before_input_io(self):
        with tempfile.TemporaryDirectory(prefix="tensor_code7-test-") as directory:
            outdir = Path(directory)/"expired"
            command = [sys.executable, str(REPO/"scripts/tensor_code7.py"), "prepare",
                       "--authorize-preparation", "--outdir", str(outdir), "--hard-utc", "2000-01-01T00:00:00Z",
                       "--manifest", "/nonexistent/DO_NOT_READ", "--approved-root", "/nonexistent/DO_NOT_READ"]
            completed = subprocess.run(command, capture_output=True, text=True, check=True)
            report = json.loads(completed.stdout)
            self.assertEqual(report["status"], "UNKNOWN")
            self.assertTrue(report["stop_reason"].startswith("hard_utc_deadline_postcheck_reserve"))
            self.assertFalse(outdir.exists())


if __name__ == "__main__":
    unittest.main()
