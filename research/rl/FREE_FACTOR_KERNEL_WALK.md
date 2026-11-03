# Exact fixed-pair kernel-circuit sparsity walk

This separate branch reuses the fixed-pair algebra in `mmsearch/free_factor_sat.py`.
For fixed pair columns P and 25-bit free vectors W[g], matrix multiplication is
the exact packed system PW=Y. A support S whose fixed-pair columns XOR to zero
permits W[g] ^= d for every g in S and any nonzero binary mask d. The tensor is
unchanged. These are known linear-kernel moves, not a new mathematical identity.

If S contains z zero groups and f groups currently equal to d, the exact change
in active groups is z−f. The modal nonzero W among S minimizes that change.
Neutral moves cross plateaus; periodic uphill proposals are capped at best+6
active groups. Most proposals use the local modal vector, with some random
existing vectors. One in ten uphill opportunities proposes an arbitrary nonzero
mask, so coefficient vectors are not permanently limited to the initial labels'
span. Coefficients and all matrix arithmetic remain integer bits throughout.

## Prepared finite family and circuits

The prepared WU family uses
`factor-pair-closure-v1/wu/dictionary.json` and KM93. WU fixes original W and U,
leaving original V free; the array name W[g] is the generic algebraic free-vector
notation, not a change in original tensor-axis convention. The saved permutation
and decoder reconstruct original U,V,W positions explicitly.

The actual preparation has 1536 distinct pairs, exact linear rank 371, nullity
1165, and 93 active baseline groups. It contains 9008 independently checked
zero-XOR supports:

- 1291 three-column circuits, found by streaming all pair sums and looking up
  the third column in an O(p) column index.
- 143 four-column circuits, found by storing only the 4278 sums from pairs of
  initially active groups, then streaming all p-choose-two pairs for collisions.
- 7574 optional symmetric differences of two retained three/four circuits
  sharing groups, with support at most eight.

Every support is deduplicated and checked against its full 625-bit column XOR.
The actual circuit span has dimension **1009**, smaller than the full kernel's
1165. Thus this walk has an additional affine restriction inside the fixed-pair
family. Combining circuits does not enlarge their linear span. The bounded
active-count policy restricts traversal further. Failure to reach 92 proves
neither global nonexistence nor UNSAT for the full fixed-pair family.

Preparation retained only O(p+93²+circuits) indexing storage, without a quadratic
all-pair hash map. The measured run on CPU2 took 0.68 wall seconds / 0.50 user
CPU seconds and peaked at about 36 MB RSS. The immutable prepared data are under
`artifacts/rl_campaign_20261102T210735Z/kernel-walk-wu-prepared-v1/`: original
inputs, canonical pairs, packed original rows, witnessed RREF, orientation,
baseline model, circuit classes/witnesses, native input, source code and hashes.
A separate exact span audit and zero-move native 5x5 baseline control are saved.

## Native implementation and verification

`native/free_factor_kernel_worker.cpp` is a new native worker. It validates all
circuits and the full original PW=Y equations before searching. Each checkpoint
checks best, current, and dirty archive models against all 625 packed rows, each
holding 25 exact free-coordinate equations. Active-group count is maintained
incrementally and checked against the z−f prediction. A fixed-size archive keeps
at most 16 models. The executable uses one thread, inherits CPU affinity, and
enforces a 512 MB address-space cap. Profiles `mixed`, `short`, and `wide` vary
the proportions of three/four/combined circuit proposals. They are fixed search
policies, not a learned controller.

The raw native prefix is `kernel_walk`; `.best.w.txt`, `.current.w.txt`, and
`.archive/*.w.txt` contain free-vector models, not full certificate triples.
`scripts/campaign_kernel_walk.py` verifies the original packed equations again,
decodes the orientation, and independently checks all 15,625 global coefficients
for every exported model. Only then does it write globally verified
`walk.stats.json` and full-triple `walk.best.txt`/`walk.current.txt` shadows for
existing monitors. Actual active groups equal essential products because fixed
pairs are distinct and both fixed factors are nonzero.

Full certificates, raw model snapshots, verification reports and checksums are
created exclusively, with at most 32 retained certificates per rank. A verified
global rank≤92 bypasses the cap, freezes a root winner/report/standalone verifier,
and stops. Final exit is always drained, including a success before polling.
Native class attempts, actual accepted/uphill moves, timing, seeds, source and
executable hashes are recorded. There is no world-record claim for the known
rank-93 baseline or a negative bounded run.

```sh
taskset -c 2 python scripts/campaign_kernel_walk.py \
  --dictionary artifacts/rl_campaign_20261102T210735Z/factor-pair-closure-v1/wu/dictionary.json \
  --baseline artifacts/km93_f2.json --orientation wu \
  --prepared artifacts/rl_campaign_20261102T210735Z/kernel-walk-wu-prepared-v1 \
  --seconds 1800 --seed 1536093 --headroom 6 --plus-every 500 \
  --restart-every 100000000 --archive-size 16 --profile mixed \
  --outdir PATH/new-kernel-walk
```

Omit `--prepared` to reproduce circuit preparation; `--prepare-only` freezes it
without search. `--max-circuits` is capped at 50,000, and `--no-combos` disables
the optional symmetric differences during fresh preparation. Saved prepared
artifact hashes and reconstructed native input are checked before reuse. A new
output directory is required. No long search was started during implementation.

Six small tests cover exact delta arithmetic including zeros; streamed circuit
classes/witnesses; a planted Strassen product split into two fixed-pair atoms
(8 active groups recover 7 through a three-circuit move); rejection of corrupt
models and nonkernel supports; UV/VW/WU decoding; exact 5x5 baseline verification;
fast-success final draining; and wall-time checkpoint preservation. The actual
p1536/9008-circuit native zero-step control also verified baseline93 globally.

```sh
python -m unittest tests.test_free_factor_kernel
```
