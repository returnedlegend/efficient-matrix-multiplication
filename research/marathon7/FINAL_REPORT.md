# Seven-hour campaign: final findings

**No verified 5×5 matrix multiplication algorithm with 92 or fewer bilinear products over F₂ was found. Best verified remains 93.** No record candidate, integer/complex lift, practical-runtime improvement, or new literature novelty is claimed.

The scheduled search window was November 3, 2026, 4:24–11:24 a.m. Pacific time (12:24:17–19:24:17 UTC). The global guard stopped at 19:24:17 UTC with `global campaign deadline reached`, no record directory and no pending record stop. The session was interrupted before final cleanup. Saved worker execution is documented; this is not a claim of seven hours of continuously supervised experimentation. This final audit performed no new target search.

| Experiment | Saved result | What remains open |
|---|---|---|
| Four-source local 10 family |111,605 unique keys excluded; two historical UNKNOWN attempts later resolved |All other sources/neighborhoods|
| Cyclic 12-term packets |All 4,060 excluded |Other packet sizes and sources|
| Cyclic 15-term packets |27,400 of 27,405 excluded |Three conditional timeouts and two cases with only Fano-branch negatives|
| New 366 whole-C3-orbit dictionary |Complete SAT result UNSAT at cost≤92; known 93 solution |Other atoms, other symmetry choices, unrestricted algorithms|
| Two Fano quotient branches |Both complete branch UNSAT, about 1.48 s summed worker wall |Their CP≤13 and repeated-pair branches are separate; no full-parent exclusion follows|
| Exact binary descent, nine hard packets |AllUNKNOWN at best residual loss 1 |Not an impossibility proof|
| Six-slot repair samples |5,400 blocks excluded:5,339 rank bounds and 61 exact local negatives |Unsampled blocks and other decompositions|
| Sparse 522-atom one-hop scan |243 exact flip 4 cycles;8,748 original-seed deltas; no improvement |Composite moves, other kernel cosets, full finite-code minimum|
| Three-parent crossover |7,140 triples; exact fixpoint reductions produced ranks 93..126 |Other combinations and subsequent paths|
| Four native crossover pilots |Starts 98/96/97/98 all returned to 93; no target |Bounded heuristic failure only|
| Prepared even-component portfolio |**Never executed**: independent-QA pins were missing |Entire proposed experiment; preparation gives no negative result|

These counts describe different, potentially overlapping finite scopes. They must not be summed as a count of distinct global algorithms.

## Useful mathematical restriction

The SAT query on the 366-orbit dictionary used a complete independent 123-vector kernel, literal orbit expansion and exact integer cost constraints. CryptoMiniSat 5.17.0 returned complete UNSAT, with no assumptions; the dictionary also contains an exact 93-product seed. Its minimum cost is therefore 93 within this finite whole-orbit model. The protected old 275 orbit columns embed unchanged, so their minimum is 93 too.

A separately checked quotient/exterior-power argument identifies a six-dimensional kernel inside the old tensor column span. All 63 nonzero tensors in that kernel have exact rank equal to their known old weighted representation. Consequently adding arbitrary whole C3 orbits whose three factors become dependent modulo the three old cube forms cannot lower the old dictionary’s minimum. Combined with the SAT result, that restricted extension class cannot reach 92. This is **not** a lower bound for unrestricted 5×5 multiplication. The UNSAT result is software-checked; no independently checked formal UNSAT certificate or Lean proof of this negative result was produced.

## Learning and experimental changes

The 8-epoch online native bandit completed with 256 additional rank 93 samples independently checked on all 15,625 coefficients by two verifiers, relative to its recorded comparison. It added 37 atoms to its verified coverage ledger. This measures exploration, not new mathematical algorithms. No record improvement or learning advantage was established. Earlier held-out validation favored random or fixed policies over the learned policies; those failures are retained rather than promoted.

New code implements cyclic tensor codes, exact rank-surplus decoders, conditional third-quotient enumeration, a compact Fano-plane SAT encoding, discrete block optimization, sparse zero-cycle mining, provenance-checked native crossover and an exact component optimizer. The last optimizer remains prepared only. No claim that these methods are new to the literature is made.

## Verification and operational limits

The published M4 source snapshot passed 1,128 tests with all 626 captured files unchanged. Final post-M4 validation passed 111 targeted tests across 21 modules, with no failures/errors/skips, and five real-clock deadline controls. Because the campaign was already expired, the tiny/planted tests used explicitly documented module-local historical-clock proxies; production clocks and deadlines were not changed and no target searches ran. The original harness’s expired-dependency failures remain recorded. A further real-process regression verifies the launcher safely inherits queue niceness 19 without requesting privileged promotion; its production algebra is unchanged.

The 366-dictionary query’s initial queued launch failed before entering the solver because of inherited niceness. The unchanged frozen experiment was then launched directly and completed successfully with exactly one native solver call. The failed launch is ERROR, not an algebraic negative. Its archived bytes remain unchanged; current source now handles both direct and inherited queue priorities.

There was no≤92 certificate to export to Lean. All coefficients are exact binary representatives. Product count is separate from additions and matrix execution speed.

## Most useful next work

1. Finish the 64 unresolved conditional child decisions and the two Fano cases’ complementary repeated-pair/prior branches, preserving completed proof prefixes.
2. Qualify and execute the still-unrun even-component portfolio for the unrestricted 522-atom dictionary; explore new kernel quotient cosets rather than repeating its exhausted one-hop scan.
3. Add genuinely different noncyclic atoms or new nondegenerate cyclic directions. More training inside the ruled-out 366-orbit dictionary cannot produce a 92-product scheme.

The expired campaign must not be restarted as if its budget were renewed. A new search requires a new campaign deadline and regenerated pinned runtime/configuration. Read-only review remains available with:

```bash
cd /workspace/efficient-matrix-multiplication
python3 -B scripts/campaign_pulse42.py artifacts/marathon7_20261103T122417Z
```

Sources: [final result audit](evidence/final-result-audit.json), [final targeted checks](evidence/final-postm4-checks.md), [Fano executions](FANO_TWO_B7_EXECUTION.json), [finite dictionary SAT](CYCLIC_NATIVE_ORBIT_SAT.md), [conditional pilot](CONDITIONAL_SURPLUS_THREE_PILOT.md), [native crossover](NATIVE_XOR3_180.md), and the checksum-indexed evidence bundles alongside them. Archived workspace paths and external asset dependencies are retained explicitly.
