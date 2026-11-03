#!/usr/bin/env python3
"""Import pinned AlphaEvolve 5x5 integer data without executing notebook code.

Only the exact assignment to decomposition_555 and three np.array literal lists
in cell 50 are accepted. Numeric source tokens are parsed as exact fractions;
the notebook's float32 annotation is inert and no floating arithmetic is used.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.verify import verify_candidate, write_standalone_verifier

COMMIT = "4226acbf237ff9ad10ba7673a2af127a2d8a5971"
SHA256 = "2cce2543e48c89aa3e91614272a698a0147dd2548ea11cf92f1292b7435d38ff"
SOURCE = f"https://raw.githubusercontent.com/google-deepmind/alphaevolve_results/{COMMIT}/mathematical_results.ipynb"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _literal(node: ast.AST, source: str):
    if isinstance(node, ast.List):
        return [_literal(child, source) for child in node.elts]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _literal(node.operand, source)
        if type(value) is not int:
            raise ValueError("unary sign requires a number")
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        token = ast.get_source_segment(source, node)
        if token is None or re.fullmatch(r"[0-9]+(?:\.[0-9]*)?", token) is None:
            raise ValueError("unsupported numeric token")
        exact = Fraction(token)
        if exact.denominator != 1 or exact.numerator not in (-1, 0, 1):
            raise ValueError("5x5 source requires integral entries in {-1,0,1}")
        return exact.numerator
    raise ValueError("only signed numeric literal lists are accepted")


def parse_data_cell(source: str) -> list[dict]:
    tree = ast.parse(source)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign):
        raise ValueError("expected exactly one assignment")
    assignment = tree.body[0]
    if (len(assignment.targets) != 1 or not isinstance(assignment.targets[0], ast.Name)
            or assignment.targets[0].id != "decomposition_555"
            or not isinstance(assignment.value, ast.Tuple)
            or len(assignment.value.elts) != 3):
        raise ValueError("unexpected data assignment")
    factors = []
    expected_call = "Attribute(value=Name(id='np', ctx=Load()), attr='array', ctx=Load())"
    expected_dtype = "keyword(arg='dtype', value=Attribute(value=Name(id='np', ctx=Load()), attr='float32', ctx=Load()))"
    for node in assignment.value.elts:
        if (not isinstance(node, ast.Call) or ast.dump(node.func) != expected_call
                or len(node.args) != 1 or len(node.keywords) != 1
                or ast.dump(node.keywords[0]) != expected_dtype):
            raise ValueError("unexpected np.array wrapper or dtype annotation")
        factor = _literal(node.args[0], source)
        if (not isinstance(factor, list) or len(factor) != 25
                or any(not isinstance(row, list) or len(row) != 93 for row in factor)
                or any(type(x) is not int for row in factor for x in row)):
            raise ValueError("expected three 25x93 integral arrays")
        factors.append(factor)
    return [
        {axis: [factors[a][i][r] for i in range(25)]
         for a, axis in enumerate(("u", "v", "w"))} for r in range(93)
    ]


def import_reference(source: Path, output_dir: Path) -> dict:
    payload = source.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != SHA256:
        raise ValueError(f"notebook SHA-256 mismatch: {digest}")
    notebook = json.loads(payload, object_pairs_hook=_unique_object)
    cells = notebook["cells"]
    if (cells[49]["cell_type"] != "markdown"
            or "Rank-93 decomposition of <5,5,5> over Z" not in "".join(cells[49]["source"])
            or cells[50]["cell_type"] != "code"):
        raise ValueError("unexpected notebook cell layout")
    terms = parse_data_cell("".join(cells[50]["source"]))
    metadata = {
        "method": "published-alphaevolve-reference", "novel": False,
        "source_repository": "https://github.com/google-deepmind/alphaevolve_results",
        "source_commit": COMMIT, "source": SOURCE, "source_sha256": digest,
        "source_cell_index_zero_based": 50,
        "attribution": "Google DeepMind; Novikov et al., AlphaEvolve (2025), arXiv:2506.13131",
        "materials_license": "CC-BY-4.0", "software_license": "Apache-2.0",
        "third_factor": "trace: w[k*5+i] contributes to output[i][k]",
        "changes": "Exact literal extraction; no notebook execution, float32 conversion, or basis change.",
    }
    integer = {"dimension": 5, "field": 0, "terms": terms, "metadata": dict(metadata)}
    integer_report = verify_candidate(integer, random_trials=64, seed=20261102)
    if not integer_report["valid"]:
        raise ValueError(f"original integer reference failed verification: {integer_report}")
    transposed = {**integer, "terms": [
        {**term, "w": [term["w"][j*5+i] for i in range(5) for j in range(5)]}
        for term in terms]}
    transpose_report = verify_candidate(transposed, random_trials=0)
    parity = Counter(tuple(x % 2 for axis in ("u", "v", "w") for x in term[axis])
                     for term in terms)
    nonzero_keys = [key for key, multiplicity in parity.items()
                    if multiplicity % 2 and all(any(key[a*25:(a+1)*25]) for a in range(3))]
    binary_terms = [{axis: list(key[a*25:(a+1)*25])
                     for a, axis in enumerate(("u", "v", "w"))}
                    for key in sorted(nonzero_keys)]
    binary = {"dimension": 5, "field": 2, "terms": binary_terms,
              "metadata": {**metadata, "changes": metadata["changes"] +
                           " Signed entries reduced modulo 2; zero terms removed and identical terms cancelled by parity; triples sorted."}}
    binary_report = verify_candidate(binary, random_trials=64, seed=20261102)
    if not binary_report["valid"]:
        raise ValueError(f"binary reference failed verification: {binary_report}")
    report = {
        "source_commit": COMMIT, "source_sha256": digest, "novel": False,
        "source_integer_term_count": len(terms), "canonical_F2_term_count": len(binary_terms),
        "zero_terms_F2": sum(not all(any(x % 2 for x in term[a]) for a in ("u", "v", "w")) for term in terms),
        "distinct_F2_triples_before_cancellation": len(parity),
        "integer": integer_report, "F2": binary_report,
        "orientation_check": {"selected": "trace convention, source W unchanged",
                              "transposed_W_valid": transpose_report["valid"],
                              "transposed_W_mismatches": transpose_report["mismatch_count"]},
        "scope": "Published reference, no discovery claim. F2 certificate literal coefficients do not establish an integer lift; the separate signed source does.",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in (("alphaevolve93_integer.json", integer), ("alphaevolve93_f2.json", binary),
                       ("alphaevolve93_verification.json", report)):
        (output_dir/name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    write_standalone_verifier(output_dir/"alphaevolve93_verify.py")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(import_reference(args.source, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
