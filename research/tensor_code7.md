# Exact whole-atom binary-code prototype

Each distinct complete rank-one triple `(u,v,w)` is one binary variable. Its column contains all `n**6` coefficients, including zeros. For n5 the system `A x = T` over F2 has 15,625 rows. Exact bitpacked column elimination carries combination witnesses and produces a complete fundamental kernel basis. Moves XOR basis cycles, changing whole terms while preserving the full tensor. Search scores every fundamental cycle, samples multi-cycle XORs, permits neutral moves and bounded temporary increases, and restarts with reordered bases.

The dictionary is only the union of explicitly approved complete seed atoms, capped at 5,000. A seed is never truncated to meet the cap. Production input states have weight93. The finite dictionary may contain no weight92 solution; heuristic failure is not an impossibility proof. No output makes a novelty claim. The planted n2 control includes the known seven Strassen atoms and checks schoolbook8→known Strassen7.

The runner is disabled by default. Disabled mode opens no production inputs and creates no output directory. Preparation and search require separate explicit authorization flags. Search also requires `--qa-approval root-reviewed` and independently supplied raw manifest/prepared hash pins. Preparation launches no search and reports only measured exact dictionary rank/nullity, packed storage, and observed high-water RSS.

Both enabled modes require a root-reviewed source-ancestry anchor manifest (`tensor-code-source-anchors-v1`), its independent `--manifest-sha256`, and `--approved-root` containing that immutable anchor package. Historical `root_approved_train` entries do not authorize a current run: current root authorization is the explicit invocation and independently pinned manifest bytes. The selected source list explicitly includes both the manifest's BFS descendant anchors and its catalog-bound `known_input_train_states`; each group is checked through the appropriate export or initial-pool registry. The loader verifies copied registry/node SHA256 hashes, complete parent closure without missing/cyclic edges, canonical identities and heldout/evaluation exclusions, historical root native training membership and arm/config pins, exact affine parent-to-child replay, and the selected BFS export entries. Unknown derivations defer. The recovery anchor package supplies this genealogy; plain source flags or freeform origin text are insufficient.

Search additionally reopens that independently approved manifest and its sources, verifies all frozen snapshots, reconstructs the full whole-atom union and exact seed masks, and rejects any difference from the prepared dictionary. Repaired self hashes cannot authorize extra atoms or seed states. All coefficients and integer metadata are literal integers; floating values and booleans are rejected.

The enabled runner requires `--campaign-dir`, independently pinned `--campaign-sha256`, and fresh `--guard-state`. It uses the canonical `mmsearch.marathon7_local.CampaignGuard` for typed fresh resource state, process identity, storage limits, canonical stop/freeze markers, signals, and resource cancellation. The absolute deadline is the minimum of caller input, pinned campaign config, and fixed **2026-11-03 19:24:17 UTC**, with three seconds reserved for diagnostic finalization. Force barriers surround source loading, dispatch, move selection, both full tensor checks, and publication. Production is restricted to CPU3, nice10 or lower priority, and at most 1,024 MiB address space. The first query defaults to 120 seconds. Sample counts and wall budgets are bounded and validated.

The following is the reviewable **disabled** first-query template; all placeholder hashes must be independently reviewed values:

```sh
python scripts/tensor_code7.py search \
  --prepared /ABSOLUTE/tensor_code7-prepared/prepared.json \
  --prepared-sha256 PREPARED_RAW_SHA256 \
  --manifest /ABSOLUTE/tensor-code-source-anchors-v1/manifest.json \
  --manifest-sha256 APPROVED_MANIFEST_RAW_SHA256 \
  --approved-root /ABSOLUTE/tensor-code-source-anchors-v1 \
  --campaign-dir /ABSOLUTE/marathon7_20261103T122417Z \
  --campaign-sha256 CAMPAIGN_RAW_SHA256 \
  --guard-state /ABSOLUTE/marathon7_20261103T122417Z/operations-v3/state.json \
  --outdir /ABSOLUTE/NEW/tensor_code7-query120 \
  --seconds 120 --cpu 3 --memory-mib 1024 --seed 7 \
  --hard-utc 2026-11-03T19:24:17Z
```

Only after root approves that concrete query add `--authorize-search --qa-approval root-reviewed`. To prepare, replace `search` with `prepare`, omit the two prepared arguments, select a fresh preparation output directory, and add `--authorize-preparation` only after separate root preparation approval. This document authorizes neither operation.

Checkpoints atomically store exact active/best state masks, iteration/restart cursor, basis permutation, complete RNG state, source/prepared/code hashes, parameters, and publication eligibility. Resume into a fresh directory with the same parameters and `--resume /ABSOLUTE/OLD/checkpoint.json`. Input, code, parameter, counter, or state invariant mismatches fail closed. Raw candidate staging uses hidden `.raw-candidates/` so the operations guard prunes every pending file. Raw candidate JSON additionally uses a top-level `UNKNOWN`, `complete:false` envelope with the candidate nested under `raw`; the operations guard cannot parse that envelope as a certificate even if copied outside hidden storage. A late operation marks the envelope `after_cutoff:true`, retains its raw witness data and an `after-cutoff` status artifact, rolls back the pending cursor/RNG transaction, returns `UNKNOWN` with `complete:false`, and cannot publish a record. Late-only terminal checkpoints never promote. An already eligible verified <=92 checkpoint terminates without further moves.

Any saved improvement passes the existing independent verifier plus a separate scalar XOR-array verifier over all tensor entries. The first eligible <=92 result is frozen under `first-record-evidence`; search stops. Diagnostic postchecks after a hold do not create within-budget eligibility. Code snapshots include the actual imported local dependency closure of the canonical guard. Inputs, ancestry files, reviewed code, actual affinity/priority/memory limits, and output checksums remain reviewable. Formal artifact structure is in `scripts/tensor_code7.schema.json`; algebraic and ancestry constraints are additionally enforced in code.

Run controls without production data:

```sh
taskset -c 2 nice -n 10 python -m unittest \
  tests.test_tensor_code7 tests.test_tensor_code7_lifecycle tests.test_tensor_code7_sources -v
```

Controls include planted known8→7, corrupted columns, deliberately non-null and incomplete bases, multi-cycle RNG/cursor split replay, exact bounded moves, literal numeric metadata, disabled input isolation, hard cutoff clamping, late return/checker publication barriers, actual operations guard raw-staging isolation, terminal resumes, and synthetic ancestry/source-binding corruption. Synthetic lineage fixtures deliberately test provenance only and launch no tensor search.
