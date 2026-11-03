# Parsed-JSON cache guard prototype

This is a separate prototype in `mmsearch/marathon7_cached_guard.py`.
No frozen guard, runner, imported Tensor Code dependency or production input is
modified. Production integration requires independent QA and a separate root
decision. The old `CampaignHold` exception is reused to preserve caller handling.

## What is cached

Only the parsed JSON value is cached. A path's key contains both its lstat
signature and followed-file stat signature: device, inode, mode, size,
mtime_ns and ctime_ns. Every load performs fresh lstat/stat observations,
including cache hits. Hits require a matching second observation. There is no
TTL-based skip of a stop, marker, process, age, storage or clock check.

On a miss, the opened descriptor's fstat must match the path's target stat.
After reading, both fstat and path signatures must still match. JSON is parsed,
then signatures are checked again before the value becomes reusable. A racing
replacement or update causes a bounded retry (at most three attempts); an
unstable or invalid input fails closed and never falls back to an older value.
Atomic replacement, same-size writes, restored mtime and symlink retargeting
invalidate the cache through inode/ctime/link/target identities.

The existing file-following symlink policy is retained, including resource
symlinks and paths outside a containing campaign directory. Both the symlink
and target are tracked; target replacement is visible even if the link is
unchanged. Broken required resource links hold; absent canonical paths retain
the old optional-path behavior. Nonregular JSON targets fail closed.

## Live authority

Every reason/check call checks the current wall deadline, invocation monotonic
budget, signal flag, explicit stop markers, canonical queue/operation stop
fields, root/child WINNER markers, guard_stopped marker, typed resource values,
timezone-aware heartbeat, current heartbeat age, live PID state and start_ticks,
and the five-GiB working-storage threshold. The absolute deadline is clamped
to2026-11-03T19:24:17Z. Heartbeat age below-5s or above60s holds, including when
unchanged cached JSON ages or UTC moves backward. Zombie/dead/reused processes
hold independently of an unchanged file.

Typed resource/liveness checks run before canonical authority, as in the old
guard. After marker/glob I/O, the resource path is re-statted and checked again
so a replacement during that I/O cannot retain the earlier authority. A final
canonical-state version/type/stop check runs once after marker/resource I/O;
it catches a queue stop written during that I/O in the same forced call. Its
fresh stable per-path snapshots, followed by the final UTC/monotonic check,
define the bounded observation point. There is no unbounded recheck loop or
claim to observe future writes. The final time check prevents I/O or parsing
that crosses a cutoff from returning allow.
An already known time/signal cutoff returns before expensive parsing. Reasons
remain diagnostic; where multiple conditions fail, the first reported reason
can differ from the old nested implementation while both hold.

The correctness claim is observational: unchanged signatures permit reuse of
the same parsed bytes; every derived time/process/marker decision is recomputed
from live observations. Cache entries never cache an allow decision. This
assumes ordinary filesystem stat identities/ctime semantics, the same local
filesystem authority model as the existing file-based guard. It is not a
filesystem transaction across all independent campaign files; each read is a
stable snapshot, followed by the existing final lifecycle barrier.

## Validation and measured performance

`tests/test_marathon7_cached_guard.py` uses temporary synthetic state only.
Controls cover a1.4MB state against the old forced guard, typed malformed data,
all marker classes, file mutation/replacement with restored mtime, read/parse
races, heartbeat aging, UTC rollback, PID reuse/zombies and actual child death,
late JSON/proc/glob calls, symlink retarget/broken-link behavior, and a resource
replacement during marker I/O. The old guard's current file pins are unchanged.
The final revision also checks a queue stop or malformed canonical type written
during marker I/O, in the same forced call; all13 tests pass.

Reproducible synthetic-only benchmark:

```sh
taskset -c 1 nice -n 10 python scripts/benchmark_marathon7_cached_guard.py \
  --iterations 80 \
  --output research/marathon7/evidence/cached-guard-synthetic-benchmark-v1.json
```

Measured on CPU1 nice10 with a1,400,000-byte synthetic operations state:

| Guard |80 forced checks total |Median check |Warm median |
|---|---:|---:|---:|
| Existing frozen guard |1.55310s |18.526ms |18.516ms |
| Separate cached prototype |0.01924s |0.145ms |0.145ms |

The measured total speedup is80.71x including the cached guard's cold first
parse (6.53ms). Its80 calls made962 fresh signature observations, parsed two
distinct files only once each, and reused478 parses. This final measurement
includes the additional final canonical recheck. These are synthetic guard
measurements; they do not establish a production query speedup or authorize
integration. No live campaign input was read by the benchmark, and old guard
plus Tensor Code source hashes were compared before/after and stayed unchanged.

## Direct child-marker scan revision

The later guard-only revision replaces Path.glob("*/WINNER.json") with
`_immediate_child_winner(root)`: one os.scandir of the campaign root, followed
by entry.is_dir(follow_symlinks=True) and a direct child/WINNER.json existence
check. It never enumerates child contents. Directory symlinks retain the old
file-following marker behavior. Resource, final canonical and time barriers
are unchanged. The earlier synthetic benchmark above belongs to the previous
b995d4... prototype; production-shaped profiling of the new scan is separate.

The revised module pin is
`09ac03c4ac1123eeb2ddba8a72653cc299aca052df9ad6c82ad618ed5cbd5cd9`.
All14 tests pass on CPU1 nice10, including960 payload files under20 child
directories with a trap that rejects any child scandir, plus matching old/new
behavior for an external directory symlink containing a winner. Late-I/O
controls now hook the marker helper so they continue checking resource and
canonical mutations during marker I/O. No production integration or query is
performed by these controls; the owner of the local runner independently
profiles and reviews this new pin before creating a guard-only overlay.
