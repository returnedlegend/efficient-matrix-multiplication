# Complete local10 fixed-family closure

All **111,605** recorded source/mask keys are closed negative at local 10 → 9,
free image rank 8, over F2. This exactly matches the original necessary-survivor
catalogue, without duplicate proof keys or unvisited masks: 12 old pilot proofs,
10,706 earlier C7 proofs and 100,887 v5 proofs.

There were 111,607 input decoder calls. The two earlier UNKNOWN attempts were
preserved and later resolved by exact proofs after guard-cost fixes; neither
UNKNOWN was counted as negative. The final unresolved count is zero.

Distinct timed launcher attempts used **3973.867 CPU seconds**
and **5521.151 summed launcher wall seconds**.
The C7 calendar interval, including dispatch/preparation gaps, was
12231.187 seconds.
Each launcher is counted once, including incomplete attempts; nested runner
times and configured wall budgets are not added again. Per-phase details and
all source/snapshot/evidence hashes are in [the curated JSON](LOCAL10_FULL_CLOSURE.json).

## Exact scope

These are fixed-outside residual decisions for the explicit catalogue from four
approved 93-product sources. They do not prove a global lower bound for 5×5
matrix multiplication, nor produce a 92-product construction. The family is
retired; a new source or neighborhood requires the next strategy decision.

## Archived replay and resume

The [portable replay archive](evidence/local10_full_closure_replay_inputs.tar.gz)
contains the four byte-exact sources, complete 111,605-row catalogue, frozen
runtime Python and a file-hash manifest. It excludes raw case-output files.
Extract it in an isolated directory and run `python3 -B verify_inputs.py` to verify all hashes without decoding. Each
catalogue row supplies source ID, mask words, three image dimensions and free
axis. Rebuild its core with frozen SourceCache, then call frozen
compact_rank2_edges43.solve_core at budget 9, that axis and max_vectors=255.
Looping all catalogue rows reproduces the finite mathematical decision set.

Operational --resume uses the original frozen bundle, identical configuration
and hash-chained cursor; UNKNOWN never advances that cursor. The archived
campaign hard cutoff remains 2026-11-03T19:24:17Z. Decoder-only mathematical
replay is separate from restarting that expired campaign.

## Separate mode-closure11 pilot

The 64-parent factor-image census found 55 closures of size 10 and 9 of size 11.
The 9 new 11-term/image-8/target-10 masks were all negative, with 209 complete
repeated-pair extensions, no UNKNOWN/error and no source expansion. Actual
runner time was 1.155 seconds; source/canonical-mask checks and the genuine N4
surplus-two whole-source control passed. [Pilot pins and measurements](MODECLOSURE11_NINE_CASES.json)
keep this distinct model separate from the local10 closure.
