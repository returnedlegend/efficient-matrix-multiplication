"""Bounded exact slice-compression scan of dimension-5 F2 certificates.

Noncertificate JSON is counted and skipped. Malformed or inexact candidate
certificates are ERROR records, never impossibility evidence. Rank 93 is a
research checkpoint; only independently verified rank <=92 is a WINNER.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from mmsearch.recombine import save
from mmsearch.slice_compression import InvalidCertificate, canonical_masks, compress_candidate
from mmsearch.verify import verify_candidate, write_standalone_verifier


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def classify(value):
    if not isinstance(value, dict) or not ("terms" in value or {"field", "dimension"} <= set(value)):
        return "NONCERTIFICATE"
    if value.get("field") != 2 or value.get("dimension") != 5:
        return "UNSUPPORTED_CERTIFICATE"
    # Matching values with wrong types, missing terms, bad factor shapes or
    # nonbit coordinates are malformed target certificates and must fail.
    canonical_masks(value)
    return "CERTIFICATE"


def discover(inputs, directories):
    paths = {str(path.resolve()): path.resolve() for path in inputs}
    for directory in directories:
        if not directory.is_dir():
            raise ValueError(f"candidate directory does not exist: {directory}")
        for path in directory.rglob("*.json"):
            if path.is_file():
                paths[str(path.resolve())] = path.resolve()
    return [paths[key] for key in sorted(paths)]


def _winner_eligible(candidate, result):
    return (type(candidate.get("dimension")) is int and candidate["dimension"] == 5 and
        type(candidate.get("field")) is int and candidate["field"] == 2 and
        len(candidate["terms"]) <= 92 and result["winner_eligible"] and result["final_verification"]["valid"])


def _freeze_first_winner(root, candidate):
    """Generic exact-certificate freezer; caller enforces campaign eligibility.

    Exclusive writes prevent replacing the first certificate even if called
    again. Exact verification is repeated before any primary bytes are saved.
    """
    primary = root/"WINNER.json"
    if primary.exists():
        raise FileExistsError("the first WINNER certificate is already frozen")
    report = verify_candidate(candidate, random_trials=16)
    if not report["valid"]:
        raise InvalidCertificate("first winner failed independent freeze verification", report)
    payloads = {
        "WINNER.json": (json.dumps(candidate, sort_keys=True, indent=2)+"\n").encode(),
        "WINNER.verification.json": (json.dumps(report, sort_keys=True, indent=2)+"\n").encode(),
        "WINNER.verify.py": (REPO/"mmsearch/verify.py").read_bytes(),
    }
    checksums = {name:hashlib.sha256(raw).hexdigest() for name, raw in payloads.items()}
    payloads["WINNER.sha256"] = (checksums["WINNER.json"]+"  WINNER.json\n").encode()
    payloads["WINNER.checksums.json"] = (json.dumps(checksums, sort_keys=True, indent=2)+"\n").encode()
    for name, raw in payloads.items():
        path = root/name
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
        path.chmod(0o444)
    return checksums


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", default=[])
    parser.add_argument("--candidate-dir", type=Path, action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument("--max-sources", type=int, default=1000)
    parser.add_argument("--minimum-age", type=float, default=30)
    parser.add_argument("--cache", type=Path, help="optional persistent raw-hash cache; keyed by implementation hashes")
    args = parser.parse_args(argv)
    if (not args.input and not args.candidate_dir) or (not math.isfinite(args.seconds) or args.seconds <= 0 or
            not math.isfinite(args.minimum_age) or args.minimum_age < 0 or args.max_sources < 1):
        parser.error("sources, positive finite seconds/max-sources and nonnegative minimum-age are required")
    started = time.monotonic()
    deadline = started+args.seconds
    paths = discover(args.input, args.candidate_dir)
    root = args.output_dir
    root.mkdir(parents=True, exist_ok=False)
    (root/"inputs").mkdir()
    code = {}
    for path in (Path(__file__), REPO/"mmsearch/slice_compression.py", REPO/"mmsearch/verify.py",
                 REPO/"mmsearch/recombine.py", REPO/"mmsearch/__init__.py", REPO/"tests/test_slice_compression.py"):
        raw = path.read_bytes()
        relative = path.relative_to(REPO)
        destination = root/"code"/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        code[str(relative)] = hashlib.sha256(raw).hexdigest()
    implementation = hashlib.sha256(json.dumps(code, sort_keys=True).encode()).hexdigest()
    cache = dict(schema="slice-scan-cache-v1", implementations={})
    cache_input = None
    if args.cache is not None and args.cache.exists():
        raw = args.cache.read_bytes()
        cache = strict_json(raw)
        if not isinstance(cache, dict) or cache.get("schema") != "slice-scan-cache-v1" or not isinstance(cache.get("implementations"), dict):
            raise ValueError("unsupported cache schema")
        (root/"inputs/cache.initial.json").write_bytes(raw)
        cache_input = dict(path=str(args.cache.resolve()), raw_sha256=hashlib.sha256(raw).hexdigest())
    entries = cache["implementations"].setdefault(implementation, {})
    provenance = dict(code_sha256=code, implementation_sha256=implementation,
        cache_input=cache_input, requested_inputs=[str(p.resolve()) for p in args.input],
        requested_directories=[str(p.resolve()) for p in args.candidate_dir],
        budget=dict(seconds=args.seconds, max_sources=args.max_sources, minimum_age=args.minimum_age),
        claim="exact F2 tensor-preserving strict term-count reductions only; rank93 is not novel; no integer lift or global impossibility claim")
    save(root/"provenance.json", provenance)
    records, counts, seen = [], Counter(), set()
    fresh_sources, best_rank, stopped = 0, None, "all discovered paths considered"
    for path in paths:
        if time.monotonic() >= deadline:
            stopped = "time budget reached"
            break
        record = dict(source=str(path))
        try:
            stat = path.stat()
            if time.time()-stat.st_mtime < args.minimum_age:
                record.update(status="TOO_YOUNG", age_seconds=max(0, time.time()-stat.st_mtime))
                records.append(record)
                counts[record["status"]] += 1
                continue
            raw = path.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            snapshot = root/"inputs"/f"{sha}.json"
            if not snapshot.exists():
                snapshot.write_bytes(raw)
            record.update(raw_sha256=sha, bytes=len(raw), snapshot=str(snapshot.resolve()))
            if sha in seen:
                record["status"] = "DUPLICATE_RAW_INPUT"
            elif sha in entries and entries[sha].get("fixed_point", True):
                record.update(status="CACHED_ERROR" if entries[sha]["status"] == "ERROR" else "CACHED", prior=entries[sha])
            else:
                seen.add(sha)
                value = strict_json(raw)
                classification = classify(value)
                if classification != "CERTIFICATE":
                    record["status"] = classification
                else:
                    if fresh_sources >= args.max_sources:
                        stopped = "max-sources reached"
                        record.update(status="DEFERRED", reason=stopped)
                        records.append(record)
                        counts[record["status"]] += 1
                        break
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:
                        stopped = "time budget reached"
                        record.update(status="DEFERRED", reason=stopped)
                        records.append(record)
                        counts[record["status"]] += 1
                        break
                    fresh_sources += 1
                    result = compress_candidate(value, seconds=remaining, stop_at_record=True)
                    candidate = result.pop("candidate")
                    directory = root/"candidates"/sha
                    save(directory/"final.json", candidate)
                    save(directory/"moves.json", result["moves"])
                    save(directory/"report.json", result)
                    write_standalone_verifier(directory/"verify.py")
                    record.update(status="VERIFIED", source_rank=result["source_rank"],
                        canonical_rank=result["canonical_rank"], final_rank=result["final_rank"],
                        move_count=len(result["moves"]), fixed_point=result["fixed_point"],
                        report_path=str((directory/"report.json").resolve()),
                        output_path=str((directory/"final.json").resolve()),
                        output_raw_sha256=hashlib.sha256((directory/"final.json").read_bytes()).hexdigest(),
                        exact_entries_checked=result["final_verification"]["exact_entries_checked"])
                    rank = result["final_rank"]
                    if _winner_eligible(candidate, result):
                        record["winner_checksums"] = _freeze_first_winner(root, candidate)
                        record["winner"] = True
                    if rank == 93:
                        save(directory/"CHECKPOINT_93.json", candidate)
                        record["research_checkpoint_only"] = True
                    best_rank = rank if best_rank is None else min(best_rank, rank)
                entries[sha] = {key:record[key] for key in ("status", "source_rank", "final_rank", "report_path", "output_raw_sha256", "fixed_point") if key in record}
        except Exception as exc:
            record.update(status="ERROR", error=f"{type(exc).__name__}: {exc}")
            if isinstance(exc, InvalidCertificate) and exc.report is not None:
                record["input_verification"] = exc.report
            if "raw_sha256" in record:
                seen.add(record["raw_sha256"])
                entries[record["raw_sha256"]] = dict(status="ERROR", error=record["error"])
        records.append(record)
        counts[record["status"]] += 1
        if (root/"WINNER.json").exists():
            stopped = "first winner frozen; no further inputs attempted"
            break
    save(root/"source_records.json", records)
    save(root/"cache.json", cache)
    if args.cache is not None:
        save(args.cache, cache)
    summary = dict(status="ERROR" if counts["ERROR"] or counts["CACHED_ERROR"] else "WINNER" if (root/"WINNER.json").exists() else "COMPLETE" if stopped == "all discovered paths considered" else "PARTIAL",
        counts=dict(counts), discovered_paths=len(paths), recorded_paths=len(records), fresh_sources=fresh_sources,
        stop_reason=stopped, best_rank=best_rank, winner=(root/"WINNER.json").exists(),
        elapsed_seconds=time.monotonic()-started, implementation_sha256=implementation,
        claim=provenance["claim"])
    save(root/"result.json", summary)
    save(root/"artifact_checksums.json", {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file() and path.name != "artifact_checksums.json"})
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 2 if summary["status"] == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
