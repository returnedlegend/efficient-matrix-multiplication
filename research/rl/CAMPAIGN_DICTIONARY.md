# Freezing a finite campaign dictionary

`scripts/freeze_campaign_dictionary.py` merges explicitly selected exact 5x5
F2 certificates and optional extra rank-one columns. It does not search or run
a solver. Repeat `--candidate PATH` and `--candidate-dir DIR` as needed; each
directory contributes only its immediate `*.json` files. Every selected file
must be a certificate: verification reports, manifests, and malformed files
raise an error rather than being silently skipped.

```sh
python scripts/freeze_campaign_dictionary.py \
  --candidate artifacts/km93_f2.json \
  --candidate PATH/alphaevolve93_f2.json \
  --candidate-dir PATH/ae-native1/verified \
  --candidate-dir PATH/fixed2-1/verified \
  --extra-dictionary PATH/older-dictionary.json \
  --output-dir PATH/new-dictionary
```

The output directory must be new. At least one complete exact certificate is
required, providing a feasible baseline. Each original certificate passes an
independent exhaustive check of all 15,625 coefficients before contribution.
Strict binary factor entries are required; duplicate products cancel over F2
and zero products are removed before counting and unioning columns. The
canonical certificate also undergoes exhaustive verification. Extra dictionaries
must be JSON arrays of nonzero integer mask triples below 2^25. Their columns
are legitimate rank-one tensors; the script makes no claim that they sum to
a complete multiplication algorithm.

`dictionary.json` is the deterministic lexicographically sorted union of
distinct triples, compatible with the existing finite-dictionary SAT drivers.
`pool.json` records all source paths, raw checksums, supplied and essential
ranks, distinct canonical algorithms, extra-column provenance, and code hashes.
The lowest essential-rank verified source becomes `baseline.json`, with its
own exhaustive verification report. Input raw bytes, per-input verification
reports, relevant source code, a standalone verifier, and output checksums are
preserved. Files are created exclusively and made read-only. Repeating the
same inputs into a different fresh directory yields identical artifact bytes.

This snapshot defines a finite set of admissible rank-one columns. A subsequent
subset-SAT UNSAT result applies only to those frozen columns and the encoded
rank bound; it does not establish global nonexistence. Selecting arbitrary
dictionary subsets is also distinct from selecting odd combinations of whole
source algorithms, so an all-odd-source affine-span parity restriction should
not be incorrectly applied to dictionary subset SAT.

Tests cover deterministic unions and provenance, strict immediate-directory
selection, invalid certificate/column rejection, duplicate and zero-product
canonicalization, immutable output protection, and minimum-rank baseline
selection: `python -m unittest tests.test_freeze_campaign_dictionary`.
