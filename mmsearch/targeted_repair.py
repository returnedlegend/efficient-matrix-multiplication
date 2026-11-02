"""Finite-budget exact F2 residual repair with discrete connected moves.

Residual weight is a search objective, never evidence for a rank reduction.
All factors, tensor deltas, linear algebra, and acceptance draws are integers.
The final candidate always passes through the independent coefficient verifier.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import random
import time

from .verify import verify_candidate, write_standalone_verifier

AXES = ("u", "v", "w")


def bits(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length()-1
        mask ^= bit


def tensor(term, width):
    """Flatten a rank-one tensor using (u*width+v)*width+w."""
    pair = 0
    for v in bits(term[1]):
        pair |= term[2] << (v*width)
    result = 0
    for u in bits(term[0]):
        result |= pair << (u*width*width)
    return result


def target(n):
    width = n*n
    result = 0
    for i in range(n):
        for j in range(n):
            for k in range(n):
                result ^= 1 << (((i*n+j)*width+j*n+k)*width+k*n+i)
    return result


def encode(factors, n, metadata=None):
    return dict(dimension=n, field=2, terms=[
        {name: [(term[axis] >> i) & 1 for i in range(n*n)]
         for axis, name in enumerate(AXES)} for term in factors],
        metadata=metadata or {})


def decode(candidate):
    report = verify_candidate(candidate, random_trials=0)
    if report["rank"] is None or candidate.get("field") != 2:
        raise ValueError("input must have the F2 certificate schema")
    if any(type(x) is not int or x not in (0, 1)
           for term in candidate["terms"] for axis in AXES for x in term[axis]):
        raise ValueError("coefficients must be strict integer bits")
    return [[sum(x << i for i, x in enumerate(term[axis])) for axis in AXES]
            for term in candidate["terms"]]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def code_hash():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), Path(__file__).with_name("verify.py"))}


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2)+"\n")
    temporary.replace(path)


class ResidualState:
    """Exact incremental residual; arbitrary joint flips include cross terms."""
    def __init__(self, factors, n):
        self.n, self.width = n, n*n
        self.factors = [term.copy() for term in factors]
        self.tensors = [tensor(term, self.width) for term in self.factors]
        self.residual = target(n)
        for value in self.tensors:
            self.residual ^= value

    @property
    def weight(self):
        return self.residual.bit_count()

    def derivative(self, move):
        slot, axis, coordinate = move
        term = self.factors[slot].copy()
        term[axis] = 1 << coordinate
        return tensor(term, self.width)

    def delta(self, moves):
        changed = {}
        for slot, axis, coordinate in moves:
            term = changed.setdefault(slot, self.factors[slot].copy())
            term[axis] ^= 1 << coordinate
        result = 0
        for slot, term in changed.items():
            result ^= self.tensors[slot] ^ tensor(term, self.width)
        return result

    def apply(self, moves):
        slots = set()
        for slot, axis, coordinate in moves:
            self.factors[slot][axis] ^= 1 << coordinate
            slots.add(slot)
        for slot in slots:
            new_tensor = tensor(self.factors[slot], self.width)
            self.residual ^= self.tensors[slot] ^ new_tensor
            self.tensors[slot] = new_tensor

    def incident(self, coordinate):
        """Every first derivative covering one residual/support coordinate."""
        u, rem = divmod(coordinate, self.width*self.width)
        v, w = divmod(rem, self.width)
        coords = (u, v, w)
        for slot, term in enumerate(self.factors):
            for axis in range(3):
                if all(term[a] >> coords[a] & 1 for a in range(3) if a != axis):
                    yield slot, axis, coords[axis]


def _random_bit(mask, rng):
    # Avoid constructing a list of all tensor coordinates for dense excursions.
    skip = rng.randrange(mask.bit_count())
    while skip:
        mask ^= mask & -mask
        skip -= 1
    return (mask & -mask).bit_length()-1


def connected_proposals(state, rng, beam=6, pair_limit=96):
    """Single moves touch the residual; pairs touch its changed support.

    Same-term cross-axis pairs are evaluated by exact tensor replacement,
    rather than incorrectly XORing two derivatives evaluated at the old state.
    """
    if not state.residual:
        return []
    anchor = _random_bit(state.residual, rng)
    singles = list(state.incident(anchor))
    rng.shuffle(singles)
    if not singles:
        # An annihilated term can have no useful first derivative. Joint moves
        # and a global perturbation can reactivate it on later iterations.
        return []
    scored = [(state.residual ^ state.derivative(move)).bit_count() for move in singles]
    order = sorted(range(len(singles)), key=lambda i: scored[i])
    proposals = [(scored[i], (singles[i],), "single") for i in order]
    for i in order[:beam]:
        first = singles[i]
        support = state.residual ^ state.derivative(first)
        if not support:
            continue
        second_moves = set(state.incident(_random_bit(support, rng)))
        # Same-slot moves capture nonlinear changes absent from the old
        # derivative graph (including initially zero derivative directions).
        second_moves.update((first[0], axis, j) for axis in range(3)
                            for j in range(state.width) if axis != first[1])
        second_moves.discard(first)
        second_moves = sorted(second_moves)
        rng.shuffle(second_moves)
        for second in second_moves[:pair_limit]:
            moves = (first, second)
            proposals.append(((state.residual ^ state.delta(moves)).bit_count(), moves, "pair"))
    return proposals


def span_proposal(state, axis, rng, slots=None):
    """Repair exactly representable slices, and explore kernel directions.

    Other factors are fixed, so all selected coefficients on one axis form
    an exact linear subproblem. Unrepresentable slices remain unchanged;
    Gaussian elimination is never misrepresented as a least-squares solve.
    """
    width = state.width
    slots = list(range(len(state.factors))) if slots is None else list(slots)
    rng.shuffle(slots)
    others = [a for a in range(3) if a != axis]
    basis, dependencies = {}, []
    for slot in slots:
        term = state.factors[slot]
        vector = 0
        for i in bits(term[others[0]]):
            vector |= term[others[1]] << (i*width)
        combination = 1 << slot
        while vector:
            pivot = vector.bit_length()-1
            if pivot not in basis:
                basis[pivot] = vector, combination
                break
            old_vector, old_combination = basis[pivot]
            vector ^= old_vector
            combination ^= old_combination
        if not vector:
            dependencies.append(combination)
    slices = [0]*width
    for index in bits(state.residual):
        u, rem = divmod(index, width*width)
        v, w = divmod(rem, width)
        coords = (u, v, w)
        slices[coords[axis]] ^= 1 << (coords[others[0]]*width+coords[others[1]])
    moves = []
    for coordinate, vector in enumerate(slices):
        combination = 0
        while vector:
            pivot = vector.bit_length()-1
            if pivot not in basis:
                break
            old_vector, old_combination = basis[pivot]
            vector ^= old_vector
            combination ^= old_combination
        if not vector:
            moves.extend((slot, axis, coordinate) for slot in bits(combination))
    if moves:
        return tuple(moves), "span_repair"
    if dependencies:
        combination = rng.choice(dependencies)
        coordinate = rng.randrange(width)
        return tuple((slot, axis, coordinate) for slot in bits(combination)), "span_plateau"
    return (), "span_unrepresentable"


def shear_proposal(state, rng):
    """Elementary GL(2,F2) move on two terms with a common factor."""
    groups = {}
    for slot, term in enumerate(state.factors):
        for axis in range(3):
            if term[axis]:
                groups.setdefault((axis, term[axis]), []).append(slot)
    choices = [(axis, slots) for (axis, _), slots in groups.items() if len(slots) > 1]
    if not choices:
        return ()
    axis, slots = rng.choice(choices)
    i, j = rng.sample(slots, 2)
    b, c = [a for a in range(3) if a != axis]
    return tuple([(i, b, bit) for bit in bits(state.factors[j][b])] +
                 [(j, c, bit) for bit in bits(state.factors[i][c])])


def _tuples(value):
    return tuple(_tuples(x) for x in value) if isinstance(value, list) else value


def search(candidate, rank=None, seconds=60, seed=0, output=None, checkpoint=None,
           resume=False, max_steps=None, max_excess=64, progress=True):
    """Return best fixed-rank candidate and independent exact report.

    Checkpoints contain current and best factors, RNG state, tabu history,
    counters, strict source identity and source-code hashes. Time budget is per
    invocation; max_steps limits additional proposals for deterministic tests.
    """
    source = decode(candidate)
    n = candidate["dimension"]
    rank = len(source) if rank is None else rank
    if type(rank) is not int or not 1 <= rank <= len(source):
        raise ValueError("rank must be positive and at most input term count")
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("seconds must be finite and nonnegative")
    if type(max_excess) is not int or max_excess < 0:
        raise ValueError("max_excess must be a nonnegative integer")
    if max_steps is not None and (type(max_steps) is not int or max_steps < 0):
        raise ValueError("max_steps must be nonnegative")
    identity = dict(source_sha256=digest(encode(source, n)), rank=rank, seed=seed,
                    max_excess=max_excess, code_sha256=code_hash())
    rng = random.Random(seed)
    counters = dict(steps=0, proposals=0, accepted=0, uphill=0, plateau=0,
                    pair_accepted=0, span_repair_accepted=0, shear_accepted=0,
                    restarts=0, distinct_states=0, initial_weight=0)
    taboo = deque(maxlen=128)
    if resume:
        if checkpoint is None:
            raise ValueError("resume requires checkpoint")
        saved = json.loads(Path(checkpoint).read_text())
        if saved["identity"] != identity:
            raise ValueError("checkpoint source, parameters or code hashes differ")
        for name in ("current_candidate", "best_candidate"):
            if (saved[name].get("dimension") != n or
                    len(saved[name].get("terms", [])) != rank):
                raise ValueError("checkpoint dimension or rank differs")
        # Route checkpoint vectors through the same strict-bit schema gate.
        current_factors = decode(saved["current_candidate"])
        best = decode(saved["best_candidate"])
        state = ResidualState(current_factors, n)
        if (state.weight != saved["current_weight"] or
                ResidualState(best, n).weight != saved["best_weight"]):
            raise ValueError("checkpoint residual measurement disagrees")
        counters = saved["counters"]
        taboo.extend(saved["tabu"])
        rng.setstate(_tuples(saved["rng_state"]))
    else:
        order = sorted(range(len(source)), key=lambda i: tensor(source[i], n*n).bit_count())
        drop = set(order[:len(source)-rank])
        state = ResidualState([term for i, term in enumerate(source) if i not in drop], n)
        best = [term.copy() for term in state.factors]
        counters["initial_weight"] = state.weight
    best_weight = ResidualState(best, n).weight
    start, steps_start = time.monotonic(), counters["steps"]
    last_save = start

    def metadata():
        return dict(method="targeted-discrete-exact-f2-repair", rank=rank,
                    residual_weight=best_weight, identity=identity, counters=dict(counters),
                    elapsed_seconds=time.monotonic()-start,
                    scope="heuristic residual objective; only exact verification certifies a scheme")

    def persist():
        if checkpoint:
            save(checkpoint, dict(version=1, identity=identity, counters=counters,
                current_candidate=encode(state.factors, n), best_candidate=encode(best, n),
                current_weight=state.weight, best_weight=best_weight,
                rng_state=rng.getstate(), tabu=list(taboo)))

    while best_weight and time.monotonic()-start < seconds and (
            max_steps is None or counters["steps"]-steps_start < max_steps):
        step = counters["steps"]
        proposals = []
        if step % 11 == 0:
            moves, kind = span_proposal(state, (step//11) % 3, rng)
            if moves:
                proposals.append(((state.residual ^ state.delta(moves)).bit_count(), moves, kind))
        if step % 3 == 0:
            moves = shear_proposal(state, rng)
            if moves:
                if state.delta(moves):
                    raise AssertionError("GL2 shear changed tensor")
                proposals.append((state.weight, moves, "shear"))
        if not proposals or step % 3:
            proposals.extend(connected_proposals(state, rng))
        # A bounded global two-bit perturbation reaches coefficient directions
        # with no current first-derivative connection to residual support.
        if not proposals or step % 17 == 0:
            moves = tuple((rng.randrange(rank), rng.randrange(3), rng.randrange(n*n))
                          for _ in range(2+(step % 3)))
            proposals.append(((state.residual ^ state.delta(moves)).bit_count(), moves, "kick"))
        rng.shuffle(proposals)
        proposals.sort(key=lambda item: item[0])
        counters["steps"] += 1
        counters["proposals"] += len(proposals)
        for weight, moves, kind in proposals:
            if weight > best_weight+max_excess:
                continue
            delta = state.delta(moves)
            # Hash complete factor state, not only residual (all shears have
            # the same residual). This prevents immediate inverse cycling.
            changed = [term.copy() for term in state.factors]
            for slot, axis, coordinate in moves:
                changed[slot][axis] ^= 1 << coordinate
            key = digest(changed)
            if key in taboo:
                continue
            excess = weight-state.weight
            temperature = 1+(step//127) % 8
            if excess > 0 and rng.randrange(temperature+4*excess) >= temperature:
                continue
            previous_weight = state.weight
            state.apply(moves)
            if state.weight != weight:
                raise AssertionError("incremental joint-move objective disagreement")
            taboo.append(key)
            counters["accepted"] += 1
            counters["distinct_states"] += 1  # distinct within bounded tabu window
            counters["uphill"] += weight > previous_weight
            counters["plateau"] += weight == previous_weight
            if kind in ("pair", "span_repair", "shear"):
                counters[kind+"_accepted"] += 1
            if weight < best_weight:
                best, best_weight = [term.copy() for term in state.factors], weight
                if progress:
                    print(json.dumps(dict(event="best", residual_weight=weight, counters=counters)), flush=True)
            break
        if counters["steps"] % 251 == 0 and state.weight > best_weight:
            state = ResidualState(best, n)
            counters["restarts"] += 1
        if time.monotonic()-last_save >= 10:
            persist()
            last_save = time.monotonic()
    persist()
    result = encode(best, n, metadata())
    report = verify_candidate(result)
    if report["mismatch_count"] != best_weight:
        raise AssertionError("independent verifier disagrees with search residual")
    result["metadata"]["status"] = "verified" if report["valid"] else "failed_exact_verification"
    if output:
        save(output, result)
        save(Path(output).with_suffix(".verification.json"), report)
        write_standalone_verifier(Path(output).with_suffix(".verify.py"))
    return result, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--rank", type=int, default=92)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--max-excess", type=int, default=64)
    args = parser.parse_args(argv)
    result, report = search(json.loads(args.input.read_text()), rank=args.rank,
        seconds=args.seconds, seed=args.seed, output=args.output,
        checkpoint=args.checkpoint, resume=args.resume, max_steps=args.max_steps,
        max_excess=args.max_excess)
    print(json.dumps(dict(valid=report["valid"], rank=report["rank"],
        residual_weight=report["mismatch_count"], counters=result["metadata"]["counters"],
        output=str(args.output))), flush=True)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
