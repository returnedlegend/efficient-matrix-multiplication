# Whole-atom dictionary SAT

`mmsearch/tensor_code7_sat.py` solves a different finite problem from nonlinear factor search: choose complete rank-one atoms from the exact dictionary already prepared for `tensor_code7`. One binary variable selects one `(u,v,w)` triple. Native CryptoMiniSat XOR constraints enforce all tensor coefficients, while a PySAT sequential counter bounds the number of selected atoms. No coefficients of an atom are independently changed.

The module independently reconstructs every column and the target from integer masks. It transposes all `n^6` equations, including zero rows. Optional exact row Gaussian elimination records original-row XOR witnesses, checks each witness, and verifies that every original augmented row reduces to zero. The reduced and original systems therefore have the same row space. Both full and reduced encodings are tested against brute force on small binary codes.

Production preparation is shared with the heuristic. The SAT runner requires the root-reviewed raw SHA-256 of the same `prepared.json`, the separately root-reviewed source manifest hash, and the explicit approved root. It calls the owner's `verify_source_binding` to recheck pinned source registries, complete nonheldout ancestry, exact affine derivations, frozen input snapshots, and reconstruction of the prepared dictionary. It then validates the prepared document and independently reconstructs the full tensor data again. The source cap is 5,000 atoms; the actual count, rank and nullity must be reported only after authorized preparation. This implementation has not run an n=5 solver.

The initial production envelope is CPU 1, niceness at least 10, one native solver thread, 1,024 MiB and at most 30 seconds. Parent polling bounds import, loading and solving, then terminates and reaps a stalled child. The child clamps inherited resource ceilings instead of raising them. The campaign's existing guard also bounds source reconstruction, formula construction, verification and publication. Late or cancelled results are `UNKNOWN`; backend errors are `ERROR`. `DICTIONARY_UNSAT` means only that this exact pinned dictionary contains no selection satisfying the bound. No result is a global tensor-rank lower bound.

Late native results remain nested diagnostic evidence under `UNKNOWN`, including a known selection state and any already reconstructed candidate. They carry `within_budget=false`, do not count as completed SAT/UNSAT outcomes, and cannot be passed to the certificate freezer. Both local budget stops and the shared campaign guard's stop exception preserve this evidence.

Every `SAT` selection is checked against the complete original columns and support bound. The resulting certificate passes the standard full tensor verifier and an independent literal coefficient reconstruction. For n=5 it also passes the strict independent 15,625-entry record checker. Before freezing, the checks run again on persisted bytes. The immutable directory appears atomically with a final `WINNER.json`; postmarker guard failure rolls it back. This module never writes the campaign stop marker. The main campaign guard retains responsibility for its own independent record freeze and stop.

The CLI is disabled unless both `--authorize-search` and `--qa-approval root-reviewed` are present. An eventual reviewed command has this form; the placeholders must be replaced by actual reviewed pins:

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.xor-deps python3 -B -m mmsearch.tensor_code7_sat \
  --authorize-search --qa-approval root-reviewed \
  --prepared PREPARED_JSON --prepared-sha256 REVIEWED_PREPARED_SHA256 \
  --manifest SOURCE_ANCHOR_MANIFEST --manifest-sha256 REVIEWED_MANIFEST_SHA256 \
  --approved-root APPROVED_SOURCE_ROOT --outdir NEW_CAMPAIGN_OUTPUT \
  --campaign-dir CAMPAIGN --campaign-sha256 REVIEWED_CAMPAIGN_SHA256 \
  --guard-state CAMPAIGN/operations-v3/state.json --hard-utc 2026-11-03T19:24:17Z \
  --cpu 1 --memory-mib 1024 --seconds 30
```

`kernel_diagnostics` is an optional, separately bounded preprocessing tool. It independently checks column rank and completeness of a supplied kernel basis. If every basis vector has even weight, every feasible codeword has the seed's weight parity: a rank-93 seed then makes a bound of 92 equivalent to 91 inside this dictionary. A DSU joins atom indices appearing in each kernel relation. Since the complete kernel basis does not cross the resulting components, the exact seed coset separates across them. Small components can be exhaustively traversed in Gray order up to nullity 20 and a total combination cap; larger components retain only safe lower bounds. Its certificates include component masks, complete local cycles, minimum witnesses, enumerated counts and whether each minimum is exact. The initial SAT path does not silently run these optional component enumerations.

The tests use only tiny controls: planted schoolbook eight products versus known Strassen seven, an explicit finite-dictionary UNSAT case, random small linear systems compared with brute force, exact component minima, timeout and cancellation mocks, corrupt-model rejection, strict pins, and immutable publication controls. Planted Strassen atoms are a solver check, not a newly discovered multiplication algorithm.
