# Exact small-slot repair prototype

`mmsearch/binary_small_slot_repair7.py` implements a different joint move from
one-factor block descent. For a compact target X and current R-slot factors,
choose3..6 slots S and keep all other factor points fixed. Form the exact

    Y = X + sum(products outside S).

Replacing the selected slots by <=|S| arbitrary binary products solves the
whole target EXACTLY iff CP(Y)<=|S|. There is no requirement to stay in the old
atom dictionary, preserve factors of selected slots, or decrease an approximate
residual one factor at a time.

## Actual-image compaction and reviewed exact routes

The prototype computes complete mode-image bases of Y. Any decomposition of Y
can be projected into these images using linear left inverses without increasing
the number of products: each image projection fixes Y, and the three mode maps
commute. Conversely compact products lift to Y through the original bases.
The implementation checks the whole compact/lifted Y equality, including zeros.

If any mode rank exceeds the available slots, that PARTICULAR fixed-outside
repair is excluded. Otherwise use the largest mode rank d and the independently
reviewed exact CP(d), CP(d+1), or CP(d+2) decoder. Surplus two uses the frozen
separate surplus-two module, within its reviewed d<=9 cap. Unsupported larger
surplus is UNKNOWN; a smaller-budget positive may still certify a repair.
No failure is promoted to a whole-tensor rank lower bound. Exact negatives are
called REPAIR_EXCLUDED and explicitly bind the fixed outside factor points.

Success is RAW_EXACT_COMPACT only after independently restoring the complete
original compact tensor by packed and scalar checks. It never publishes an
ambient candidate. The raw output and state hash bind the original target,
selected indices and literal fixed outside points. Guards check every complete
positive/negative return and child return. Caps, timeouts, cancellations and
incomplete children are UNKNOWN. The prototype timeout cap is60 seconds.

`propose_slot_sets` ranks3/4-slot sets by how many residual-image directions
their current factor spans fail to cover. This stage calls no decoder and makes
no CP existence claim. It is a cheap proposal heuristic; rank bounds and exact
subdecoders remain the authority for an individual repair.

## Tiny evidence after the nine-case baseline

All6 unit tests pass, including all256 binary2x2x2 tensors repaired by three
slots, fixed-outside retention, independent full target reconstruction,
conditional rank exclusions, zero targets, malformed/capped/late UNKNOWN paths
and proposal-only selection. No N=5 slot call was made.

The bounded known n2 benchmark starts from schoolbook8 with its first product
dropped, yielding the same loss1 plateau that the earlier coordinate controller
failed to escape. It tried ALL35 three-slot sets, ALL35 four-slot sets and ALL7
six-slot sets, keeping the complement fixed:

| Selected slots |Exact fixed-outside exclusions |Raw exact compact repairs |
|---|---:|---:|
|3 |35 |0 |
|4 |35 |0 |
|6 |0 |7 |

All77 calls took0.060 seconds on CPU1 nice10 under512MiB address space.
Each6-slot repair leaves one of the original schoolbook products fixed and
constructs a valid known seven-product decomposition of the n2 tensor. This
shows an actual joint-step escape from the tested loss1 coordinate plateau.
It is a solver control, not a new matrix-multiplication algorithm. The small
3/4-slot failures are retained and apply only to those fixed-outside choices.
The full inputs and raw results are stored under
`research/marathon7/evidence/binary-small-slot-tiny-v1/`.

The N=5 baseline showed loss1 in all9 attempted packets, but it does not follow
that any small-slot repair there will succeed. No production source, packet,
slot set or optimizer was called by these tiny tests. Independent QA and separate
root authority are required before any N=5 small-slot use.
