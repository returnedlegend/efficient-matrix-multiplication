# Quotient exterior projection: rank195, kernel dimension6

The stronger proposed domination test fails its rank198 premise. For the
approved old tensor-column span B of dimension201, the exterior projection has
rank195, so its kernel on B has dimension6, not3. This reveals three additional
linear coupling directions; it establishes no product-count improvement.

Let K be the span of the three independent old cube forms in F2^25. Choose the
explicit quotient projection q:F2^25→F2^22 whose kernel is K. The natural linear
map from tensors to Λ³(F2^22) sends a pure tensor u tensor v tensor w to
q(u) wedge q(v) wedge q(w). A nonfixed whole C3 orbit has three summands;
their wedges agree, and3=1 over F2. Its image is therefore the single wedge.
A fixed cube maps to zero. This also shows that every S3-symmetric tensor is
in the kernel: distinct-factor permutations pair up in characteristic two,
and repeated-factor wedges vanish.

The audit projected all275 original whole-orbit columns into1540 exterior
coordinates. Exact elimination found rank195. Every one of the original275
full-tensor column relations was checked against its projected counterpart,
so the projection is compatible with the actual old tensor span. Explicit
quotient basis/projection columns, all column images, independent pivot
indices, and reduced projection rows with original-column coefficient masks
were saved.

The kernel has a particularly simple basis: exactly six original orbit
tensors, with indices135,254,274 (the three cubes, weight1 each) and136,137,170
(three nonfixed orbits, weight3 each). All six have zero exterior projection
and are independent as full tensors. The latter three are independent modulo
the cube span. The supplemental kernel receipt preserves full tensor masks,
old orbit coefficient masks, weights, and this independence certificate.
Those weights describe the original available representations, not a proven
minimum.

Had the rank been198, dimension counting would give ker(F restricted to B)
equal to the old cube span. Any sum of newly added quotient-dependent whole
orbits would then lie in this cube span whenever it appeared in a valid
old-plus-new solution; the existing cube flattening bound would prove
domination. Rank195 leaves the three extra directions, so neither that
domination conclusion nor its proposed requirement of three independent
external quotient directions is established.

Tiny controls passed3/3, zero failures/errors/skips: all4096 triples of binary
four-dimensional wedge factors, independent literal exterior expansion,
bilinearity and alternation, exact quotient kernel and linearity, and scalar
full-tensor checks of whole C3 orbits, cubes and S3-symmetric tensors. The
first eight N5 columns were independently re-evaluated at all125000 full
coefficients and projected through a coefficient-level implementation.

The static job completed in0.610 seconds with0.472 process CPU seconds, CPU1
nice10/1024MiB under a30-second outer cap. Input seals, source/code pins, live
campaign guards and final publication barriers matched. No solver, decoder,
optimization, candidate or dictionary extension was used.

Artifacts are under `artifacts/marathon7_20261103T122417Z/`:

| Artifact | SHA256 |
| --- | --- |
| `c3-quotient-wedge-audit-001/manifest.json` | `e00b1b54318966b7f82454d2cfe236a8810f05587e7364e3ba6c3b6cea7ed34a` |
| `c3-quotient-wedge-audit-001/rank-witness.json` | `77f83a8c4faa8887551145a8b237b260ac99804009a8abc8c2a356da9531b679` |
| `c3-quotient-wedge-audit-001/quotient-projection.json` | `d31c09a03663d57ce0423e416a44bf629ba3f77197724454650d51462d46864d` |
| `c3-quotient-wedge-kernel-witnesses-v1.json` | `1332a7bbd2935071e7a173791661bc87d7c8ccab36125569ac70a34fcadf5eb3` |
| `scripts/audit_c3_quotient_wedge7.py` | `63c9fca544941e377e962e247b13dfbd028dc1b7acb84864b7480937fe753572` |
| `tests/test_c3_quotient_wedge7.py` | `e506a6ba8fa2aa16e76744329e48113e83ce48f1184d8c0fc944d119918a5cb1` |

The finite old-span kernel structure is not a global CP lower bound.
