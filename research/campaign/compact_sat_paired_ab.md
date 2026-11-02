# Paired compact SAT symmetry experiment

Observed 2026-11-02T17:03:56Z: 48 matching local patches were solved
with the same canonical source, selected terms, exact image bases, initial phases,
and 100,000-conflict limit. Every matched patch has K=6.

Plain compact SAT returned UNKNOWN on all 48 patches. Adding safe U-vector
lexicographic ordering returned UNSAT on all 48. Ties and zero factors remain
allowed; ordering only removes permutations of identical-domain mutable slots.
These UNSAT results apply only to the specified frozen local patches.

The matched plain runs used 155.878 seconds
and 4,800,031 conflicts; the lexicographic runs used
41.993 seconds and
1,507,010 conflicts. The observed elapsed ratio is
3.71. Wall times include solver child startup
and initialization, exclude encoding/ingestion, and come from concurrently running
workers pinned to separate cores. They are empirical wall measurements.

The companion JSON records every patch ID, source hash, CNF hash, exact dimensions,
phases, statuses, timing, budgets, solver statistics, and frozen code hashes. Only
complete records present in both logs are compared; unpaired or interrupted work
is excluded. This evidence supports spending the next phase on U-lex compact
patches with K7–12, while retaining explicit UNKNOWN statuses for budget exhaustion.
