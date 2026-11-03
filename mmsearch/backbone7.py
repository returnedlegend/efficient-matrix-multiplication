"""Exact corank-one rank-one-backbone decoding; restricted upper bounds otherwise.

The input is the complete list of raw slices of an actual unfolding.  No slice
or original rank-one factor point is replaced by a reduced echelon vector.
"""
from datetime import datetime, timezone
import math
import time

from .compact_sat import BinaryBasis
from .compact_eight43 import bits, exact_coordinates
from .compact_coset43 import _insert, digest, expand_products, mode_slices, pair_column

DEADLINE = "2026-11-03T19:24:17Z"
HARD_DEADLINE = datetime.fromisoformat(DEADLINE.replace("Z", "+00:00")).timestamp()


def _matrix(value, rows, columns):
    if (type(rows) is not int or type(columns) is not int or min(rows, columns) < 0
            or type(value) is not int or value < 0 or value >> (rows * columns)):
        raise ValueError("matrix outside declared binary shape")


def rank_factorization(value, rows, columns):
    """Return exactly rank(value) original rank-one points summing to value."""
    _matrix(value, rows, columns)
    mask = (1 << columns) - 1
    raw = [(value >> (i * columns)) & mask for i in range(rows)]
    pivots, independent_rows = {}, []
    for row in raw:
        if _insert(pivots, row):
            independent_rows.append(row)  # Retain the original row, not its residue.
    left = [0] * len(independent_rows)
    for i, row in enumerate(raw):
        for j in bits(exact_coordinates(row, independent_rows)):
            left[j] |= 1 << i
    points = [dict(column=pair_column(a, b, columns), left=a, right=b)
              for a, b in zip(left, independent_rows)]
    rebuilt = 0
    for point in points:
        if not point["left"] or not point["right"]:
            raise AssertionError("zero factor in exact rank factorization")
        rebuilt ^= point["column"]
    if rebuilt != value:
        raise AssertionError("matrix rank factorization did not reconstruct input")
    return points


def matrix_rank(value, rows, columns):
    _matrix(value, rows, columns)
    pivots = {}
    mask = (1 << columns) - 1
    for i in range(rows):
        _insert(pivots, (value >> (i * columns)) & mask)
    return len(pivots)


def solve_pair_image(targets, rows, columns, budget, max_vectors=65535,
                     cancelled=None, timeout_seconds=None, deadline_utc=DEADLINE):
    """Decide every budget exactly when dim(S/B0)<=1; construct upper bounds else.

    For quotient dimension >1 a failed weighted-basis construction is UNKNOWN,
    never a global negative.  Enumeration caps and all guard stops are UNKNOWN.
    Successful witnesses reconstruct *every* supplied raw slice, including zeros,
    duplicates and linearly dependent slices.
    """
    targets = list(targets)
    _matrix(0, rows, columns)
    for target in targets:
        _matrix(target, rows, columns)
    if type(budget) is not int or budget < 0:
        raise ValueError("nonnegative integer budget required")
    if type(max_vectors) is not int or max_vectors < 0:
        raise ValueError("nonnegative enumeration cap required")
    if (timeout_seconds is not None and
            (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
             or timeout_seconds < 0)):
        raise ValueError("finite nonnegative timeout required")
    stamp = datetime.fromisoformat(deadline_utc.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("deadline requires timezone")
    deadline = min(stamp.timestamp(), HARD_DEADLINE)
    started = time.monotonic()
    identity = dict(algorithm="backbone7", target_sha256=digest(targets),
                    raw_target_count=len(targets), left_width=rows, right_width=columns,
                    budget=budget, effective_deadline_utc=datetime.fromtimestamp(
                        deadline, timezone.utc).isoformat())

    def finish(status, case, **kw):
        # Gaussian work, enumeration or lifting may cross a guard boundary.
        # Every completed answer, including an immediate negative, is barred.
        if status != "UNKNOWN":
            reason = stop()
            if reason:
                status, case = "UNKNOWN", reason
        return dict(identity, status=status, complete=status != "UNKNOWN", case=case, **kw)

    def stop():
        if time.time() >= deadline:
            return "deadline"
        if timeout_seconds is not None and time.monotonic() - started >= timeout_seconds:
            return "timeout"
        if cancelled and cancelled():
            return "cancelled"
        return None

    reason = stop()
    if reason:
        return finish("UNKNOWN", reason)
    space = BinaryBasis(targets)
    d = len(space.vectors)
    identity.update(target_rank=d, space_basis=list(space.vectors))
    if budget < d:
        return finish("LOCAL_UNSAT", "dimension_bound", exact_scope="global_dimension_bound")
    count = (1 << d) - 1
    if count > max_vectors:
        return finish("UNKNOWN", "subspace_enumeration_cap", span_vectors=count)

    # Store actual matrices and their exact rank; never enumerate ambient points.
    entries, inside_basis, inside_pivots = [], [], {}
    for coordinates in range(1, count + 1):
        reason = stop()
        if reason:
            return finish("UNKNOWN", reason, enumerated_vectors=coordinates - 1)
        value = space.expand(coordinates)
        rank = matrix_rank(value, rows, columns)
        entries.append((coordinates, value, rank))
        if rank == 1 and _insert(inside_pivots, coordinates):
            point = rank_factorization(value, rows, columns)[0]
            inside_basis.append(dict(point, span_coordinates=coordinates))
    b = len(inside_basis)
    q = d - b
    stats = dict(span_vectors=count, enumerated_vectors=count, inside_rank=b,
                 quotient_dimension=q,
                 backbone_basis=[dict(p) for p in inside_basis],
                 exact_scope="global_optimum" if q <= 1 else "restricted_family_upper_bound")
    if budget == d and b < d and q > 1:
        return finish("LOCAL_UNSAT", "inside_rankone_deficiency", **dict(stats,
                      exact_scope="global_dimension_equal_budget_bound"))

    # Canonical quotient residues under the echelon coordinate projection.
    backbone = BinaryBasis([p["span_coordinates"] for p in inside_basis])
    minima = {}
    for coordinates, value, rank in entries:
        reason = stop()
        if reason:
            return finish("UNKNOWN", reason, **stats)
        quotient = coordinates ^ backbone.expand(backbone.coordinates(coordinates))
        if quotient:
            entry = dict(quotient=quotient, span_coordinates=coordinates,
                         column=value, matrix_rank=rank)
            old = minima.get(quotient)
            if old is None or (rank, value) < (old["matrix_rank"], old["column"]):
                minima[quotient] = entry
    quotient_pivots, chosen = {}, []
    for entry in sorted(minima.values(), key=lambda e: (e["matrix_rank"], e["quotient"], e["column"])):
        reason = stop()
        if reason:
            return finish("UNKNOWN", reason, **stats)
        if _insert(quotient_pivots, entry["quotient"]):
            chosen.append(dict(entry))
    if len(chosen) != q:
        raise AssertionError("weighted quotient basis does not span S/B0")
    upper = b + sum(e["matrix_rank"] for e in chosen)
    stats.update(quotient_minima=[dict(e) for _, e in sorted(minima.items())],
                 chosen_quotient_basis=chosen, restricted_family_optimum=upper,
                 cp_upper_bound=upper, exact_cp_rank=upper if q <= 1 else None)
    if upper > budget:
        if q <= 1:
            return finish("LOCAL_UNSAT", "exact_backbone_optimum_exceeds_budget", **stats)
        return finish("UNKNOWN", "restricted_upper_bound_exceeds_budget", **stats)

    pool = [dict(p) for p in inside_basis]
    for entry in chosen:
        reason = stop()
        if reason:
            return finish("UNKNOWN", reason, **stats)
        pool.extend(rank_factorization(entry["column"], rows, columns))
    # Select original rank-one points.  Reduced rows are only membership aids.
    selected, pivots = [], {}
    for point in pool:
        if _insert(pivots, point["column"]):
            selected.append(dict(point))
    columns_basis = [p["column"] for p in selected]
    coefficients = []
    for target in targets:
        reason = stop()
        if reason:
            return finish("UNKNOWN", reason, **stats)
        mask = exact_coordinates(target, columns_basis)
        rebuilt = 0
        for j in bits(mask):
            rebuilt ^= selected[j]["column"]
        if rebuilt != target:
            raise AssertionError("raw slice witness failed")
        coefficients.append(mask)
    if len(selected) > budget:
        raise AssertionError("constructed support exceeds budget")
    reason = stop()
    if reason:
        return finish("UNKNOWN", reason, **stats)
    return finish("SAT", "backbone_exact" if q <= 1 else "restricted_weighted_quotient_upper_bound",
                  support=selected, target_coordinates=coefficients,
                  factor_point_pool=pool, **stats)


def solve_core(core, shape, target, axis=None, **kwargs):
    """Apply the slice-image decoder and verify the full raw tensor expansion."""
    started = time.monotonic()
    timeout = kwargs.get("timeout_seconds")
    if (timeout is not None and
            (type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout < 0)):
        raise ValueError("finite nonnegative timeout required")
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
    if timeout is not None:
        kwargs["timeout_seconds"] = max(0, timeout - (time.monotonic() - started))
    result = solve_pair_image(slices, shape[other[0]], shape[other[1]], target, **kwargs)
    result.update(shape=list(shape), axis=axis, core_sha256=digest(dict(shape=list(shape), core=core)))
    def stopped():
        deadline = datetime.fromisoformat(result["effective_deadline_utc"]).timestamp()
        return ("deadline" if time.time() >= deadline else
                "timeout" if timeout is not None and time.monotonic() - started >= timeout else
                "cancelled" if kwargs.get("cancelled") and kwargs["cancelled"]() else None)
    if result["status"] != "UNKNOWN":
        reason = stopped()
        if reason:
            result.update(status="UNKNOWN", complete=False, case=reason)
            return result
    if result["status"] == "SAT":
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
        if len(products) > target or expand_products(products, shape) != list(core):
            raise AssertionError("full raw tensor witness failed")
        reason = stopped()
        if reason:
            result.update(status="UNKNOWN", complete=False, case=reason)
            return result
        result.update(products=products, core_entries_checked=len(core))
    return result
