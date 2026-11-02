"""Safely import pinned Kauers–Moosbauer schemes without evaluating source code.

Only signed sums of aij/bij/cij monomials are accepted. No eval or floating
point arithmetic is used. Exact coefficient verification is mandatory.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.verify import verify_candidate, write_standalone_verifier

SOURCES = {
    "95": {"repo": "jakobmoosbauer/flips", "commit": "e31a0a0f0d2577cee5da047ca7dcae0c61992e40",
           "path": "solutions/555-95-mod2.exp", "sha256": "b40354f5ee16172665e9f60a8fa92777f9993ae824aad69d0321c4b11021e13f", "rank": 95, "field": 2},
    "93": {"repo": "jakobmoosbauer/symmetric-flips", "commit": "3e2d4dd8acf831ef65c7c6b13ed787330e1e3483",
           "path": "schemes/555m93.txt", "sha256": "89b86d46243b2245bd6197cd0967fdb5b7c0da0de9ea2fd2b3f5ec2f74c9b804", "rank": 93, "field": 2},
}


def parse(source: bytes) -> list[dict]:
    terms = []
    for line in source.decode("utf-8").splitlines():
        line = re.sub(r"\s+", "", line)
        if not line:
            continue
        match = re.fullmatch(r"\(([^()]*)\)\*?\(([^()]*)\)\*?\(([^()]*)\)", line)
        if match is None:
            raise ValueError("malformed product of three linear forms")
        term = {}
        for axis, label, form in zip(("u", "v", "w"), "abc", match.groups()):
            tokens = list(re.finditer(r"([+-]?)(" + label + r")([1-5])([1-5])", form))
            if not tokens or "".join(m.group() for m in tokens) != form:
                raise ValueError("linear form contains an unsupported expression")
            vector = [0] * 25
            for index, m in enumerate(tokens):
                if index and not m[1]:
                    raise ValueError("missing coefficient separator")
                offset = (int(m[3])-1)*5 + int(m[4])-1
                vector[offset] += -1 if m[1] == "-" else 1
            if any(x not in (-1, 0, 1) for x in vector):
                raise ValueError("coefficient outside {-1,0,1}")
            term[axis] = vector
        terms.append(term)
    return terms


def import_scheme(source, kind, output):
    spec = SOURCES[kind]
    payload = Path(source).read_bytes()
    if hashlib.sha256(payload).hexdigest() != spec["sha256"]:
        raise ValueError("source checksum does not match pinned author dataset")
    terms = parse(payload)
    if len(terms) != spec["rank"]:
        raise ValueError("unexpected term count")
    data = {"field": spec["field"], "dimension": 5, "terms": terms,
            "metadata": {"method": "published-kauers-moosbauer-baseline", "novel": False,
                         "source": f"https://github.com/{spec['repo']}/blob/{spec['commit']}/{spec['path']}",
                         "source_sha256": spec["sha256"], "source_commit": spec["commit"],
                         "attribution": "Manuel Kauers and Jakob Moosbauer; author-published scheme",
                         "upstream_license_notice": "GPL-3.0-or-later; see research/KM_SOURCE.md",
                         "third_factor": "trace: w[k*5+i] contributes to output[i][k]"}}
    report = verify_candidate(data, random_trials=64)
    if not report["valid"]:
        raise ValueError("imported certificate failed exact verification: " + str(report))
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n")
    target.with_suffix(".verification.json").write_text(json.dumps(report, indent=2) + "\n")
    write_standalone_verifier(target.with_suffix(".verify.py"))
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source")
    ap.add_argument("--kind", choices=SOURCES, default="95")
    ap.add_argument("--output", default="artifacts/km95_f2.json")
    args = ap.parse_args()
    print(json.dumps(import_scheme(args.source, args.kind, args.output), indent=2))
