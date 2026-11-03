# Published AlphaEvolve reference

This is imported public reference data, **not a discovery of this campaign**.
Source: Google DeepMind, Novikov et al., *AlphaEvolve: A coding agent for
scientific and algorithmic discovery* (2025), arXiv:2506.13131.

Repository: <https://github.com/google-deepmind/alphaevolve_results>.
Pinned commit: `4226acbf237ff9ad10ba7673a2af127a2d8a5971`.
The immutable notebook is
<https://raw.githubusercontent.com/google-deepmind/alphaevolve_results/4226acbf237ff9ad10ba7673a2af127a2d8a5971/mathematical_results.ipynb>.
Its SHA-256 is
`2cce2543e48c89aa3e91614272a698a0147dd2548ea11cf92f1292b7435d38ff`.

Copyright 2025 Google DeepMind Technologies Limited, as stated in the notebook.
Upstream software is Apache-2.0; other materials are CC-BY-4.0. The source
notebook, upstream README, and repository LICENSE are retained beside this
file. See <https://creativecommons.org/licenses/by/4.0/legalcode> for the data
license. The upstream README states that execution code for AlphaEvolve is not
included in the public repository.

`scripts/import_alphaevolve93.py` parses only the numeric literals in notebook
cell 50 (zero based), headed by “Rank-93 decomposition of <5,5,5> over Z” in
cell 49. It validates the entire notebook hash and permits only the expected
assignment, tuple, array wrappers, lists, signed numeric literals, and inert
`dtype=np.float32` annotation. It does not execute notebook cells or upstream
scripts. Numeric source tokens are read as exact fractions and required to be
integers in {-1,0,1}; the original float32 annotation is never evaluated.

Changes: the signed integer arrays were converted to project JSON, then reduced
modulo 2 for a separate binary seed. Zero terms are removed, duplicate triples
cancel by parity, and binary triples are sorted. The binary seed still has 93
distinct nonzero terms. No basis change was made. The third factor retains the
source trace coordinates: `w[k*5+i]` contributes to output `(i,k)`.

The integer and binary identities each independently pass all 15,625 tensor
coefficient checks and 64 random matrix products. Transposing W instead fails
200 integer coefficient checks. The signed certificate establishes an integer
identity; the literal binary certificate alone does not (1,381 integer
mismatches). See `alphaevolve93_verification.json` and the retained independent
standard-library verifier, `alphaevolve93_verify.py`.

Reproduce from the project root:

```sh
python3 scripts/import_alphaevolve93.py \
  artifacts/rl_campaign_20261102T210735Z/public/alphaevolve93_source.ipynb \
  artifacts/rl_campaign_20261102T210735Z/public
```
