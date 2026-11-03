# C3 polarization extension: the actual seed is rank 3, with nonzero cube XOR

**Design-stage record:** the subsequent [static domination audit](C3_CUBE_SPACE_DOMINATION.md) proves that the isolated extension and the entire pure seed-cube-span closure cannot improve the original finite dictionary optimum. The necessary-congruence diagnostics below are insufficient to justify optimization.

The approved seed's three cube factors are **4096, 262208 and 16777217**. They have **GF2 rank 3** and XOR **17043521**, the row-major 5×5 identity mask. They do **not** form a 2D zero-XOR line. A single pair polarization can therefore remove the current dictionary's cost-congruence obstruction without introducing a new ambient factor direction. This is permission under necessary invariants, not a rank 92 construction.

No n5 extended dictionary, tensor column, expanded candidate or decoder/SAT search was generated. This work inspected the existing sealed dictionary's metadata, reused the existing cube-polarization identity in a separate tiny prototype, and checked small projected cube/parity spaces.

## Identity and the concrete pair

The existing `mmsearch/cube_polarization.py` implements the exact F2 tensor identity

`cube(a) + cube(b) + cube(a+b) + Cyc(a,a,b) + Cyc(a,b,b) = 0`.

Here `Cyc` contains the three distinct cyclic rotations. Multilinearity expands `cube(a+b)` into its two pure cubes and six mixed tensor products; every term then cancels in pairs. For distinct nonzero binary vectors `a,b`, the relation contains **five distinct whole-orbit columns** with weights **1,1,1,3,3**, or **nine expanded literal products**. Its five-column selection support is odd, so adjoining it breaks the old even-kernel selection-parity restriction. This is the existing polarization identity, not a new algebraic result.

The smallest proposed extension chooses `a=4096`, `b=262208`, `a+b=266304`. Static canonical-representative lookups found that the following three orbit types are absent from the old 275-column dictionary: `cube(a+b)`, `Cyc(a,a,b)` and `Cyc(a,b,b)`. The two original cubes are present and selected in the seed. Thus an approved future materialization would add exactly **three columns**, giving **278 columns and 826 expanded products**. The relation is independent of the old kernel because it has nonzero new-column coordinates; nullity is at least 75, and rank lies between 201 and 203, pending the actual extension audit.

Toggling that relation predicts a cost change of `−1−1+1+3+3=+5`: the known 93-product seed would become a **98-product** cyclic excursion with **two cubes and 32 nonfixed orbits** (34 selected orbits total). No candidate bytes for this n5 excursion have been produced. The other two original cube pairs also have a new sum cube and two absent nonfixed orbit types; each has the same predicted +5 cost, but the proposal adds only the first pair.

## Why the actual congruence obstruction is removed

The old complete 74-vector kernel projects onto the three cube coordinates as either `000` or `111`, with even whole-orbit-selection parity. The seed cube state is `111` and its selection parity is odd. After adjoining one new sum cube, the known old projection generator is `(1110, even)` and the polarization generator toggles the two chosen old cubes plus the new cube with odd selection parity.

The joint projected affine space has only four states. It permits cube counts **0, 2 or 3**, and its necessary weighted-cost residues modulo 6 are **{0,2,3}**. In particular **92 ≡2 mod6 is permitted**. The concrete predicted excursion costs98, also2 modulo 6. Reaching92 from that excursion would still require removing six products, for example two nonfixed orbits; the congruence check supplies no such relation or solution.

Polarization preserves the XOR of selected cube factor vectors because `a xor b xor(a+b)=0`. That XOR is **nonzero** in this seed, so an affine cube-XOR coset can contain two selected cube forms. The existing old-kernel all-three cube toggle additionally changes selected-cube XOR by the identity mask. The zero-XOR cube-code obstruction therefore cannot be applied to this actual seed as though its cube XOR were fixed at zero.

All diagnostics above concern the span of the old complete kernel plus the new known polarization relation. A future full extended-kernel audit may reveal more relations. A permitted residue never proves an achievable product count. Conversely, an absent residue in a merely proposed relation span must not be claimed as an exclusion for an unaudited larger dictionary.

## The 2D-line and zero-XOR 3D caveats still matter

The prototype also checks the cases from the root's warning. If three selected cubes formed a 2D line `a,b,a+b`, their XOR would be zero. Pair polarization would toggle all three cubes, leaving zero cubes rather than two. In that known relation family, cube count remains0 or3 and product cost stays divisible by3, so exact 92 is excluded by a necessary invariant.

With all seven nonzero forms of a 3D factor space and selected cube XOR fixed at zero, possible cube-subset weights are **0,3,4,7**. None is2 modulo3. Adding one independent direction to a 2D line therefore need not remove the mod3 obstruction. In a 4D space, the five forms `{e1,e2,e3,e4,e1+e2+e3+e4}` form a zero-XOR circuit of weight5, which is2 modulo3. Two new independent directions from a 2D line can make this particular necessary obstruction disappear. It still does not establish a tensor solution of weight92. These zero-XOR cases do not describe the actual rank3/nonzero-XOR seed audited here.

## Tiny prototype and controls

New files are `mmsearch/cyclic_tensor_polarization7.py` and `tests/test_cyclic_tensor_polarization7.py`; the existing helper and generic atom-code modules are unchanged. All extension-generation functions reject n5. The prototype reuses `polarize_cubes`, encodes five-orbit zero relations and computes only bounded joint cube/parity projection diagnostics.

Six controls pass, zero skipped:

- Every one of the 105 distinct nonzero factor pairs at width4 gives five distinct orbit columns, nine expanded products and exactly zero tensor.
- An exact n3 naive 27 seed polarizes to 32 products, with two cubes, through an odd five-orbit kernel relation; both full 729-entry primary and independent checks pass before and after.
- The actual-source-shaped rank3/nonzero-XOR projection permits cost residue2 modulo 6.
- A 2D line and all seven zero-XOR 3D cube forms retain the exact 92 congruence obstruction.
- A 4D zero-XOR weight5 circuit removes that necessary obstruction in the projected model.
- n5 extension generation and invalid inputs remain rejected.

Projected enumeration is capped at 15 cube variables and projected rank16; the 4D test visits only 4096 cube/parity projections. It does not enumerate the original 74-dimensional tensor-code state space or optimize a weighted objective.

## Proposed next authorization: audit only

The frozen proposal is `artifacts/marathon7_20261103T122417Z/cyclic-polarization7-prototype-v1/next-audit-proposal.json`, currently disabled. It requests one **n5 extension dictionary/rank audit**, not a solver or decoder: retain the sealed 275-column dictionary, add exactly the three orbit types for the first pair above, check all 15,625 coefficients of each new column and the exact zero relation, and recompute full/compressed rank, complete kernel parity and the joint cube/parity projection. Retain the exact 93 source and independently verify any materialized 98-cost excursion on persisted bytes through both full verifiers. Stop and report before proposing optimization.

Suggested limits remain **30 seconds, CPU1 at nice 10, 1,024 MiB, 32 MiB output, at most 2,000 orbit columns**, with the canonical fresh guard and strict 19:24:17 UTC clamp. Recheck the same approved source closure and external root eligibility pins; the added forms are deterministic sums of two already approved seed-cube factors, with no new source payload, factor palette product or outside independent direction. The previous complete dictionary audit took 5.78 measured CPU seconds, but that is context rather than a guarantee for a new run. Three full and compressed bit columns add at most about 8 KiB of raw column bits before serialization/overhead. A cutoff remains UNKNOWN, and no automatic retry or continuation is proposed.

Evidence: [evidence/cyclic-polarization7.json](evidence/cyclic-polarization7.json), including exact source/dictionary hashes, static membership results, six-control log pins and the disabled audit proposal. No n5 extension, optimization or search was run; no old campaign file, generic branch or Git state was modified.
