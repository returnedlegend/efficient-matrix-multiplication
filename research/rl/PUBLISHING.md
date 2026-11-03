# Published campaign bundle

The user explicitly authorized pushing the completed research changes to
GitHub after the search ended. Original statements prohibiting publication
in the campaign configuration, reports and handoff describe the historical
search authorization. They are preserved as evidence of that earlier scope;
the later authorization covers this publication and does not extend search.

The [six-hour report](SIX_HOUR_REPORT_20261103.md) records the outcome: best
independently verified count 93 over F₂, no improvement to 92, and 390 passing
tests. Finite negative searches do not settle whether rank 92 exists.

## Scope and provenance

The Git bundle includes source, tests, pinned requirements, selected reports,
exact certificates and independent verification, the final checkpoint with
its matching schedule, the separately evaluated policy snapshot, the warm
policy, and frozen recovery and restart inputs. Bulk raw run trees, recovery
archives, compiled untracked binaries and native solver payloads are retained
in the original workspace and are not included in Git. A reference to such
historical material does not mean it is part of this selected bundle.

The campaign's
[final_checksums.json](../../artifacts/rl_campaign_20261102T210735Z/final_checksums.json)
is a **historical selected snapshot**. Its recorded repository HEAD is
`b909e8607ee31617488c6bc8acc077ef8e0cb288`; campaign source changes were
uncommitted at that time. Its file hashes, rather than that base commit alone,
identify the source bytes used. The publication's
[publication_manifest.json](../../artifacts/rl_campaign_20261102T210735Z/publication_manifest.json)
records the selected bundle and current hashes. It is separate from the
historical checksum record. The original reproduction document is preserved
at [its historical path](../../artifacts/rl_campaign_20261102T210735Z/publication/historical/research/rl/REPRODUCING.md)
so its historical checksum remains verifiable after publication clarifications.
Relative links inside that byte-preserved copy retain their original
`research/rl/` context; consult the corresponding current research document
when reading it from the archival directory.

## Paths, verification and replay

Historical JSON and command arrays retain absolute paths beginning with
`/workspace/efficient-matrix-multiplication/`. Interpret that prefix as the
original checkout location. For read-only inspection or verification, map its
repository-relative suffix to your own checkout; use published snapshot
certificates when the original raw source path was excluded. Do not rewrite
the original evidence or its hashes.

The independent standard-library verifier and predeadline snapshots are in
`artifacts/rl_campaign_20261102T210735Z/predeadline-best-verification/`.
The final saved identities and their exact verification reports are in
`artifacts/rl_campaign_20261102T210735Z/final-best-certificates/`.
These checks cover all 15,625 tensor coefficients, with random matrix products
as supplemental checks. They establish the supplied identities over F₂.

Follow [REPRODUCING.md](REPRODUCING.md) for frozen evaluation. Strict training
resume requires original path, binary and source identities; a relocated or
rebuilt environment may require fresh training instead. The evaluated policy
snapshot and final training checkpoint are different states. New search needs
a new authorized budget, deadline and output directory.
