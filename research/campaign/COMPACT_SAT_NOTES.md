# Exact multilinear-image SAT preprocessing

`scripts/campaign_compact_sat.py` uses the bounded campaign scheduler with
`mmsearch/compact_sat.py` as encoder. Keep its output directory separate from
the baseline worker. Flags match `campaign_sat.py`, plus `--symmetry none` or
`--symmetry u-lex`. The default is no symmetry constraint. Repeated `--seed-dir`
arguments are supported. Existing output directories resume automatically;
changing symmetry on resume is rejected.

For a selected patch of K+1 source products, form its exact residual tensor R.
The column images of its three mode flattenings have dimensions rU,rV,rW.
Gaussian elimination over GF2 supplies a basis B for each image and a linear
coordinate map L with L B = I. Then P = B L is the identity on that image.
Consequently `(PU tensor PV tensor PW) R = R`. Any decomposition of R into at
most K products can be projected term by term into these images without
increasing its number of products. Conversely, expanding a decomposition in
the image bases gives a decomposition in the original coordinates. This
preserves the existence of a local K-slot decomposition exactly.

Every image basis is supported inside the union of the selected source factor
supports. Thus the compact image formulation also collapses the original union
and full-support branches, avoiding repeated encodings of their common core.
No factor is fixed to a guessed value and no integer lift is asserted.

The encoder constrains every rU*rV*rW compressed tensor entry. Original-coordinate
factor variables are linked to basis coefficients by exact XOR constraints,
so the existing decoder expands the solution without modification. Before
solving, expansion of the core tensor is checked against all original residual
entries (15,625 for the 5×5 experiment). A SAT assignment is independently
verified against all 15,625 multiplication-tensor entries after decoding.
The map/log records bases, coordinate projections, core dimensions, original
entry count, compressed equation count, and whether symmetry was used.

Optional `u-lex` constrains compact U coefficient vectors of successive mutable
slots to be lexicographically nondecreasing. All mutable slots have identical
coordinate domains; permuting products always gives a representative meeting
this constraint. Equal vectors and zero factors remain allowed. This removes
only term-permutation symmetry and does not fix arbitrary factors.

Validation: 27 SAT/campaign tests passed, including exhaustive basis coordinate
round trips and linearity, exhaustive lex-comparator truth table, full-versus-
compact SAT and UNSAT controls, nontrivial naive 2×2 rank8→rank7 discovery with
both symmetry settings, and the all-zero residual. A known93→92 smoke patch
with K9 compressed from 40,829 variables/164,220 clauses to 10,729 variables/
41,889 clauses (567 core equations); its 1,000-conflict result was UNKNOWN.
This is a local budgeted experiment, not a rank lower bound.
