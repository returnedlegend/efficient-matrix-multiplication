# All quotient-wedge-zero whole-orbit extensions are dominated

For the approved old finite C3 dictionary, adding any collection of whole
C3 orbits whose three factor images are dependent modulo the old cube-factor
span cannot lower the finite-dictionary optimum. The exact six-dimensional
kernel calculation and63 completed partial-tensor rank questions prove this.
This is **not** a global matrix-multiplication rank lower bound and does not
claim the old finite optimum is93.

## Linear map and kernel

Let B be the201-dimensional span of the275 approved old orbit tensors. Let K
be the span of the three old cube forms in F2^25, and q the explicit projection
to F2^25/K. The natural exterior map F sends a nonfixed whole C3 orbit to
q(u) wedge q(v) wedge q(w), since its three cyclic summands have the same wedge
and3=1 over F2. Cubes map to zero. The checked projection has rank195 on B,
and its six-dimensional kernel has the following independent old-orbit basis:

| Orbit indices | Product weights |
| --- | --- |
| 135,254,274 | 1,1,1 |
| 136,137,170 | 3,3,3 |

All six original tensor columns are independent. Their whole-orbit product
supports are disjoint, so the natural old representation of a basis sum has
cost w equal to the sum of its selected basis weights. Each nonzero kernel
tensor Y has a unique such basis mask.

## Exact63-element certificate

All63 nonzero Y were constructed from their original full ambient tensors.
Each was compactified using its **actual** three mode images, not an assumed
factor palette. Projection followed by expansion checked all15625 ambient
coefficients for every Y. Their exact image ranks agree in all three modes.
The resulting compact core and explicit basis injections are persisted.

For each Y, its old representation proves CP(Y)<=w. The question CP(Y)<=w-1
closed as follows:

| Route | Cases | Complete outcomes |
| --- | --- | --- |
| Actual flattening rank>w-1 | 19 | excluded |
| CP(d) rank-one image test | 24 | LOCAL_UNSAT |
| CP(d+1) rank-two-edge test | 16 | LOCAL_UNSAT |
| CP(d+2) repeated-pair extension test | 4 | LOCAL_UNSAT |

There are zero UNKNOWN, ERROR or SAT outcomes. The44 decoder decisions used43
calls and one reuse of an identical full compact core at the identical budget;
each reused decision remains bound to the separately checked ambient image
injections. Previously completed literal-packet result hashes were checked
for matching core/budget scope; none was queried again. Therefore **CP(Y)=w
for every nonzero Y in ker(F restricted to B)**; the zero tensor has cost zero.

The phase completed in1.503 seconds with1.402 process CPU seconds under CPU1
nice10/1024MiB, a120-second overall cap and two seconds per case. The source,
prepared-core and loaded-code pins remained fixed. Three tiny protocol controls
passed, covering a genuine surplus-two partial positive with all15625 original
ambient coefficients checked, complete negative versus cancellation, and four
late positive barriers retaining UNKNOWN/raw evidence. No production global
M5 query, WINNER, records directory, or global stop marker was written. Had a
partial positive occurred, it would have remained a hidden partial-tensor
witness requiring separate global source containment and validation.

Only seven old-basis sums are contained as products in any of the32 approved
rank93 seeds; those are cube-only sums already closed by flattening. No
non-cube kernel sum was treated as a whole matrix-multiplication source.

## Domination proof

Consider any solution representing the old target T using old dictionary
orbits and newly added whole C3 orbits, every new orbit having wedge zero.
Write T=O+Y, where O is its old-orbit part and Y its new-orbit part. Because
T and O belong to B, Y belongs to B. Every new orbit maps to zero, so F(Y)=0.
Thus Y lies in the certified six-dimensional kernel.

Let w be the cost of the corresponding selected old kernel-basis orbits. The
certificate proves CP(Y)=w. Any new-term representation of Y costs at least
CP(Y), so replacing all new terms by those selected old orbits costs no more.
Combine them with O, cancel duplicate old orbits by binary parity, and obtain
an old-only solution of no greater cost. Conversely every old-only solution
is still present in the extended dictionary. The two finite optima are equal.

This argument covers arbitrary new factor forms and arbitrary interactions
among their wedge-zero orbits; it is not limited to the previously tested346
one-external-factor spaces. It does not cover a new nonfixed orbit with three
independent quotient factors. Any genuinely improving whole-C3-orbit extension
must therefore include at least one such orbit. No claim about arbitrary
noncyclic products, a general-field lift, or global CP rank follows.

## Pinned evidence

Artifacts are under `artifacts/marathon7_20261103T122417Z/`:

| Artifact | SHA256 |
| --- | --- |
| `c3-wedge-kernel63-prep-v1/manifest.json` | `51468e048d9ac2878ac985f5e92515dedeec27b3e91229b0bc507c88a000e94f` |
| `c3-wedge-kernel63-queries-v1/manifest.json` | `d38d569c826a32c14d14f205da0bd0d084d06c7aa845f7e954a632b2693e42a5` |
| `c3-quotient-wedge-kernel-witnesses-v1.json` | `1332a7bbd2935071e7a173791661bc87d7c8ccab36125569ac70a34fcadf5eb3` |
| `scripts/query_c3_wedge_kernel63_7.py` | `d9c038ebdcd62efe245e8ee714e5248f5843493afd432bc2c612143018ac8f92` |
| `tests/test_c3_wedge_kernel63_queries7.py` | `1a4172e1d53fcaaeffe7511b32889ce0de74f5e1def36806d942daede62219ec` |

Each input case retains its exact old products, ambient tensor, actual image
bases, compact core, input hashes and approved-seed containment metadata. Each
complete decoder result retains its exact raw census/cursor certificate.
