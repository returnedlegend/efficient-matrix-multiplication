"""Generate exact F2 seeds outside one frozen short-circuit kernel span.

This is algebraic diversification, never SAT/UNSAT or full-algorithm
inequivalence evidence. No search worker or solver is launched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from mmsearch.free_factor_sat import build_system
from mmsearch.kernel_coset_seeds import (apply_shift_checked, build_span, circuit_masks,
    exclusive, freeze_first_record, fundamental_kernel, nonmembership_proof,
    pair_column, pw_rows, score_shift)
from mmsearch.recombine import digest


def load_json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique)


def freeze_json(path, value):
    exclusive(path, (json.dumps(value, sort_keys=True, indent=2)+"\n").encode())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--dictionary", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--max-seeds", type=int, default=16)
    parser.add_argument("--max-rank", type=int, default=99)
    args = parser.parse_args(argv)
    if args.max_seeds < 1 or args.max_rank < 0:
        parser.error("positive max-seeds and nonnegative max-rank required")
    started = time.monotonic()
    root = args.outdir
    root.mkdir(parents=True, exist_ok=False)
    provenance = dict(inputs=[], code_sha256={}, scope="relative only to the exact old short-circuit span; no SAT/UNSAT or full-algorithm inequivalence claim")

    def freeze_input(path, name):
        raw = path.read_bytes()
        target = root/"inputs"/name
        exclusive(target, raw)
        provenance["inputs"].append(dict(source=str(path.resolve()), snapshot=str(target.resolve()),
            raw_sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)))
        return load_json(raw)

    dictionary = freeze_input(args.dictionary, "dictionary.json")
    baseline = freeze_input(args.baseline, "baseline.json")
    prepared = freeze_input(args.prepared/"system.json", "prepared-system.json")
    circuits = freeze_input(args.prepared/"circuits.json", "circuits.json")
    measured = freeze_input(args.prepared/"circuit-span.audit.json", "old-span-audit.json")
    freeze_input(args.prepared/"system.audit.json", "prepared-system-audit.json")
    freeze_input(args.prepared/"preparation.json", "preparation.json")
    old_checksums = freeze_input(args.prepared/"checksums.json", "prepared-checksums.json")
    for relative, expected in old_checksums.items():
        if hashlib.sha256((args.prepared/relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f"prepared artifact checksum mismatch: {relative}")
    for name in ("dictionary.json", "baseline.json"):
        supplied = root/"inputs"/name
        if supplied.read_bytes() != (args.prepared/"inputs"/name).read_bytes():
            raise ValueError(f"prepared input bytes differ from supplied {name}")
    for path in (Path(__file__), REPO/"mmsearch/kernel_coset_seeds.py", REPO/"tests/test_kernel_coset_seeds.py",
                 REPO/"mmsearch/free_factor_sat.py", REPO/"mmsearch/recombine.py", REPO/"mmsearch/recombine_sat.py",
                 REPO/"mmsearch/verify.py", REPO/"mmsearch/__init__.py"):
        raw = path.read_bytes()
        relative = path.relative_to(REPO)
        exclusive(root/"code"/relative, raw)
        provenance["code_sha256"][str(relative)] = hashlib.sha256(raw).hexdigest()
    if prepared["metadata"]["orientation"] != "wu" or prepared["metadata"]["dimension"] != 5:
        raise ValueError("campaign generator requires the prepared dimension5 WU fixed-pair system")
    system = build_system(dictionary, 5, "wu", baseline)
    for key in ("pairs", "coefficients", "right_sides", "baseline_vectors", "reduced"):
        expected = json.loads(json.dumps(system[key]))
        if prepared[key] != expected:
            raise ValueError(f"fresh exact system differs from prepared {key}")
    width = system["metadata"]["width"]
    columns = [pair_column(pair, width) for pair in system["pairs"]]
    masks = circuit_masks(columns, circuits)
    span = build_span(masks)
    kernel = fundamental_kernel(system)
    if len(span) != measured["circuit_span_rank"] or len(kernel) != measured["linear_nullity"]:
        raise ValueError("recomputed span/kernel dimensions differ from the measured old audit")
    source = system["baseline_vectors"]
    source_rank = sum(bool(v) for v in source)
    old_pw = pw_rows(system, source)
    if old_pw != system["right_sides"]:
        raise AssertionError("source PW does not equal the complete target")
    provenance.update(source_rank=source_rank, source_candidate_sha256=digest(baseline),
        pair_count=len(columns), columns_sha256=digest([hex(c) for c in columns]),
        circuit_count=len(masks), circuit_span_rank=len(span), full_kernel_dimension=len(kernel),
        quotient_dimension=len(kernel)-len(span), selection="distinct nonzero coset remainders sorted by new rank, support size, active support preference")
    freeze_json(root/"provenance.json", provenance)
    freeze_json(root/"source-state.json", dict(vectors=source, observed_pw=old_pw,
        target_pw=system["right_sides"], observed_pw_sha256=digest(old_pw), source_rank=source_rank,
        baseline_verification=system["metadata"]["baseline"]))
    freeze_json(root/"span.audit.json", dict(circuit_masks_hex=[hex(m) for m in masks],
        basis=[dict(pivot=row["pivot"], vector_hex=hex(row["vector"]),
            original_circuit_xor_witness_hex=hex(row["circuit_xor"])) for row in span],
        circuit_count=len(masks), span_rank=len(span), full_kernel_dimension=len(kernel),
        columns_sha256=provenance["columns_sha256"]))
    scored, members, outside, active_outside, best = [], 0, 0, 0, {}

    def save_seed(item, directory):
        proof, score = item["proof"], item["score"]
        candidate, vectors, report = apply_shift_checked(system, proof, score)
        new_pw = pw_rows(system, vectors)
        if new_pw != old_pw or new_pw != system["right_sides"]:
            raise AssertionError("new PW, old PW and target differ")
        evidence = dict(free_coordinate=item["free_coordinate"], score=score,
            original_n_hex=hex(proof["vector"]), reduced_remainder_hex=hex(proof["remainder"]),
            reduction_basis_xor_hex=hex(proof["basis_xor"]), original_circuit_xor_hex=hex(proof["circuit_xor"]),
            explicit_P_n_hex="0x0", support=[i for i in range(len(columns)) if proof["vector"] >> i & 1],
            source_state=str((root/"source-state.json").resolve()), source_state_sha256=hashlib.sha256((root/"source-state.json").read_bytes()).hexdigest(),
            d=score["d"], changed_free_coordinate_bits=[i for i in range(width) if score["d"] >> i & 1],
            new_pw=new_pw, old_pw_sha256=digest(old_pw), target_pw_sha256=digest(system["right_sides"]),
            shift_column_claim="each set bit of d changes that free-coordinate column by n, which is outside this old S; at least one bit is set",
            scope=provenance["scope"])
        freeze_json(directory/"candidate.json", candidate)
        freeze_json(directory/"verification.json", report)
        freeze_json(directory/"vectors.json", vectors)
        freeze_json(directory/"shift-proof.json", evidence)
        exclusive(directory/"verify.py", (REPO/"mmsearch/verify.py").read_bytes())
        return dict(rank=report["rank"], candidate=str((directory/"candidate.json").resolve()),
            raw_sha256=hashlib.sha256((directory/"candidate.json").read_bytes()).hexdigest(),
            remainder_hex=hex(proof["remainder"]), support_size=score["support_size"],
            active_support=score["active_support"], exact_entries_checked=report["exact_entries_checked"]), candidate

    winner = False
    outputs = []
    for free, vector in kernel:
        try:
            proof = nonmembership_proof(columns, masks, span, vector)
        except ValueError as exc:
            if "lies in the old short-circuit span" not in str(exc):
                raise
            members += 1
            continue
        outside += 1
        score = score_shift(source, vector, width)
        active_outside += bool(score["active_support"])
        item = dict(free_coordinate=free, proof=proof, score=score)
        scored.append(dict(free_coordinate=free, n_hex=hex(vector), remainder_hex=hex(proof["remainder"]), **score))
        key = (score["new_rank"], score["support_size"], -score["active_support"], vector)
        previous = best.get(proof["remainder"])
        if previous is None or key < previous[0]:
            best[proof["remainder"]] = key, item
        if score["new_rank"] <= 92:
            output, candidate = save_seed(item, root/"first-record-evidence")
            freeze_first_record(root, candidate)
            outputs.append(output)
            winner = True
            break
    if not winner:
        selected = sorted(best.values(), key=lambda pair:pair[0])
        for _key, item in selected:
            if item["score"]["new_rank"] > args.max_rank or len(outputs) >= args.max_seeds:
                break
            output, _candidate = save_seed(item, root/"seeds"/f"seed-{len(outputs):02d}-rank{item['score']['new_rank']}")
            outputs.append(output)
    freeze_json(root/"fundamental-scores.json", scored)
    result = dict(status="WINNER" if winner else "EXACT_DIVERSIFICATION_SEEDS",
        elapsed_seconds=time.monotonic()-started, pair_count=len(columns),
        full_kernel_dimension=len(kernel), circuit_span_rank=len(span), quotient_dimension=len(kernel)-len(span),
        enumeration_complete=not winner, fundamental_members=members, fundamental_outside=outside, outside_touching_baseline_active=active_outside,
        distinct_nonzero_remainders=len(best), distinct_remainders_within_max_rank=sum(item[1]["score"]["new_rank"] <= args.max_rank for item in best.values()),
        minimum_scored_rank=min((s["new_rank"] for s in scored), default=None), max_rank=args.max_rank,
        source_rank=source_rank, outputs=outputs, scope=provenance["scope"], solver_or_search_called=False)
    freeze_json(root/"result.json", result)
    freeze_json(root/"checksums.json", {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()})
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
