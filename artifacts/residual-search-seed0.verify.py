"""Independent, standard-library-only certificate verification.

This module deliberately does not import the search or tensor construction code.
Every tensor coefficient is checked over the declared field.  Integer equality
is reported separately; equality over F2 never establishes an integer lift.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys


def _schema_error(candidate) -> str | None:
    if not isinstance(candidate, dict):
        return "candidate must be a JSON object"
    field = candidate.get("field")
    if type(field) is not int or field not in (0, 2):
        return "field must be 2 (F2) or 0 (integers)"
    n = candidate.get("dimension")
    if type(n) is not int or n < 1:
        return "dimension must be a positive integer"
    terms = candidate.get("terms")
    if not isinstance(terms, list):
        return "terms must be an array"
    for index, term in enumerate(terms):
        if not isinstance(term, dict) or set(term) != {"u", "v", "w"}:
            return f"term {index} must have exactly u, v, and w"
        for axis in ("u", "v", "w"):
            vector = term[axis]
            if not isinstance(vector, list) or len(vector) != n * n:
                return f"term {index}.{axis} must have {n*n} entries"
            if any(type(value) is not int for value in vector):
                return f"term {index}.{axis} entries must be integers (booleans are rejected)"
    return None


def _random_multiplication(candidate: dict, trials: int, seed: int) -> dict:
    """Supplementary test using direct input/output multiplication."""
    rng = random.Random(seed)
    n, field = candidate["dimension"], candidate["field"]
    for trial in range(trials):
        a = [rng.randrange(2) if field == 2 else rng.randrange(-3, 4) for _ in range(n*n)]
        b = [rng.randrange(2) if field == 2 else rng.randrange(-3, 4) for _ in range(n*n)]
        output = [0] * (n*n)
        for term in candidate["terms"]:
            product = sum(x*y for x, y in zip(term["u"], a)) * sum(x*y for x, y in zip(term["v"], b))
            for k in range(n):
                for i in range(n):
                    output[i*n+k] += term["w"][k*n+i] * product
        expected = [sum(a[i*n+j] * b[j*n+k] for j in range(n))
                    for i in range(n) for k in range(n)]
        if field == 2:
            output = [value % 2 for value in output]
            expected = [value % 2 for value in expected]
        if output != expected:
            return {"passed": False, "trials": trial + 1, "seed": seed,
                    "failed_trial": trial}
    return {"passed": True, "trials": trials, "seed": seed}


def verify_candidate(candidate, random_trials: int = 8, seed: int = 0) -> dict:
    """Fail closed on schema errors and exactly check the declared coefficient ring.

    field=2 means F2. field=0 means the integers.  ``integer_valid`` always
    refers to the literal signed coefficients in the supplied certificate.
    ``rank`` is the supplied number of rank-one terms, an upper bound on rank.
    """
    report = {"valid": False, "field_valid": False, "integer_valid": False,
              "dimension": None, "field": None, "rank": None,
              "exact_entries_checked": 0, "errors": []}
    error = _schema_error(candidate)
    if error:
        report["errors"].append(error)
        return report
    if type(random_trials) is not int or random_trials < 0 or type(seed) is not int:
        report["errors"].append("random_trials must be a nonnegative integer and seed an integer")
        return report
    n, field, terms = candidate["dimension"], candidate["field"], candidate["terms"]
    width = n*n
    report.update(dimension=n, field=field, rank=len(terms))
    reconstructed = [0] * (width**3)
    for term in terms:
        supports = [[(index, value) for index, value in enumerate(term[axis]) if value]
                    for axis in ("u", "v", "w")]
        for a, u in supports[0]:
            for b, v in supports[1]:
                for c, w in supports[2]:
                    reconstructed[(a*width+b)*width+c] += u*v*w
    mismatch_count = 0
    integer_mismatch_count = 0
    examples = []
    # Enumerate all n**6 entries, including the expected zeros.  Computing the
    # target here independently catches tensor construction/indexing errors.
    for a in range(width):
        i, j = divmod(a, n)
        for b in range(width):
            other_j, k = divmod(b, n)
            for c in range(width):
                other_k, other_i = divmod(c, n)
                expected = int(j == other_j and k == other_k and i == other_i)
                literal = reconstructed[(a*width+b)*width+c]
                observed = literal % 2 if field == 2 else literal
                integer_mismatch_count += literal != expected
                if observed != expected:
                    mismatch_count += 1
                    if len(examples) < 8:
                        examples.append({"indices": [a, b, c], "expected": expected,
                                         "observed": observed})
    report.update(exact_entries_checked=width**3,
                  mismatch_count=mismatch_count,
                  mismatch_examples=examples,
                  integer_mismatch_count=integer_mismatch_count,
                  field_valid=mismatch_count == 0,
                  integer_valid=integer_mismatch_count == 0)
    if mismatch_count:
        report["errors"].append(f"exact tensor equality failed at {mismatch_count} coefficients")
    random_report = _random_multiplication(candidate, random_trials, seed)
    report["random_multiplication"] = random_report
    if not random_report["passed"]:
        report["errors"].append("supplementary random multiplication test failed")
    report["valid"] = report["field_valid"] and random_report["passed"]
    return report


def verify_file(path, random_trials: int = 8, seed: int = 0) -> dict:
    """Read a JSON certificate; file/JSON failures are invalid reports."""
    try:
        # Repeated keys are ambiguous and must not silently overwrite a field.
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate JSON key: {key}")
                result[key] = value
            return result
        candidate = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, ValueError, RecursionError) as exc:
        return {"valid": False, "field_valid": False, "integer_valid": False,
                "dimension": None, "field": None, "rank": None,
                "exact_entries_checked": 0, "errors": [f"cannot read certificate: {exc}"]}
    return verify_candidate(candidate, random_trials=random_trials, seed=seed)


def write_standalone_verifier(path) -> Path:
    """Export this independent verifier as a self-contained Python script."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Exactly verify a matrix multiplication certificate")
    parser.add_argument("candidate", help="candidate JSON file")
    parser.add_argument("--random-trials", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--require-integer", action="store_true", help="also require equality of the literal integer tensor")
    parser.add_argument("--export-standalone", metavar="PATH", help="write a standalone verifier script")
    args = parser.parse_args(argv)
    if args.export_standalone:
        write_standalone_verifier(args.export_standalone)
    report = verify_file(args.candidate, random_trials=args.random_trials, seed=args.seed)
    if args.require_integer and not report["integer_valid"]:
        report["valid"] = False
        report["errors"].append("integer tensor equality was required and failed")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(_main())
