# Compactification and mixed12 independent QA

## Mathematical scope

For a literal source tensor T=sum_i a_i tensor b_i tensor c_i and a selected
index set I, let R be the XOR of precisely those original products. Let A,B,C
be the spans of the selected factors in the three modes. Exact basis
injections i_A,i_B,i_C give a unique core G with

    R = (i_A tensor i_B tensor i_C) G.

This compactification preserves CP rank over F2. Lifting a decomposition of G
proves rank(R)<=rank(G). Conversely choose linear left inverses of the three
injections and project any decomposition of R; zero products can be removed,
so rank(G)<=rank(R). The argument permits ambient decompositions whose factors
initially lie outside A,B,C. It does not require a rank-one census or a
factor-image saturation assumption.

The separate opposite-pair independence precondition justifies saying that
these factor spans are the **actual mode images**. If the selected opposite
pair columns are independent, the corresponding matricization is A_I P_I^t,
with P_I full column rank. A right inverse of P_I^t shows its image is exactly
im(A_I). Full source opposite-pair rank K implies this for every literal
subset, in each of the three modes. This must be rechecked for each new native
export; it is not inherited merely because the exporter started from a
previous rank93 source. Without independence, factor-image coordinates still
give a valid exact core, but their dimensions need not be actual mode ranks.
The control (1,1,1)+(2,1,1) has factor dimension two in mode zero and actual
mode rank one.

For fixed images A,B,C, finite source-factor closure is the set J of original
source indices whose three factors lie in these images. It contains I and
does not enlarge the images. Membership over every original source term
therefore makes closure idempotent. With the source pair-independence
precondition, the residual on J also has these same actual mode images.
Closure does **not** say R_I=R_J: adding source terms changes the residual, and
all added indices must also be removed from the frozen outside products when
repairing J. It does not enumerate all rank-one points of any tensor subspace.

For a replacement sum P with R_I=P checked exactly, the full tensor identity is

    T = (sum over original indices outside I) + P.

For source size K, old subset size k and replacement size m, the unsimplified
global count is K-k+m; parity canonicalization can only decrease it. A rank94
export needs a two-product local improvement to reach92. A one-product
improvement there reaches at most93, whereas it reaches92 from rank93.
Finite negatives apply only to the exact selected residual with its specified
outside products frozen. They imply no global lower bound.

## Deterministic genuine-surplus-two controls

The independent helper `tests/test_compactification7_independent.py` provides
`planted_n4(extra_count)` for extra_count four or five. Start with the seven
naive N2 products indexed by (i,j,k) in {0,1}^3 except (0,0,0), embedded in
naive N4 as

    (E_ij, E_jk, E_ki).

Add the first four or five triples from

    (0,2,2), (0,3,3), (1,2,3), (1,3,2), (2,0,2).

In each mode these extra factors occupy distinct coordinate positions outside
the initial 2x2 factor block. The compact residual is therefore the direct sum
of the seven-product gadget and four/five isolated rank-one terms. Each full
source is the unmodified naive N4 tensor, with64 products and all three
opposite-pair ranks64. The selected supports have pair ranks11 or12 and actual
mode ranks8 or9 in all three modes.

| Mode shape | Source subset | Target | CP(d+1) decision | CP(d+2) decision |
| --- | --- | --- | --- | --- |
| 8x8x8 | 11 | 10 | complete LOCAL_UNSAT at9 | SAT with10 |
| 9x9x9 | 12 | 11 | complete LOCAL_UNSAT at10 | SAT with11 |

Both constructive positives use `repeated_coset_pair_extension`, so they
exercise the genuine surplus-two path. They are stronger controls than
inflating independent products and repairing directly to CP(d). Each lift
reconstructs the full original ambient residual, then repairs naive N4 from64
to63 products. Primary and independent whole-tensor verifiers each check all
4096 coefficients. These are synthetic N4 controls only; the N5 target92 and
15625-entry production eligibility gates are unchanged.

## Mixed12 adapter review

The reviewed runner is `scripts/run_c3_mixed12_pilot7.py`, SHA256
`1e8f86f3df9bcd6f5212837a51d59e1a754a504098653b9a5f08329d0cca8364`.
It routes target d/d+1 to the existing exact decoder and d+2 to
`surplus_two7` with mode-rank cap9, vector cap1023, extension cap1533 and
20-second per-case timeout. Unsupported surplus remains UNKNOWN. `SourceCache`
reconstructs the selected literal residual, verifies exact ambient/core
equality, and checks every actual mode rank before decoding. Production source
and preparation pins remain explicit in the runner and frozen configuration.

The independent actual `run_case` tests exercised both N4 positives through
source loading, core construction, decoding, lifting, persisted primary and
independent validation, and publication to the control records directory.
Seven injected late barriers—post solve, post lift, post primary, post
independent, pre canonical rename, post eligible publication, and post result
publication—each produced UNKNOWN with hidden raw evidence and no eligible
record or visible completed result. No WINNER or global freeze was created by
the N4 controls.

Five independent tests plus the owner's three targeted tests passed **8/8,
zero failures/errors/skips**, in0.896 seconds, CPU1 nice10/512MiB, with a
40-second outer bound. Evidence:
`artifacts/marathon7_20261103T122417Z/compactification-independent-controls-v2.{log,result.json}`.
Independent test SHA256:
`e049c411c67b31c19b372a02f248897ea95b013f22b895c6d2c4dff1d012a9f9`.
The tested closure helper SHA256 was
`73e510be75ed2220992a3a80dfe8e7a1c53487e49418942f41055cb30223b4b4`;
the tested surplus-two module SHA256 was
`3fb2d76b3297b0f5962175af9054b8c33ae02a351bab8f603d88f29e71d31107`.
No production N5 decoder was called by this review.

## Native-export provenance handoff

The proposed native-export corpus is a separate contract from the old affine
source loader. Its final pack was not yet available for independent inspection
when this note was written. Acceptance requires the actual raw export bytes
bound to their parent run/source/configuration/binary and root-approved train
lineage; exact primary and independent tensor checks; literal field/dimension
and essential support count; freshly computed all-mode pair ranks; a frozen
selection/atom-cap receipt; and explicit handling of rank94 rather than the
old hardcoded rank93 masks. Validity of the mathematical compactification is
not approval of an uninspected source pack or a new production query.
