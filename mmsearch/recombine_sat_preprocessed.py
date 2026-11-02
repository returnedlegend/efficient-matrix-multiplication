"""Exact RREF and affine-class preprocessing for fixed-dictionary subset SAT.

Original term indicator IDs remain available to the independent decoder.
Forced terms and affine pair classes only simplify the cardinality constraint;
this transformation preserves every feasible dictionary subset.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
from pathlib import Path

from .recombine import digest
from .recombine_sat import bits, row_reduce


def _proof_sum(mask, proofs):
    result = 0
    for i in bits(mask):
        result ^= proofs[i]
    return result


def preprocess_rows(rows, variables, proofs=None):
    """Return equivalent original-ID links, representative XORs and exact cost.

    An augmented row uses coefficient bits0..variables-1 and RHS bitvariables.
    Proofs identify XOR combinations of original ambient tensor equations.
    """
    if type(variables) is not int or variables < 1 or any(type(r) is not int or r < 0 or r >> (variables+1) for r in rows):
        raise ValueError("invalid augmented GF2 rows")
    if proofs is not None and len(proofs) != len(rows):
        raise ValueError("one proof per row is required")
    basis, combinations = row_reduce(rows, variables)
    witnesses = combinations if proofs is None else [_proof_sum(c, proofs) for c in combinations]
    mask = (1 << variables)-1
    if any(not r & mask and r >> variables for r in basis):
        return dict(contradiction=True, clauses=[[]], xors=[], cardinality_literals=[],
                    constant_cost=0, rref_rows=basis, rref_proofs=witnesses, classes=[],
                    substituted_row_proofs=[], forced_ones=0, forced_zeros=0)
    pivots = [((r & mask) & -(r & mask)).bit_length()-1 for r in basis]
    for j in reversed(range(len(basis))):
        pivot_bit = 1 << pivots[j]
        for i in range(j):
            if basis[i] & pivot_bit:
                basis[i] ^= basis[j]
                witnesses[i] ^= witnesses[j]
    parent, parity = list(range(variables)), [0]*variables

    def find(x):
        if parent[x] != x:
            previous = parent[x]
            parent[x] = find(previous)
            parity[x] ^= parity[previous]
        return parent[x]

    for row in basis:
        coeff = row & mask
        if coeff.bit_count() != 2:
            continue
        x, y = list(bits(coeff))
        rx, ry = find(x), find(y)
        relation = parity[x] ^ parity[y] ^ (row >> variables)
        if rx == ry:
            if relation:
                raise AssertionError("RREF pair equations contradict")
        else:
            high, low = max(rx, ry), min(rx, ry)
            parent[high], parity[high] = low, relation
    forced = {}
    for row in basis:
        coeff = row & mask
        if coeff.bit_count() == 1:
            x = coeff.bit_length()-1
            root = find(x)
            value = parity[x] ^ (row >> variables)
            if root in forced and forced[root] != value:
                raise AssertionError("RREF units contradict")
            forced[root] = value
    groups = defaultdict(list)
    for x in range(variables):
        groups[find(x)].append((x, parity[x]))
    clauses, literals, classes = [], [], []
    constant, forced_ones, forced_zeros = 0, 0, 0
    for root, members in sorted(groups.items()):
        rep = root+1
        for x, offset in members:
            variable = x+1
            if x == root:
                continue
            clauses.extend([[variable, rep], [-variable, -rep]] if offset else
                           [[-variable, rep], [variable, -rep]])
        positives = sum(offset == 0 for x, offset in members)
        negatives = len(members)-positives
        fixed = forced.get(root)
        if fixed is not None:
            clauses.append([rep if fixed else -rep])
            cost = positives*fixed+negatives*(1-fixed)
            constant += cost
            forced_ones += cost
            forced_zeros += len(members)-cost
            weight, literal = 0, None
        else:
            constant += min(positives, negatives)
            weight = abs(positives-negatives)
            literal = rep if positives > negatives else -rep
            literals.extend([literal]*weight)
        classes.append(dict(representative=rep, members=[dict(variable=x+1, xor_offset=p) for x, p in members],
            positive_count=positives, negative_count=negatives, forced_value=fixed,
            cost_constant=(positives*fixed+negatives*(1-fixed) if fixed is not None else min(positives, negatives)),
            weighted_literal=literal, weight=weight))
    xors, substituted_proofs = [], []
    for row, witness in zip(basis, witnesses):
        rhs, coeff = row >> variables, 0
        for x in bits(row & mask):
            root = find(x)
            rhs ^= parity[x]
            if root in forced:
                rhs ^= forced[root]
            else:
                coeff ^= 1 << root
        if coeff:
            xors.append(([i+1 for i in bits(coeff)], bool(rhs)))
            substituted_proofs.append(witness)
        elif rhs:
            raise AssertionError("affine class substitution produced contradiction")
    return dict(contradiction=False, clauses=clauses, xors=xors, cardinality_literals=literals,
                constant_cost=constant, rref_rows=basis, rref_proofs=witnesses, classes=classes,
                substituted_row_proofs=substituted_proofs, forced_ones=forced_ones, forced_zeros=forced_zeros)


def weighted_cardinality(literals, bound, variables, encoding="cardnetwrk"):
    """Repeated signed literals encode nonnegative integer weights exactly."""
    if type(bound) is not int or type(variables) is not int or variables < 1 or any(
            type(lit) is not int or not 1 <= abs(lit) <= variables for lit in literals):
        raise ValueError("invalid weighted cardinality")
    if encoding not in ("cardnetwrk", "totalizer", "seqcounter"):
        raise ValueError("invalid cardinality encoder")
    if bound < 0:
        return [[]], variables
    if bound >= len(literals):
        return [], variables
    from pysat.card import CardEnc, EncType
    card = CardEnc.atmost(lits=literals, bound=bound, top_id=variables, encoding=getattr(EncType, encoding))
    return list(card.clauses), max(variables, card.nv)


def build_problem(system, rank=92, encoding="cardnetwrk"):
    if type(rank) is not int or rank < 0:
        raise ValueError("invalid rank bound")
    count = len(system["dictionary"])
    pre = preprocess_rows(system["reduced"], count, system["proofs"])
    remaining = rank-pre["constant_cost"]
    cardinality, nv = weighted_cardinality(pre["cardinality_literals"], remaining, count, encoding)
    clauses = pre["clauses"]+cardinality
    metadata = dict(system["metadata"], rank_bound=rank, cardinality_encoding=encoding,
        selection_variable_map="dictionary index i maps to original indicator variable i+1",
        selection_variables=count, solver_threads=1, variables=nv, cnf_clauses=len(clauses),
        native_xors=len(pre["xors"]), preprocessing=dict(
            method="exact-RREF-affine-pair-classes-signed-weighted-cardinality-v1",
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            forced_ones=pre["forced_ones"], forced_zeros=pre["forced_zeros"],
            cardinality_constant=pre["constant_cost"], residual_cardinality_bound=remaining,
            weighted_literal_count=len(pre["cardinality_literals"]),
            classes=pre["classes"], contradiction=pre["contradiction"],
            rref_augmented_rows_hex=[hex(r) for r in pre["rref_rows"]],
            rref_original_row_xor_witnesses_hex=[hex(r) for r in pre["rref_proofs"]],
            substituted_row_original_xor_witnesses_hex=[hex(r) for r in pre["substituted_row_proofs"]],
            proof_policy="substituted rows additionally use the explicit forced/equivalence CNF links"))
    metadata["formula_sha256"] = digest(dict(nv=nv, clauses=clauses, xors=pre["xors"]))
    return dict(nv=nv, clauses=clauses, xors=pre["xors"], metadata=metadata, system=system)
