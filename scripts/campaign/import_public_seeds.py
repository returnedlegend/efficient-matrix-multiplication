"""Import numeric FastMatrixF2 public seeds; never execute upstream code.

The input is a sparse checkout of the pinned commit. Exact tensor verification
uses this project's independent verifier, not the source's verification flag.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mmsearch.verify import verify_candidate

COMMIT = "5fd32f680acf2a7708ea6a2d40d10f7e7537957c"
REPO = "https://github.com/big-brain-zaru/FastMatrixF2"


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("checkout", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    head = subprocess.check_output(
        ["git", "-C", str(args.checkout), "rev-parse", "HEAD"], text=True).strip()
    if head != COMMIT:
        raise ValueError(f"checkout must be pinned to {COMMIT}")
    out = args.output
    for directory in (out / "seeds", out / "raw", out / "attribution"):
        directory.mkdir(parents=True, exist_ok=True)
    attribution = {}
    for name in ("README.md", "LICENSE", "CITATION.cff", "main.tex"):
        source = args.checkout / name
        shutil.copyfile(source, out / "attribution" / name)
        attribution[name] = hashlib.sha256(source.read_bytes()).hexdigest()

    sources = []
    distinct = {}
    reports = []
    for path in sorted((args.checkout / "results").rglob("*rank93*.json")):
        raw = path.read_bytes()
        data = json.loads(raw, object_pairs_hook=unique_object)
        if (data.get("format") != [5, 5, 5] or data.get("field") != "F2"
                or type(data.get("rank")) is not int or data["rank"] != 93):
            raise ValueError(f"unsupported format/field/rank: {path}")
        terms = data.get("scheme_bitmasks")
        if not isinstance(terms, list) or len(terms) != 93:
            raise ValueError(f"wrong term count: {path}")
        for term in terms:
            if (not isinstance(term, list) or len(term) != 3
                    or any(type(mask) is not int or not 0 < mask < (1 << 25)
                           for mask in term)):
                raise ValueError(f"invalid numeric factors: {path}")
        key = tuple(sorted(tuple(term) for term in terms))
        if len(set(key)) != 93:
            raise ValueError(f"duplicate rank-one terms: {path}")
        relative = path.relative_to(args.checkout).as_posix()
        source_url = f"https://raw.githubusercontent.com/big-brain-zaru/FastMatrixF2/{COMMIT}/{relative}"
        source_hash = hashlib.sha256(raw).hexdigest()
        if key not in distinct:
            seed_id = f"seed{len(distinct):03d}"
            candidate = {
                "field": 2, "dimension": 5,
                "terms": [{axis: [(mask >> i) & 1 for i in range(25)]
                           for axis, mask in zip(("u", "v", "w"), term)}
                          for term in key],
                "metadata": {
                    "method": "imported-public-same-rank-reference", "novel": False,
                    "rank": 93, "source": source_url, "source_commit": COMMIT,
                    "source_sha256": source_hash,
                    "attribution": "Nadim F. Zaru, FastMatrixF2 v1.0.0 (2026-09-18)",
                    "upstream_license": "MIT; retained in ../attribution/LICENSE",
                    "third_factor": "trace: w[k*5+i] contributes to output[i][k]",
                },
            }
            report = verify_candidate(candidate, random_trials=8)
            if (not report["valid"] or report["exact_entries_checked"] != 15625
                    or report["rank"] != 93):
                raise ValueError(f"independent verification failed: {path}: {report}")
            seed_path = out / "seeds" / f"{seed_id}.json"
            seed_path.write_text(json.dumps(candidate, separators=(",", ":")) + "\n")
            (out / "raw" / f"{seed_id}.json").write_bytes(raw)
            reports.append({"seed_id": seed_id, "certificate_sha256":
                            hashlib.sha256(seed_path.read_bytes()).hexdigest(), **report})
            distinct[key] = seed_id
        sources.append({"path": relative, "url": source_url,
                        "sha256": source_hash, "seed_id": distinct[key]})

    manifest = {
        "repository": REPO, "commit": COMMIT, "imported_at_utc":
        __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "source_files": len(sources), "distinct_term_sets": len(distinct),
        "rank": 93, "field": "F2", "dimension": 5,
        "scope": "Public reference data, no rank improvement; inequivalence not independently checked.",
        "attribution_sha256": attribution, "sources": sources,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "verification.json").write_text(json.dumps(reports, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in ("commit", "source_files", "distinct_term_sets", "rank")}))


if __name__ == "__main__":
    main()
