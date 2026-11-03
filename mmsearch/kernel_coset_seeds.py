"""Exact solution shifts outside one measured short-circuit kernel span.

These are diversification seeds, not SAT/UNSAT conclusions or statements
about equivalence of full multiplication algorithms.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

from .free_factor_sat import bits, decode_vectors, satisfies
from .verify import verify_candidate


def pair_column(pair, width):
    result = 0
    for index in bits(pair[0]):
        result |= pair[1] << (index*width)
    return result


def kernel_zero(columns, vector):
    if type(vector) is not int or vector <= 0 or vector >> len(columns):
        raise ValueError("nonzero in-range kernel support required")
    value = 0
    for index in bits(vector):
        value ^= columns[index]
    return value == 0


def circuit_masks(columns, circuits):
    masks = []
    for circuit in circuits:
        support = circuit["support"]
        if (not isinstance(support, list) or not support or len(set(support)) != len(support) or
                any(type(i) is not int or not 0 <= i < len(columns) for i in support)):
            raise ValueError("invalid circuit support")
        mask = sum(1 << i for i in support)
        if not kernel_zero(columns, mask):
            raise ValueError("circuit column XOR is nonzero")
        masks.append(mask)
    return masks


def reduce_span(vector, basis):
    remainder, selected = vector, 0
    for index, row in enumerate(basis):
        if remainder >> row["pivot"] & 1:
            remainder ^= row["vector"]
            selected ^= 1 << index
    return remainder, selected


def build_span(masks):
    rows = {}
    for index, original in enumerate(masks):
        vector, proof = original, 1 << index
        while vector:
            pivot = vector.bit_length()-1
            if pivot not in rows:
                rows[pivot] = dict(pivot=pivot, vector=vector, circuit_xor=proof)
                break
            vector ^= rows[pivot]["vector"]
            proof ^= rows[pivot]["circuit_xor"]
    basis = [rows[pivot] for pivot in sorted(rows, reverse=True)]
    validate_span(masks, basis)
    return basis


def validate_span(masks, basis):
    pivots = [row["pivot"] for row in basis]
    if pivots != sorted(set(pivots), reverse=True):
        raise ValueError("span basis pivots are not unique descending indices")
    for row in basis:
        if row["vector"] <= 0 or row["vector"].bit_length()-1 != row["pivot"]:
            raise ValueError("span basis pivot is invalid")
        proof = row["circuit_xor"]
        if type(proof) is not int or proof <= 0 or proof >> len(masks):
            raise ValueError("invalid span circuit witness")
        actual = 0
        for index in bits(proof):
            actual ^= masks[index]
        if actual != row["vector"]:
            raise ValueError("span basis witness does not reproduce row")
    if any(reduce_span(mask, basis)[0] for mask in masks):
        raise ValueError("basis does not span all supplied circuits")
    return True


def fundamental_kernel(system):
    count = len(system["pairs"])
    rows = system["reduced"]["rows"]
    pivots = [(row[0] & -row[0]).bit_length()-1 for row in rows]
    if (system["reduced"]["contradictions"] or len(set(pivots)) != len(rows) or
            any(p < 0 for p in pivots)):
        raise ValueError("consistent RREF with distinct pivots required")
    for i, (coefficient, _rhs, _proof) in enumerate(rows):
        if any(coefficient >> pivot & 1 for j, pivot in enumerate(pivots) if j != i):
            raise ValueError("coefficient rows are not RREF")
    result = []
    for free in range(count):
        if free in pivots:
            continue
        vector = 1 << free
        for pivot, row in zip(pivots, rows):
            if row[0] >> free & 1:
                vector |= 1 << pivot
        if any((row & vector).bit_count() % 2 for row in system["coefficients"]):
            raise AssertionError("fundamental vector fails original kernel equations")
        result.append((free, vector))
    if len(result) != system["reduced"]["nullity"]:
        raise AssertionError("fundamental kernel dimension mismatch")
    return result


def nonmembership_proof(columns, masks, basis, vector):
    if not kernel_zero(columns, vector):
        raise ValueError("proposed shift is not in the full kernel")
    remainder, selected = reduce_span(vector, basis)
    if not remainder:
        raise ValueError("proposed shift lies in the old short-circuit span")
    proof = 0
    for index in bits(selected):
        proof ^= basis[index]["circuit_xor"]
    result = dict(vector=vector, remainder=remainder, basis_xor=selected, circuit_xor=proof,
                  column_xor=0, scope="nonmembership relative only to this exact old circuit span")
    verify_nonmembership(columns, masks, basis, result)
    return result


def verify_nonmembership(columns, masks, basis, proof):
    vector = proof["vector"]
    if not kernel_zero(columns, vector):
        raise ValueError("shift vector is not a kernel vector")
    remainder, selected = reduce_span(vector, basis)
    if not remainder or remainder != proof["remainder"] or selected != proof["basis_xor"]:
        raise ValueError("nonmembership remainder or reduction witness is invalid")
    circuit_proof = 0
    for index in bits(selected):
        circuit_proof ^= basis[index]["circuit_xor"]
    if circuit_proof != proof["circuit_xor"] or circuit_proof >> len(masks) or proof["column_xor"] != 0:
        raise ValueError("nonmembership circuit XOR witness is invalid")
    difference = 0
    for index in bits(circuit_proof):
        difference ^= masks[index]
    if difference != vector ^ remainder:
        raise ValueError("original vector/remainder difference does not have the claimed circuit witness")
    return True


def score_shift(vectors, vector, width):
    if type(vector) is not int or vector <= 0 or vector >> len(vectors):
        raise ValueError("invalid shift support")
    support = list(bits(vector))
    frequencies = Counter(vectors[i] for i in support if vectors[i])
    maximum = max(frequencies.values(), default=0)
    d = min((value for value, frequency in frequencies.items() if frequency == maximum), default=1)
    if not 0 < d < 1 << width:
        raise ValueError("invalid nonzero shift vector")
    zeros = sum(vectors[i] == 0 for i in support)
    delta = zeros-maximum
    return dict(d=d, delta=delta, new_rank=sum(bool(v) for v in vectors)+delta,
        support_size=len(support), active_support=len(support)-zeros,
        baseline_zeros=zeros, maximum_nonzero_frequency=maximum,
        shift_selection="most frequent existing nonzero free vector; mask1 only if support has no active vector")


def pw_rows(system, vectors):
    result = []
    for coefficient in system["coefficients"]:
        value = 0
        for index in bits(coefficient):
            value ^= vectors[index]
        result.append(value)
    return result


def apply_shift_checked(system, proof, score):
    source = system["baseline_vectors"]
    width = system["metadata"]["width"]
    expected = score_shift(source, proof["vector"], width)
    if score != expected:
        raise ValueError("rank-delta or shift-selection score is incorrect")
    columns = [pair_column(pair, width) for pair in system["pairs"]]
    if not kernel_zero(columns, proof["vector"]):
        raise ValueError("shift is not in the exact kernel")
    vectors = list(source)
    for index in bits(proof["vector"]):
        vectors[index] ^= score["d"]
    if sum(bool(v) for v in vectors) != score["new_rank"]:
        raise AssertionError("exact active-count delta formula failed")
    if not satisfies(system, vectors):
        raise AssertionError("shift failed original PW=Y equations")
    candidate = decode_vectors(system, vectors, dict(method="exact-F2-kernel-coset-diversification-seed",
        field_claim="F2 only; no integer lift or full-algorithm inequivalence claim"))
    report = verify_candidate(candidate, random_trials=16)
    if not report["valid"] or report["rank"] != score["new_rank"]:
        raise AssertionError("seed failed independent full tensor verification")
    return candidate, vectors, report


def exclusive(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
    path.chmod(0o444)


def freeze_first_record(root, candidate, *, dimension=5, maximum_rank=92):
    root = Path(root)
    if (root/"WINNER.json").exists():
        raise FileExistsError("first record certificate is already frozen")
    report = verify_candidate(candidate, random_trials=16)
    if (not report["valid"] or type(candidate["field"]) is not int or candidate["field"] != 2 or
            candidate["dimension"] != dimension or report["rank"] > maximum_rank):
        raise ValueError("candidate does not meet the independently verified record threshold")
    payloads = {"WINNER.json":(json.dumps(candidate, sort_keys=True, indent=2)+"\n").encode(),
        "WINNER.verification.json":(json.dumps(report, sort_keys=True, indent=2)+"\n").encode(),
        "WINNER.verify.py":Path(__file__).with_name("verify.py").read_bytes()}
    checksums = {name:hashlib.sha256(raw).hexdigest() for name, raw in payloads.items()}
    payloads["WINNER.sha256"] = (checksums["WINNER.json"]+"  WINNER.json\n").encode()
    for name, raw in payloads.items():
        exclusive(root/name, raw)
    return checksums
