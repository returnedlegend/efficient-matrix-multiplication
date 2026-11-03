# Necessary low-rank-span bound over F2

The proposed bound is valid. The separate helper
`mmsearch/rank2_span_bound7.py` implements only this necessary condition. No
production decoder, runner, preparation artifact, or search configuration was
changed, and this review made no N5 query or solver call.

## Statement and proof

Let S be a d-dimensional binary matrix slice image and let

    q(S) = dim span { M in S : matrix_rank(M) <= 2 }.

If the tensor has CP rank at most d+c, for a nonnegative integer c, then

    q(S) >= max(0, d+c-(2^c-1)).

A CP decomposition gives rank-one matrices whose span L contains S. Delete
dependent matrices from that generating set; the remaining original rank-one
matrices P_1,...,P_r form a basis of L, with r <= d+c. Put c' = dim(L/S), so
r=d+c' and 0<=c'<=c.

Partition the basis matrices by their value in L/S. Keep every basis matrix in
the zero class; each is a rank-one member of S. In each nonempty nonzero class,
choose an anchor and keep P_i+P_anchor for every other member. Each difference
lies in S and has rank at most two. All these kept matrices are independent:
in any linear relation, the coefficient of each nonanchor original basis
matrix forces its difference coefficient to vanish, then the zero-class
coefficients also vanish. If k is the number of nonempty nonzero quotient
classes, their number is r-k.

There are at most 2^c'-1 such classes. Therefore

    q(S) >= r-k >= d+c'-(2^c'-1) >= d+c-(2^c-1).

The last inequality holds because h(t)=t-(2^t-1) is nonincreasing on the
nonnegative integers: h(t+1)-h(t)=1-2^t<=0. The nonnegative dimension gives the
outer maximum. This also covers c'=0 and redundant original CP terms.

For c=0,1,2,3,4 the required dimensions are respectively d,d,d-1,d-4,d-11,
clamped at zero. This is a bound on the span of **rank at most two**, including
rank-one points. It does not require an exact-rank-two point.

## Sharpness and strict limits

For S=span(diag(1,1,1,0),diag(0,0,0,1)), d=2 and the nonzero ranks are 3,1,4.
The four coordinate rank-one matrices cover S, and another-mode flattening
has rank four, so CP=4=d+2. Here q(S)=1=d-1, proving the c=2 bound can be tight.
There is no exact-rank-two point. Thus a general exact-rank-two-seed requirement
would reject a feasible CP<=d+2 instance.

The condition can exclude instances even when a rank-two seed exists. Take
three disjoint diagonal blocks of sizes 2,3,3 in Mat(8,8). Their slice image
has d=3 and q(S)=1: only the first nonzero block has rank at most two. The c=2
threshold is two, so CP<=5 is excluded despite that rank-two point.

Passing is not an existence certificate. For example, the one-slice matrix
I_2 has d=1 and q(S)=1, and passes at budget one although its CP rank is two.
The existing distinct-coset obstruction [33,33792] in Mat(4,4) likewise passes
at budget three. No completion, affine-anchor, or coset compatibility is
deduced by this helper.

## Helper contract

`classify_pair_image` takes the actual raw packed slice matrices, both matrix
dimensions, and an absolute CP budget. It computes the image basis without
discarding raw-input provenance: its fingerprint binds dimensions and all
ordered original slices, including zeros, repetitions, and dependencies.
Low-rank witnesses retain original packed matrices and their image coordinates.
The existing `compact_rank2_edges43.matrix_rank_at_most_two` supplies matrix
rank classification; the dimension calculation uses exact binary elimination.

* `EXCLUDED` means the flattening rank exceeds the budget, or a completed
  enumeration establishes the necessary-span deficiency.
* `NOT_EXCLUDED` means the necessary threshold has been witnessed, possibly
  before enumeration completes, or the threshold is vacuous. It makes no
  existence claim.
* `UNKNOWN` means a vector cap, cancellation, or wall budget prevented a
  timely necessary decision. Stops are checked before and after matrix rank
  calculations and again before return. They cooperatively bound work; they
  cannot preempt one rank calculation or input materialization.

The default enumeration cap is 65,535 nonzero image matrices. Callers can set
`seconds` and a cancellation callback. Deficiency requires the full image;
prefix observations cannot exclude a budget. `complete` describes the
necessary decision, while `enumeration_complete` describes the scan.
`rank2_span_rank` is exact only after a full classified scan;
`observed_rank2_span_rank` and the independent witnesses describe any prefix.
An input budget below d is rejected by the ordinary flattening bound first.

## Targeted verification

Controls v2 passed **10 tests, zero failures/errors/skips**, with 1.324 seconds
of test-runner time under CPU1, nice10, 512 MiB and a 180-second outer limit.
There were no solver calls and no production N5 reads or queries.

The independent portable rank-one-cover oracle checked every binary subspace
of Mat(2,2) and Mat(2,3): **2,892 spaces and 28,786 budget decisions**, with zero
unsafe exclusions. Exact CP is the least dimension of a rank-one-generated
cover space. There were 1,800 passing necessary decisions with CP above the
budget, confirming that passing is deliberately incomplete. These two-row
spaces all have q(S)=d, so a second exhaustive family exercises actual
low-rank-span deficiency.

That second family embeds all 2,892 binary subspaces of coordinate dimensions
four and six as diagonal matrices. Exact CP equals the number of active
diagonal coordinates: coordinate rank-one terms attain that value, and another
mode flattening gives the same lower bound. Across **8,724 budget decisions**,
the classifier made 3,407 sound exclusions, including **520 c=2 exclusions**.
Tests additionally cover the sharp example, the stronger seed-present
exclusion, raw zero/dependent slices, literal input validation, early passing
witnesses, vector caps, cancellation, and a rank calculation finishing late.

Evidence is in
`artifacts/marathon7_20261103T122417Z/rank2-span-bound-controls-v2.{log,json,result.json}`.
The before/after source pins were unchanged during the run:

| File | SHA256 |
| --- | --- |
| `mmsearch/rank2_span_bound7.py` | `b4388978ed49e10a9487e7c78c0059381ce680233045ebd5db0580c850f66c4b` |
| `tests/test_rank2_span_bound7.py` | `691febf8c8fecb4586a150f0a65700ba797b60f54cd264965fb7077abd8e5b5a` |
| `tests/fixtures/compact_rank2_edges43_oracle.py` | `f9b00ed3873abe61ce4456cfbf51f04bf9fd9342978d04cbd4b804231b4d40e8` |

Production integration requires a separate decision. In particular, this
review does not change the assumptions or scope of existing exact-rank-two
decoders.
