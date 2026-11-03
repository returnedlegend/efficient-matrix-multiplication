#!/usr/bin/env python3
"""Independent exhaustive 5x5/F2 bilinear certificate checker (stdlib only).

No search, tensor, or existing verification modules are imported. A valid result
is an upper-bound construction only; canonical R is this decomposition's number
of essential products, never a claim of globally minimal tensor rank.
"""
import argparse
import hashlib
import json
from pathlib import Path


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key: {key!r}")
        obj[key] = value
    return obj


def _bad_constant(value):
    raise ValueError(f"non-JSON numeric constant: {value}")


def parse_certificate(raw):
    data = json.loads(raw, object_pairs_hook=_unique_object,
                      parse_constant=_bad_constant)
    if type(data) is not dict:
        raise ValueError("certificate must be a JSON object")
    for key, expected in (("dimension", 5), ("field", 2)):
        if type(data.get(key)) is not int or data[key] != expected:
            raise ValueError(f"{key} must be exact integer {expected}")
    if type(data.get("terms")) is not list:
        raise ValueError("terms must be a JSON array")
    terms = []
    for r, term in enumerate(data["terms"]):
        if type(term) is not dict:
            raise ValueError(f"term {r} must be a JSON object")
        factors = []
        for name in ("u", "v", "w"):
            vector = term.get(name)
            if (type(vector) is not list or len(vector) != 25 or
                    any(type(bit) is not int or bit not in (0, 1) for bit in vector)):
                raise ValueError(f"term {r}.{name} must contain exactly 25 integer bits (no bools/floats)")
            factors.append(tuple(vector))
        terms.append(tuple(factors))
    return terms


def canonical_terms(terms):
    """Discard zero products and cancel identical triples in characteristic 2."""
    odd = set()
    zero_count = 0
    for term in terms:
        if any(not any(vector) for vector in term):
            zero_count += 1
            continue
        if term in odd:
            odd.remove(term)
        else:
            odd.add(term)
    return sorted(odd), zero_count


def _check_all_basis_outputs(n, terms):
    """Direct scalar bilinear evaluation; n parameter exists for small controls.

    For every A=E_ab and B=E_cd, evaluate all n*n output entries.
    The third factor is a trace factor: w[k*n+i] contributes to C[i,k].
    """
    checked = mismatches = nonzero_expected = nonzero_observed = 0
    examples = []
    for a in range(n):
        for b in range(n):
            for c in range(n):
                for d in range(n):
                    products = [(u[a*n+b] * v[c*n+d], w) for u, v, w in terms]
                    for i in range(n):
                        for k in range(n):
                            actual = 0
                            for product, w in products:
                                actual ^= product * w[k*n+i]
                            expected = int(b == c and i == a and k == d)
                            checked += 1
                            nonzero_expected += expected
                            nonzero_observed += actual
                            if actual != expected:
                                mismatches += 1
                                if len(examples) < 32:
                                    examples.append({"A_basis": [a,b], "B_basis": [c,d],
                                                     "output": [i,k], "expected": expected,
                                                     "actual": actual})
    return {"basis_input_pairs_checked": n**4, "output_bits_checked": checked,
            "expected_one_bits": nonzero_expected, "observed_one_bits": nonzero_observed,
            "mismatch_count": mismatches, "mismatch_examples": examples}


def canonical_certificate(terms):
    return {"dimension": 5, "field": 2,
            "terms": [dict(zip(("u", "v", "w"), map(list, term))) for term in terms]}


def verify_bytes(raw):
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    report = {"schema": "independent-record42-v1", "valid": False,
              "record_eligible": False, "dimension": 5, "field": 2,
              "candidate_source_sha256": hashlib.sha256(raw).hexdigest(),
              "verifier_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "proof_flags": {"strict_json": True, "all_basis_outputs_exhaustive": False,
                              "independent_of_search_tensor_existing_verifiers": True,
                              "canonical_zero_removal_and_GF2_duplicate_cancellation": True,
                              "formal_lean_proof_checked": False, "integer_lift_claim": False,
                              "global_rank_lower_bound_claim": False,
                              "global_minimal_rank_claim": False},
              "convention": "row-major A,B; trace W[k*5+i] contributes to output C[i*5+k]",
              "rank_scope": "canonical essential product count of supplied decomposition; upper bound only",
              "errors": []}
    try:
        terms = parse_certificate(raw)
        canonical, zero_count = canonical_terms(terms)
    except (ValueError, TypeError, UnicodeError) as exc:
        report["errors"] = [str(exc)]
        return report
    canonical_raw = (json.dumps(canonical_certificate(canonical), sort_keys=True,
                                separators=(",", ":")) + "\n").encode()
    report.update({"nominal_input_products": len(terms), "zero_input_products": zero_count,
                   "duplicate_products_cancelled": len(terms)-zero_count-len(canonical),
                   "canonical_essential_products": len(canonical),
                   "essential_rank": len(canonical),
                   "canonical_certificate_sha256": hashlib.sha256(canonical_raw).hexdigest()})
    report.update(_check_all_basis_outputs(5, canonical))
    report["exact_entries_checked"] = report["output_bits_checked"]
    report["proof_flags"]["all_basis_outputs_exhaustive"] = report["output_bits_checked"] == 15625
    report["valid"] = report["mismatch_count"] == 0
    report["record_eligible"] = report["valid"] and len(canonical) <= 92
    return report


def verify_file(path):
    return verify_bytes(Path(path).read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("certificate", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--canonical-output", type=Path)
    parser.add_argument("--require-record", action="store_true")
    args = parser.parse_args()
    raw = args.certificate.read_bytes()
    report = verify_bytes(raw)
    if args.canonical_output and report["valid"]:
        canonical, _ = canonical_terms(parse_certificate(raw))
        args.canonical_output.write_text(json.dumps(canonical_certificate(canonical), sort_keys=True,
                                                   separators=(",", ":")) + "\n")
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output)
    print(output, end="")
    accepted = report["record_eligible"] if args.require_record else report["valid"]
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
