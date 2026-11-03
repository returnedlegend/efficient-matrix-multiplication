"""Separate larger-mode CP<=d+2 protocol prototype; no production query authorization.

Enumerate rank-two differences inside S, not the ambient rank-one variety.
All caps and late guard exits are UNKNOWN. Existing decoders remain untouched.
"""
from datetime import datetime, timezone
import math
import time

from .backbone7 import DEADLINE, HARD_DEADLINE, _matrix
from .backbone7 import solve_pair_image as solve_backbone
from .compact_sat import BinaryBasis
from .compact_eight43 import bits, exact_coordinates
from .compact_coset43 import _insert, digest, expand_products, mode_slices, pair_column
from .compact_rank2_edges43 import (matrix_rank_at_most_two, rank_two_splits,
                                   rankone_factors)
from .compact_rank2_edges43 import solve_pair_image as solve_one

MAX_MODE_RANK = 12


class _Guard:
    def __init__(self, cancelled, timeout_seconds, deadline_utc):
        if (timeout_seconds is not None and
                (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                 or timeout_seconds < 0)):
            raise ValueError("finite nonnegative timeout required")
        stamp = datetime.fromisoformat(deadline_utc.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("deadline requires timezone")
        self.started = time.monotonic()
        self.timeout = timeout_seconds
        self.deadline = min(stamp.timestamp(), HARD_DEADLINE)
        self.cancelled = cancelled

    def reason(self):
        if time.time() >= self.deadline:
            return "deadline"
        if self.timeout is not None and time.monotonic() - self.started >= self.timeout:
            return "timeout"
        if self.cancelled and self.cancelled():
            return "cancelled"
        return None

    def stopped(self):
        return self.reason() is not None

    def remaining(self):
        return None if self.timeout is None else max(0, self.timeout - (time.monotonic() - self.started))


def solve_pair_image(targets, rows, columns, budget=None, max_vectors=8191,
                     max_extensions=24573, max_mode_rank=MAX_MODE_RANK,
                     cancelled=None, timeout_seconds=None, deadline_utc=DEADLINE):
    """Exactly decide budgets<=d+2, within the explicit enumeration limits.

    A returned SAT includes original rank-one points and coordinates for every
    supplied raw slice. LOCAL_UNSAT requires all relevant extensions completed.
    The extension cursor is diagnostic only; it does not authorize skipping work.
    """
    targets = list(targets)
    _matrix(0, rows, columns)
    for value in targets:
        _matrix(value, rows, columns)
    if budget is not None and (type(budget) is not int or budget < 0):
        raise ValueError("nonnegative integer budget required")
    if any(type(v) is not int or v < 0 for v in (max_vectors, max_extensions, max_mode_rank)):
        raise ValueError("nonnegative integer search caps required")
    if max_mode_rank > MAX_MODE_RANK:
        raise ValueError("larger-mode protocol cap cannot exceed12")
    guard = _Guard(cancelled, timeout_seconds, deadline_utc)
    identity = dict(algorithm="surplus_two_large7", target_sha256=digest(targets),
                    raw_target_count=len(targets), left_width=rows, right_width=columns,
                    budget=budget, effective_deadline_utc=datetime.fromtimestamp(
                        guard.deadline, timezone.utc).isoformat())

    def finish(status, case, **kw):
        if status != "UNKNOWN":
            reason = guard.reason()
            if reason:
                status, case = "UNKNOWN", reason
        return dict(identity, status=status, complete=status != "UNKNOWN", case=case, **kw)

    reason = guard.reason()
    if reason:
        return finish("UNKNOWN", reason)
    space = BinaryBasis(targets)
    d = len(space.vectors)
    budget = d + 2 if budget is None else budget
    identity.update(target_rank=d, space_basis=list(space.vectors), budget=budget)
    if budget < d:
        return finish("LOCAL_UNSAT", "dimension_bound")
    if budget > d + 2:
        return finish("UNKNOWN", "unsupported_surplus_gt_two")
    if d > max_mode_rank:
        return finish("UNKNOWN", "mode_rank_cap")
    count = (1 << d) - 1
    if count > max_vectors:
        return finish("UNKNOWN", "subspace_enumeration_cap", span_vectors=count)

    def emit(pool, case, **stats):
        selected, pivots = [], {}
        for original in pool:
            reason = guard.reason()
            if reason:
                return finish("UNKNOWN", reason, **stats)
            point = dict(original)
            if (not point["left"] or not point["right"] or
                    pair_column(point["left"], point["right"], columns) != point["column"] or
                    point["left"] >> rows or point["right"] >> columns):
                raise AssertionError("child supplied invalid original rank-one point")
            if _insert(pivots, point["column"]):
                selected.append(point)
        basis = [p["column"] for p in selected]
        coordinates = []
        for target in targets:
            reason = guard.reason()
            if reason:
                return finish("UNKNOWN", reason, **stats)
            mask = exact_coordinates(target, basis)
            rebuilt = 0
            for j in bits(mask):
                rebuilt ^= basis[j]
            if rebuilt != target:
                raise AssertionError("original raw slice reconstruction failed")
            coordinates.append(mask)
        if len(selected) > budget:
            raise AssertionError("lifted rank-one support exceeds requested budget")
        return finish("SAT", case, support=selected, factor_point_pool=[dict(p) for p in pool],
                      target_coordinates=coordinates, **stats)

    prior = solve_one(targets, rows, columns, min(budget, d + 1),
                      max_vectors=max_vectors, cancelled=guard.stopped)
    reason = guard.reason()
    if reason:
        return finish("UNKNOWN", reason)
    if prior["status"] == "SAT":
        return emit(prior["support"], "surplus_one_cover", prior_result_sha256=digest(prior))
    if prior["status"] == "UNKNOWN" or not prior.get("complete"):
        return finish("UNKNOWN", "surplus_one_incomplete", prior_case=prior.get("case"))
    if budget <= d + 1:
        return finish("LOCAL_UNSAT", "surplus_one_complete_negative", prior_result_sha256=digest(prior))

    inside, inside_pivots, rank_two = [], {}, []
    for coordinates in range(1, count + 1):
        reason = guard.reason()
        if reason:
            return finish("UNKNOWN", reason, enumerated_vectors=coordinates - 1)
        value = space.expand(coordinates)
        rank, _ = matrix_rank_at_most_two(value, rows, columns)
        if rank == 1 and _insert(inside_pivots, coordinates):
            left, right = rankone_factors(value, rows, columns)
            inside.append(dict(column=value, left=left, right=right, span_coordinates=coordinates))
        elif rank == 2:
            rank_two.append((coordinates, value))
    b = len(inside)
    stats = dict(span_vectors=count, enumerated_vectors=count, inside_rank=b,
                 backbone_codimension=d - b, prior_result_sha256=digest(prior))
    if b >= d:
        raise AssertionError("surplus-one negative contradicted full rank-one backbone")
    if b == d - 1:
        child = solve_backbone(targets, rows, columns, budget, max_vectors=max_vectors,
                               cancelled=guard.stopped, timeout_seconds=guard.remaining(),
                               deadline_utc=deadline_utc)
        reason = guard.reason()
        if reason:
            return finish("UNKNOWN", reason, **stats)
        if child["status"] == "SAT":
            return emit(child["support"], "exact_corank_one_backbone",
                        exact_cp_rank=child["exact_cp_rank"], child_result_sha256=digest(child), **stats)
        if child["status"] == "LOCAL_UNSAT" and child.get("complete"):
            return finish("LOCAL_UNSAT", "exact_corank_one_negative",
                          exact_cp_rank=child.get("exact_cp_rank"), child_result_sha256=digest(child), **stats)
        return finish("UNKNOWN", "backbone_incomplete", child_case=child.get("case"), **stats)

    backbone = BinaryBasis([p["span_coordinates"] for p in inside])
    candidates = {}
    splits_tested = 0
    relevant_differences = 0
    for coordinates, value in rank_two:
        reason = guard.reason()
        if reason:
            return finish("UNKNOWN", reason, **stats)
        residue = coordinates ^ backbone.expand(backbone.coordinates(coordinates))
        if not residue:
            continue
        relevant_differences += 1
        for split in rank_two_splits(value, rows, columns):
            splits_tested += 1
            coset = split["p"] ^ space.expand(space.coordinates(split["p"]))
            if not coset:
                raise AssertionError("outside-backbone split endpoints unexpectedly inside S")
            if coset != split["q"] ^ space.expand(space.coordinates(split["q"])):
                raise AssertionError("rank-two split endpoints differ modulo S")
            candidates.setdefault(coset, dict(split, coset=coset, difference=value,
                                               difference_coordinates=coordinates))
    ordered = sorted(candidates)
    stats.update(rank_two_matrices=len(rank_two), relevant_rank_two_differences=relevant_differences,
                 unordered_rank_two_splits=splits_tested, total_extensions=len(ordered),
                 extension_cosets=ordered, tested_extensions=[])
    for cursor, coset in enumerate(ordered):
        reason = guard.reason()
        if reason:
            return finish("UNKNOWN", reason, extension_cursor=cursor, **stats)
        if cursor >= max_extensions:
            return finish("UNKNOWN", "extension_cap", extension_cursor=cursor, **stats)
        seed = candidates[coset]
        extended = BinaryBasis(list(space.vectors) + [seed["p"]])
        if len(extended.vectors) != d + 1:
            raise AssertionError("seed did not produce a one-dimensional extension")
        child = solve_one(extended.vectors, rows, columns, d + 2,
                          max_vectors=max_vectors, cancelled=guard.stopped)
        reason = guard.reason()
        if reason:
            return finish("UNKNOWN", reason, extension_cursor=cursor, **stats)
        if child["status"] == "SAT":
            return emit(child["support"], "repeated_coset_pair_extension",
                        extension_cursor=cursor, extension_certificate=dict(seed),
                        child_result_sha256=digest(child), **stats)
        if child["status"] != "LOCAL_UNSAT" or not child.get("complete"):
            return finish("UNKNOWN", "extension_child_incomplete", extension_cursor=cursor,
                          child_case=child.get("case"), **stats)
        stats["tested_extensions"].append(dict(coset=coset, status="LOCAL_UNSAT",
                                               child_result_sha256=digest(child)))
    return finish("LOCAL_UNSAT", "all_repeated_pair_extensions_negative",
                  extension_cursor=len(ordered), **stats)


def solve_core(core, shape, target=None, axis=None, **kwargs):
    """Decode and verify every coefficient of the original uncompressed core."""
    guard = _Guard(kwargs.get("cancelled"), kwargs.get("timeout_seconds"),
                   kwargs.get("deadline_utc", DEADLINE))
    if (len(shape) != 3 or any(type(v) is not int or v < 0 for v in shape)
            or len(core) != math.prod(shape)
            or any(type(v) is not int or v not in (0, 1) for v in core)):
        raise ValueError("invalid binary tensor core")
    if axis is None:
        ranks = [len(BinaryBasis(mode_slices(core, shape, j)[0]).vectors) for j in range(3)]
        axis = max(range(3), key=lambda j: (ranks[j], shape[j], -j))
    if type(axis) is not int or axis not in (0, 1, 2):
        raise ValueError("invalid free axis")
    slices, other = mode_slices(core, shape, axis)
    kwargs["timeout_seconds"] = guard.remaining()
    result = solve_pair_image(slices, shape[other[0]], shape[other[1]], target, **kwargs)
    result.update(shape=list(shape), axis=axis, core_sha256=digest(dict(shape=list(shape), core=core)))
    def finish():
        if result["status"] != "UNKNOWN":
            reason = guard.reason()
            if reason:
                result.update(status="UNKNOWN", complete=False, case=reason)
        return result
    if finish()["status"] != "SAT":
        return result
    free = [0] * len(result["support"])
    for i, mask in enumerate(result["target_coordinates"]):
        for j in bits(mask):
            free[j] |= 1 << i
    products = []
    for j, entry in enumerate(result["support"]):
        term = [0, 0, 0]
        term[axis], term[other[0]], term[other[1]] = free[j], entry["left"], entry["right"]
        if all(term):
            products.append(term)
    if len(products) > result["budget"] or expand_products(products, shape) != list(core):
        raise AssertionError("full raw core expansion failed")
    result.update(products=products, core_entries_checked=len(core))
    return finish()
