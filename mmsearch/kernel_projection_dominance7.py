"""Exact weighted finite-code dominance through a complete kernel projection.

No source loading, atom generation, target optimization or dataset access.
The sufficient certificate depends on the chosen lifts of the new projection.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import time

DEADLINE = "2026-11-03T19:24:17Z"
HARD_DEADLINE = datetime.fromisoformat(DEADLINE.replace("Z", "+00:00")).timestamp()
MAX_PROJECTION_RANK = 20
MAX_STATES = 1 << MAX_PROJECTION_RANK


class _Stopped(Exception):
    pass


def _integer(value, name, low=0, high=None):
    if type(value) is not int or value < low or (high is not None and value > high):
        raise ValueError("invalid literal integer " + name)
    return value


def _xor(columns, mask):
    result = 0
    while mask:
        bit = mask & -mask
        result ^= columns[bit.bit_length() - 1]
        mask ^= bit
    return result


def _insert(pivots, vector):
    while vector:
        pivot = vector.bit_length() - 1
        if pivot not in pivots:
            pivots[pivot] = vector
            return True
        vector ^= pivots[pivot]
    return False


def _rank(vectors, check):
    pivots = {}
    for vector in vectors:
        check()
        _insert(pivots, vector)
    return len(pivots)


def complete_kernel(columns, check=lambda: None):
    """Exact fundamental kernel with full column-combination witnesses."""
    pivots, cycles = {}, []
    for i, column in enumerate(columns):
        check()
        vector, witness = column, 1 << i
        while vector:
            pivot = vector.bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = vector, witness
                break
            previous = pivots[pivot]
            vector ^= previous[0]
            witness ^= previous[1]
        if not vector:
            cycles.append(witness)
    return cycles, len(pivots)


def _weights(values, count, name):
    values = [1] * count if values is None else list(values)
    if len(values) != count:
        raise ValueError(name + " has wrong length")
    for value in values:
        _integer(value, name)
    return values


def _weight_classes(values):
    classes = {}
    for i, weight in enumerate(values):
        if weight:
            classes[weight] = classes.get(weight, 0) | (1 << i)
    return tuple(sorted(classes.items()))


def _cost(mask, classes):
    return sum(weight * (mask & coordinates).bit_count() for weight, coordinates in classes)


def inspect_dominance(base_columns, extended_columns, target, base_state,
                      base_weights=None, extended_weights=None,
                      extended_kernel=None, projection_lifts=None,
                      max_projection_rank=20, max_states=MAX_STATES,
                      cancelled=None, timeout_seconds=None, deadline_utc=DEADLINE):
    """Certify equal GLOBAL minima inside two explicitly aligned finite codes.

    DOMINATED proves equal minima for the full binary fibers with these exact
    columns, target and nonnegative integer costs. POTENTIAL proves only that
    this selected-lift sufficient condition fails; it returns no new solution.
    Caps and every late guard exit are UNKNOWN, including a partial negative scan.
    Supplied kernels must be independent, null and complete. Supplied lifts
    must be independent under new-coordinate projection and span its full image.
    """
    base_columns, extended_columns = list(base_columns), list(extended_columns)
    old_count, total_count = len(base_columns), len(extended_columns)
    if total_count < old_count or extended_columns[:old_count] != base_columns:
        raise ValueError("extended old-column prefix does not match the base in order")
    for column in base_columns + extended_columns:
        _integer(column, "binary column")
    _integer(target, "target")
    _integer(base_state, "base feasible state", 0, (1 << old_count) - 1)
    if _xor(base_columns, base_state) != target:
        raise ValueError("supplied base state is not feasible for the exact target")
    base_weights = _weights(base_weights, old_count, "base weights")
    if extended_weights is None:
        extended_weights = base_weights + [1] * (total_count - old_count)
    extended_weights = _weights(extended_weights, total_count, "extended weights")
    if extended_weights[:old_count] != base_weights:
        raise ValueError("old-coordinate cost alignment changed in the extension")
    _integer(max_projection_rank, "projection-rank cap", 0, MAX_PROJECTION_RANK)
    _integer(max_states, "state-enumeration cap", 0, MAX_STATES)
    if (timeout_seconds is not None and
            (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
             or timeout_seconds < 0)):
        raise ValueError("finite nonnegative timeout required")
    stamp = datetime.fromisoformat(deadline_utc.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("absolute deadline timezone required")
    deadline = min(stamp.timestamp(), HARD_DEADLINE)
    started = time.monotonic()
    binding = dict(base_columns_hex=[hex(c) for c in base_columns],
                   extended_columns_hex=[hex(c) for c in extended_columns],
                   target_hex=hex(target), base_state_hex=hex(base_state),
                   base_weights=base_weights, extended_weights=extended_weights)
    identity = dict(algorithm="weighted_kernel_projection_dominance7",
                    input_sha256=hashlib.sha256(json.dumps(binding, sort_keys=True,
                        separators=(",", ":")).encode()).hexdigest(),
                    base_columns=old_count, extended_columns=total_count,
                    new_columns=total_count - old_count,
                    max_projection_rank=max_projection_rank, max_states=max_states,
                    timeout_seconds=timeout_seconds,
                    effective_deadline_utc=datetime.fromtimestamp(deadline, timezone.utc).isoformat(),
                    search_space="all binary selections whose full packed column XOR equals target; aligned nonnegative integer costs",
                    no_solution_or_novelty_claim=True)
    progress = dict(enumerated_states=0, margin_scan_complete=False,
                    minimum_margin_observed=None, minimum_nonzero_margin_observed=None,
                    nonzero_margin_minimizer_observed=None)

    def reason():
        if time.time() >= deadline:
            return "deadline"
        if timeout_seconds is not None and time.monotonic() - started >= timeout_seconds:
            return "timeout"
        if cancelled and cancelled():
            return "cancelled"
        return None

    def check():
        stopped = reason()
        if stopped:
            raise _Stopped(stopped)

    def finish(status, case, **kw):
        if status != "UNKNOWN":
            stopped = reason()
            if stopped:
                status, case = "UNKNOWN", stopped
        complete = status != "UNKNOWN"
        return dict(identity, **progress, status=status, case=case, complete=complete,
                    minimum_equality_certified=status == "DOMINATED",
                    minimum_margin=progress["minimum_margin_observed"] if complete else None,
                    minimum_nonzero_margin=progress["minimum_nonzero_margin_observed"] if complete else None,
                    **kw)

    try:
        check()
        base_rank = _rank(base_columns, check)
        generated, extended_rank = complete_kernel(extended_columns, check)
        kernel = generated if extended_kernel is None else list(extended_kernel)
        null_pivots = {}
        for cycle in kernel:
            check()
            _integer(cycle, "nonzero kernel basis vector", 1, (1 << total_count) - 1)
            if _xor(extended_columns, cycle):
                raise ValueError("supplied kernel vector is nonzero under full columns")
            if not _insert(null_pivots, cycle):
                raise ValueError("supplied kernel basis is dependent")
        if len(kernel) != total_count - extended_rank:
            raise ValueError("supplied extended kernel basis is incomplete")
        new_pivots, selected = {}, []
        for cycle in kernel:
            check()
            if _insert(new_pivots, cycle >> old_count):
                selected.append(cycle)  # Retain the original complete zero relation.
        projection_rank = len(new_pivots)
        if projection_rank != (total_count - extended_rank) - (old_count - base_rank):
            raise AssertionError("projection rank differs from exact kernel nullity gain")
        if projection_lifts is not None:
            selected = list(projection_lifts)
            supplied_pivots = {}
            for lift in selected:
                check()
                _integer(lift, "nonzero projected lift", 1, (1 << total_count) - 1)
                if _xor(extended_columns, lift):
                    raise ValueError("projection lift is not an exact full-column zero relation")
                if not _insert(supplied_pivots, lift >> old_count):
                    raise ValueError("projection lifts are dependent or have zero new projection")
            if len(selected) != projection_rank:
                raise ValueError("projection lifts do not cover the complete new kernel image")
            for cycle in kernel:
                value = cycle >> old_count
                for pivot in sorted(supplied_pivots, reverse=True):
                    if value >> pivot & 1:
                        value ^= supplied_pivots[pivot]
                if value:
                    raise ValueError("projection lifts miss a new-coordinate kernel direction")
        identity.update(base_rank=base_rank, extended_rank=extended_rank,
                        base_nullity=old_count - base_rank,
                        extended_nullity=len(kernel), projected_kernel_rank=projection_rank,
                        kernel_completeness_verified=True,
                        projection_basis_complete=True,
                        projection_lifts_hex=[hex(c) for c in selected],
                        required_states=1 << projection_rank)
        check()
        if projection_rank > max_projection_rank:
            return finish("UNKNOWN", "projection_rank_cap")
        old_mask = (1 << old_count) - 1
        old_classes = _weight_classes(base_weights)
        new_classes = _weight_classes(extended_weights[old_count:])
        count = 1 << projection_rank
        combined = 0
        first_negative = None
        minimizer = None
        for ordinal in range(min(count, max_states)):
            check()
            if ordinal:
                combined ^= selected[(ordinal & -ordinal).bit_length() - 1]
            alpha = ordinal ^ (ordinal >> 1)
            old_part, new_part = combined & old_mask, combined >> old_count
            old_cost, new_cost = _cost(old_part, old_classes), _cost(new_part, new_classes)
            margin = new_cost - old_cost
            witness = dict(alpha_hex=hex(alpha), zero_relation_hex=hex(combined),
                           old_coordinates_hex=hex(old_part), new_coordinates_hex=hex(new_part),
                           old_cost=old_cost, new_cost=new_cost, margin=margin)
            previous = progress["minimum_margin_observed"]
            if previous is None or margin < previous:
                progress["minimum_margin_observed"] = margin
                minimizer = witness
            if alpha:
                previous = progress["minimum_nonzero_margin_observed"]
                if previous is None or margin < previous:
                    progress["minimum_nonzero_margin_observed"] = margin
                    progress["nonzero_margin_minimizer_observed"] = witness
            if margin < 0 and first_negative is None:
                first_negative = witness
            progress["enumerated_states"] += 1
        if progress["enumerated_states"] != count:
            return finish("UNKNOWN", "state_enumeration_cap",
                          observed_negative_relation=first_negative,
                          observed_margin_minimizer=minimizer)
        progress["margin_scan_complete"] = True
        if first_negative is not None:
            return finish("POTENTIAL", "selected_lift_bound_has_negative_margin",
                          negative_relation=first_negative, margin_minimizer=minimizer,
                          interpretation="sufficient condition fails for these lifts; no improved feasible solution established")
        return finish("DOMINATED", "all_projected_lift_combinations_nonnegative",
                      margin_minimizer=minimizer,
                      interpretation="extended and base minimum weighted costs are equal inside these exact finite binary dictionaries")
    except _Stopped as exc:
        return finish("UNKNOWN", str(exc))
