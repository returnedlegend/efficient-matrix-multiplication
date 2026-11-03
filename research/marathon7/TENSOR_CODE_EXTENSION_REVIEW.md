# Independent odd-atom extension review

Status: **PASS on the final prep-only design-v3 pins below.** The CLI early-stop
UNKNOWN fix is accepted. No N=5 extension generation, production
preparation, heuristic optimization or SAT query was run in this review.

| File | Final accepted SHA256 |
|---|---|
| mmsearch/tensor_code7_extension.py | ee606cfe26ff6e06b58449e044ea05f999ac77e7eb6beb01039b1949edf50587 |
| scripts/tensor_code7_extension.py | a610093c88ed6439b4d4de71d249593d1ff48c506e96798a6f6ae6b77ae95f61 |
| tests/test_tensor_code7_extension.py | 3b38fb79dd4538a3a2655be9a86eff3dd6b56ef47a266bf15cac9f8b23d57a23 |
| scripts/tensor_code7_extension.schema.json | e004b12b126499e82162db5a571285fc15f1002c5a8b1d8180f84363430456c1 |
| research/tensor_code7_extension.md | 1eff9b09ee27e978fd54a9b753e4ffd6c6df43cde73fd0067a1731ef5edb7b0d |

All five current files match `/tmp/tensor_code7-extension-pins-v3.json` and the
separate design-v3 snapshot. The initial design-v2 archive remains untouched.
The worktree v1 raw-staging repair is separately pinned at runner8f40b6c0...;
authentication of the old base uses its original frozen b15bf99a... source
loader, not a relaxed replacement. No code in either old archive was changed.

## Mathematical identity and parity

For x=a tensor b tensor c and y=d tensor e tensor f over F2,

    x+y = (a+d) tensor b tensor c
        + d tensor b tensor (c+f)
        + d tensor (b+e) tensor f.

Expansion leaves abc+def because dbc and dbf each occur twice. The same
identity holds for any factor-axis order when the same permutation is applied
to both inputs and undone in every output. This is a choice of tensor
coordinates, not an assumed matrix-multiplication tensor automorphism.

All five points must be nonzero and pairwise distinct. Their selection mask
then has weight five and is a complete-tensor kernel vector of odd parity.
For an all-even old kernel and an odd-weight old solution, every old feasible
state has odd weight. Adding the certified odd vector makes both parities
available; it does not prove that weight92, or any improvement, exists.
An odd five-cycle cannot consist entirely of old points if the old kernel is
all-even, and the implementation independently requires an external old-base
point regardless of that fact.

The module keeps the original point order, appends only unique certified
derived points, and keeps every old seed mask numerically identical (zero new
bits). The full extended kernel is recomputed with exact rank/nullity and a
required odd basis vector. Each supplied five-cycle is also checked by both
packed full-column XOR and independent scalar products at every coefficient.

## Authenticity and bounded scope

The approved parent raw pin is
`cf4644cab66d697f05d6724d919973b9884f17def9586c0e1220b9ea67554e2b`.
The approved32-source manifest remains
`26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8`.
The original package remains immutable. authenticate_base checks the raw parent
pin, loaded exact core hash, all frozen v1 code hashes, strict original source
and ancestry reconstruction, original mathematics and weight93 source masks.
The production CLI obtains its receipt through that authentication path;
untrusted document metadata alone does not authorize new base atoms.

Witness raw bytes require a separate external root pin. Parent IDs are strict
literal integers into the ORIGINAL dictionary, even after earlier relations
append new atoms. Chaining through newly derived parents is rejected. Axis
orders, explicit derived atoms and all top-level/record keys are checked.
Unknown fields, numeric aliases, duplicate five-cycles, zero factors, changed
parents and self-repaired extra atoms or seeds fail closed. The limits are
1..16 relations, <=100 unique new atoms and <=5000 total atoms;16 relations
actually contribute at most48 new points before deduplication.

The trusted v2 reader reauthenticates the parent/source closure and rebuilds
the entire v2 document from the independently pinned witness bytes, then
compares canonical serialized values. V1's exact-union and weight93 source
policies remain unchanged; V1 rejects the new schema. Any future SAT/heuristic
adapter must explicitly opt into the separate authenticated v2 reader.

## Guards and expired raw evidence

Preparation has no search or SAT mode. Enabling it requires separate root-QA
and preparation flags, a new output directory and all parent/witness/source/
campaign pins. It uses the canonical time/resource/global-stop guard and
barriers after source snapshotting, reconstruction, prepared publication and
late return. Late prepared data is demoted to a noncandidate raw artifact;
its schema has no explicit terms and operations-v3 cannot ingest it as a
matrix-multiplication candidate.

The future-search raw helper writes only a hidden `.raw-candidates` directory
and nests the raw candidate under a top-level UNKNOWN/complete:false envelope.
The operations walker prunes that directory, and canonical_candidate rejects
the envelope even if explicitly copied. The schema-valid expired92 fixture
checks ingestion isolation; it is not an exact rank92 multiplication claim.
Current v1 worktree raw-staging repairs are a separate reviewed change; the
original frozen114-file preparation is not patched.

One initial CLI blocker was found and fixed: pre_dispatch Guard Stop was outside
the runner's handler, producing an uncaught exception rather than an UNKNOWN
response on an expired authorized invocation. The final runner catches this
early stop, returns UNKNOWN/complete:false without opening the missing base or
witness paths, and does not create an output directory. Its new test uses a
valid synthetic campaign to exercise actual canonical guard construction.

## Executed independent checks

All15 final owner extension controls pass on CPU1 nice10 in0.121 seconds. An independent
complete sweep of parent triples with factors from {1,2,3}, embedded in the n2
factor spaces, tested all six axis orders:1296 valid five-term relations each
reconstructed zero at every64 scalar coefficients;3078 cases with zero output
factors were rejected. The parent raw pin, measured406 atoms/rank309/nullity97,
all97 recorded kernel basis parities and32 original weight93 masks were read
and checked without rerunning N=5 preparation or a query. All113 files in the
original checksums receipt, including27 frozen code files, still match; the
checksums file itself is the114th preserved package file. Evidence is
`research/marathon7/evidence/tensor-code-extension-independent-math-v2.json`.

An independent CLI lifecycle harness uses only the exact known n2 schoolbook8
base and one five-cycle, with ancestry authentication deliberately mocked to
avoid opening any production sources. Expired pre-dispatch, late-after-build
and late-after-publication controls all return UNKNOWN/complete:false with no
eligible prepared file. The late published file is demoted and rejected by
operations-v3 candidate canonicalization. Evidence and the reproducible
harness are `tensor-code-extension-independent-protocol-v2.json` and
`review_extension_protocol_tiny.py` in the same evidence directory. Together
these18 executed owner/protocol controls cover early expiry and late barriers;
the separate1296-relation exhaustive sweep covers the identity itself.

No blocker remains for preparation from a separately reviewed exact witness
manifest. This acceptance does not authorize N=5 witness selection, a new
selector variant, production preparation or subsequent optimization.

## Concrete preparation proposal for root review

Keep witness selection separate from preparation. Review and freeze a bounded
selector/config first: known32 original seed states only, coactive ORIGINAL
parent IDs, fixed six axis orders, <=8192 attempted pair/axis records, first
<=16 distinct valid certified five-cycles, <=100 new points. A lexicographic
variant and any separately proposed pair-span/coset-prioritized variant need
their own deterministic ordering/config pin. No selector runs during this
review. Record all attempted, skipped, accepted and incomplete-cap counts;
never treat a selection cap or absence of selected relations as a tensor
negative. Root must pin the resulting exact witness manifest before the
following preparation-only invocation.

```sh
timeout --signal=TERM --kill-after=5s 150s \
  taskset -c 3 nice -n 10 python -B scripts/tensor_code7_extension.py \
  --base-prepared /workspace/efficient-matrix-multiplication/artifacts/marathon7_20261103T122417Z/tensor-code-prep-001/prepared.json \
  --base-sha256 cf4644cab66d697f05d6724d919973b9884f17def9586c0e1220b9ea67554e2b \
  --witnesses /workspace/efficient-matrix-multiplication/artifacts/marathon7_20261103T122417Z/tensor-code-extension-witnesses-001.json \
  --witnesses-sha256 ROOT_REVIEWED_NEW_WITNESS_RAW_SHA256 \
  --source-manifest /workspace/efficient-matrix-multiplication/artifacts/marathon7_20261103T122417Z/tensor-code-source-anchors-v1/manifest.json \
  --source-manifest-sha256 26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8 \
  --approved-root /workspace/efficient-matrix-multiplication/artifacts/marathon7_20261103T122417Z/tensor-code-source-anchors-v1 \
  --campaign-dir /workspace/efficient-matrix-multiplication/artifacts/marathon7_20261103T122417Z \
  --campaign-sha256 d71f859137dd407a29751f683afa97a0cbd23a91dbda4b6581bb5c477e671219 \
  --guard-state /workspace/efficient-matrix-multiplication/artifacts/marathon7_20261103T122417Z/operations-v3/state.json \
  --outdir /workspace/efficient-matrix-multiplication/artifacts/marathon7_20261103T122417Z/tensor-code-extension-prep-001 \
  --hard-utc 2026-11-03T19:24:17Z --seconds 120 \
  --authorize-extension-preparation --qa-approval root-reviewed
```

The witness pin is intentionally unresolved until separately authorized bounded
generation and review produce real bytes. The proposed resource bounds are
CPU3/nice10,1GiB address space,120s inner budget and150s outer limiter. This
command generates no search/SAT result. Successful preparation reports measured
dictionary growth, rank/nullity, odd parity, runtime and memory; any subsequent
optimization requires separate review and root authorization.
