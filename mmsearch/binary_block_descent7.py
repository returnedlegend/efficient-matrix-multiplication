"""Exact GF2 coordinate blocks for compact CP<=14 approximation/decomposition.

The loss is the integer number of incorrect tensor coefficients. Successful
compact witnesses remain RAW and require independent full ambient verification.
No source loading, ambient matrix-multiplication verification or publication.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import random
import time

MAX_RANK = 14
MAX_MODE = 15
MAX_CODEWORDS = 1 << MAX_RANK
MAX_HISTORY = 10000
DEADLINE = "2026-11-03T19:24:17Z"
HARD_DEADLINE = datetime.fromisoformat(DEADLINE.replace("Z", "+00:00")).timestamp()


class _Stopped(Exception):
    pass


class _Guard:
    def __init__(self, timeout_seconds, cancelled, deadline_utc):
        if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                or not 0 <= timeout_seconds <= 120):
            raise ValueError("timeout must be finite0..120 seconds")
        parsed = datetime.fromisoformat(deadline_utc.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("deadline timezone required")
        self.deadline = min(parsed.timestamp(), HARD_DEADLINE)
        self.started = time.monotonic()
        self.seconds = timeout_seconds
        self.cancelled = cancelled

    def reason(self):
        if time.time() >= self.deadline:
            return "deadline"
        if time.monotonic() - self.started >= self.seconds:
            return "timeout"
        if self.cancelled and self.cancelled():
            return "cancelled"
        return None

    def check(self):
        reason = self.reason()
        if reason:
            raise _Stopped(reason)


def _integer(value, name, low=0, high=None):
    if type(value) is not int or value < low or (high is not None and value > high):
        raise ValueError("invalid literal integer " + name)
    return value


def _validate(core, shape, factors=None):
    shape, core = tuple(shape), list(core)
    if len(shape) != 3 or any(type(d) is not int or not 0 <= d <= MAX_MODE for d in shape):
        raise ValueError("compact shape must contain three literal dimensions0..15")
    if len(core) != math.prod(shape) or any(type(v) is not int or v not in (0, 1) for v in core):
        raise ValueError("core must contain all literal binary tensor coefficients")
    if factors is None:
        return core, shape, None
    factors = [tuple(term) for term in factors]
    if len(factors) > MAX_RANK:
        raise ValueError("at most14 product slots supported")
    for term in factors:
        if len(term) != 3 or any(type(v) is not int or v < 0 or v >> d for v, d in zip(term, shape)):
            raise ValueError("invalid literal binary factor masks")
    return core, shape, factors


def _bits(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def _packed(core):
    return sum(value << i for i, value in enumerate(core))


def _input_digest(core, shape):
    return hashlib.sha256(json.dumps([list(shape), core], separators=(",", ":")).encode()).hexdigest()


def _tensor(factors, shape):
    value = 0
    for left, middle, right in factors:
        for a in _bits(left):
            for b in _bits(middle):
                value ^= right << ((a * shape[1] + b) * shape[2])
    return value


def residual_loss(core, shape, factors):
    core, shape, factors = _validate(core, shape, factors)
    return (_packed(core) ^ _tensor(factors, shape)).bit_count()


def scalar_loss(core, shape, factors):
    """Independent scalar coefficient loop, including every expected zero."""
    core, shape, factors = _validate(core, shape, factors)
    loss = 0
    for a in range(shape[0]):
        for b in range(shape[1]):
            for c in range(shape[2]):
                predicted = 0
                for left, middle, right in factors:
                    predicted ^= ((left >> a) & 1) & ((middle >> b) & 1) & ((right >> c) & 1)
                loss += predicted != core[(a * shape[1] + b) * shape[2] + c]
    return loss


def _pair_column(left, right, columns):
    value = 0
    for i in _bits(left):
        value ^= right << (i * columns)
    return value


def _slices(core, shape, axis):
    other = [i for i in range(3) if i != axis]
    targets = []
    for i in range(shape[axis]):
        matrix = 0
        for j in range(shape[other[0]]):
            for k in range(shape[other[1]]):
                xyz = [0, 0, 0]
                xyz[axis], xyz[other[0]], xyz[other[1]] = i, j, k
                matrix |= core[(xyz[0] * shape[1] + xyz[1]) * shape[2] + xyz[2]] << (j * shape[other[1]] + k)
        targets.append(matrix)
    return targets, other


def _distance(target, word):
    return (target ^ word).bit_count()


def _block(core, shape, factors, axis, guard, max_codewords):
    guard.check()
    count = 1 << len(factors)
    if count > max_codewords:
        raise _Stopped("codeword_cap")
    targets, other = _slices(core, shape, axis)
    columns = [_pair_column(term[other[0]], term[other[1]], shape[other[1]]) for term in factors]
    current = [sum(((term[axis] >> row) & 1) << t for t, term in enumerate(factors))
               for row in range(shape[axis])]
    closest, minima = list(current), []
    for target, mask in zip(targets, current):
        word = 0
        for t in _bits(mask):
            word ^= columns[t]
        minima.append(_distance(target, word))
    before = sum(minima)
    word = 0
    for ordinal in range(count):
        guard.check()
        if ordinal:
            word ^= columns[(ordinal & -ordinal).bit_length() - 1]
        coordinates = ordinal ^ (ordinal >> 1)
        for row, target in enumerate(targets):
            distance = _distance(target, word)
            if distance < minima[row] or (distance == minima[row] and closest[row] != current[row]
                                          and coordinates < closest[row]):
                minima[row], closest[row] = distance, coordinates
    updated = [list(term) for term in factors]
    for t in range(len(factors)):
        updated[t][axis] = sum(((mask >> t) & 1) << row for row, mask in enumerate(closest))
    updated = [tuple(term) for term in updated]
    after = (_packed(core) ^ _tensor(updated, shape)).bit_count()
    if after != sum(minima) or after > before or scalar_loss(core, shape, updated) != after:
        raise AssertionError("exact binary block minimum failed full scalar reconstruction")
    guard.check()
    return dict(status="BLOCK_MINIMUM", complete=True, factors=updated,
                axis=axis, loss_before=before, loss_after=after,
                row_distances=minima, row_coefficients=closest,
                enumerated_codewords=count,
                changed_bits=sum((a[axis] ^ b[axis]).bit_count() for a, b in zip(factors, updated)))


def exact_block_update(core, shape, factors, axis, max_codewords=MAX_CODEWORDS,
                       timeout_seconds=120, cancelled=None, deadline_utc=DEADLINE):
    """Globally minimize one complete factor block with the other two fixed."""
    core, shape, factors = _validate(core, shape, factors)
    _integer(axis, "axis", 0, 2)
    _integer(max_codewords, "codeword cap", 0, MAX_CODEWORDS)
    guard = _Guard(timeout_seconds, cancelled, deadline_utc)
    try:
        result = _block(core, shape, factors, axis, guard, max_codewords)
        guard.check()
    except _Stopped as exc:
        result = dict(status="UNKNOWN", complete=False, case=str(exc))
    result.update(publication_eligible=False, requires_ambient_verification=True,
                  input_sha256=_input_digest(core, shape),
                  scope="exact compact factor-block minimum only; no global CP feasibility negative")
    return result


def optimize(core, shape, rank, initial_factors=None, seed=7, axis_order=(0, 1, 2),
             max_sweeps=50, max_restarts=4, max_perturbations=3, perturb_bits=2,
             max_codewords=MAX_CODEWORDS, timeout_seconds=120,
             cancelled=None, deadline_utc=DEADLINE):
    """Monotone exact blocks with bounded discrete perturbations and restarts.

    Every zero-loss output is RAW_EXACT_COMPACT, never an ambient certificate.
    Every unsuccessful/limited/stopped run is UNKNOWN, never UNSAT.
    """
    core, shape, _ = _validate(core, shape)
    _integer(rank, "rank", 0, MAX_RANK)
    _integer(seed, "seed", -(1 << 63), (1 << 63) - 1)
    for value, name in [(max_sweeps, "sweep budget"), (max_restarts, "restart budget"),
                        (max_perturbations, "perturbation budget")]:
        _integer(value, name, 0, 100000)
    _integer(perturb_bits, "perturbation bits", 1, 32)
    _integer(max_codewords, "codeword cap", 0, MAX_CODEWORDS)
    axis_order = tuple(axis_order)
    if any(type(v) is not int for v in axis_order) or sorted(axis_order) != [0, 1, 2]:
        raise ValueError("axis order must be a literal permutation0,1,2")
    if initial_factors is not None:
        _, _, initial_factors = _validate(core, shape, initial_factors)
        if len(initial_factors) != rank:
            raise ValueError("initial slot count differs from rank")
    guard = _Guard(timeout_seconds, cancelled, deadline_utc)
    rng = random.Random(seed)
    packed = _packed(core)
    best_loss = None
    best_factors = None
    history = []
    history_dropped = 0
    block_updates = codewords = perturbations = 0
    restart = sweep = 0
    def finish(status, case):
        stopped = guard.reason()
        if stopped:
            status, case = "UNKNOWN", stopped
        result = dict(status=status, complete=status == "RAW_EXACT_COMPACT", case=case,
            field=2, shape=list(shape), rank_slots=rank, seed=seed,
            best_loss=best_loss, best_factors=[list(t) for t in best_factors] if best_factors is not None else None,
            block_updates=block_updates, enumerated_codewords=codewords,
            perturbations=perturbations, restart_cursor=restart, sweep_cursor=sweep,
            elapsed_seconds=time.monotonic() - guard.started, history=history,
            history_dropped=history_dropped, input_sha256=_input_digest(core, shape),
            parameters=dict(axis_order=list(axis_order), max_sweeps=max_sweeps,
                max_restarts=max_restarts, max_perturbations=max_perturbations,
                perturb_bits=perturb_bits, max_codewords=max_codewords, timeout_seconds=timeout_seconds),
            publication_eligible=False, requires_ambient_verification=True,
            scope="heuristic rank-slot search on the supplied compact binary tensor; failure is UNKNOWN")
        if status == "RAW_EXACT_COMPACT":
            if best_loss != 0 or scalar_loss(core, shape, best_factors) != 0:
                raise AssertionError("raw exact compact observation failed independent scalar check")
            late = guard.reason()
            if late:
                result.update(status="UNKNOWN", complete=False, case=late, after_cutoff=True)
            result["raw_compact"] = dict(products=[list(t) for t in best_factors],
                shape=list(shape), exact_entries_checked=len(core), packed_and_scalar_losses=[0, 0],
                ambient_verified=False)
        return result
    def record(value):
        nonlocal history_dropped
        if len(history) < MAX_HISTORY:
            history.append(value)
        else:
            history_dropped += 1
    def consider(factors, loss):
        nonlocal best_factors, best_loss
        if best_loss is None or loss < best_loss:
            best_loss, best_factors = loss, list(factors)
    def random_factors():
        return [tuple(rng.randrange(1, 1 << d) if d else 0 for d in shape) for _ in range(rank)]
    choices = [(t, axis, bit) for t in range(rank) for axis in range(3) for bit in range(shape[axis])]
    try:
        guard.check()
        for restart in range(max_restarts + 1):
            guard.check()
            factors = list(initial_factors) if restart == 0 and initial_factors is not None else random_factors()
            loss = (packed ^ _tensor(factors, shape)).bit_count()
            consider(factors, loss)
            record(dict(action="initial" if restart == 0 else "restart", restart=restart,
                                loss=loss, best_loss=best_loss))
            if best_loss == 0:
                return finish("RAW_EXACT_COMPACT", "zero_compact_residual")
            local_perturbations = 0
            for sweep in range(max_sweeps):
                start_loss = loss
                for axis in axis_order:
                    guard.check()
                    block = _block(core, shape, factors, axis, guard, max_codewords)
                    if block["loss_before"] != loss:
                        raise AssertionError("block unfolding and full residual losses differ")
                    factors, loss = block["factors"], block["loss_after"]
                    block_updates += 1
                    codewords += block["enumerated_codewords"]
                    consider(factors, loss)
                    record(dict(action="block", restart=restart, sweep=sweep, axis=axis,
                        loss_before=block["loss_before"], loss_after=loss, best_loss=best_loss,
                        changed_bits=block["changed_bits"]))
                    if loss == 0:
                        return finish("RAW_EXACT_COMPACT", "zero_compact_residual")
                if loss == start_loss:
                    if local_perturbations >= max_perturbations or not choices:
                        record(dict(action="plateau", restart=restart, sweep=sweep,
                                            loss=loss, best_loss=best_loss))
                        break
                    changed = [list(t) for t in factors]
                    flips = rng.sample(choices, min(perturb_bits, len(choices)))
                    for t, axis, bit in flips:
                        changed[t][axis] ^= 1 << bit
                    before = loss
                    factors = [tuple(t) for t in changed]
                    loss = (packed ^ _tensor(factors, shape)).bit_count()
                    local_perturbations += 1
                    perturbations += 1
                    consider(factors, loss)
                    record(dict(action="perturb", restart=restart, sweep=sweep,
                        flips=[list(f) for f in flips], loss_before=before, loss_after=loss, best_loss=best_loss))
                    if loss == 0:
                        return finish("RAW_EXACT_COMPACT", "zero_compact_residual")
        return finish("UNKNOWN", "bounded_restarts_exhausted")
    except _Stopped as exc:
        return finish("UNKNOWN", str(exc))
