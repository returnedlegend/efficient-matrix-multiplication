"""Versioned guard/profiling adapter for the unchanged frozen whole-atom SAT.

The base encoder, native clauses, time/memory bounds and verification/freezer
remain untouched. Only its campaign-guard component and diagnostic hooks change.
"""
from __future__ import annotations

from contextlib import contextmanager
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time

from mmsearch import tensor_code7_sat as base
from mmsearch.marathon7_cached_guard import CampaignGuard as CachedCampaignGuard
from scripts import tensor_code7 as owner

OriginalOwnerGuard = owner.Guard
OriginalWorker = base._worker
OriginalSolveLinear = base.solve_linear
OriginalLoadPrepared = base.load_root_pinned_prepared
_PROFILE = None


class StageProfile:
    def __init__(self, output, *, owns_output=False, claim_on_load=False):
        self.output = Path(output) if output is not None else None
        self.owns_output = owns_output
        self.claim_on_load = claim_on_load
        self.started = time.monotonic()
        self.phase_started = self.started
        self.stage = "not_started"
        self.last_active_stage = "not_started"
        self.durations = {}
        self.guard_calls = 0
        self.solve_linear_entered = False
        self.last_write = -float("inf")

    def mark(self, stage, *, force=False):
        now = time.monotonic()
        changed = stage != self.stage
        if changed:
            self.durations[self.stage] = self.durations.get(self.stage, 0) + now - self.phase_started
            self.stage, self.phase_started = stage, now
        if stage != "driver_finished":
            self.last_active_stage = stage
        if self.owns_output and self.output is not None and self.output.is_dir() and (force or changed or now - self.last_write >= 1):
            self.last_write = now
            self._write(self.output / "profiler-parent.json", self.observation())

    @staticmethod
    def _write(path, value):
        temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
        with temporary.open("wb") as stream:
            stream.write(base.raw_json(value))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)

    def observation(self):
        now = time.monotonic()
        durations = dict(self.durations)
        durations[self.stage] = durations.get(self.stage, 0) + now - self.phase_started
        workers = []
        if self.owns_output and self.output is not None and self.output.is_dir():
            for path in sorted(self.output.glob("profiler-worker-*.json")):
                workers.append(json.loads(path.read_bytes()))
        return dict(schema="tensor-code-sat-stage-profile.v5", stage=self.stage,
                    last_active_stage=self.last_active_stage,
                    elapsed_seconds=now - self.started, stage_seconds=durations,
                    guard_calls=self.guard_calls, solve_linear_entered=self.solve_linear_entered,
                    native_solve_called=any(record["native_solve_called"] for record in workers),
                    workers=workers, claim="Execution telemetry only; no SAT/UNSAT or within-budget claim.")


def stage_for(barrier):
    if "formula" in barrier:
        return "formula_construction"
    if "native" in barrier:
        return "native_dispatch_or_poll"
    if "verification" in barrier:
        return "candidate_verification"
    if "freeze" in barrier or "marker" in barrier or "publication" in barrier:
        return "publication_barrier"
    if "prepared" in barrier:
        return "prepared_validation"
    if any(word in barrier for word in ("source", "ancestor", "lineage", "root", "frozen")):
        return "source_binding"
    return "input_and_lifecycle"


class CachedTensorGuard(OriginalOwnerGuard):
    """Retain owner's pins/signals/reserve; replace only canonical file polling."""
    def __init__(self, hard_utc, seconds, campaign_dir=None, guard_state=None,
                 campaign_sha256=None, stop_markers=()):
        super().__init__(hard_utc, seconds, campaign_dir, guard_state,
                         campaign_sha256, stop_markers)
        if campaign_dir is not None:
            self.canonical = CachedCampaignGuard(seconds, self.hard.isoformat(), stop_markers,
                                                 guard_state, campaign_dir=campaign_dir)
            if self.canonical.resources is None:
                raise ValueError("production canonical resource guard required")

    def __call__(self, barrier="loop"):
        if _PROFILE is not None:
            _PROFILE.guard_calls += 1
            _PROFILE.mark(_PROFILE.stage if barrier == "loop" else stage_for(barrier))
        return super().__call__(barrier)


def profiled_worker(problem, deadline, conflicts, memory_mib, sender):
    """Transparent solver proxy persists actual solve entry before calling it."""
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    profile = _PROFILE
    path = profile.output / f"profiler-worker-{os.getpid()}.json" if profile and profile.owns_output and profile.output else None
    record = dict(pid=os.getpid(), stage="native_backend_import", native_solve_called=False,
                  native_solve_calls=0, started_monotonic=time.monotonic())
    def mark(stage):
        record["stage"] = stage
        record["updated_monotonic"] = time.monotonic()
        if path is not None:
            # Failure to persist the entry prevents the native call, rather than
            # reporting false telemetry about an unobserved solver invocation.
            StageProfile._write(path, record)
    try:
        mark("native_backend_import")
        import pycryptosat
        original = pycryptosat.Solver
        class ProfiledSolver:
            def __init__(self, *args, **kwargs):
                mark("native_formula_loading")
                self.solver = original(*args, **kwargs)
            def __getattr__(self, name):
                return getattr(self.solver, name)
            def solve(self, *args, **kwargs):
                record["native_solve_called"] = True
                record["native_solve_calls"] += 1
                mark("native_solve")
                answer = self.solver.solve(*args, **kwargs)
                mark("native_solve_returned")
                return answer
        pycryptosat.Solver = ProfiledSolver
        try:
            return OriginalWorker(problem, deadline, conflicts, memory_mib, sender)
        finally:
            pycryptosat.Solver = original
    except Exception as exc:
        try:
            sender.send(dict(status="ERROR", error=f"{type(exc).__name__}: {exc}"))
        finally:
            sender.close()


def profiled_solve_linear(*args, **kwargs):
    if _PROFILE is not None:
        _PROFILE.solve_linear_entered = True
        _PROFILE.mark("native_dispatch_or_poll", force=True)
    result = OriginalSolveLinear(*args, **kwargs)
    if _PROFILE is not None:
        _PROFILE.mark("native_result_returned", force=True)
        result["profiler"] = _PROFILE.observation()
    return result


def profiled_load_prepared(*args, **kwargs):
    if _PROFILE is not None:
        # Base main invokes this hook only after its exclusive mkdir succeeds.
        # Never infer ownership merely from a directory appearing during a race.
        if _PROFILE.claim_on_load:
            _PROFILE.owns_output = True
        _PROFILE.mark("source_binding", force=True)
    result = OriginalLoadPrepared(*args, **kwargs)
    if _PROFILE is not None:
        _PROFILE.mark("source_binding_complete", force=True)
    return result


@contextmanager
def installed(output=None, *, owns_output=False, claim_on_load=False):
    global _PROFILE
    previous = (owner.Guard, base._worker, base.solve_linear, base.load_root_pinned_prepared, _PROFILE)
    profile = StageProfile(output, owns_output=owns_output, claim_on_load=claim_on_load)
    _PROFILE = profile
    owner.Guard, base._worker, base.solve_linear = CachedTensorGuard, profiled_worker, profiled_solve_linear
    base.load_root_pinned_prepared = profiled_load_prepared
    try:
        yield profile
    finally:
        owner.Guard, base._worker, base.solve_linear, base.load_root_pinned_prepared, _PROFILE = previous


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--authorize-search", action="store_true")
    parser.add_argument("--qa-approval")
    parser.add_argument("--outdir", type=Path)
    selected, _ = parser.parse_known_args(argv)
    if not selected.authorize_search or selected.qa_approval != "root-reviewed":
        # The base disabled path reads no inputs and owns no output directory.
        return base.main(argv)
    output = selected.outdir
    if output is not None and (output.exists() or output.is_symlink()):
        raise FileExistsError(f"SAT output already exists: {output}")
    with installed(output, claim_on_load=True) as profile:
        try:
            return base.main(argv)
        finally:
            profile.mark("driver_finished", force=True)
            if profile.owns_output and output is not None and (output / "result.json").is_file():
                path = output / "result.json"
                result = json.loads(path.read_bytes())
                result["profiler"] = profile.observation()
                StageProfile._write(path, result)


if __name__ == "__main__":
    raise SystemExit(main())
