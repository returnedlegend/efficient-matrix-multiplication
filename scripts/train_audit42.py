"""Read-only structural-collision audit; no novelty reward is introduced."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.native_bridge import canonical_terms
from mmsearch.rl_search import _write, term_hash
from scripts.select_diverse93_seeds import rank_histogram


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--new93-dir", type=Path, required=True)
    p.add_argument("--record-runs", type=Path, required=True)
    p.add_argument("--record-seed", action="append", type=Path, default=[])
    p.add_argument("--sample", type=int, default=128)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cpu", type=int, default=2)
    args = p.parse_args(argv)
    os.sched_setaffinity(0, {args.cpu})
    runs = sorted(args.record_runs.iterdir())
    stride = max(1, len(runs)//args.sample)
    sampled = runs[::stride][:args.sample]
    paths = sorted(args.new93_dir.glob("*.json"))+args.record_seed+[run/"input.json" for run in sampled if (run/"input.json").is_file()]
    rows = []
    for path in paths:
        payload = path.read_bytes()
        candidate = json.loads(payload)
        terms = canonical_terms(candidate)
        hist = rank_histogram(terms)
        single = Counter((axis, term[axis]) for term in terms for axis in range(3))
        # Coarse sharing/density may create informative collisions; audit only.
        counts = (len(terms), hist, sum(value*(value-1)//2 for value in single.values())//20,
                  sum(value.bit_count() for term in terms for value in term)//50)
        rows.append({"path": str(path.resolve()), "sha256": hashlib.sha256(payload).hexdigest(),
                     "rank": len(terms), "term_hash": term_hash(terms), "histogram": hist,
                     "coarse_fingerprint": hashlib.sha256(repr(counts).encode()).hexdigest()})
    histograms = Counter(tuple(row["histogram"]) for row in rows)
    coarse = Counter(row["coarse_fingerprint"] for row in rows)
    def stats(values):
        return {"distinct": len(values), "repeated_rows": sum(count-1 for count in values.values()),
                "largest_bucket": max(values.values(), default=0)}
    result = {"format": "structural-collision-audit-v42", "sample_count": len(rows),
              "sampling": "evenly spaced sorted immutable record-run inputs plus NEW93 pool16 and old restart sources",
              "term_hash": stats(Counter(row["term_hash"] for row in rows)),
              "factor_rank_histogram": stats(histograms), "coarse_fingerprint": stats(coarse), "rows": rows,
              "interpretation": "collisions alone do not show usefulness; no reward change or cap renewal authorized by this audit",
              "verification_scope": "strict F2 schema/term decode; relies on frozen source full-coefficient verifications, no new tensor verification"}
    _write(args.output, result)
    print(json.dumps({key:value for key,value in result.items() if key != "rows"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
