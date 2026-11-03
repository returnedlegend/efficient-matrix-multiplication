# Optional slice postcompression on kernel checkpoints

`scripts/campaign_kernel_walk_v2.py` is a separate clone of the frozen v1 runner.
Enable `--slice-compress --compression-seconds .25` to apply the unchanged frozen
`mmsearch/slice_compression.py` compressor to each new canonical raw full
best/current/archive state. Raw W models first satisfy PW=Y and independent full
tensor verification. Compression runs before raw per-rank storage-cap skipping,
so a capped raw portfolio cannot hide a useful derived algorithm.

The processed key is the raw canonical term-set hash, persisted in
`compression_state.json`. Each state is compressed once, using
`compress_candidate(stop_at_record=True)`. The quarter-second budget is the
compressor's internal search budget; its mandatory exact verification has a
small additional overhead. No rank drop means no derived candidate is published.
Strict drops receive another independent full-tensor check, then an immutable
derived certificate, report, checksum, source input/model, and complete move
proof. Input, source code, compressor, generic first-winner helper, and proof
hashes are preserved. Derived fixed pairs may differ from the original family,
which is explicitly recorded rather than interpreted as another native W state.

The first verified raw or derived candidate meeting the target uses the existing
exclusive `_freeze_first_winner` helper. It repeats exact verification and freezes
the primary certificate, SHA, report, standalone verifier, and checksums. A
callback immediately terminates the native worker. Once a primary exists, every
later scan and final drain skips all compression and primary writes. The first
algorithm is never replaced by another representation or subsequent refactoring.

`walk.stats.json` continues to report actual raw native active-group best/current
ranks. It never claims that a derived rank92 algorithm is a 92-group W model.
Separate fields expose `derived_best_rank`, `best_verified_rank`,
`primary_candidate_rank`, `primary_candidate_path`, and `campaign_target_reached`.
The native `target_reached` flag remains about the raw W model. The best verified
pointer retains a better derived certificate even when subsequent raw rank93
models are checked or stored. A valid derived algorithm outside the pair family
is a legitimate global result; fixed-pair SAT negatives would not exclude it.

Launch v2 with the same prepared data and binary as v1, adding the two optional
flags and a fresh output directory:

```sh
taskset -c 2 python scripts/campaign_kernel_walk_v2.py \
  --dictionary artifacts/rl_campaign_20261102T210735Z/factor-pair-closure-v1/wu/dictionary.json \
  --baseline artifacts/km93_f2.json --orientation wu \
  --prepared artifacts/rl_campaign_20261102T210735Z/kernel-walk-wu-prepared-v1 \
  --seconds 1800 --seed 1536093 --headroom 6 --plus-every 500 \
  --restart-every 100000000 --archive-size 16 --profile mixed \
  --slice-compress --compression-seconds .25 --outdir PATH/new-kernel-v2
```

The v1 wrapper, kernel module, native source/binary, prepared dependency data,
compressor, and first-winner helper are unchanged. Main remains strict 5x5 with
target92. Two small tests use a legitimate 2x2 raw rank9 source with a latent
three-to-two slice, producing postcompressed rank8 even though zero-step native
W stayed9. They check raw-versus-derived statistics, immediate stop notification,
first-winner byte/SHA immutability, final-drain compression refusal, processing
before a full raw storage cap, and repeated-state caching. No long search was
started during preparation.
