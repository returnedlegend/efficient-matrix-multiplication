# Inner cancellation poller independent QA

**PASS:**15/15 targeted controls, zero failures/errors/skips. Module pin: `f96027d9bf8e7ef9489378d71c107924cab94180bcf63cfc7e8a8db6f904b07b`. Runner pin: `62647f178702200192992095bdf6dd8f00c7db92d68547e193588c1fb1d939d3`. No N5 decoder query or broad regression was run.

Only inner decoder filesystem polling is coalesced, at a configured interval no greater than50ms. Signals, UTC, invocation time and the current case deadline are checked on every callback, before and after filesystem work. The next observation is scheduled from its start time, not its finish. The interval bounds added coalescing at callback opportunities; it does not promise arbitrary synchronous filesystem I/O completes within50ms.

All completion and publication checks remain fresh. The concrete runner differs from frozen v4 only by importing/creating one poller, delegating the inner `cancelled()` callback, and adding diagnostic counts. `check_case`, pre/post source/solve/full/independent verification, result commitment and WINNER barriers are byte-identical. A cached clear inner observation therefore cannot authorize a completed result.

The independent run combined seven owner fake-clock tests, three concrete N2 runner controls and five independently authored controls. It tested49 stop phases on a1ms callback grid, all four immediate clock/signal conditions after filesystem work, seven forced barrier names, changing case deadlines with one persistent poller, and an actual N2 SAT whose original point witnesses/raw zero/repeated/dependent slices exactly match direct polling. Completed SAT and complete-negative returns arriving after a new stop both become UNKNOWN; raw evidence remains, the cursor stays open, no negative journal entry or positive marker is published, and the small positive resumes correctly.

Evidence: `artifacts/marathon7_20261103T122417Z/cancel-poller-independent-qa.{json,log,result.json}`. This accepts the module and reviewed runner delta for freezing. Root retains the production decision after checking the final bundle/catalogue/proposal pins; no untested N5 throughput or search result is claimed.
