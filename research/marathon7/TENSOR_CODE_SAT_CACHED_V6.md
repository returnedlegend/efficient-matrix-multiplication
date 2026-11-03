# SAT cached adapter v6 output ownership fix

The frozen v5 adapter failed independent review: its finalizer could write telemetry into an existing output directory, including on a disabled call. Frozen v5 is preserved as rejected evidence and is not a launch candidate.

V6 changes only adapter output ownership. Disabled invocations delegate directly to the unchanged base disabled path, without installing profiling hooks or inspecting an output directory. Authorized calls reject an existing output path before any input read or output write. The profiler is armed only when the unchanged base runner has successfully created its exclusive new output directory and entered its source-loader hook. A directory appearing during a failed creation race is never claimed by the finalizer. This also handles the standard `--outdir=PATH` argument form.

The original SAT encoder, native worker, complete tensor/source checks, late-UNKNOWN evidence and hidden publication staging remain byte-for-byte unchanged. V6 retains the specifically approved cached guard `b995d4a3ac668e2da3fc37482782eb86d5d11a0ae00165c52b32500b09d1bd2d` from the frozen v5 package; it does not adopt a later working-tree guard version. All 30 original v4 runtime files and 27 prepared owner pins remain unchanged.

The isolated v6 runtime passes 23 original controls, five independent controls and eight adapter controls with no skips. The added controls check disabled existing-output calls, authorized existing-output calls, and failed exclusive-creation races. Each preserves prior result bytes and creates no telemetry file. Existing-output calls also pass standalone frozen-CLI checks. No n=5 solve is performed during this review.

The resource envelope and data pins remain unchanged: the same 406-atom prepared dictionary, CPU 1, one solver thread, 1,024 MiB, 30 seconds total driver time and 45 seconds outer wall. Execution-stage telemetry uses the existing v5 telemetry schema. The new job is disabled until independent delta QA and root launch approval.
