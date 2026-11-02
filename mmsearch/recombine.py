"""Exact affine-code search over F2 rank-one term dictionaries.

Every state is an odd GF2 combination of independently verified algorithms.
Thus every scored state is exact; the objective is term count, never residual.
An all-odd-rank source pool only represents odd ranks (93 can reach 91, not 92).
No claim about algorithms outside the supplied finite dictionary is implied.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
import time

from .verify import verify_candidate

AXES = ("u", "v", "w")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def code_hash():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), Path(__file__).with_name("verify.py"))}


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+".tmp")
    tmp.write_text(json.dumps(value, sort_keys=True, indent=2)+"\n")
    tmp.replace(path)


def encode(terms, n, metadata=None):
    return dict(dimension=n, field=2, terms=[
        {axis: [(term[a] >> i) & 1 for i in range(n*n)]
         for a, axis in enumerate(AXES)} for term in sorted(terms)],
        metadata=metadata or {})


def canonical_terms(candidate):
    """Strict integer-bit vectors; duplicate terms cancel modulo two.

    Zero factors are rejected so padding cannot manufacture mixed parity.
    """
    if not isinstance(candidate, dict) or type(candidate.get("dimension")) is not int or candidate["dimension"] < 1:
        raise ValueError("dimension must be a positive integer")
    if type(candidate.get("field")) is not int or candidate["field"] != 2:
        raise ValueError("field must be F2")
    if not isinstance(candidate.get("terms"), list):
        raise ValueError("terms must be an array")
    width = candidate["dimension"]**2
    result = set()
    for term in candidate["terms"]:
        if not isinstance(term, dict) or set(term) != set(AXES):
            raise ValueError("term must have exactly u, v, w")
        for axis in AXES:
            v = term[axis]
            if not isinstance(v, list) or len(v) != width or any(type(x) is not int or x not in (0, 1) for x in v):
                raise ValueError("factor must contain strict integer bits of dimension squared length")
        triple = tuple(sum(x << i for i, x in enumerate(term[axis])) for axis in AXES)
        if not all(triple):
            raise ValueError("zero factors are forbidden; no parity padding")
        if triple in result:
            result.remove(triple)
        else:
            result.add(triple)
    return tuple(sorted(result))


class Pool:
    """Immutable verified source pool; coefficient index matches source order."""
    def __init__(self, candidates, provenance=None):
        if not candidates:
            raise ValueError("empty source pool")
        n = candidates[0].get("dimension") if isinstance(candidates[0], dict) else None
        sources, terms, seen = [], [], set()
        for i, candidate in enumerate(candidates):
            canonical = canonical_terms(candidate)
            if candidate["dimension"] != n:
                raise ValueError("source dimensions differ")
            report = verify_candidate(candidate, random_trials=0)
            if not report["valid"]:
                raise ValueError("source failed independent exact tensor verification")
            sha = digest(encode(canonical, n))
            if sha in seen:
                continue
            seen.add(sha)
            terms.append(canonical)
            sources.append(dict(canonical_sha256=sha, rank=len(canonical),
                exact_entries_checked=report["exact_entries_checked"],
                provenance=provenance[i] if provenance else {}))
        self.dimension, self.sources = n, sources
        self.dictionary = tuple(sorted(set(t for algorithm in terms for t in algorithm)))
        positions = {t: i for i, t in enumerate(self.dictionary)}
        self.vectors = [sum(1 << positions[t] for t in algorithm) for algorithm in terms]
        self.dictionary_sha256 = digest(self.dictionary)
        self.sha256 = digest(dict(dimension=n, dictionary_sha256=self.dictionary_sha256,
                                  sources=sources))

    def combine(self, coefficients):
        if type(coefficients) is not int or coefficients < 0 or coefficients >> len(self.sources):
            raise ValueError("coefficient mask out of range")
        if coefficients.bit_count() % 2 != 1:
            raise ValueError("an exact state requires an odd number of source algorithms")
        result = 0
        for i, vector in enumerate(self.vectors):
            if coefficients >> i & 1:
                result ^= vector
        return result

    def candidate(self, coefficients, metadata=None):
        vector = self.combine(coefficients)
        return encode([t for i, t in enumerate(self.dictionary) if vector >> i & 1], self.dimension,
                      dict(metadata or {}, coefficients_hex=hex(coefficients),
                           selected_source_sha256=[s["canonical_sha256"] for i, s in enumerate(self.sources)
                                                   if coefficients >> i & 1],
                           dictionary_sha256=self.dictionary_sha256, pool_sha256=self.sha256))

    def manifest(self):
        parities = sorted(set(s["rank"] % 2 for s in self.sources))
        return dict(dimension=self.dimension, field=2, sources=self.sources,
            dictionary_sha256=self.dictionary_sha256, dictionary_size=len(self.dictionary),
            pool_sha256=self.sha256, source_rank_parities=parities,
            parity_limitation=("all odd ranks: every represented exact state has odd rank; 92 is unreachable"
                               if parities == [1] else "mixed/even source parity; no all-odd restriction"))


def _tuples(value):
    return tuple(_tuples(x) for x in value) if isinstance(value, list) else value


def search(pool, *, seconds=5, seed=0, target=92, max_steps=300000,
           anchors=16, neighbors=48, walk_steps=50000, max_weight=100,
           checkpoint=None, resume=False):
    """Bounded triples, pair-cycle walk, and exhaustive local pair sweep.

    A completed local sweep only certifies that no A XOR B cycle from this
    source pool reduces the final incumbent. Checkpoints retain exact GF2
    coefficients and RNG state, and replay when limited by step count.
    """
    if not math.isfinite(seconds) or seconds <= 0 or any(type(x) is not int for x in
            (seed, target, max_steps, anchors, neighbors, walk_steps, max_weight)):
        raise ValueError("invalid search bounds")
    if min(target, max_steps, anchors, neighbors, max_weight) < 1 or walk_steps < 0:
        raise ValueError("invalid search bounds")
    started = time.monotonic()
    deadline = started+seconds
    count = len(pool.sources)
    identity = dict(pool_sha256=pool.sha256, code_sha256=code_hash(), seed=seed,
                    target=target, anchors=anchors, neighbors=neighbors,
                    walk_steps=walk_steps, max_weight=max_weight)
    rng = random.Random(seed)
    first = min(range(count), key=lambda i: (pool.vectors[i].bit_count(), i))
    state = dict(identity=identity, best_coeff=hex(1 << first), current_coeff=hex(1 << first),
                 phase="anchors", anchor=0, pair_i=0, pair_j=1, walk=0,
                 evaluations=0, accepted=0, improvements=0, local_pairs_checked=0,
                 local_cycle_minimum=False)
    if resume:
        state = json.loads(Path(checkpoint).read_text())
        if state["identity"] != identity:
            raise ValueError("checkpoint pool, parameters, or code differ")
        rng.setstate(_tuples(state["rng_state"]))
    best_coeff, current_coeff = int(state["best_coeff"], 16), int(state["current_coeff"], 16)
    best, current = pool.combine(best_coeff), pool.combine(current_coeff)
    # Small bounded nearest lists are computed with exact integer popcounts.
    near = []
    for vector in pool.vectors:
        if time.monotonic() >= deadline:
            break
        near.append(sorted(range(count), key=lambda j: ((vector ^ pool.vectors[j]).bit_count(), j))[:neighbors])
    order = sorted(range(count), key=lambda i: (pool.vectors[i].bit_count(), i))[:anchors]
    initial_evaluations = state["evaluations"]

    def update(candidate, coeff):
        nonlocal best, best_coeff
        if candidate.bit_count() < best.bit_count():
            best, best_coeff = candidate, coeff
            state["improvements"] += 1
            return True
        return False

    while (len(near) == count and time.monotonic() < deadline and
           state["evaluations"]-initial_evaluations < max_steps and best.bit_count() > target):
        phase = state["phase"]
        if phase == "anchors":
            if state["anchor"] >= len(order) or count < 2:
                state.update(phase="walk", pair_i=0, pair_j=1)
                current, current_coeff = best, best_coeff
                continue
            anchor = order[state["anchor"]]
            local = near[anchor]
            i, j = state["pair_i"], state["pair_j"]
            if i >= len(local)-1:
                state.update(anchor=state["anchor"]+1, pair_i=0, pair_j=1)
                continue
            a, b = local[i], local[j]
            candidate = pool.vectors[anchor] ^ pool.vectors[a] ^ pool.vectors[b]
            update(candidate, (1 << anchor) ^ (1 << a) ^ (1 << b))
            j += 1
            state.update(pair_i=i+(j == len(local)), pair_j=(i+2 if j == len(local) else j))
        elif phase == "walk":
            if state["walk"] >= walk_steps or count < 2:
                state.update(phase="local", pair_i=0, pair_j=1, local_pairs_checked=0)
                continue
            a = rng.randrange(count)
            b = rng.choice(near[a])
            candidate = current ^ pool.vectors[a] ^ pool.vectors[b]
            delta = candidate.bit_count()-current.bit_count()
            if candidate.bit_count() <= max(max_weight, best.bit_count()) and (
                    delta <= 0 or rng.random() < math.exp(-delta/2.0)):
                current = candidate
                current_coeff ^= (1 << a) ^ (1 << b)
                state["accepted"] += 1
                update(current, current_coeff)
            state["walk"] += 1
            if state["walk"] % 2000 == 0:
                current, current_coeff = best, best_coeff
        elif phase == "local":
            i, j = state["pair_i"], state["pair_j"]
            if i >= count-1:
                state.update(phase="done", local_cycle_minimum=True)
                break
            candidate = best ^ pool.vectors[i] ^ pool.vectors[j]
            improved = update(candidate, best_coeff ^ (1 << i) ^ (1 << j))
            state["local_pairs_checked"] += 1
            if improved:
                state.update(pair_i=0, pair_j=1, local_pairs_checked=0)
            else:
                j += 1
                state.update(pair_i=i+(j == count), pair_j=(i+2 if j == count else j))
        else:
            break
        state["evaluations"] += 1
    state.update(best_coeff=hex(best_coeff), current_coeff=hex(current_coeff), rng_state=rng.getstate(),
                 best_rank=best.bit_count())
    if checkpoint:
        save(checkpoint, state)
    candidate = pool.candidate(best_coeff, dict(method="exact-F2-affine-code-recombination",
        code_sha256=code_hash(), seed=seed, counters={k: state[k] for k in
            ("phase", "evaluations", "accepted", "improvements", "local_pairs_checked", "local_cycle_minimum")},
        budget=dict(seconds=seconds, max_steps=max_steps, anchors=anchors, neighbors=neighbors,
                    walk_steps=walk_steps, max_weight=max_weight), source_pool=pool.manifest()))
    report = verify_candidate(candidate, random_trials=8, seed=seed)
    if not report["valid"] or report["rank"] != best.bit_count():
        raise AssertionError("affine-code state failed independent exact verification")
    return candidate, report, state
