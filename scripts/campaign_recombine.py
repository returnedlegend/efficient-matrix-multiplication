"""Bounded exact F2 affine-code recombination; run with external CPU affinity."""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.recombine import Pool, canonical_terms, digest, encode, save, search
from mmsearch.verify import verify_candidate, write_standalone_verifier


def read_source(path, dimension):
    """Read once, including live native files, and retain its exact byte hash."""
    path = Path(path)
    raw = path.read_bytes()
    if path.suffix == ".txt":
        terms = [tuple(map(int, line.split())) for line in raw.decode().splitlines() if line.strip()]
        if not terms or any(len(t) != 3 or any(not 0 < x < 1 << (dimension*dimension) for x in t) for t in terms):
            raise ValueError("invalid native term triples")
        candidate = encode(terms, dimension)
    else:
        def unique(pairs):
            value = {}
            for k, v in pairs:
                if k in value:
                    raise ValueError("duplicate JSON key")
                value[k] = v
            return value
        candidate = json.loads(raw, object_pairs_hook=unique)
    terms = canonical_terms(candidate)
    if candidate["dimension"] != dimension:
        raise ValueError("wrong source dimension")
    candidate = encode(terms, dimension)
    report = verify_candidate(candidate, random_trials=0)
    if not report["valid"]:
        raise ValueError("source is not an exact F2 algorithm")
    return candidate, dict(path=str(path), raw_sha256=hashlib.sha256(raw).hexdigest(),
                          canonical_sha256=digest(candidate), verification=report)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, action="append", default=[])
    p.add_argument("--seed-dir", type=Path, action="append", default=[])
    p.add_argument("--raw-glob", action="append", default=[])
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--dimension", type=int, default=5)
    p.add_argument("--seconds", type=float, default=30)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--target", type=int, default=92)
    p.add_argument("--max-steps", type=int, default=300000)
    p.add_argument("--anchors", type=int, default=16)
    p.add_argument("--neighbors", type=int, default=48)
    p.add_argument("--walk-steps", type=int, default=50000)
    p.add_argument("--max-weight", type=int, default=100)
    p.add_argument("--max-sources", type=int, default=0)
    p.add_argument("--resume", action="store_true")
    a = p.parse_args(argv)
    if not math.isfinite(a.seconds) or a.seconds <= 0 or a.dimension < 1 or a.max_sources < 0:
        p.error("invalid bounds")
    started = time.monotonic()
    root = a.output_dir
    root.mkdir(parents=True, exist_ok=True)
    checkpoint = root/"checkpoint.json"
    candidates, provenance, rejected = [], [], []
    if a.resume:
        previous = json.loads((root/"pool.json").read_text())
        for entry in previous["sources"]:
            record = entry["provenance"]
            candidate = json.loads(Path(record["snapshot"]).read_text())
            if digest(candidate) != entry["canonical_sha256"]:
                raise ValueError("source snapshot changed")
            candidates.append(candidate)
            provenance.append(record)
    else:
        # Capture raw live states first: these can supply genuine even ranks.
        paths = [Path(x) for pattern in a.raw_glob for x in sorted(glob.glob(pattern, recursive=True))]
        paths += a.input
        paths += [x for folder in a.seed_dir for x in sorted(folder.rglob("*.json"))]
        seen = set()
        for path in paths:
            if a.max_sources and len(candidates) >= a.max_sources:
                break
            try:
                candidate, record = read_source(path, a.dimension)
                sha = record["canonical_sha256"]
                if sha in seen:
                    continue
                snapshot = root/"sources"/(sha+".json")
                save(snapshot, candidate)
                record["snapshot"] = str(snapshot.resolve())
                candidates.append(candidate)
                provenance.append(record)
                seen.add(sha)
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                rejected.append(dict(path=str(path), error=str(exc)))
            if time.monotonic()-started >= a.seconds:
                break
    pool = Pool(candidates, provenance)
    manifest = pool.manifest()
    manifest.update(rejected=rejected, wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    save(root/"pool.json", manifest)
    save(root/"dictionary.json", pool.dictionary)
    remaining = max(0.001, a.seconds-(time.monotonic()-started))
    candidate, verification, state = search(pool, seconds=remaining, seed=a.seed, target=a.target,
        max_steps=a.max_steps, anchors=a.anchors, neighbors=a.neighbors, walk_steps=a.walk_steps,
        max_weight=a.max_weight, checkpoint=checkpoint, resume=a.resume)
    candidate["metadata"]["wrapper_sha256"] = manifest["wrapper_sha256"]
    save(root/"best.json", candidate)
    save(root/"best.verification.json", verification)
    write_standalone_verifier(root/"best.verify.py")
    found = verification["valid"] and verification["rank"] <= a.target
    if found:
        save(root/"FOUND.json", candidate)
        save(root/"FOUND.verification.json", verification)
        write_standalone_verifier(root/"FOUND.verify.py")
    summary = dict(exact=True, best_rank=verification["rank"], target=a.target, found=found,
        sources=len(pool.sources), source_rank_counts={str(rank): sum(s["rank"] == rank for s in pool.sources)
                                                     for rank in sorted({s["rank"] for s in pool.sources})},
        dictionary_size=len(pool.dictionary), dictionary_sha256=pool.dictionary_sha256,
        pool_sha256=pool.sha256, parity_limitation=manifest["parity_limitation"],
        local_cycle_minimum=state["local_cycle_minimum"], local_pairs_checked=state["local_pairs_checked"],
        phase=state["phase"], evaluations=state["evaluations"], accepted=state["accepted"],
        elapsed_seconds=time.monotonic()-started,
        scope="finite supplied source pool; local cycle minimum is not a global rank bound")
    save(root/"summary.json", summary)
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
