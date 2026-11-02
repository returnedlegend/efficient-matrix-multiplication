# Why uniform union, full, and image SAT share a feasibility key

This equivalence applies to the actual frozen worker implementations in this
campaign, over GF2. It does not justify merging arbitrary support restrictions.

For a selected subset S of K+1 source products, freeze every product outside S
and seek K mutable products for their residual R. The deleted index identifies
a slot to remove; changing it within S merely relabels the K mutable slots.
The frozen complement and R depend only on S.

`build_local_cnf` computes one coordinate set `support[axis]` as the union over
`active_terms + [drop_term]`. Its loop then assigns exactly that same set to
every active slot. There are no per-slot masks, guessed factor values, nonzero
constraints, or hard source-phase clauses. Thus R belongs to U0 tensor V0 tensor
W0, where U0,V0,W0 are these shared coordinate subspaces.

Let UR,VR,WR be the column images of the three mode flattenings of R. Each image
lies inside the corresponding shared coordinate subspace, and

    R belongs to UR tensor VR tensor WR.

Choose linear projections PU,PV,PW onto those images that restrict to the
identity there; complements exist over the finite-dimensional field GF2.
Then `(PU tensor PV tensor PW) R = R`. Applying these projections term by term
to any ambient decomposition of R into K products gives K products in the image
spaces, and hence in the shared coordinate union. Products may become zero;
the encoders allow zero factors and represent an upper bound of K products.
Conversely, every union-supported decomposition is an ambient decomposition.
Consequently full and shared-union feasibility are equivalent. Choosing exact
bases for the image spaces is an invertible coordinate change on each image,
so compact image-coordinate feasibility is equivalent as well.

The implemented BinaryBasis coordinate maps are linear left inverses of the
image bases. Projection need not be orthogonal. The compact preprocessor checks
expansion against every original residual coefficient, and every SAT candidate
is independently checked against every original multiplication-tensor entry.
GF2 projections yield coefficients0/1, so canonical ternary representatives
remain available. No corresponding integer lift is asserted.

Optional U-lex ordering does not change feasibility: every mutable slot has
the same factor domains and bases, so one can sort whole products by their U
coefficient vectors. Ties and zero factors remain allowed.

The valid unconditional dedup key is therefore

    (field2, dimension, canonical source hash, selected source-index set, K).

This key records distinct frozen neighborhoods, not tensor-isomorphism classes.
It does not merge different canonical source decompositions simply because their
residuals happen to be isomorphic.

Individual slot supports, fixed active coefficients/factors, mandatory nonzero
products, dictionary atom restrictions, and similar conditioning may exclude
the projected representative. Such branches must be excluded or given a
restriction-specific key. `campaign_sat_audit.py` whitelists the known encoders,
separates recorded nonuniform/fixing conditions, excludes unrecognized dictionary
branches, and distinguishes mathematical bound rejection from solver UNSAT.

Earlier suggestions that this campaign's uniform support union could exclude
an ambient local rank-K solution were too pessimistic: that would require
nonuniform slot restrictions or a coefficient domain not closed under these
GF2 linear projections. The actual uniform-union worker has neither.
