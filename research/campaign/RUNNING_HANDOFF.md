# Two-hour record-search campaign

Started: 2026-11-02 16:43:24 UTC. Hard deadline: 18:43:24 UTC.
Target: at most92 exact bilinear products overF2, against the best accessible,
independently verified published scheme93. Source-check limitations and the
307 imported public seeds are documented in RECORD_CHECK.md.

Artifacts: `artifacts/campaign_20261102T164324Z/`.

The experiment is bounded to4 CPU cores and8GiB RAM. Each worker is pinned to
one of CPUs0–3 and has an inherited address-space limit. A separate guard tracks
summed process-tree RSS (conservatively counting shared pages repeatedly), stops
jobs above7GiB to leave headroom, and stops all recorded process groups at the
global deadline. Its first implementation could not read sandboxed /proc task
children and undercounted descendants; it was corrected to use ps parent links.
Only samples labeled `ps-based summed RSS` include the complete worker trees.

Current plan:

* CPU0: native unrestricted flips, frozenv1 binary,600-second phases using
  different verified rank93 seeds and varying rank excursion/restart settings.
* CPU1: native cyclic flips, frozenv2 binary, similarly diversified phases.
* CPU2: initial600-second full-coordinate SAT baseline, then compact-image
  SAT without term-order symmetry for1800seconds.
* CPU3: initial600-second fixed-rank92 ALS, then600-second compact-image SAT
  with safe term-permutation symmetry breaking. Subsequent allocation will use
  measured results and the targeted-repair prototype.

Limited-worker `.running.json` files contain command/PID/resource evidence;
`.result.json` files contain exit status/timing. A PID is not a readiness check.
Search code and binaries were copied with SHA256 manifests under `frozen/`.
Native checkpoints are independently reverified before entering the capped JSON
portfolio. The SAT pipeline only consumes exact93-term sources. Any92-or-fewer
candidate must be preserved, independently verified again, and compiled through
the existing Lean exporter before a formal result is claimed.

Read current saved state with:

```sh
python3 scripts/campaign_status.py
```

Resume instructions after an interruption:

1. Inspect running processes, saved limits, status files and the actual remaining
   budget. Do not duplicate a live worker or assume a saved PID remains valid.
2. Revalidate the strongest candidate and inspect any FOUND.json/WINNER.json.
3. The SAT workers resume automatically using the same output directory and
   exactly matching seed/rank/K/symmetry parameters from their saved commands.
4. Native phases can restart from saved `.best.txt` or exact verified JSON
   snapshots; record a new seed/phase and provenance rather than overwriting
   old evidence. The Python wrapper currently starts fresh seeded phases, so
   use a new output directory if restarting that wrapper.
5. Do not silently extend this campaign beyond the stated two-hour budget.

All reported UNSAT results are local to frozen neighborhoods and chosen support
constraints; UNKNOWN is not UNSAT. Initial residual1 after deleting a singleton
product is not evidence of approaching a record.

## Adaptations through17:12UTC

InitialALS600s finished invalid at residual1. BaselineSAT600s completed48attempts (27localUNSAT/21UNKNOWN). Compactu-lex600s completed204attempts (82UNSAT/122UNKNOWN). PlaincompactA/B was stopped adaptively after51UNKNOWN outcomes; its in-flight attempt is INTERRUPTED_NO_SOLVER_RESULT, not UNSAT. Matched48patches showed plainUNKNOWN vsu-lexUNSAT, with source/core/phase hashes checked. Details:compact_sat_paired_ab.json/.md. CPU2 nowcompactu-lex K7–12 seed11. CPU3 nowtargetedrepair600s ondiversepublishedseeds. CyclicnativeCPU1 completedtwo600s phases plusashortpartialphase; stoppedgracefully at17:10UTC tostartnativeXORu-lexSAT K7–12 seed11. CPU0 unrestrictednativecontinues. Nextplannedoptimization:exactKoszul-flattening necessarybounds beforeSAT, innewseparatemodules; oldrunningcodefrozen. All79tests passed at17:06UTC, including5x5plantedcontrols; tests have small-instanceSATsuccesses that are NOTrecorddiscoveries.

## Adaptations through17:29UTC

Koszul p1 filtering andoptionalp2 introduced asNEWmodules/wrappers; proofnotesandtests under research/campaign. CurrentCPU1 p1wide nativeXOR K10–18 seed29; CPU2 p2CaDiCaL K8–16 seed37; CPU3 p2nativeXOR K8–16 seed37 withlevels2 (boundeddeeperretries). CPU0nativeunrestrictedstillrunning. Fullpoolrecombinationfinished15s:552exactalgorithms,903uniqueterms,1,281,100evaluations, best93, finite-poolpair-cyclelocalminimum only. Newbranchbeingimplemented:globalSATover903termdictionary withatmost92selectedtermsand alltensorlinearconstraints, notlimitedtooddsourcecombination span. All102tests passed in11.8s; logandcodehashes savedatcampaignroot. Noexact<=92candidate.

## Firsthour checkpoint (~17:45UTC)

Noexact<=92candidate. Nativeflips>2.5Bsteps, best93. Fixed903termdictionary solverUNSAT at<=92 in55.2s withrank93controlSAT (NOTindependentlycheckedUNSATproof/globalbound). Expandedpreprocessed1091termdictionary activeCPU1 since17:40:41. Queueafterthisjob:dictionary-loop freezesfreshcollectorcolumns andvariescardinalityencoding/budget; absoluteend18:39UTC leavesreportingheadroom. Collector continuouslycheckswholeintermediatealgorithms andcollectsnonzerorank1terms; snapshotshashes/provenance saved. CPU2p2CaDiCaL (end~17:53) followedbyall6orientations/p1+p2CaDiCaL K9–18seed71,500kconflicts60sec initialbudget,levels2. CPU3p2nativeXOR (end~17:56) followedbymatchingorientedXOR phase. CPU0nativeunrestrictedends~18:38. Guardglobaldeadline18:43:24. Existingafter_job preventsnewjobsafterdeadlineorifverifiedwriterFOUND/WINNERcandidatepresent. Resourcewrappernowalsocapsfuturejobsbyglobalremainingtime. Leanpublished93baselinecompiledexit0;trustpropext/Quot.sound/Lean.ofReduceBool. Newalgorithmssourcesfrozen; testsfinalrunninglogtest_suite_final.log. Noformallycheckedrecordproofexists.

## FINAL — campaign closed

The two-hour campaign is complete. All registered search workers stopped; no exact rank92-or-lower candidate was found. Best verified count93overF2. Native search:5,064,066,009steps. Final local audit:3,237neighborhoods,2,131exact-bound exclusions,112solverUNSAT,994UNKNOWN-only. All130tests pass;401nativecertificates rechecked at6,265,625coefficients,zero invalid. Published93baseline Leanproofcompiledexit0withdocumentednative-evaluatortrust. Dictionary903solverUNSATisrestrictedandhasnoindependentlycheckedUNSATtrace;1812,2022,2058expandedqueriesUNKNOWN. ReadREPORT.mdandsat_audit_final.mdforfinalevidence. Futuresearchrequiresanewauthorizedbudget/newcampaignfolder; do not reuse stalePIDs or extend thisdeadline. SavedSATstate resumes scheduling/cursors,notlearnedclauses. Nativecheckpoints canseednewruns,ororiginalseed/steps replayfrozenbinary. No paidexternalcompute,publication,orpushwasperformed.
