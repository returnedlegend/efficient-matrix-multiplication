"""Bounded exact recovery mixing and explicitly censored native difficulty probes.

No training or original v1/v2 code is changed. Failure of a finite probe is
UNKNOWN_WITHIN_PROBE, never a lower-bound proof or a new-rank claim.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

from mmsearch.rl_search import canonical_terms, gl_move, term_hash
from mmsearch.search import (_flip, _plus, _reduction, decode_candidate,
                             encode_candidate, residual)
from mmsearch.verify import verify_candidate


def freeze_json(directory, value):
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()
    digest = hashlib.sha256(payload).hexdigest()
    path = Path(directory)/(digest+".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise RuntimeError("immutable pool object collision")
    return {"path": str(path.resolve()), "sha256": digest}


def checked_terms(candidate, n):
    terms = canonical_terms(decode_candidate(candidate, n), n)
    normalized = encode_candidate(terms, n)
    if not verify_candidate(normalized, random_trials=0)["valid"]:
        raise ValueError("pool candidate failed independent exact verification")
    return terms


def bounded_mix(base, *, n, rng, known_rank=93, record_rank=92,
                steps=1000, max_rank=100, seconds=10, reduction_every=0):
    """Mix exact states while rejecting states at/below the known rank.

    A genuine record encountered in a proposed move is returned immediately,
    even though it lies below the mixing floor. Every proposed transition is
    checked exactly; periodic full independent checks guard common-code bugs.
    """
    base = canonical_terms(base, n)
    if len(base) != known_rank or residual(base, n):
        raise ValueError("mix requires an exact seed at the declared known rank")
    if not 1 <= record_rank < known_rank < max_rank or steps < 1 or seconds <= 0 or reduction_every < 0:
        raise ValueError("invalid bounded mixing configuration")
    current = gl_move(base, n, rng)
    started = time.monotonic()
    accepted = rejected_floor = rejected_cap = completed = reductions = 0
    rank_histogram = {}
    for iteration in range(steps):
        if time.monotonic()-started >= seconds:
            break
        if len(current) <= known_rank or iteration % 23 == 0:
            proposed = _plus(current, rng, False)
        elif reduction_every and iteration % reduction_every == 0:
            proposed = _reduction(current, False)
            reductions += 1
            if proposed is None:
                proposed = _flip(current, rng, False)
        else:
            proposed = _flip(current, rng, False)
        completed += 1
        if proposed is None:
            continue
        if residual(proposed, n):
            raise AssertionError("exact mixing operator changed tensor")
        if len(proposed) <= record_rank:
            candidate = encode_candidate(proposed, n, task_kind="VERIFIED_RECORD_FROM_MIXING")
            if not verify_candidate(candidate, random_trials=0)["valid"]:
                raise AssertionError("independent mixing record check failed")
            return proposed, {"status": "verified_record", "steps": completed,
                              "rank": len(proposed), "source_term_hash": term_hash(base)}
        if len(proposed) <= known_rank:
            rejected_floor += 1
            continue
        if len(proposed) > max_rank:
            rejected_cap += 1
            continue
        current = proposed
        accepted += 1
        rank_histogram[len(current)] = rank_histogram.get(len(current), 0)+1
        if iteration % 256 == 0 and not verify_candidate(encode_candidate(current, n), random_trials=0)["valid"]:
            raise AssertionError("independent mixing checkpoint failed")
    if not known_rank < len(current) <= max_rank:
        raise RuntimeError("mixing did not reach an inflated bounded state")
    if not verify_candidate(encode_candidate(current, n), random_trials=0)["valid"]:
        raise AssertionError("independent final mixing check failed")
    return current, {"status": "mixed", "steps": completed, "requested_steps": steps,
                     "accepted": accepted, "rejected_floor": rejected_floor,
                     "rejected_cap": rejected_cap, "reduction_attempts": reductions,
                     "rank_histogram": rank_histogram, "rank": len(current),
                     "source_term_hash": term_hash(base), "term_hash": term_hash(current),
                     "wall_seconds": time.monotonic()-started,
                     "reduction_every": reduction_every,
                     "immediate_reduction_available": _reduction(current, False) is not None,
                     "floor": known_rank+1, "cap": max_rank}


def probe_candidate(candidate, bridge, *, known_rank=93, record_rank=92,
                    seed=0, steps=50000, seconds=2, profile="exploit"):
    n = candidate["dimension"]
    initial_rank = len(checked_terms(candidate, n))
    result = bridge.run(candidate, action=profile, seconds=seconds, seed=seed,
                        target_rank=known_rank, step_limit=steps)
    if result.get("status") != "ok":
        return {"status": "incomplete_probe", "profile": profile, "record": None}
    best = result["best_candidate"]
    terms = checked_terms(best, n)
    rank = len(terms)
    # The native bridge also independently verifies every archived output.
    # Inspect any unexpectedly better archive rather than trusting only stats.
    for item in result.get("candidates", []):
        if item["rank"] <= record_rank:
            archived = json.loads(Path(item["path"]).read_text())
            archived_terms = checked_terms(archived, n)
            if len(archived_terms) < rank:
                best, terms, rank = archived, archived_terms, len(archived_terms)
    attempts = result.get("attempted_moves", 0)
    history = result.get("stats", {}).get("history", [])
    first_improvement = next((entry["step"] for entry in history
                              if entry.get("rank", initial_rank) < initial_rank), None)
    status = ("verified_record" if rank <= record_rank else
              "known_bound_recovered" if rank <= known_rank else
              "unknown_within_probe" if attempts >= steps else "incomplete_probe")
    return {"status": status, "profile": profile, "best_rank": rank,
            "initial_rank": initial_rank, "rank_reduction": initial_rank-rank,
            "first_improvement_step": first_improvement,
            "attempted_moves": attempts, "step_budget": steps, "seed": seed,
            "cpu_seconds": result.get("cpu_seconds", 0),
            "wall_seconds": result.get("wall_seconds", 0), "run_dir": result.get("run_dir"),
            "record": best if status == "verified_record" else None,
            "claim": "finite probe outcome; unsolved is not a hardness or nonexistence proof"}
