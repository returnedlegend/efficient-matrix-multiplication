# Mixed15 rank-12 necessary filter

The one authorized pass over all 112 deferred rank-12 packets excluded **three** at local budget 14. The other **109** passed only a necessary condition and remain unresolved. No CP decoder or decomposition search was called; the nine rank-11 packets were untouched.

For actual slice-image dimension 12 and surplus two, CP ≤14 requires the span of matrices of rank at most two—including rank-one matrices—to have dimension at least 11. The unchanged reviewed module `rank2_span_bound7.py` (`b4388978ed49e10a9487e7c78c0059381ce680233045ebd5db0580c850f66c4b`) found exact span dimension 10 in each excluded case after enumerating all 4,095 nonzero image matrices:

- `c3-mixed15-p09-15-23-26`
- `c3-mixed15-p10-11-14-19`
- `c3-mixed15-p12-15-21-23`

Every other packet supplied an independent 11-vector low-rank witness before enumeration ended. Its full low-rank span dimension was not measured; no existence claim follows. The pass classified 322,890 matrices in total. All 112 actual cores were reconstructed from the pinned approved source, fully expanded and checked before classification; source/core hashes and mode bases are retained per case. The source passed both full 15,625-coordinate verifiers.

A separate read-only audit reconstructed and independently ranked every pass witness. It also replayed all 4,095 matrices for each of the three negatives using independent row-rank elimination and verified that every low-rank matrix belongs to the recorded 10-dimensional span. Three controls cover a true-surplus-two N4 necessary pass, a necessary pass with no CP solution at the requested budget, full negative enumeration, cancellation and a late hidden `UNKNOWN` return.

The bounded pass ran on CPU 3 at nice 10 / 512 MiB, with 120 seconds internally / 150 externally. It used 6.700714 CPU seconds, 7.039711 outer wall seconds and peak RSS 126,876 KiB. There were no unknowns or errors.

The 109-case larger-mode decoder plan is disabled and binds each exact source-index list, core hash and serialized input hash. The separate larger-mode surplus-two prototype has passed independent review; actual N5 decoder queries still require execution authorization. The first three passing cases are listed for a bounded calibration. No automatic query continuation is enabled.

Artifacts: `c3-mixed15-rank2-filter112-001` and `c3-mixed15-rank2-filter112-seal-v1`. Summary pin: `8c8ebbebf7986694603c998b0adc710fba2ae4d7964b9faad2917ebc232af539`; passed plan: `01e263117d4fb3e86748035d7509ee380dda65ff8d6d51f4bee55c0baca68c64`; seal: `d0a1e46d5b96c08af7bf5391aa754dac858c7a2c81eed17c2b561eafd895c393`. Small evidence: `evidence/c3-mixed15-rank2-filter112.json` (`733af498123eae1568648b25b217090f4cebcd90fe3fe27adff983b9616a8c43`). These are local finite-packet exclusions, with no global rank lower bound.
