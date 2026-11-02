# Published AlphaTensor baseline

`artifacts/alphatensor_5x5_f2_rank96.json` is the **published rank-96**
factorization for 5×5 matrix multiplication over F2. It is an imported baseline,
not a newly discovered decomposition, and does **not** satisfy a rank < 95 goal.

Source: Google DeepMind, AlphaTensor, commit
`1949163da3bef7e3eb268a3ac015fd1c2dbfc767`,
[`algorithms/factorizations_f2.npz`](https://github.com/google-deepmind/alphatensor/blob/1949163da3bef7e3eb268a3ac015fd1c2dbfc767/algorithms/factorizations_f2.npz),
member `5,5,5.npy`, shape `(3,25,96)`.

Archive SHA-256:
`70f09f349d8d2874ef0e0e089459c7320f5aa3eef277df5ffa67f573709db2da`.

Attribution: Copyright 2022 DeepMind Technologies Limited. The upstream
notebook states that software is Apache-2.0 and all other materials are
[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).
The factorization data and this converted artifact retain that CC-BY-4.0
attribution. The only transformation is conversion from the numeric source
arrays to JSON terms; no basis change or coefficient modification was made.
The source is associated with Fawzi et al., *Discovering faster matrix
multiplication algorithms with reinforcement learning*, Nature 610, 47–53
(2022), DOI: [10.1038/s41586-022-05172-4](https://doi.org/10.1038/s41586-022-05172-4).

## Coordinates and verification

The accompanying upstream `explore_factorizations.ipynb` states that factors
represent the symmetrized tensor. All coordinates here are row-major:

`T[5*i+j, 5*j+k, 5*k+i] = 1` for `0 <= i,j,k < 5`.

Consequently the third factor contributes as `w[5*k+i]` to output entry
`C[i,k]`. The JSON retains this trace convention without transposing `w`.
The importer reconstructs all 15,625 coefficients with exact int64 arithmetic,
reduces modulo 2, and checks coefficient equality. All coefficients agree.

## Reproduce

From the repository root:

```sh
python scripts/import_alphatensor.py /path/to/factorizations_f2.npz
```

The importer first checks the archive hash. It loads only `5,5,5.npy` with
`allow_pickle=False`; that member is a numeric int64 array, even though some
other archive members are object arrays. No pickle deserialization is needed.
