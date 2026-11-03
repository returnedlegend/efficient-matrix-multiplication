# SAT cached adapter v7

V7 preserves the independently accepted v6 output-ownership fix and changes only the cached guard module to the later root-approved version `09ac03c4ac1123eeb2ddba8a72653cc299aca052df9ad6c82ad618ed5cbd5cd9`. That guard checks direct-child winner paths without scanning each child's result files. Its independent 24-case review is pinned in this proposal.

The adapter remains `7141cd4f395f87eb7f9b5f11b756235c3f06e0f9c2133920d5ecbca6b6b62a06`. The SAT source remains `b37413c39b2be409f76f5fb6dda2867b82804c471c1f1737d88614f79593b82b`; all 30 original math/runtime files, 27 prepared owner-code pins and immutable data pins remain unchanged. V5 and v6 snapshots are preserved.

The isolated v7 runtime passes 23 base, five independent and eight adapter controls with zero skips. Disabled calls read no production inputs; disabled and authorized existing-output calls preserve all prior bytes. Actual queue validators pass. This package starts no production query and remains disabled pending final delta QA and root launch.

The resource envelope remains CPU 1, one solver thread, 1,024 MiB, 30 seconds driver time and 45 seconds outer wall. Parent and worker profiler records distinguish source validation, formula construction, dispatch and actual native `solve` entry. No new mathematical outcome follows from either prior preprocessing timeout.
