# Small contextual controller: measured comparison, no learned-policy promotion

`mmsearch/binary_block_controller7.py` adds12 discrete arms: six axis orders,
three bit-perturbation sizes, one factor resample, best-state perturbation and
a random restart. Each arm applies exact GF2 factor-block minima from the
independently reviewed core. Tensor coefficients remain literal binary masks.
The contextual table uses residual-density, stagnation and sparse residual-mode
support buckets. Counts, reward sums and reward components are exact integers.
No network, GPU, real-valued factor update or policy-gradient machinery is used.

The per-action reward is1000 times integer residual decrease, plus a small
new-state bonus of2 times core entries. Terminal product-count credit is
2000 times entries times actual verified product benefit, and is available ONLY
after zero packed residual AND an independent zero scalar residual check.
Nonzero-loss approximations never receive product-count/validity credit,
regardless of inactive slots or apparent product count. Already exact input
fixtures receive no controller training credit merely for being supplied.
Global best loss is retained separately from exploratory current loss.

The policy checkpoint includes all context/arm integer statistics, update count,
seed, operator names and full RNG state. Frozen evaluation does not mutate its
table or RNG. Search outputs also retain diagnostic state/RNG/visited-state
checkpoints. Raw exact compact observations have no ambient publication format
and require independent global expansion/verification. The target rank never
drops while residual is positive. In the authorized15->14 pilot, a verified
14-slot compact success would already meet the global92 goal, so the canonical
guard owns freeze/stop; a speculative13-slot phase is not dispatched.

## Actual bounded training and disjoint-seed comparison

`scripts/train_binary_block_controller7.py` ran96 tiny/planted episodes with
training fixture seeds10000..10095 and policy seed71701. It then froze the
checkpoint and compared32 disjoint planted fixture seeds20000..20031 per
policy. These are synthetic seed splits on the known n2 tensor, not private
training/evaluation data. Run time was2.691 seconds on CPU1 nice10 with a512MiB
address-space limit; no N=5 source or target was read.

| Frozen evaluation policy |Raw exact observations/32 |Sum best residual |Actions |
|---|---:|---:|---:|
| Fixed control |15 |47 |424 |
| Learned contextual bandit |14 |52 |447 |
| Uniform arms |11 |61 |525 |

The predeclared promotion rule required the learned policy to strictly beat
BOTH controls on `(exact successes,-total best residual)` after all comparisons.
It did not. The selected policy was FIXED, and trained weights were not promoted
into the N=5 pilot. Every policy failed all8 schoolbook-drop-one cases, retaining
loss1, and all8 cold starts. This is limited tiny-data evidence, not proof that a
control will be best on other tensors.

Full logs, exact checkpoint, seed/config evidence and CSV/SVG training curves
are in `research/marathon7/evidence/binary-block-controller-training-v1/`.
The model checkpoint SHA256 is
`608bde7a2e6d8209297a6d777052e25178ff938833eec880106d22ade868aa4a`.

## Actual qualified nine-case baseline pilot

The root-authorized pilot used only the nine frozen mixed15/d11 cases, source
raw56e2dc... and the append-only all-nine-core pin supplement f0487990.... The
supplement reconstructs the complete15-product target, checks all ambient
entries, actual mode ranks11 in all modes, and freezes the compact input/bases.
Initialization removes just one MINIMUM compact-support-volume source product
to form14 approximate slots; it never removes that product from the TARGET.
Independent QA accepted the entire33-file runtime closure and all9 source/cores.

Runtime reuses the unchanged reviewed mixed12 `run_case` lifecycle and its50ms
CancelPoller, hidden raw returns, full ambient15625-entry primary+strict
independent checks, postpublication gates and late/error record quarantine.
No local WINNER or separate first-record publisher is used in this driver;
the canonical C7 guard owns global record freeze/stop. A bridge maps ONLY
packed+scalar verified zero compact loss to the existing SAT-positive protocol;
every heuristic failure maps to UNKNOWN, never a negative CP result.

Actual result: **9 attempts,9 UNKNOWN, best losses1 in every case**, in108.523
seconds on CPU1 nice10 with1GiB address-space limit. No exact or eligible global
candidate was emitted. All9 mathematical cases remain open. Artifacts are in
`artifacts/marathon7_20261103T122417Z/binary-block-d11-pilot9-001/`, including
the exact plan/QA/code snapshots and hidden raw controller states. This unchanged
pilot was not repeated. The measured loss1 plateau motivates a different joint
slot operator rather than claiming benefit from further fitting the same bandit.
