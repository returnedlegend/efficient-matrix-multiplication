# C3 polarization audit: parity obstruction removed, no optimization run

**Follow-up static proof:** [C3_CUBE_SPACE_DOMINATION.md](C3_CUBE_SPACE_DOMINATION.md) establishes that this isolated extension is strictly dominated on its new branch and leaves the finite optimum unchanged. The whole pure seed-cube-span closure is also dominated. The congruence opening reported below remains correct but is not useful optimization coupling. No SAT run on this isolated extension is proposed.

The authorized one-pair extension audit completed successfully. It adds exactly **three columns** to the sealed cyclic dictionary, giving **278 whole-orbit columns**, **826 expanded products**, full/compressed rank **203**, and complete kernel dimension **75**. The original 93-product state and the derived **98-product** excursion both passed primary and strict independent full 15,625-entry checks on persisted bytes.

The complete kernel now contains an odd selection relation. Its joint cube/parity image permits necessary cost residues **{0,2,3} modulo 6**, so exact cost **92** is no longer excluded by the previous parity/modulo obstruction. **No weight 92 solution, minimum weight, SAT result or decoder result is established.**

| Audited quantity | Base | Extension |
| --- | ---: | ---: |
| Whole-orbit columns | 275 | 278 |
| Cube / nonfixed columns | 3 / 272 | 4 / 274 |
| Distinct expanded products | 819 | 826 |
| Full and compressed rank | 201 | 203 |
| Complete independent kernel dimension | 74 | 75 |
| Odd vectors in the deterministic kernel basis | 0 | 1 |
| Individually forced variables / cube variables | 0 / 0 | 0 / 0 |

The exact frozen pair is `a=4096`, `b=262208`, `a+b=266304`. Only `cube(a+b)`, `Cyc(a,a,b)` and `Cyc(a,b,b)` were added. Canonical sorting remapped old indices; every old full and compressed column was compared byte-for-byte through the saved old-to-new index map. No old orbit was replaced, no outside factor direction was introduced, and no private evaluation payload was read. The unchanged existing `cube_polarization.py` helper was hash-checked and used to independently reproduce the expanded excursion.

The known zero relation contains five distinct orbit columns and nine expanded products. In the new sorted dictionary its indices are **135,136,138,256,257**. Toggling it changes the selected state from **33 orbits / 93 products** (three cubes, 30 nonfixed orbits) to **34 orbits / 98 products** (two cubes, 32 nonfixed orbits). This verified excursion removes the old invariant trap without improving the best product count.

Every new column received independent evaluation of all 15,625 coefficients and projection/inverse checks, totaling **46,875 new-column coefficient checks**. The audit additionally reconstructed and independently checked the entire 278-column dictionary, totaling **4,343,750 coefficient checks**, with the same number of full projection/inverse coefficient checks. Full and compressed eliminations agree at rank 203, every kernel witness has zero syndrome in both representations, and independent elimination of witness masks confirms rank 75. The complete cube-factor span still has GF2 rank 3.

Projecting the complete kernel to the four cube coordinates together with whole-selection parity has rank **2** and exactly **four** affine projected states. Allowed cube counts are **0,2,3**, and both whole-selection parities occur. The resulting necessary weighted-cost residues are **0,2,3 modulo 6**. This is a complete projection of this finite audited code, not an enumeration of tensor-code states or a weighted search. Congruence permission for 92 does not supply a 92-product state; a separate authorized optimization would be required.

Eight frozen controls passed before dispatch: the six polarization controls plus two audit-wrapper controls. The actual frozen CLI preview reported zero mutations and zero generated n5 columns. The single live audit then used **5.085671 measured CPU seconds** (4.653861 user, 0.431810 system), **5.107367 outer wall seconds**, and **34,300 KiB** peak RSS. It ran on **CPU3 at nice 10**, under the original **30-second / 1,024 MiB / 32 MiB** limits, maximum 278 columns/826 products, strict 19:24:17 UTC clamp and fresh canonical stage guards. Final output is **1,868,474 bytes**. The child was reaped and CPU3 was explicitly released to the waiting tensor-code preparation owner.

The sealed package is `artifacts/marathon7_20261103T122417Z/cyclic-polarization7-audit-001`. Its completion seal matches the manifest and checksum inventory, `UNKNOWN.json` is absent, and all **43** declared file hashes were rechecked after completion. The frozen config/runtime/pair witness and control log remain in the package and its adjacent `cyclic-polarization7-audit-ready-v1`. Old packages remain immutable.

| Artifact | SHA-256 |
| --- | --- |
| Extended `dictionary.json` | `4b94540939eaa1f7c06d777729bfb2d2f28312eac81dfb2d7a3beb83098c00fb` |
| `manifest.json` | `abaf21f4402c02ef0175b98fe90c82dc76c5c7a2b861a291e9c956346eae2dbd` |
| `COMPLETE.json` | `f2192d70e63f0fa12287dcb2a60341db11b22bfdfa0f24817ad02c82b1fe5699` |
| Frozen `config.json` | `2bfd6c9520ee2f6074e9454697da7ebb1235ffc389fa633a1cf9d34da8a08b12` |
| `pair-witness.json` | `a081ed8355a348891898d0d520a316b644dee44643ad68de85c52174535c1214` |

Tracked compact evidence and source/runtime pins: [evidence/cyclic-polarization7-audit.json](evidence/cyclic-polarization7-audit.json). No solver, optimization, heuristic, decoder search, continuation, paid compute, publication or Git operation was performed. The n5-rejecting tiny prototype remains unchanged; the explicit audit wrapper is separate.
