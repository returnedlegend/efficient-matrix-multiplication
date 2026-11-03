"""One-round, witnessed rank-one closure of an orientation's fixed pairs.

The new atoms broaden group choices without changing the linear column span.
Dummy free masks in emitted dictionaries are not matrix-multiplication algorithms.
No solver is called by this script.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import hashlib
import itertools
import json
from pathlib import Path
import random
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from mmsearch.free_factor_sat import ORIENTATIONS, audit, build_system, canonical_pairs, estimate_formula
from mmsearch.recombine import digest, save
from mmsearch.verify import verify_candidate


def outer_mask(pair, width):
    a, b = pair
    result = 0
    while a:
        bit = a & -a
        i = bit.bit_length()-1
        result |= b << (i*width)
        a ^= bit
    return result


def gf2_column_rank(columns):
    basis = {}
    for column in columns:
        while column:
            pivot = column.bit_length()-1
            if pivot in basis:
                column ^= basis[pivot]
            else:
                basis[pivot] = column
                break
    return len(basis)


def _candidate_stream(old_pairs, shared_axis, rng):
    """Round-robin shared-factor buckets, using only original pair indices."""
    groups = defaultdict(list)
    for index, pair in enumerate(old_pairs):
        groups[pair[shared_axis]].append(index)
    keys = sorted(key for key, members in groups.items() if len(members) > 1)
    rng.shuffle(keys)
    queue = deque()
    for key in keys:
        members = groups[key]
        rng.shuffle(members)
        queue.append(iter(itertools.combinations(members, 2)))
    while queue:
        candidates = queue.popleft()
        try:
            first, second = next(candidates)
        except StopIteration:
            continue
        queue.append(candidates)
        parent_a, parent_b = old_pairs[first], old_pairs[second]
        pair = list(parent_a)
        pair[1-shared_axis] ^= parent_b[1-shared_axis]
        yield tuple(pair), tuple(sorted((first, second)))


def augment_pairs(pairs, width, max_pairs=1536, seed=20261102, orientation="uv"):
    if (type(width) is not int or width < 1 or type(max_pairs) is not int or max_pairs < 0 or
            type(seed) is not int or orientation not in ORIENTATIONS):
        raise ValueError("invalid augmentation parameters")
    normalized = set()
    for pair in pairs:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2 or
                any(type(v) is not int or v < 0 or v >> width for v in pair)):
            raise ValueError("pairs must contain two in-range integer masks")
        if all(pair):
            normalized.add(tuple(pair))
    old_pairs = tuple(sorted(normalized))
    if max_pairs < len(old_pairs):
        raise ValueError("max-pairs cannot remove original pairs")
    seen = set(old_pairs)
    streams = [_candidate_stream(old_pairs, axis, random.Random(f"{seed}:{orientation}:{axis}"))
               for axis in range(2)]
    exhausted, selected, accepted = [False, False], [], [0, 0]
    rejected = dict(zero=0, duplicate=0)
    next_axis = seed % 2
    while len(seen) < max_pairs and not all(exhausted):
        axis = next_axis
        next_axis = 1-axis
        if exhausted[axis]:
            continue
        while True:
            try:
                pair, parents = next(streams[axis])
            except StopIteration:
                exhausted[axis] = True
                break
            if not all(pair):
                rejected["zero"] += 1
                continue
            if pair in seen:
                rejected["duplicate"] += 1
                continue
            first, second = (old_pairs[i] for i in parents)
            column = outer_mask(pair, width)
            if column != outer_mask(first, width) ^ outer_mask(second, width):
                raise AssertionError("rank-one pair XOR identity failed")
            seen.add(pair)
            accepted[axis] += 1
            selected.append(dict(pair=list(pair), shared_fixed_axis=axis, xor_fixed_axis=1-axis,
                parent_pair_indices=list(parents), parent_pairs=[list(first), list(second)],
                outer_column_hex=hex(column), outer_xor_verified=True))
            break
    result_pairs = tuple(sorted(seen))
    old_rank = gf2_column_rank(outer_mask(pair, width) for pair in old_pairs)
    new_rank = gf2_column_rank(outer_mask(pair, width) for pair in result_pairs)
    if new_rank != old_rank:
        raise AssertionError("one-round closure changed the exact column span")
    return dict(old_pairs=old_pairs, pairs=result_pairs, witnesses=selected,
        metadata=dict(orientation=orientation, width=width, seed=seed,
            max_pairs=max_pairs, old_pair_count=len(old_pairs), new_pair_count=len(result_pairs),
            target_reached=len(result_pairs) == max_pairs, added_pairs=len(selected),
            shared_first_additions=accepted[0], shared_second_additions=accepted[1],
            old_column_rank=old_rank, new_column_rank=new_rank,
            old_pairs_sha256=digest(old_pairs), new_pairs_sha256=digest(result_pairs),
            rejected=rejected, generation_rounds=1, parents_policy="original pairs only",
            selection_policy="seeded bucket round robin; alternate accepted shared-first/shared-second additions until an axis is exhausted"))


def augmented_dictionary(dictionary, closure, orientation):
    first, second, free = ORIENTATIONS[orientation]
    result = [list(term) for term in dictionary]
    for witness in closure["witnesses"]:
        triple = [0, 0, 0]
        triple[first], triple[second] = witness["pair"]
        triple[free] = 1
        if not all(triple):
            raise AssertionError("dummy dictionary triple must be nonzero in every factor")
        result.append(triple)
    return result


def _summary(system):
    metadata = system["metadata"]
    return dict(pair_count=metadata["pair_count"], linear_rank=metadata["linear_rank"],
        linear_nullity=metadata["linear_nullity"], forced_active=metadata["forced_active"],
        forced_zero=metadata["forced_zero"], inconsistent=metadata["linear_inconsistent"],
        baseline_merged_rank=metadata["baseline"]["merged_rank"],
        formula_memory_estimate=estimate_formula(system, 92))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--orientation", choices=["uv", "vw", "wu", "all"], required=True)
    parser.add_argument("--max-pairs", type=int, default=1536)
    parser.add_argument("--seed", type=int, default=20261102)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.max_pairs < 0:
        parser.error("max-pairs must be nonnegative")
    started = time.monotonic()
    root = args.outdir
    root.mkdir(parents=True, exist_ok=False)
    provenance = dict(inputs=[], code_sha256={})
    for path, name in ((args.dictionary, "dictionary.json"), (args.baseline, "baseline.json")):
        raw = path.read_bytes()
        snapshot = root/"inputs"/name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(raw)
        provenance["inputs"].append(dict(path=str(path.resolve()), snapshot=str(snapshot.resolve()),
            raw_sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)))
    dictionary = json.loads((root/"inputs/dictionary.json").read_bytes())
    baseline = json.loads((root/"inputs/baseline.json").read_bytes())
    report = verify_candidate(baseline, random_trials=16)
    if not report["valid"] or baseline["field"] != 2:
        raise ValueError("baseline must pass independent exact F2 tensor verification")
    dimension = baseline["dimension"]
    # The campaign inputs and all emitted dummy triples are legitimate nonzero
    # rank-one atoms; an atom list itself is not asserted to be an algorithm.
    bound = 1 << dimension**2
    if (not isinstance(dictionary, list) or any(not isinstance(t, (list, tuple)) or len(t) != 3 or
            any(type(x) is not int or not 0 < x < bound for x in t) for t in dictionary)):
        raise ValueError("dictionary must contain nonzero in-range integer mask triples")
    files = [Path(__file__), REPO/"tests/test_augment_factor_pairs.py",
        REPO/"mmsearch/free_factor_sat.py", REPO/"mmsearch/recombine.py",
        REPO/"mmsearch/recombine_sat.py", REPO/"mmsearch/verify.py", REPO/"mmsearch/__init__.py"]
    for path in files:
        raw = path.read_bytes()
        relative = path.relative_to(REPO)
        destination = root/"code"/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        provenance["code_sha256"][str(relative)] = hashlib.sha256(raw).hexdigest()
    provenance.update(seed=args.seed, max_pairs=args.max_pairs,
        baseline_verification=report, orientation_files_policy="each file contains only its own orientation's additions",
        claim="old assignments remain included; each new outer column is the XOR of two old columns; no rank-92 feasibility or integer lift claim")
    save(root/"provenance.json", provenance)
    orientations = ["uv", "vw", "wu"] if args.orientation == "all" else [args.orientation]
    summaries = []
    for orientation in orientations:
        old_pairs = canonical_pairs(dictionary, dimension, orientation)
        closure = augment_pairs(old_pairs, dimension**2, args.max_pairs, args.seed, orientation)
        output = augmented_dictionary(dictionary, closure, orientation)
        output_pairs = canonical_pairs(output, dimension, orientation)
        if output_pairs != closure["pairs"]:
            raise AssertionError("orientation-specific dummy mapping changed the selected pair set")
        old_system = build_system(dictionary, dimension, orientation, baseline, provenance)
        new_system = build_system(output, dimension, orientation, baseline, provenance)
        if not (old_system["metadata"]["linear_rank"] == new_system["metadata"]["linear_rank"] ==
                closure["metadata"]["old_column_rank"]):
            raise AssertionError("independent column-rank and packed-RREF ranks disagree")
        if old_system["metadata"]["baseline"]["merged_rank"] != new_system["metadata"]["baseline"]["merged_rank"]:
            raise AssertionError("new zero-initialized groups changed the baseline")
        directory = root/orientation
        save(directory/"dictionary.json", output)
        save(directory/"witnesses.json", dict(metadata=closure["metadata"],
            old_pairs=[list(p) for p in old_pairs], witnesses=closure["witnesses"],
            outer_layout="bit a*width+b is fixed-pair outer-product coefficient (a,b)"))
        save(directory/"old.system.audit.json", audit(old_system))
        save(directory/"new.system.audit.json", audit(new_system))
        summary = dict(orientation=orientation, **{k:v for k,v in closure["metadata"].items() if k != "orientation"},
            old=_summary(old_system), new=_summary(new_system),
            dictionary_path=str((directory/"dictionary.json").resolve()),
            dictionary_raw_sha256=hashlib.sha256((directory/"dictionary.json").read_bytes()).hexdigest(),
            dictionary_canonical_sha256=new_system["metadata"]["input_dictionary_sha256"],
            triple_count=len(output))
        save(directory/"manifest.json", summary)
        summaries.append(summary)
        del old_system, new_system
    result = dict(status="READY" if all(s["target_reached"] for s in summaries) else "INSUFFICIENT_CANDIDATES",
        elapsed_seconds=time.monotonic()-started, orientations=summaries, solver_called=False,
        scope=provenance["claim"], provenance_sha256=hashlib.sha256((root/"provenance.json").read_bytes()).hexdigest())
    save(root/"result.json", result)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
