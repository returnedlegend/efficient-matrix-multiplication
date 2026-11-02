#!/usr/bin/env python3
"""Safely import and exactly check the published AlphaTensor F2 5x5 baseline.

Only the numeric 5,5,5.npy member is read. Pickled object-array members are never
loaded, and NumPy's allow_pickle is explicitly disabled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

SOURCE_COMMIT = "1949163da3bef7e3eb268a3ac015fd1c2dbfc767"
SOURCE_SHA256 = "70f09f349d8d2874ef0e0e089459c7320f5aa3eef277df5ffa67f573709db2da"
SOURCE_URL = (
    "https://github.com/google-deepmind/alphatensor/blob/"
    f"{SOURCE_COMMIT}/algorithms/factorizations_f2.npz"
)


def import_baseline(source: Path) -> dict:
    """Return an attributed certificate after checking every tensor coefficient."""
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError(f"source SHA-256 mismatch: {digest}")
    with np.load(source, allow_pickle=False) as archive:
        factors = archive["5,5,5"]
    if factors.shape != (3, 25, 96) or factors.dtype.kind not in "iu":
        raise ValueError("unexpected published factorization shape or dtype")
    if not np.all((factors == 0) | (factors == 1)):
        raise ValueError("published factors are not binary")

    # int64 avoids small-integer accumulation overflow; there are 96 terms.
    factors = factors.astype(np.int64)
    reconstructed = np.einsum("ar,br,cr->abc", *factors) % 2
    expected = np.zeros((25, 25, 25), dtype=np.int64)
    for i in range(5):
        for j in range(5):
            for k in range(5):
                expected[5 * i + j, 5 * j + k, 5 * k + i] = 1
    residual = np.bitwise_xor(reconstructed, expected)
    if np.any(residual):
        raise ValueError(f"coefficient verification failed: {np.count_nonzero(residual)} mismatches")

    return {
        "dimension": 5,
        "field": 2,
        "terms": [
            {axis: factors[a, :, r].tolist() for a, axis in enumerate(("u", "v", "w"))}
            for r in range(96)
        ],
        "metadata": {
            "method": "published-alphatensor-baseline",
            "rank": 96,
            "novel": False,
            "source": SOURCE_URL,
            "source_repository": "https://github.com/google-deepmind/alphatensor",
            "source_commit": SOURCE_COMMIT,
            "source_sha256": digest,
            "source_member": "5,5,5.npy",
            "attribution": "Copyright 2022 DeepMind Technologies Limited; AlphaTensor published factorization.",
            "materials_license": "CC-BY-4.0",
            "materials_license_url": "https://creativecommons.org/licenses/by/4.0/",
            "third_factor": "trace: w[k*5+i] contributes to output[i][k]",
            "tensor_convention": "T[(i,j),(j,k),(k,i)] = 1; row-major coordinates",
            "changes": "Numeric source arrays converted to binary JSON terms; no change of basis or term modification.",
            "verification": {"method": "exact coefficient equality modulo 2", "coefficients": 15625, "mismatches": 0},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Pinned upstream factorizations_f2.npz")
    parser.add_argument("--output", type=Path, default=Path("artifacts/alphatensor_5x5_f2_rank96.json"))
    args = parser.parse_args()
    certificate = import_baseline(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(certificate, indent=2) + "\n", encoding="utf-8")
    print(f"Verified all 15625 coefficients over F2: rank 96; wrote {args.output}")


if __name__ == "__main__":
    main()
