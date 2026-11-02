"""Bounded fixed-rank F2 search using bitset coordinate descent and ALS.

For inconsistent ALS systems, Gaussian elimination fits an independent subset
of equations. That is a proposal, never a least-squares optimum or certificate.
Only its measured full tensor residual decides whether to accept it.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import random
import time

from .verify import verify_candidate, write_standalone_verifier


def _bits(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def _outer(left, right, width):
    result = 0
    for index in _bits(left):
        result |= right << (index * width)
    return result


def _target(n, axis):
    width = n*n
    result = [0] * width
    others = [a for a in range(3) if a != axis]
    for i in range(n):
        for j in range(n):
            for k in range(n):
                coords = (i*n+j, j*n+k, k*n+i)
                result[coords[axis]] ^= 1 << (coords[others[0]]*width + coords[others[1]])
    return result


def _residual(factors, target, width, axis):
    result = target.copy()
    others = [a for a in range(3) if a != axis]
    for term in factors:
        pair = _outer(term[others[0]], term[others[1]], width)
        for index in _bits(term[axis]):
            result[index] ^= pair
    return result


def _weight(factors, targets, width):
    return sum(row.bit_count() for row in _residual(factors, targets[0], width, 0))


def _coordinate_sweep(factors, target, width, axis, rng):
    """Exactly minimize each binary coefficient with all others held fixed."""
    residual = _residual(factors, target, width, axis)
    others = [a for a in range(3) if a != axis]
    order = list(range(len(factors)))
    rng.shuffle(order)
    flips = 0
    for term_index in order:
        term = factors[term_index]
        pair = _outer(term[others[0]], term[others[1]], width)
        size = pair.bit_count()
        if not size:
            continue
        for index in range(width):
            if 2 * (residual[index] & pair).bit_count() > size:
                term[axis] ^= 1 << index
                residual[index] ^= pair
                flips += 1
    return sum(row.bit_count() for row in residual), flips


def solve_gf2(rows, rhs, variables, rng=None):
    """Solve independent equations, with simultaneous bit-packed RHS columns.

    Returns (solution masks per variable, inconsistent reduced row count).
    When inconsistent, the returned solution only fits retained independent
    rows. It is not a minimum Hamming residual solution.
    """
    basis = {}
    order = list(range(len(rows)))
    if rng is not None:
        rng.shuffle(order)
    inconsistent = 0
    for index in order:
        left, right = rows[index], rhs[index]
        while left:
            pivot = (left & -left).bit_length() - 1
            if pivot not in basis:
                basis[pivot] = (left, right)
                break
            old_left, old_right = basis[pivot]
            left ^= old_left
            right ^= old_right
        if not left and right:
            inconsistent += 1
    solution = [0] * variables
    for pivot in sorted(basis, reverse=True):
        left, right = basis[pivot]
        for index in _bits(left ^ (1 << pivot)):
            right ^= solution[index]
        solution[pivot] = right
    return solution, inconsistent


def _als_proposal(factors, target, width, axis, rng):
    others = [a for a in range(3) if a != axis]
    rows = [0] * (width*width)
    for index, term in enumerate(factors):
        pair = _outer(term[others[0]], term[others[1]], width)
        for coordinate in _bits(pair):
            rows[coordinate] |= 1 << index
    residual = _residual(factors, target, width, axis)
    rhs = [0] * (width*width)
    for coordinate, row in enumerate(residual):
        for pair_coordinate in _bits(row):
            rhs[pair_coordinate] |= 1 << coordinate
    delta, inconsistent = solve_gf2(rows, rhs, len(factors), rng)
    proposal = [term.copy() for term in factors]
    for term, change in zip(proposal, delta):
        term[axis] ^= change
    return proposal, inconsistent


def _decode(candidate):
    return [[sum((value % 2) << i for i, value in enumerate(term[axis]))
             for axis in ("u", "v", "w")] for term in candidate["terms"]]


def _encode(factors, n, metadata):
    return {"dimension": n, "field": 2,
            "terms": [{axis: [(term[a] >> i) & 1 for i in range(n*n)]
                       for a, axis in enumerate(("u", "v", "w"))} for term in factors],
            "metadata": metadata}


def _emit(factors, n, metadata, output):
    candidate = _encode(factors, n, dict(metadata, status="unverified"))
    report = verify_candidate(candidate)
    if report["mismatch_count"] != metadata["residual_weight"]:
        raise AssertionError("search residual disagrees with independent verifier")
    candidate["metadata"]["status"] = "verified" if report["valid"] else "failed_exact_verification"
    if output is not None:
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(candidate, indent=2) + "\n")
        destination.with_suffix(".verification.json").write_text(json.dumps(report, indent=2) + "\n")
        write_standalone_verifier(destination.with_suffix(".verify.py"))
    return candidate, report


def search(candidate, rank=94, seconds=60, seed=0, output=None, progress=True):
    """Search at fixed term count and return best candidate plus exact report.

    Runtime is bounded by ``seconds`` plus at most one sweep/verification.
    Starting terms are dropped by residual weight, then randomized at restarts.
    There is no cyclic-orbit constraint and no integer-lift claim.
    """
    if candidate.get("field") != 2:
        raise ValueError("search requires field=2")
    checked = verify_candidate(candidate, random_trials=0)
    if checked.get("rank") is None:
        raise ValueError("invalid input certificate schema: " + str(checked["errors"]))
    if type(rank) is not int or not 1 <= rank <= len(candidate["terms"]):
        raise ValueError("rank must be positive and no larger than the input term count")
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("seconds must be finite and nonnegative")
    n = candidate["dimension"]
    width = n*n
    targets = [_target(n, axis) for axis in range(3)]
    source = _decode(candidate)
    rng = random.Random(seed)
    start = time.monotonic()
    deadline = start + seconds
    iteration = restarts = als_proposals = als_accepted = inconsistent_rows = 0
    # Favor dropping sparse rank-one tensors in the initial state.
    order = sorted(range(len(source)), key=lambda i: source[i][0].bit_count()
                   * source[i][1].bit_count() * source[i][2].bit_count())
    removed = set(order[:len(source)-rank])
    current = [term.copy() for i, term in enumerate(source) if i not in removed]
    best = copy.deepcopy(current)
    best_weight = current_weight = _weight(best, targets, width)

    def metadata():
        return {"method": "fixed-rank-f2-coordinate-and-independent-subsystem-als",
                "rank": rank, "seed": seed, "residual_weight": best_weight,
                "iterations": iteration, "restarts": restarts,
                "als_proposals": als_proposals, "als_accepted": als_accepted,
                "inconsistent_reduced_rows": inconsistent_rows,
                "elapsed_seconds": time.monotonic()-start,
                "cyclic_constraint": False,
                "third_factor": "trace: w[k*n+i] contributes to output[i][k]"}

    def announce():
        if progress:
            print(json.dumps({"rank": rank, "residual_weight": best_weight,
                              "iteration": iteration, "restarts": restarts}), flush=True)

    announce()
    stale = 0
    while best_weight and time.monotonic() < deadline:
        iteration += 1
        before = current_weight
        for axis in (2, 1, 0):
            if time.monotonic() >= deadline:
                break
            current_weight, _ = _coordinate_sweep(current, targets[axis], width, axis, rng)
            proposal, inconsistent = _als_proposal(current, targets[axis], width, axis, rng)
            inconsistent_rows += inconsistent
            als_proposals += 1
            proposal_weight = _weight(proposal, targets, width)
            if proposal_weight < current_weight:
                current, current_weight = proposal, proposal_weight
                als_accepted += 1
            if current_weight < best_weight:
                best, best_weight = copy.deepcopy(current), current_weight
                announce()
                _emit(best, n, metadata(), output)
            if not best_weight:
                break
        stale = stale+1 if current_weight >= before else 0
        if stale >= 2 and best_weight:
            restarts += 1
            stale = 0
            if restarts % 3 == 0:
                kept = rng.sample(range(len(source)), rank)
                current = [source[i].copy() for i in kept]
            else:
                current = copy.deepcopy(best)
                for _ in range(1 + restarts % 8):
                    current[rng.randrange(rank)][rng.randrange(3)] ^= 1 << rng.randrange(width)
            current_weight = _weight(current, targets, width)
    announce()
    return _emit(best, n, metadata(), output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="artifacts/alphatensor_5x5_f2_rank96.json")
    parser.add_argument("--output", default="artifacts/als_rank94.json")
    parser.add_argument("--rank", type=int, default=94)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    candidate = json.loads(Path(args.input).read_text())
    _, report = search(candidate, args.rank, args.seconds, args.seed, args.output)
    print(json.dumps({"valid": report["valid"], "rank": report["rank"],
                      "residual_weight": report["mismatch_count"], "output": args.output}), flush=True)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
