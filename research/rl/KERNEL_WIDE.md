# Optional wide kernel-circuit branch

`native/free_factor_kernel_worker_wide.cpp` is a separate source/executable that
accepts 3–128 groups per exact kernel support. The old source and frozen binary
remain unchanged. The changes are the length guard, distinct `MMKERNELWIDE1`
input magic and wide engine name, plus counters for attempted/accepted supports
longer than eight. The modal-vector/delta mathematics, incremental active count,
PW=Y checks at start/checkpoints, archive, clock, and native 512 MB address-space
limit are unchanged. The outer pilot reserves 768 MiB for the Python wrapper
and native process together on one CPU.

`mmsearch/free_factor_kernel_wide.py` owns its 3–128 validator and serializer.
Neither serialization nor the prepared-only runner calls the old eight-group
validator. Every support has distinct in-range indices and full 625-bit P*n=0.
Class0 remains a triple, class1 an anchored quadruple, and class2 includes known
combinations and fundamental supports. The existing `wide` profile still samples
20% class0, 30% class1, and 50% class2; it does not mean every proposal is long.
`long_support_attempts` and `long_support_accepted` expose actual long activity.

The compact new data append 69 independently chosen, shortest-first fundamental
supports to the verified 9262-circuit short-expanded set. Total9331 supports
span all1165 dimensions of the fixed-pair kernel; baseline remains KM93 on1536
WU pairs. The complement lengths are9–105, median25. Source RREF/free-coordinate
witnesses, nonzero remainders against earlier spans, all P*n=0 checks, and the
full-span proof are retained from `wide-independent-complement/`. The new
`scripts/prepare_kernel_wide.py` additionally checks every support and both span
ranks itself before freezing the prepared format.

Exact initial modal admissibility among the69 new directions is:

| Headroom | Maximum initial rank | Admissible directions |
| ---: | ---: | ---: |
| 6 | 99 | 1 |
| 9 | 102 | 13 |
| 12 | 105 | 22 |
| 16 | 109 | 29 |
| 24 | 117 | 42 |
| 32 | 125 | 48 |

These counts use delta=zeros−maximum nonzero-vector frequency on each support.
They are initial best-d measurements, not guarantees that a proposal will be
selected or that every kernel direction is accessible under a rank cap.
**Full linear kernel span does not prove bounded-headroom graph connectivity
or nonexistence of a low-rank solution.**

`scripts/campaign_kernel_walk_wide.py` is a prepared-only V2 variant. It reuses
the frozen postcompression, immutable first-winner handling, independent global
verification, raw/derived rank distinction, and finite-family scope. Its defaults
are600 seconds, headroom16, plus every100, restart every1e9, profilewide. This is
an intentional larger escape budget, not an identical control to headroom6.
The initial raw cap is109. Inline V2 compression has no rank100 cutoff and keeps
its .25s budget; separate audits that stop at rank100 must report higher raw
states as skipped rather than infer failure.

Prepared data:
`artifacts/rl_campaign_20261102T210735Z/kernel-wide-prepared-v1/`.
The reviewable job JSON and frozen hashes are under
`frozen/kernel-wide-v1/`. Root can launch after reviewing the short pilot:

```sh
python scripts/campaign_kernel_walk_wide.py \
  --dictionary artifacts/rl_campaign_20261102T210735Z/factor-pair-closure-v1/wu/dictionary.json \
  --baseline artifacts/km93_f2.json --orientation wu \
  --prepared artifacts/rl_campaign_20261102T210735Z/kernel-wide-prepared-v1 \
  --binary artifacts/rl_campaign_20261102T210735Z/frozen/kernel-wide-v1/native/free_factor_kernel_worker_wide \
  --seconds 600 --seed 116593 --headroom 16 --plus-every 100 \
  --restart-every 1000000000 --archive-size 16 --profile wide \
  --slice-compress --compression-seconds .25 --outdir PATH/new-wide-pilot
```

Three brief tests cover a nine-group kernel move, one actual accepted native
wide update with full global2x2 verification, and Python/native rejection of
nonkernel and129-group supports. A separate zero-step native control loaded all
9331 supports, checked original PW=Y, and independently verified all15,625 global
coefficients of baseline93. The prepared-only wrapper compatibility check also
passed. No long search was launched during preparation.

```sh
python -m unittest tests.test_kernel_wide
```
