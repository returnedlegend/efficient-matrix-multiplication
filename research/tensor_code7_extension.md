# V2 proposal: escape the even-kernel dictionary by certified odd relations

The authorized v1 preparation measured406 atoms, rank309 and nullity97. Independent diagnostics found all97 fundamental cycles even. Therefore every feasible v1 state has odd weight, since its approved seed has weight93. In that exact finite dictionary, weight92 is unrepresentable and a <=92 query can only find <=91. This is a finite-dictionary fact, not a global rank lower bound.

V2 adds only authenticated derived whole atoms. For existing parents `x=(a,b,c)` and `y=(d,e,f)`, use the exact F2 identity

```
x + y = (a+d,b,c) + (d,b,c+f) + (d,b+e,f).
```

The five terms XOR to the zero tensor: the two extra `d*b*c` and two extra `d*b*f` contributions cancel. Require all five atoms distinct and nonzero. Its selection mask has odd weight5 and lies in the complete tensor kernel. If the old kernel contains only even cycles, at least one of the three derived atoms must lie outside the old dictionary. Once added, the exact feasible affine fiber contains both weight parities. This does not imply any state of weight92 exists.

No production extension has been generated. The current work is a new contract, preparation-only runner and tiny controls. V1 source/code/data/checksums remain unchanged. The new runner has no heuristic or SAT mode.

## Authenticated contract

Witness schema: `tensor_code7.extension_witnesses.v2`. Initial limits:1..16 relations, at most100 new atoms, at most5000 total atoms. Each relation derives exactly three terms, so16 relations add at most48 distinct atoms before deduplication. Parent IDs refer only to the original base dictionary; chained extension parents are initially rejected. Factor-axis permutations are explicit permutations of0,1,2, applied to both parents and undone after derivation; these are algebraic coordinate choices, not an assumed matrix-tensor symmetry.

```json
{
  "schema": "tensor_code7.extension_witnesses.v2",
  "base_prepared_sha256": "ROOT_PINNED_BASE_RAW_SHA256",
  "base_dictionary_sha256": "BASE_DICTIONARY_SHA256",
  "max_new_atoms": 100,
  "relations": [{
    "id": "plus-000",
    "parent_atom_ids": [0, 7],
    "axis_permutation": [0, 1, 2],
    "new_atoms": [[9,1,1],[8,1,9],[8,9,8]]
  }]
}
```

The shown IDs/atoms are the tiny n2 fixture, not production selections. Production parent IDs/witnesses have not been selected.

The external root approval must pin the old prepared raw hash (`cf4644cab66d697f05d6724d919973b9884f17def9586c0e1220b9ea67554e2b`), approved source-anchor manifest raw hash (`26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8`), new code/config and exact witness-manifest raw hash. A historical base receipt cannot authorize a new invocation. `authenticate_base` checks the frozen v1 code closure, invokes its unchanged strict source/ancestry reconstruction, recomputes all original mathematics and requires every original source state to remain weight93. New atom eligibility inherits solely from those authenticated base parents. No external candidate data, evaluation input or unknown ancestry is admitted.

Each new witness is independently reconstructed from its two base IDs. Both exact packed full-tensor XOR and a separate scalar-product checker inspect all `n**6` coefficients of the five-term zero relation. Duplicate relations, zero factors, aliased numeric types, unknown fields, wrong axes, wrong parents, wrong explicit atoms and cap violations fail closed. Existing atom IDs remain unchanged; unique derived atoms append in witness order. All32 old weight93 seed masks remain identical, padded with zeros at the new coordinates. No optional weight94 certificate is required or admitted as a source.

Prepared schema: `tensor_code7.extension_prepared.v2`. It records the base/witness/source pins, complete atoms/columns/target, padded seeds, full rebuilt kernel/rank/nullity, odd-cycle certificates, observed parity change and authenticated base receipt. The unchanged v1 loader rejects this schema. `validate_extension_prepared` rebuilds the entire v2 document from the independently pinned base plus witnesses and rejects self-repaired hashes, extra atoms, changed seeds, changed columns or invented parity flags. A SAT adapter must call the v2 trusted reader and explicitly opt into this schema after separate QA; accepting it as v1 is forbidden.

## Proposed production preparation after separate root authorization

1. Freeze the reviewed v2 code and a deterministic pair-selection configuration. A suggested initial selector visits the32 approved seed supports round robin, visits coactive base parent pairs lexicographically and tries the six axis orders in fixed order. Accept the first16 distinct nondegenerate relations that introduce an old-dictionary-external atom; stop after8192 attempted pair/axis records if incomplete. These are deterministic algebraic preparation trials, not target queries. Record attempted/skipped/accepted counts; do not substitute invented atoms if fewer than16 qualify.
2. Generate only the witness manifest, under canonical campaign guards and a bounded helper resource budget, then independently pin that exact manifest. No N5 generation is authorized by this document.
3. Run the new preparation-only runner on CPU3/nice10/1024MiB/120s, with an outer150s limiter and fresh canonical guard. It authenticates/copies the immutable v1 package, verifies each derived relation twice, rebuilds the full new code and reports actual atom growth/rank/nullity/parity/memory/time. Do not forecast these as measured values.
4. Independent QA checks the pinned witnesses and new prepared document. Only then propose a separate bounded v2 SAT or heuristic query. Existing v1 queries remain finite-dictionary evidence and their archives stay unchanged.

The prep runner is disabled by default and reads no production inputs. Enabling it requires both `--authorize-extension-preparation --qa-approval root-reviewed` and all independent base/witness/source/campaign raw-hash pins. No parent-pair selector runs automatically. The proposed future preparation command is:

```sh
python -B scripts/tensor_code7_extension.py \
  --base-prepared /ABSOLUTE/tensor-code-prep-001/prepared.json \
  --base-sha256 ROOT_APPROVED_BASE_RAW_SHA256 \
  --witnesses /ABSOLUTE/REVIEWED/extension-witnesses.json \
  --witnesses-sha256 ROOT_APPROVED_WITNESS_RAW_SHA256 \
  --source-manifest /ABSOLUTE/tensor-code-source-anchors-v1/manifest.json \
  --source-manifest-sha256 ROOT_APPROVED_SOURCE_MANIFEST_RAW_SHA256 \
  --approved-root /ABSOLUTE/tensor-code-source-anchors-v1 \
  --campaign-dir /ABSOLUTE/marathon7_20261103T122417Z \
  --campaign-sha256 ROOT_APPROVED_CAMPAIGN_RAW_SHA256 \
  --guard-state /ABSOLUTE/marathon7_20261103T122417Z/operations-v3/state.json \
  --outdir /ABSOLUTE/NEW/tensor-code-extension-prep-001 \
  --hard-utc 2026-11-03T19:24:17Z --seconds 120
```

This remains disabled without the two explicit authorization flags. It does not run search or SAT even when preparation is authorized. The canonical guard currently uses the existing strict implementation; any cached replacement needs separate owner QA before integration.

## Raw-witness isolation for future v2 search integration

`retain_raw_candidate` stores late evidence only in hidden `.raw-candidates/` and wraps the candidate inside a top-level `UNKNOWN`, `complete:false`, `after_cutoff:true` envelope. This addresses cross-integration with operations-v3: its normal `walk_files` prunes the hidden directory, and `canonical_candidate` rejects the wrapper even if the file is explicitly copied or found without pruning. The original raw data stays readable for explicit later verification and never acquires publication eligibility through this API. Future v2 search must use this API for raw staging and preserve independent postsolve/full-tensor/publication guards; this prep-only runner has no candidate publication path.

Tiny controls run on CPU1/nice10:

```sh
taskset -c 1 nice -n 10 python -m unittest tests.test_tensor_code7_extension -v
```

The positive fixture starts from the exact n2 schoolbook8 dictionary, whose kernel is trivial/even, and adds one certified five-term relation. The padded weight8 solution XOR that odd cycle is weight9, proving both parities occur without claiming an improved multiplication scheme. No N5 extension generation, heuristic or SAT query is performed by these controls. The raw92 cross-guard fixture is deliberately only a schema-valid synthetic shape, not an exact rank92 multiplication claim.
