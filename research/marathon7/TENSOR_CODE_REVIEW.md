# Independent Tensor Code 7 review

Final decision: **PASS on the frozen final pins and independently root-approved
source manifest below.** The earlier blockers are resolved for the separately
reviewed bounded first query. This review runs no production preparation,
tensor query or search, and does not replace root launch authorization.

## Final accepted pins and evidence

| File | SHA256 |
|---|---|
| mmsearch/tensor_code7.py | e5fa2a84c00ee5e10076ff3902963cf27dfe86b43fc4d4ad885cef8f3f7291e1 |
| scripts/tensor_code7.py | b15bf99affff1ca9cad431ce481aa1f4d8043f23ca07f55b6ad365fbc9f3bef9 |
| tests/test_tensor_code7.py | 16b1c28df8d5294972395b11865eddfc0875803af2550ea70071563c72cf680b |
| tests/test_tensor_code7_lifecycle.py | 0e5de0432f84f3a9a598ac9a445bf78d6d8edd19a6708efd77cb8fe0d09e889e |
| tests/test_tensor_code7_sources.py | a2dd46317fe51c39903ee779e900e0367bfa1badde0f5a018d1164baabeab787 |
| scripts/tensor_code7.schema.json | b826534eb2c6577b43904071505a7f3e1895de40e370473d704248a8d9bfdfaa |
| research/tensor_code7.md | fe5507f5ebc3e95725ddf50cf7d3ca085cc93481acccb674b85e6ef7fe43b5bf |

The independently approved manifest SHA256 is
`26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8`.
Its trust anchor is the separate root decision
`artifacts/marathon7_20261103T122417Z/root-review-decisions/tensor-code-source-anchors-approved.json`,
which approves BOTH `anchors` and `known_input_train_states`, 16 sources each.
The frozen manifest's pending-review label is not an approval substitute;
current approval is this external decision and the independently supplied raw
manifest hash. The loader deliberately selects precisely those two groups.

I independently read and hashed the actual pinned package, without calling
load_sources, prepare, validate_prepared or any production tensor construction.
All42 nodes and7 registries match their recorded bytes and canonical identities.
The22 exact affine edges (4 ordinary and18 no-compression-change) and4
canonical-term-preserving copy edges replay from actual parent term sets.
Every selected anchor's exact ancestor closure reaches the claimed native
training root; all16 roots match historical initial-pool, train-split and
root-arm/config evidence. All node term/RL identities are checked against the
pinned heldout/evaluation exclusions. Selected BFS states match export registry
entries; selected native inputs are catalog-bound roots. This independently
checks ancestry and split eligibility rather than inferring them from a hash.
The audit made81 pinned-file reads totaling7,278,232 bytes and wrote
`research/marathon7/evidence/tensor-code-final-lineage-independent.json`.

The final search path additionally requires the independently supplied raw
prepared hash. It reopens the approved manifest, validates actual source and
registry bytes, compares frozen lineage registries and source snapshots, then
reconstructs every prepared field produced by prepare, including the full atom
union and exact seed masks. Thus adding atoms or states and repairing internal
self hashes cannot bypass the external reviewed source closure. Source cap5000
never truncates a seed. Preparation independently checks selected tensors under
both exact checkers before constructing a production dictionary; that production
operation remains unrun in this review.

The final core rejects floating/bool field, dimensions, factors, rank/nullity,
weights and cursor counters. The production runner rejects nonliteral n5/F2
before potentially expensive tensor validation. Guard clamps caller and pinned
campaign deadlines to the fixed2026-11-03T19:24:17Z cutoff, requires fresh typed
canonical resource/campaign state, checks signals/stop/freeze conditions, and
forces barriers after move selection, both full checkers, and publication.
The pending cursor/order/RNG transaction rolls back on a late result; raw late
witnesses remain UNKNOWN and cannot acquire publication eligibility. A resumed
eligible <=92 checkpoint freezes without another move, while a late-only one
cannot promote. Failed heuristic searches return UNKNOWN, complete=false,
with a separate stop reason. Samples are capped4096, dictionary size5000;
CLI CPU3, nice>=10 and address space<=1024MiB remain enforced. Actual approved
source/package sizes are bounded by the reviewed pinned package, with canonical
campaign storage checks at forced barriers.

I reran the15 core controls and9 source controls on CPU1 nice10: **24/24 PASS**
in0.283 seconds. The independent lifecycle reviewer passed **9/9** final
controls, including late selection/checker returns, terminal resumes and actual
multi-cycle split RNG replay; see `TENSOR_CODE_LIFECYCLE_QA.md`. The verifier
also reports **866/866** in the final unified suite with all33 Tensor Code
controls and stable final hashes. These controls use planted/synthetic inputs;
no production preparation or search is asserted. Code review confirms both
candidate checkers still visit all15,625 entries for n5 and retain the correct
trace convention `w[k*n+i] -> output[i][k]`.

No blocking issue remains for the concrete root-pinned bounded first query.
Its production dictionary rank/nullity, memory and search outcome must be
measured by the separately authorized preparation/query, not inferred here.

## Initial review history (superseded by the final acceptance above)

The initial five-file implementation was BLOCKED on its pins below. The
following records the original findings and reproductions, which the final
implementation and expanded controls resolve.

## Reviewed pins

| File | SHA256 |
|---|---|
| mmsearch/tensor_code7.py | 8709a5b47f80d69f56c3e08a90292a0aa6451e8da62f765f61af101032e06e3e |
| scripts/tensor_code7.py | 71ed860863e171add62ea7a3d60fbf9bf07d51465f0ea0f2a7559fbe42f6302b |
| scripts/tensor_code7.schema.json | 3ceca6720be8119557f251392eb894108f7b8dc44bb1ad2e7c227129bb89ee46 |
| tests/test_tensor_code7.py | 500d0467c45dd458e89cc4e5965b29535c604135800647fe4d4ce9a329d80f98 |
| research/tensor_code7.md | 192d83113a0381be156befb3433b609dda1d06385e113896530d678ccd426434 |
| mmsearch/verify.py, independent checker | 491282f4e940b9969b2a94ee51994d71ceefd9dc5a19167b779b9d2a6098f46f |

## Passing mathematical checks

The columns contain whole atoms u tensor v tensor w, with bit position
`((a*n*n+b)*n*n+c)`. The target sets exactly
`a=i*n+j, b=j*n+k, c=k*n+i`. This matches both the coefficient loop and direct
matrix multiplication in verify.py: `w[k*n+i]` contributes to output `[i][k]`.
There is no fixed/free factor projection or restriction to positive target
entries: all n^6 coefficients, including expected zeros, are constrained.

Gaussian elimination carries combination witnesses. A dependent column yields
a null vector; independent pivots plus generated cycles satisfy rank-nullity.
Validation checks each cycle is nonzero, distinct, null and independent, then
recomputes matrix rank and checks the kernel dimension. This proves complete
kernel span for the frozen finite dictionary. Exact states satisfy Ax=T;
every proposed move is checked Az=0 before mutation. The weight change formula
`|z|-2|x intersect z|` is correct. For an incoming state within the ceiling,
negative, neutral and bounded positive choices preserve the rank ceiling.

Both candidate checkers visit all n^6 entries. The saved candidate is reread
and compared with the checked in-memory object. Successful checks over F2 do
not claim an integer lift or novelty. No unsuccessful exit currently claims
UNSAT; however, its protocol needs explicit UNKNOWN as described below.

## Executed controls

`taskset -c 2 nice -n 10 python -m unittest tests.test_tensor_code7 -v`
passed all **14 tests** in 0.194 seconds during this review. These include the
explicitly planted schoolbook8/known-Strassen7 dictionary, corrupted columns,
non-null/dependent/incomplete kernel rejection, exhaustive small kernel span
checks, bounded moves, RNG serialization and disabled/expired input isolation.
The planted reduction is a solver control, not a new algorithm.

Additional tiny, nonproduction reproductions established:

* Changing a valid prepared N=2 document's field to JSON float `2.0` is accepted
  by validate_prepared. Preparation of a float-field candidate itself is rejected
  by verify.py; the acceptance gap is specifically the prepared-input path.
* Constructing Guard with `2030-01-01T00:00:00Z` leaves that later date effective,
  rather than the campaign cutoff 2026-11-03T19:24:17Z.
* Guard accepts NaN seconds and its elapsed-seconds comparison never fires.

## Blockers communicated to the owner

1. **Fixed cutoff and bounded calls.** Clamp every requested UTC deadline to
   2026-11-03T19:24:17Z; reject nonfinite/nonpositive elapsed budgets. Bound samples
   and poll guards within potentially expensive move generation, Gaussian
   validation and verification. A three-second reserve is not a post-call
   deadline check. The current runner has no campaign canonical stop/freeze or
   resource-state integration; resolve that contract with root before launch.
2. **Late result publication.** The loop checks guard before choose_move but
   not after it. A delayed call can mutate state and publish a <=92 record after
   expiry. save_candidate similarly publishes after two unchecked verifier
   calls. Check guards after those calls and immediately before completed
   result publication. Preserve a stopped observation as UNKNOWN and do not
   publish a valid record status. Another reviewer is preparing synthetic
   late-return controls; no real N=5 query is needed.
3. **Actual input eligibility and lineage.** Preparation confines paths and
   checks raw source hashes but trusts source-provided approval booleans and a
   nonempty origin string. Search does not reopen the approved manifest or
   snapshots, recheck eligibility ancestry, or reconstruct the dictionary and
   seed states from those frozen whole sources. A self-consistent prepared
   document with changed atoms/seeds and repaired internal hashes can pass the
   algebra while its source records describe something else. Require an
   independently root-reviewed, hash-bound eligibility/source manifest and
   approved root at search; replay exact sources and compare complete atom
   union and seed states. Preserve authoritative ancestry/eligibility evidence,
   rather than inferring eligibility from a term hash or filename alone.
4. **Strict prepared types.** Require literal integer field=2 and positive
   integer dimension, and strict integer nonnegative rank/nullity/counts/cursor
   fields. JSON Schema is not executed by the runner and does not replace
   algebraic/type checks in validate_prepared or Walk.from_json.
5. **UNKNOWN and checkpoints.** Normal MAX_RESTARTS and caught Stop exits do not
   include explicit `status=UNKNOWN, complete=false` and a separate stop reason.
   Unsuccessful finite-dictionary heuristic search is incomplete. Validate
   checkpoint counters and best/current/ceiling invariants; a resumed best
   already <=92 must freeze and stop before another move. Presently winner is
   reset false and only a strict new improvement triggers terminal handling.
6. **Lifecycle replay and caps.** The RNG test repeatedly invokes choose_move on
   unchanged states and a one-cycle fixture; it does not test full split-run
   checkpoint/restart replay with multiple cycles. Add such a tiny fixture,
   exact post-stop checkpoint controls, bounded manifest/source counts and
   storage/input byte caps. CPU3, nice>=10 and <=1024 MiB address-space limits
   are enforced in the CLI, but samples and input/storage sizes lack hard caps.

The owner has been notified and is coordinating fixes. This review edits none
of the five implementation files. Any subsequent acceptance must record new
hashes and rerun the expanded tiny controls. Production remains unlaunched.
