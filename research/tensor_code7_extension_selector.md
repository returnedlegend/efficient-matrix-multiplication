# Separate pair-span-escape selector, version1

This append-only selector leaves the frozen odd-identity/prepared-v2 contract unchanged. It implements the root's stronger pair-space criterion rather than the earlier lex-first proposal. Generation produces only authenticated algebraic five-term witnesses and diagnostics; it does not build an extended kernel or run a target query.

For oriented parents `x=(a,b,c)` and `y=(d,e,f)`, the three derived UV columns are

```
(a+d) tensor b = (a tensor b) + (d tensor b)
d tensor b
d tensor (b+e) = (d tensor b) + (d tensor e).
```

If both parents are active in the chosen seed, their original UV columns lie in its projected span S. Therefore all three new UV columns have the same remainder as the cross column `d tensor b` modulo S. The new projected span gains exactly1 dimension when that remainder is nonzero, otherwise0. It can gain at most1. The identical argument applies to the larger original whole-dictionary projected span P. N5 pair columns contain625 exact bits; no floating arithmetic is used.

An odd three-term split can change full-code parity while leaving a fixed pair span unchanged. This does not escape an existing minimum93 proof for that pair space. The five-term selector therefore requires an escape from the selected seed pair span. Global P escape is a stronger scheduling preference, not a claim of global algorithm novelty or a guarantee of a weight92 state. The existing minimum93 results apply only to their independently certified spaces.

`select_witnesses` scans at most8192 candidate parent-pair/axis records. It visits the32 approved seed supports round robin, coactive base parent pairs lexicographically, and all six axis orders in fixed order. It rejects zero/duplicate identities, relations wholly in the old dictionary, and seed-span nonescapes. From this fixed bounded pool it chooses at most16 distinct five-term cycles, prioritizing global pair escape, independent quotient directions, new cosets and balanced source use, with deterministic trial-order ties. It adds at most100 new atoms, or fewer when that cap or the5000 total cap prevents a choice. Each relation derives only three atoms, so16 relations introduce at most48 unique atoms. There is no fallback that invents candidates when the bounded prefix is insufficient.

Each accepted record reports the exact source-seed mask, base parent IDs, axis order, seed/global basis ranks and hashes, cross column, reduced seed/global remainders, exact projected rank gains and selected quotient independence. Accepted five-term zero tensors receive both complete packed and independent scalar checks. These are algebraic diagnostics only. The final frozen v3 preparation contract reconstructs and independently verifies every witness and grants this selector no mathematical trust privilege.

The new CLI `scripts/tensor_code7_extension_select.py` is disabled by default. Root explicitly authorized one bounded N5 witness generation on2026-11-03 using parent raw SHA `cf4644cab66d697f05d6724d919973b9884f17def9586c0e1220b9ea67554e2b` and the32-source anchor raw SHA `26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8`. That authorization does not permit an extended-dictionary build, heuristic or SAT query. The approved generation bounds are8192 attempts,16 relations,100 new atoms,120 seconds, CPU1/nice10,1024MiB and32MiB output. Old406-atom experiment archives stay unchanged.

The helper uses the DIRECT cached guard pinned to `09ac03c4ac1123eeb2ddba8a72653cc299aca052df9ad6c82ad618ed5cbd5cd9`, independently audited by24 synthetic controls. No legacy `marathon7_local.CampaignGuard` instance handles selector calls. Current file signatures, typed fresh resource state, live PID identity, canonical markers and clocks remain authority. Source/config/output/publication stages force fresh barriers; inner calls use the direct guard's live checks and cached JSON parses. Deadline is clamped to caller, pinned C7 config and fixed19:24:17 UTC. A late witness remains hidden and nested in UNKNOWN metadata. The helper freezes current code closure and the unchanged approved base package, plus actual parameters/resources. It has no target-query path.

The mathematical and CLI controls use tiny data or expired/missing-input cases:

```sh
taskset -c 1 nice -n 10 python -B -m unittest tests.test_tensor_code7_extension_selector -v
```

They cover rank-gain equivalence, all axis orders, global-versus-seed span differences, deterministic bounded selection, rejection of odd relations that stay inside S, exact full zero checks, parameter/coactivity guards, disabled input isolation, and expired authorization without base input IO. No production witness generation occurs in these tests.
