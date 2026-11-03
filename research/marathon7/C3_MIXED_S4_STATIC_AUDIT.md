# Static mixed-S4 intersection audit

All **32 tested four-dimensional factor spans** have exactly the old
three-dimensional cube span as their intersection with the approved old
tensor-column span. No additional coupling direction was found. Retire this
tested one-external-direction family; no decoder or optimization was run.

The input is the approved275-column C3 dictionary, SHA256
`23ff2b7ef344b79277712731cdc80ecc4b030a82026ca77d9fec32a02ebd047b`, with
sealed manifest `eb6337722adaf26ecc3e11795cc94865c2a556db7af70d4efd83b917bb0a392b`.
Its full column span B has rank201. Start with the independent cube forms
4096,262208,16777217. Traverse base representatives in their frozen order and
each representative's factors in axis order. For each external factor e, take
V=span(old three forms,e), rejecting a factor already in the old span and
deduplicating V by its nonzero quotient residue modulo that fixed old span.
Keep the first32 distinct V; no direction is selected by its outcome.

The C3-fixed tensor space in V tensor V tensor V has24 basis tensors, one per
cyclic coordinate orbit on four factor directions. The audit generated only
these linear-space bases, not a factor palette, extended dictionary, candidate,
or decomposition. It used the existing exact `intersection_witnesses` helper
and checked the rank identity and all old/space coefficient witnesses.

| Quantity | Result for every tested V |
| --- | --- |
| dim B | 201 |
| dim C3-fixed tensor space in V cubed | 24 |
| dim intersection | 3 |
| dim union | 222 |

The three old independent cubes belong to each intersection. Its dimension
three therefore proves equality with their span. For an extension confined to
any one of these tested V, the new-term tensor sum Y in a solution must lie
both in B and in that invariant space. Thus Y is a sum of selected old cubes.
Independence of their factor forms makes a mode-flattening rank equal to the
number of cubes in that sum, so no new-product representation is cheaper than
those existing cubes. This domination applies to each tested V separately.
It does not establish domination of a dictionary that combines multiple
different external directions, or of untested directions, and implies no
global CP lower bound.

The first24-column basis was independently evaluated at every full tensor
coefficient: **375,000 coefficient checks**, all equal. The bounded job used
CPU1 nice10,1024MiB with a30-second hard outer cap; it completed in1.008 seconds
with0.890 process CPU seconds. Source seals and runtime code pins matched
before and after. Global campaign guards, live cancellation checks, publication
barriers, and the fixed19:24:17UTC cap remained active. Solver, decoder,
candidate-optimization, and extended-dictionary counts are all zero.

Sealed evidence:
`artifacts/marathon7_20261103T122417Z/c3-mixed-s4-space-audit-001/`.
Every tested direction has its full24-column basis and explicit old/space
intersection masks in `spaces/NN-{basis,intersection}.json`.

| File | SHA256 |
| --- | --- |
| `manifest.json` | `10fc4f65538ef95ea5920737ac996a0084ea93c5881f586d3133214999d715b9` |
| `directions.json` | `ea26d6047d7ecbc2fa2673a216ee917bd6e22c10a709adb069f7261f359f8239` |
| `scripts/audit_c3_mixed_s4_space7.py` | `dd6efb87e62ca8ab6e53dcd1c38e027b2a4e171952b2872087b97a691f8852da` |

Driver evidence is `c3-mixed-s4-static32-driver-v1.{log,result.json}` in the
same campaign directory. No broader continuation was launched.
