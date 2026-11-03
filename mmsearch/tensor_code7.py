"""Exact full rank-one atom binary code. No fixed/free factor projection.

A column contains all n**6 tensor coefficients. A state chooses whole (u,v,w)
triples, and every proposed move belongs to the complete column kernel over F2.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import random
from typing import Callable

from mmsearch.verify import verify_candidate

SCHEMA = "tensor_code7.v1"
AXES = ("u", "v", "w")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def strict_load(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=unique)


def supports(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def atom_from_term(term, n):
    if type(term) is not dict or set(term) != set(AXES):
        raise ValueError("term must have exactly u,v,w")
    answer = []
    for axis in AXES:
        vector = term[axis]
        if type(vector) is not list or len(vector) != n*n:
            raise ValueError("wrong vector width")
        if any(type(x) is not int or x not in (0, 1) for x in vector):
            raise ValueError("only literal integer 0/1 coefficients are accepted")
        value = sum(x << i for i, x in enumerate(vector))
        if not value:
            raise ValueError("zero rank-one factor rejected")
        answer.append(value)
    return tuple(answer)


def term_from_atom(atom, n):
    if len(atom) != 3 or any(type(v) is not int or v <= 0 or v >= 1 << (n*n) for v in atom):
        raise ValueError("invalid atom bitmask")
    return {axis: [(value >> j) & 1 for j in range(n*n)] for axis, value in zip(AXES, atom)}


def atom_column(atom, n):
    # Validate before shifting: arbitrary-size or negative inputs must not loop.
    term_from_atom(atom, n)
    width = n*n
    column = 0
    for a in supports(atom[0]):
        for b in supports(atom[1]):
            for c in supports(atom[2]):
                column |= 1 << ((a*width+b)*width+c)
    return column


def target_tensor(n):
    if type(n) is not int or n < 1:
        raise ValueError("positive integer dimension required")
    out = 0
    w = n*n
    for i in range(n):
        for j in range(n):
            for k in range(n):
                out |= 1 << (((i*n+j)*w+j*n+k)*w+k*n+i)
    return out


def xor_columns(columns, state):
    if type(state) is not int or state < 0 or state.bit_length() > len(columns):
        raise ValueError("state outside dictionary")
    result = 0
    for i in supports(state):
        result ^= columns[i]
    return result


def validate_kernel(columns, cycles):
    seen = set()
    for cycle in cycles:
        if not cycle or cycle in seen or xor_columns(columns, cycle):
            raise ValueError("nonzero/duplicate/invalid kernel vector")
        seen.add(cycle)
    # Linear independence of a fundamental kernel basis is independently checked.
    pivots = {}
    for cycle in cycles:
        value = cycle
        while value:
            p = value.bit_length()-1
            if p not in pivots:
                pivots[p] = value
                break
            value ^= pivots[p]
        if not value:
            raise ValueError("dependent kernel basis")
    return True


def fundamental_kernel(columns, order=None, guard: Callable[[], None] | None = None):
    """Column Gaussian elimination with bitpacked exact coefficient witnesses."""
    count = len(columns)
    order = list(range(count)) if order is None else list(order)
    if sorted(order) != list(range(count)):
        raise ValueError("order must be a permutation")
    pivots, cycles = {}, []
    for index in order:
        if guard:
            guard()
        value, witness = columns[index], 1 << index
        while value:
            pivot = value.bit_length()-1
            previous = pivots.get(pivot)
            if previous is None:
                pivots[pivot] = value, witness
                break
            value ^= previous[0]
            witness ^= previous[1]
        if not value:
            cycles.append(witness)
    validate_kernel(columns, cycles)
    if len(pivots) + len(cycles) != count:
        raise AssertionError("rank-nullity failure")
    return cycles, len(pivots)


def second_check(candidate):
    """Independent coefficient checker with scalar indexing and XOR arrays."""
    n = candidate["dimension"]
    width = n*n
    observed = bytearray(n**6)
    for term in candidate["terms"]:
        atom_from_term(term, n)
        for a in range(width):
            if not term["u"][a]:
                continue
            for b in range(width):
                if not term["v"][b]:
                    continue
                for c in range(width):
                    if term["w"][c]:
                        observed[(a*width+b)*width+c] ^= 1
    mismatches = 0
    for a in range(width):
        i, j = divmod(a, n)
        for b in range(width):
            jj, k = divmod(b, n)
            for c in range(width):
                kk, ii = divmod(c, n)
                mismatches += observed[(a*width+b)*width+c] != int(j == jj and k == kk and i == ii)
    return {"valid": mismatches == 0, "exact_entries_checked": n**6, "mismatch_count": mismatches,
            "checker": "tensor_code7 scalar XOR array"}


def checked_candidate(atoms, state, n, guard=None):
    candidate = {"field": 2, "dimension": n,
                 "terms": [term_from_atom(atoms[i], n) for i in supports(state)],
                 "metadata": {"method": SCHEMA, "rank": state.bit_count(), "novelty_claim": False,
                              "third_factor": "trace: w[k*n+i] contributes to output[i][k]"}}
    first = verify_candidate(candidate, random_trials=8, seed=7)
    if guard:
        guard("post_full_tensor")
    second = second_check(candidate)
    if guard:
        guard("post_independent")
    if not first["valid"] or not second["valid"]:
        raise ValueError("independent full tensor candidate verification failed")
    return candidate, {"standard": first, "scalar": second}


def prepare(candidates, cap=5000, guard=None):
    if not candidates or type(cap) is not int or cap < 1 or cap > 5000:
        raise ValueError("nonempty candidates and dictionary cap 1..5000 required")
    n = candidates[0].get("dimension")
    if type(n) is not int or n < 1:
        raise ValueError("invalid dimension")
    atoms, atom_ids, seeds, seed_terms = [], {}, [], []
    for candidate in candidates:
        if guard:
            guard()
        if type(candidate.get("dimension")) is not int or candidate.get("dimension") != n or type(candidate.get("field")) is not int or candidate.get("field") != 2:
            raise ValueError("all inputs must be same dimension and F2")
        terms = [atom_from_term(t, n) for t in candidate["terms"]]
        if not verify_candidate(candidate, random_trials=8, seed=7)["valid"] or not second_check(candidate)["valid"]:
            raise ValueError("source seed failed exact tensor checks")
        additions = list(dict.fromkeys(t for t in terms if t not in atom_ids))
        # Never truncate a seed: either its whole exact state fits, or reject.
        if len(atoms)+len(additions) > cap:
            raise ValueError("dictionary cap would truncate an approved seed; use a smaller explicit source list")
        for atom in additions:
            atom_ids[atom] = len(atoms)
            atoms.append(atom)
        state = 0
        for atom in terms:
            state ^= 1 << atom_ids[atom]
        seeds.append(state)
        seed_terms.append(len(terms))
    columns = [atom_column(a, n) for a in atoms]
    target = target_tensor(n)
    if any(xor_columns(columns, x) != target for x in seeds):
        raise AssertionError("prepared seed not exact")
    cycles, rank = fundamental_kernel(columns, guard=guard)
    document = {"schema": SCHEMA, "dimension": n, "field": 2, "tensor_entries": n**6,
                "atoms": [list(a) for a in atoms], "columns_hex": [hex(c) for c in columns],
                "target_hex": hex(target), "seed_states_hex": [hex(x) for x in seeds],
                "seed_supplied_terms": seed_terms, "seed_weights": [x.bit_count() for x in seeds],
                "kernel_hex": [hex(z) for z in cycles], "dictionary_size": len(atoms),
                "rank": rank, "nullity": len(cycles), "dictionary_sha256": digest(atoms),
                "columns_sha256": digest([hex(c) for c in columns]),
                "scope": "whole rank-one triples; complete n**6 binary tensor equations; no novelty claim"}
    return document


def validate_prepared(document, guard=None):
    if document.get("schema") != SCHEMA or type(document.get("field")) is not int or document.get("field") != 2:
        raise ValueError("wrong prepared schema/field")
    n = document["dimension"]
    for key in ("dimension", "tensor_entries", "dictionary_size", "rank", "nullity"):
        if type(document.get(key)) is not int or document[key] < (1 if key in ("dimension", "tensor_entries") else 0):
            raise ValueError(f"invalid integer metadata: {key}")
    if any(type(w) is not int or w < 0 for w in document["seed_weights"]):
        raise ValueError("invalid integer seed weights")
    atoms = [tuple(a) for a in document["atoms"]]
    if len(atoms) > 5000 or len(set(atoms)) != len(atoms):
        raise ValueError("invalid dictionary")
    columns = []
    for atom in atoms:
        if guard:
            guard()
        columns.append(atom_column(atom, n))
    if document["columns_hex"] != [hex(c) for c in columns]:
        raise ValueError("corrupted column: does not equal full atom tensor")
    if document["target_hex"] != hex(target_tensor(n)) or document["tensor_entries"] != n**6:
        raise ValueError("incorrect full target")
    if document["dictionary_sha256"] != digest(atoms) or document["columns_sha256"] != digest(document["columns_hex"]):
        raise ValueError("dictionary/column hash mismatch")
    cycles = [int(z, 16) for z in document["kernel_hex"]]
    validate_kernel(columns, cycles)
    _fresh, rank = fundamental_kernel(columns, guard=guard)
    if rank != document["rank"] or len(cycles) != len(columns)-rank or document["nullity"] != len(cycles):
        raise ValueError("rank/nullity or kernel completeness mismatch")
    seeds = [int(x, 16) for x in document["seed_states_hex"]]
    if not seeds or any(xor_columns(columns, x) != target_tensor(n) for x in seeds):
        raise ValueError("nonexact seed")
    if document["seed_weights"] != [x.bit_count() for x in seeds] or document["dictionary_size"] != len(atoms):
        raise ValueError("prepared metadata mismatch")
    return atoms, columns, seeds, cycles


def cycle_delta(state, cycle):
    return cycle.bit_count() - 2*(state & cycle).bit_count()


@dataclass
class Walk:
    """Serializable search cursor; every random choice comes from this RNG."""
    state: int
    best: int
    restart: int = 0
    step: int = 0
    no_improvement: int = 0
    moves: int = 0

    def to_json(self):
        return {"state_hex": hex(self.state), "best_hex": hex(self.best), "restart": self.restart,
                "step": self.step, "no_improvement": self.no_improvement, "moves": self.moves}

    @classmethod
    def from_json(cls, value):
        for key in ("restart", "step", "no_improvement", "moves"):
            if type(value.get(key)) is not int or value[key] < 0:
                raise ValueError("invalid checkpoint counter")
        if value["moves"] > value["step"] or value["no_improvement"] > value["step"] or value["restart"] > value["step"]:
            raise ValueError("inconsistent checkpoint counters")
        if int(value["best_hex"], 16) < 0 or int(value["state_hex"], 16) < 0:
            raise ValueError("negative checkpoint state")
        if int(value["best_hex"], 16).bit_count() > int(value["state_hex"], 16).bit_count():
            raise ValueError("checkpoint best is worse than state")
        return cls(int(value["state_hex"], 16), int(value["best_hex"], 16),
                   value["restart"], value["step"], value["no_improvement"], value["moves"])


def choose_move(state, cycles, rng, ceiling, samples=256, guard=None):
    """Steepest single-cycle improvement plus sampled exact multi-cycle jumps.

    All single fundamental cycles are scored. Sampled pairs and larger XORs can
    expose reductions hidden by individual deltas. At a plateau, neutral moves
    and bounded temporary increases diversify the exact state.
    """
    if type(samples) is not int or not 0 <= samples <= 4096:
        raise ValueError("samples outside reviewed 0..4096 bound")
    if not cycles:
        return None, "no_kernel"
    choices = list(cycles)
    for _ in range(samples):
        if guard:
            guard()
        move = 0
        degree = rng.choice((2, 2, 3, 4, 6, 8))
        for index in rng.sample(range(len(cycles)), min(degree, len(cycles))):
            move ^= cycles[index]
        if move:
            choices.append(move)
    scored = []
    for z in choices:
        if guard:
            guard()
        scored.append((cycle_delta(state, z), z))
    best = min(delta for delta, _ in scored)
    if best < 0:
        return rng.choice([z for delta, z in scored if delta == best]), "steepest_negative"
    neutral = [z for delta, z in scored if delta == 0]
    if neutral and rng.random() < .8:
        return rng.choice(neutral), "neutral"
    bounded = [z for delta, z in scored if state.bit_count()+delta <= ceiling]
    if bounded:
        return rng.choice(bounded), "bounded_temporary"
    return None, "ceiling"


def rng_restore(value):
    def tuple_tree(v):
        return tuple(tuple_tree(x) for x in v) if isinstance(v, list) else v
    rng = random.Random()
    rng.setstate(tuple_tree(value))
    return rng
