# Interim bounded campaign snapshot — 2026-11-03 01:25:36 UTC

This is an interim report of existing files, not completion of the six-hour campaign or new tensor verification. Deadline: 2026-11-03 03:07:35 UTC.

`report.json` preserves 85 job rows, selected artifact summaries, evidence file SHA256 references, read-limit flags, current guard and separate dictionary CPU reconstruction. `jobs.csv` is the resource/status table. Completed launcher status/exit code, mathematical solver status, and positive-control status are separate columns. A zero outer exit code does not imply SAT. Registered running metadata is checked only for PID existence/state, not process identity. Files are read sequentially, so this is not an atomic campaign-wide snapshot.

The collector consumed 3,834,468 bytes in bounded reads and approximately 0.158 CPU seconds including export, pinned CPU2/nice10. It never traverses recovery/native trees, imports tensor solvers, or starts jobs. A large `sat-initial/manifest.json` exceeded the 2 MiB per-file limit and is explicitly marked skipped. JSON total budget is 64 MiB; 512 jobs and 256 immediate child directories are the defaults. Missing, partial, symlink and truncated evidence are explicit. There is no full campaign CPU total: the dictionary wrapper omitted its solver grandchild (891.78 CPU seconds reconstructed separately), and running jobs lack final rusage. Summed job wall times overlap and are not campaign duration.

Repeat safely into a new snapshot directory, or overwrite only this collector's report files in an existing snapshot:

```sh
cd /workspace/efficient-matrix-multiplication
taskset -c 2 nice -n 10 python scripts/collect_rl_campaign_report.py \
  artifacts/rl_campaign_20261102T210735Z \
  --output-dir artifacts/rl_campaign_20261102T210735Z/report-snapshot-DEADLINE
```

The source remains read-only; output contains only collector JSON/CSV. Near-deadline observations and a standalone research report remain future work. Tests: `taskset -c 2 nice -n 10 python -m unittest tests.test_collect_rl_campaign_report -v`.
