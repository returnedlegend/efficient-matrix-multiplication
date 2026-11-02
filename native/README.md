# Native exact flip worker

`bash scripts/build_native.sh [OUTPUT_BINARY]` compiles with the system C++17
compiler and writes `OUTPUT_BINARY.sha256` containing source and binary hashes.
No third-party solver code is incorporated.

Input consists of decimal unsigned factor-mask triples, one term per line,
using the same trace convention and least-significant-bit vector indexing as
`mmsearch.search.decode_candidate`. Duplicate terms cancel in F2; zero factors
are discarded. The worker checks every coefficient against the requested
matrix multiplication tensor before beginning.

```
native/flip_worker --input seed.txt --output results/seed0 \
  --n 5 --target 92 --max-rank 99 --seed 0 \
  --steps 1000000000000 --seconds 600 --checkpoint-seconds 30 \
  --archive-size 256 --archive-every 100 \
  --plus-every 250 --restart-every 50000
```

The walk uses exact two-term flips, plus identities and immediate two-factor
merges. Single-factor and factor-pair buckets are updated incrementally.
`--cyclic` applies each identity together with its cyclic rotations, requires
cyclic closure in the seed, and preserves that closure (including fixed cubes).
It is available in version two of the source and in `flip_worker_cyclic`;
the binary still defaults to unrestricted walks unless `--cyclic` is supplied.
The rank cap is absolute. All random choices use `mt19937_64`; reproducibility
requires the same binary, initial triples, options and completed step count.
Wall-clock budget checks happen every 256 moves. SIGINT/SIGTERM requests a
graceful final checkpoint.

Output files are atomically replaced:

- `PREFIX.best.txt`: smallest-rank exact state encountered.
- `PREFIX.current.txt`: current exact walk state, possibly above best rank.
- `PREFIX.stats.json`: budgets, actual steps, rank history, move counters and
  archive size. `target_reached` reports the rank comparison.
- `PREFIX.archive/0.txt`, `1.txt`, etc.: distinct states at the current best
  rank. Read indices below `archive_size` in stats; old higher indices may
  remain after a best-rank improvement. Archive replacement uses a bounded
  random pool with a two-word fingerprint for duplicate filtering.

The worker checks all coefficients of best, current and dirty archive entries
before each checkpoint and immediately on every improvement. A caller should
also verify candidate artifacts with the independent Python certificate
verifier. A rank goal is a search objective, not an existence claim.

`--trace PATH` writes every state after a move for small verification tests.
`--allow-arbitrary` skips the matrix multiplication input restriction while
still checking that the initial tensor is preserved; it marks `exact: false`
in stats and is intended for identity tests.

`python -m unittest tests.test_native -v` compiles a separate temporary binary,
checks arbitrary-tensor identities at every move, independently verifies small
dimension checkpoints/archives, and verifies a reproducible walk from the
published rank-93 certificate for dimension five. It also checks cyclic tensor
identities and orbit closure at every move and a cyclic dimension-five walk.

`flip_worker_v1.cpp` freezes the initial unrestricted campaign implementation;
`flip_worker_v2.cpp` freezes the version adding cyclic support and stricter
input/budget validation. Campaign jobs should copy a matching source snapshot,
binary and SHA256 manifest before launch.
