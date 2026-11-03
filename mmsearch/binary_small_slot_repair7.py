"""Exact3..6-slot conditional repairs for a compact binary approximation.

Other slots remain fixed. Complete negatives exclude only that selected repair,
never the whole CP rank. No source loading, N5 calls or publication here.
"""
import hashlib
import json
from itertools import combinations
import math

from . import binary_block_descent7 as block
from .compact_sat import BinaryBasis
from .compact_rank2_edges43 import solve_core as solve_one
from .surplus_two7 import solve_core as solve_two


def _images(packed, shape, guard):
    bases = []
    for axis in range(3):
        other = [j for j in range(3) if j != axis]
        vectors = []
        for j in range(shape[other[0]]):
            guard.check()
            for k in range(shape[other[1]]):
                vector = 0
                for i in range(shape[axis]):
                    xyz = [0, 0, 0]
                    xyz[axis], xyz[other[0]], xyz[other[1]] = i, j, k
                    index = (xyz[0] * shape[1] + xyz[1]) * shape[2] + xyz[2]
                    vector |= ((packed >> index) & 1) << i
                vectors.append(vector)
        bases.append(BinaryBasis(vectors))
    return bases


def _compact(packed, shape, bases, guard):
    dims = [len(b.vectors) for b in bases]
    projections = [[basis.coordinates(1 << j) for j in range(width)]
                   for basis, width in zip(bases, shape)]
    compressed = 0
    for index in block._bits(packed):
        guard.check()
        a, rem = divmod(index, shape[1] * shape[2])
        b, c = divmod(rem, shape[2])
        compressed ^= block._tensor([(projections[0][a], projections[1][b], projections[2][c])], dims)
    lifted = 0
    for index in block._bits(compressed):
        guard.check()
        a, rem = divmod(index, dims[1] * dims[2])
        b, c = divmod(rem, dims[2])
        lifted ^= block._tensor([(bases[0].vectors[a], bases[1].vectors[b], bases[2].vectors[c])], shape)
    if lifted != packed:
        raise AssertionError("actual-mode compaction did not restore every residual coefficient")
    return [(compressed >> i) & 1 for i in range(math.prod(dims))], dims


def repair_slots(core, shape, factors, selected, *, timeout_seconds=60, cancelled=None,
                 deadline_utc=block.DEADLINE, max_vectors=1023, max_extensions=1533):
    core, shape, factors = block._validate(core, shape, factors)
    selected = list(selected)
    if (not 3 <= len(selected) <= 6 or len(set(selected)) != len(selected)
            or any(type(i) is not int or not 0 <= i < len(factors) for i in selected)):
        raise ValueError("select3..6 distinct literal slot indices")
    if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 0 <= timeout_seconds <= 60:
        raise ValueError("small-slot timeout must be0..60s")
    guard = block._Guard(timeout_seconds, cancelled, deadline_utc)
    budget = len(selected)
    outside = [term for i, term in enumerate(factors) if i not in set(selected)]
    identity = dict(algorithm="exact_binary_small_slot_repair7", selected_slots=selected,
        local_budget=budget, old_slots=len(factors), fixed_outside_slots=len(outside),
        input_sha256=block._input_digest(core, shape),
        factor_state_sha256=hashlib.sha256(json.dumps(factors,separators=(",",":")).encode()).hexdigest(),
        fixed_outside_factors=[list(t) for t in outside],
        scope="only this selected-slot repair with all other factor points fixed",
        no_global_cp_negative_claim=True, publication_eligible=False, requires_ambient_verification=True)
    def finish(status, case, **kw):
        reason = guard.reason()
        if reason:status, case = "UNKNOWN", reason
        return dict(identity, status=status, complete=status != "UNKNOWN", case=case, **kw)
    try:
        guard.check()
        residual = block._packed(core) ^ block._tensor(outside, shape)
        bases = _images(residual, shape, guard)
        dims = [len(b.vectors) for b in bases]
        stats = dict(actual_mode_shape=dims, residual_mode_bases=[b.vectors for b in bases],
                     loss_before=block.residual_loss(core, shape, factors))
        if max(dims) > budget:
            return finish("REPAIR_EXCLUDED", "selected_residual_mode_rank_exceeds_slots", **stats)
        if not residual:
            products = []
            decoder = dict(status="SAT", complete=True, case="zero_selected_residual", products=[])
        else:
            compact, dims = _compact(residual, shape, bases, guard)
            axis = max(range(3), key=lambda j: (dims[j], -j))
            d = dims[axis]
            stats.update(compact_core_sha256=hashlib.sha256(bytes(compact)).hexdigest(), compact_entries=len(compact),
                         chosen_axis=axis, surplus=budget-d)
            if budget > d + 2:
                decoder = solve_one(compact,dims,d+1,axis=axis,max_vectors=max_vectors,
                                    cancelled=lambda:guard.reason() is not None)
                guard.check()
                if decoder["status"]!="SAT":
                    return finish("UNKNOWN", "unsupported_selected_residual_surplus", **stats)
            elif budget <= d + 1:
                decoder = solve_one(compact, dims, budget, axis=axis,
                                    max_vectors=max_vectors, cancelled=lambda:guard.reason() is not None)
            else:
                decoder = solve_two(compact, dims, budget, axis=axis, max_vectors=max_vectors,
                    max_extensions=max_extensions, cancelled=lambda:guard.reason() is not None,
                    timeout_seconds=max(0, guard.seconds-(__import__('time').monotonic()-guard.started)),
                    deadline_utc=deadline_utc)
            guard.check()
            if decoder["status"] == "LOCAL_UNSAT" and decoder.get("complete"):
                return finish("REPAIR_EXCLUDED", "exact_selected_residual_negative", decoder_case=decoder.get("case"), **stats)
            if decoder["status"] != "SAT":
                return finish("UNKNOWN", "selected_residual_decoder_incomplete", decoder_case=decoder.get("case"), **stats)
            products = []
            for term in decoder["products"]:
                lifted = []
                for mask, basis in zip(term, bases):
                    lifted.append(basis.expand(mask))
                products.append(tuple(lifted))
        result_factors = outside + products
        if (len(products) > budget or block.residual_loss(core, shape, result_factors)
                or block.scalar_loss(core, shape, result_factors)):
            raise AssertionError("joint slot repair failed the complete original compact tensor")
        guard.check()
        return finish("RAW_EXACT_COMPACT", "exact_joint_slot_replacement", loss_after=0,
            factors=[list(t) for t in result_factors], replacement_products=[list(t) for t in products],
            full_compact_entries_checked=len(core), decoder_case=decoder.get("case"), **stats)
    except block._Stopped as exc:
        return finish("UNKNOWN", str(exc))


def propose_slot_sets(core, shape, factors, *, sizes=(3, 4), max_examined=2048, limit=24,
                      timeout_seconds=60, cancelled=None, deadline_utc=block.DEADLINE):
    """Rank missing residual image directions cheaply; does not call a decoder."""
    core, shape, factors = block._validate(core, shape, factors)
    if any(type(s) is not int or not 3 <= s <= 6 for s in sizes):raise ValueError("slot sizes3..6 only")
    if type(timeout_seconds) not in (int,float) or not math.isfinite(timeout_seconds) or not 0<=timeout_seconds<=60:
        raise ValueError("slot-selection timeout must be0..60s")
    block._integer(max_examined, "selection cap", 0, 2048)
    block._integer(limit, "selection output cap", 0, 128)
    guard = block._Guard(timeout_seconds, cancelled, deadline_utc)
    candidates = []
    examined = 0
    try:
        guard.check()
        residual = block._packed(core) ^ block._tensor(factors, shape)
        images = _images(residual, shape, guard)
        for size in sizes:
            for slots in combinations(range(len(factors)), size):
                guard.check()
                if examined >= max_examined:
                    return dict(status="UNKNOWN", complete=False, case="slot_selection_cap",
                        examined=examined, proposals=sorted(candidates, key=lambda r:r["score"])[:limit], decoder_calls=0)
                missing = []
                for axis in range(3):
                    selected_basis = BinaryBasis([factors[i][axis] for i in slots])
                    joined = BinaryBasis(selected_basis.vectors + images[axis].vectors)
                    missing.append(len(joined.vectors) - len(selected_basis.vectors))
                candidates.append(dict(slots=list(slots), missing_image_dimensions=missing,
                                       score=[sum(missing), max(missing), size, *slots]))
                examined += 1
        guard.check()
        return dict(status="SLOT_PROPOSALS_ONLY", complete=True, examined=examined,
                    proposals=sorted(candidates, key=lambda r:r["score"])[:limit], decoder_calls=0,
                    no_cp_feasibility_claim=True)
    except block._Stopped as exc:
        return dict(status="UNKNOWN", complete=False, case=str(exc), examined=examined,
                    proposals=sorted(candidates, key=lambda r:r["score"])[:limit], decoder_calls=0)
