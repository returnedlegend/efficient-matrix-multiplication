import copy
import itertools
from pathlib import Path
import random
import tempfile
import unittest

from mmsearch.free_factor_sat import build_system, satisfies
from mmsearch.kernel_coset_seeds import (apply_shift_checked, build_span, circuit_masks,
    freeze_first_record, fundamental_kernel, kernel_zero, nonmembership_proof,
    pair_column, reduce_span, score_shift, validate_span, verify_nonmembership)
from mmsearch.recombine import canonical_terms
from mmsearch.tensor import naive_candidate, strassen_candidate
from mmsearch.verify import verify_candidate


class KernelCosetSeedTests(unittest.TestCase):
    def system(self):
        source = naive_candidate(2)
        dictionary = sorted(set(canonical_terms(source)) | set(canonical_terms(strassen_candidate(2))))
        return build_system(dictionary, 2, "wu", source)

    def test_full_kernel_and_strict_smaller_circuit_span(self):
        system = self.system()
        columns = [pair_column(p, 4) for p in system["pairs"]]
        kernel = fundamental_kernel(system)
        self.assertEqual(len(kernel), system["reduced"]["nullity"])
        self.assertTrue(all(kernel_zero(columns, n) for _, n in kernel))
        masks = [kernel[0][1], kernel[1][1], kernel[0][1] ^ kernel[1][1]]
        span = build_span(masks)
        self.assertEqual(len(span), 2)
        self.assertTrue(validate_span(masks, span))
        known = {0, masks[0], masks[1], masks[0] ^ masks[1]}
        for coefficients in range(1 << len(kernel)):
            n = 0
            for i, (_, vector) in enumerate(kernel):
                if coefficients >> i & 1:
                    n ^= vector
            self.assertEqual(reduce_span(n, span)[0] == 0, n in known)
        support = [i for i in range(len(columns)) if kernel[0][1] >> i & 1]
        self.assertEqual(circuit_masks(columns, [{"support":support}]), [kernel[0][1]])

    def test_exact_delta_including_zero_and_frequency_ties(self):
        rng = random.Random(11)
        for length in range(1, 8):
            for _ in range(20):
                source = [rng.randrange(8) for _ in range(length)]
                n = rng.randrange(1, 1 << length)
                score = score_shift(source, n, 3)
                moved = [value ^ score["d"] if n >> i & 1 else value for i, value in enumerate(source)]
                self.assertEqual(sum(bool(v) for v in moved), score["new_rank"])
                deltas = []
                for d in range(1, 8):
                    updated = [v ^ d if n >> i & 1 else v for i, v in enumerate(source)]
                    deltas.append(sum(bool(v) for v in updated)-sum(bool(v) for v in source))
                self.assertEqual(score["delta"], min(deltas))
        self.assertEqual(score_shift([0, 0], 3, 3)["delta"], 2)
        self.assertEqual(score_shift([1, 1, 0], 7, 3)["delta"], -1)

    def test_latent_n2_coset_exact_full_tensor_and_nonmembership_proof(self):
        system = self.system()
        columns = [pair_column(p, 4) for p in system["pairs"]]
        kernel = fundamental_kernel(system)
        masks = [kernel[0][1]]
        span = build_span(masks)
        n = next(n for _, n in kernel if reduce_span(n, span)[0])
        proof = nonmembership_proof(columns, masks, span, n)
        self.assertTrue(verify_nonmembership(columns, masks, span, proof))
        score = score_shift(system["baseline_vectors"], n, 4)
        candidate, shifted, report = apply_shift_checked(system, proof, score)
        self.assertTrue(satisfies(system, shifted))
        self.assertTrue(report["valid"])
        self.assertEqual(report["exact_entries_checked"], 64)
        self.assertEqual(len(candidate["terms"]), score["new_rank"])
        self.assertTrue(verify_candidate(candidate, random_trials=16)["valid"])
        self.assertNotEqual(shifted, system["baseline_vectors"])

    def test_bad_kernel_nonmembership_span_and_delta_rejected(self):
        system = self.system()
        columns = [pair_column(p, 4) for p in system["pairs"]]
        kernel = fundamental_kernel(system)
        masks = [kernel[0][1]]
        span = build_span(masks)
        with self.assertRaises(ValueError):
            nonmembership_proof(columns, masks, span, 1)
        with self.assertRaises(ValueError):
            nonmembership_proof(columns, masks, span, masks[0])
        n = next(n for _, n in kernel if reduce_span(n, span)[0])
        proof = nonmembership_proof(columns, masks, span, n)
        for key in ("remainder", "basis_xor", "circuit_xor", "column_xor"):
            bad = copy.deepcopy(proof)
            bad[key] ^= 1
            with self.assertRaises(ValueError):
                verify_nonmembership(columns, masks, span, bad)
        bad_span = copy.deepcopy(span)
        bad_span[0]["circuit_xor"] = 0
        with self.assertRaises(ValueError):
            validate_span(masks, bad_span)
        score = score_shift(system["baseline_vectors"], n, 4)
        score["delta"] += 1
        with self.assertRaises(ValueError):
            apply_shift_checked(system, proof, score)

    def test_first_record_helper_exclusive_generic_n2_only(self):
        # Generic n2 threshold8 is a freezer test, never a research record.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = naive_candidate(2)
            checksums = freeze_first_record(root, first, dimension=2, maximum_rank=8)
            raw = (root/"WINNER.json").read_bytes()
            with self.assertRaises(FileExistsError):
                freeze_first_record(root, strassen_candidate(2), dimension=2, maximum_rank=8)
            self.assertEqual((root/"WINNER.json").read_bytes(), raw)
            self.assertEqual((root/"WINNER.sha256").read_text().split()[0], checksums["WINNER.json"])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                freeze_first_record(Path(tmp), naive_candidate(2))


if __name__ == "__main__":
    unittest.main()
