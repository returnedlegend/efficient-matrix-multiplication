# Proposed local12 / image9 / target11 preparation

Status: proposal only. No N=5 census or decoder query is authorized by this
document, and no queue change accompanies it. Root reviews this plan before a
bounded preparation run. A separate frozen release and review precede any
production CP query.

The residual contains **12 selected products**, has maximum actual mode-image
dimension **9**, and seeks **11 products**. Replacing it in a verified 93-product
source would give at most 92 products. Its free image rank9/target11 invokes the
new complete surplus-two decoder. This is a different source/mask residual from
the local10/image8/target9 family; no local10 negative transfers to it.

## Fixed sources and parent proposal

Use the four already approved immutable rank93 sources in
`local-ten-lowrank-span43-ready-v1`, rebound by their explicit file hashes.
Recheck each full F2 tensor on all15625 entries, and each opposite pair-column
image rank93, before any source contributes a candidate. No evaluation source or
unapproved BFS descendant enters this release.

The explicit111605 parent10 source/mask catalogue supplies construction anchors,
not feasibility evidence. Freeze at most64 parent records,16 per source, from a
seeded stratified sample:8 per source from its smallest-domain quartile and8
uniformly from its remaining records, without replacement. Store the seed,
selection algorithm, parent catalogue hash, and the complete selected parent
records before preparation. A parent10 can have been queried or unqueried: its
status gives no conclusion about a different12-product residual.

For each parent, the83 outside products give3403 unordered additions. Build
each axis's exact parent factor-span basis once. For additions x,y compute

    new_dimension[a] = parent_dimension[a] + rank(residue_a(x), residue_a(y)).

Here each residue uses the fixed parent-span projection. Retain pairs with all
three dimensions<=9 and maximum9. The source's verified pair-image independence
justifies these factor dimensions as actual mode-image dimensions; the later
core check verifies that identity again. Seed-shuffle the admissible pair list,
then interleave parents and sources. Deduplicate by `(source_sha256, mask12)`.
Record the parent10 mask and both added indices for every proposed12 mask.

The first preparation is bounded by64 parents,217792 raw pair checks,500 unique
shape-admissible12 masks,120 seconds wall time,512MiB AS, and32MiB output. Stop
at the first limit; report partial traversal as partial, with its exact cursor.
The500-mask cap precedes p2 filtering, so sparse p2 survivors do not trigger an
unbounded search for a desired survivor count. These are proposed limits for
root approval, not a production launch.

## Exact preparation filters and records

For each of at most500 shape-admissible masks, lazily construct the compact
core from the frozen12 source factors. Verify selected cardinality12, all
indices distinct, full ambient equality over15625 coefficients, and all three
actual slice-image ranks equal the stated dimensions. Choose a fixed free axis
with dimension9, breaking ties by axis index.

Compute existing exact p2 Koszul bounds for all three modes at target11. No
cost-capped or skipped mode counts as a pass. With dimensions<=9, matrices fit
the existing reviewed default caps. Record each matrix rank, rank-one
contribution, matrix hash, and lower bound. Retain a case only when every mode
was computed and every bound<=11. This is a necessary filter, never existence
evidence. The optional later rank<=3-in-image span bound is outside this first
proposal and would need its own reviewed implementation and scope.

Persist compact source/mask/parent/additions/shape/p2 metadata and disposition
for each processed mask. Persist only a current unfinished core, plus four
query-free replay controls; all other future cores are rebuilt lazily. Use
atomic cursor updates and a hash-chained record journal. Resume binds sources,
parent catalogue, fixed parent list, seed, caps, order and code hashes. A signal,
stale guard, changed pin, partial p2 computation or cutoff leaves that mask open;
it never becomes a p2 rejection or a completed decoder negative.

## Proposed acceptance and later query boundary

An independent preparation audit checks source eligibility/lineage, source-mask
uniqueness and separation from earlier mask cardinalities, parent/addition
containment, every disposition count, cursor coverage, all retained core/raw
image hashes and all three retained p2 matrices. Unit controls use small planted
terms, including a cheap-shape false positive rejected by actual-image checking,
duplicate parent extensions, corrupted masks, a p2 cutoff, and exact resume.

Only after root accepts those preparation artifacts should a separate disabled
query bundle be proposed. Its initial batch is at most25 retained12 masks, with
rank9/target11, max_vectors1023 and max_extensions1533. Actual queue-schema
validation and read-only append preview are mandatory. It uses the fresh
campaign guard and hard19:24:17UTC cutoff; all caps/late calls remain UNKNOWN.
An extension-capped UNKNOWN never implies absence of a cover. Full15625 and the
independent certificate checker must both accept any candidate before WINNER.
