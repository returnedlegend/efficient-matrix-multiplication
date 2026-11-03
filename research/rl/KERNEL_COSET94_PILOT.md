# Prepared 300-second kernel pilot from the distinct rank94 seed

The confirmed input is
`kernel-coset-seeds-v1/seeds/seed-00-rank94/candidate.json` under the current
campaign. Its raw SHA-256 is
`d3eda639da69ca850756734d3330013aaa3ee032ae4eba8662907727d4a793cb`.
Independent verification checked all 15,625 coefficients and confirmed rank94.

The frozen `prepare_system` algebra accepts this baseline. The frozen V2 main
entry point, however, explicitly rejects any source canonical rank other than
93. Therefore `scripts/campaign_kernel_coset94_pilot.py` is a separate copy with
a rank94-only source guard, a 300-second default, and the additional wrapper
provenance entry. Its native kernel mathematics, V2 postcompression, immutable
first-winner handling, and target92 behavior are unchanged. The original V2,
kernel module, compressor, and frozen native executable are not edited.

The pilot command intentionally omits `--prepared`: baseline-active pair sums
and anchored four-circuits are regenerated from this rank94 source. A separate
prepare-only preflight already succeeded, yielding 1536 fixed pairs, 94 active
groups, linear rank371/nullity1165, and 8898 checked circuits: 1291 triples,
139 baseline-anchored quads, and 7468 combinations. Preparation on CPU2 nice10
took 2.26 wall seconds, 0.68 user CPU seconds, and about 36 MB peak RSS. The
control ran the frozen native executable with zero moves, rechecked all circuits
and PW=Y, then independently decoded and checked the full rank94 algorithm at
all 15,625 entries. It performed no search.

The regenerated circuits and old circuits both span dimension1009; their union
also has dimension1009. Regeneration therefore changes the circuit inventory
without bridging the old move span in this case. The rank94 model's displacement
from KM93 lies outside both spans, so it tests a different original S-coset.
This is a coefficient-space observation, not a claim of algorithm inequivalence,
active-count reachability, or a new multiplication bound. A negative 300-second
walk is neither global nor fixed-family UNSAT. Optional slice compression may
leave the native family and remains independently verified.

The reviewable job JSON is
`artifacts/rl_campaign_20261102T210735Z/kernel-coset94-preflight-v1/job.json`.
It requests CPU2, a 300-second internal budget and a 315-second outer limit,
512 MB, the frozen kernel binary, target92, headroom6, mixed circuits, plus every
500 moves, restart every100M moves, archive16, and V2 slice compression at .25s
per new raw state. Root can queue it after `fixed2-long3` and before `fixed2-long4`.
No long run has been launched by this preparation.
