"""Auxiliary pair watcher helper with the active-source cap raised to109.

All discovery, exact verification and worker budgets match the frozen helper.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import multiprocessing as mp
from pathlib import Path
import resource
import signal
import time

from .pair_column_compression import compress_candidate
from .recombine import digest
from .search import encode_candidate
from .slice_compression import InvalidCertificate, canonical_masks


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def policy(campaign, now=None):
    now = time.time() if now is None else now
    value = strict_json((Path(campaign)/"campaign.json").read_bytes())
    if not isinstance(value, dict) or value.get("state") != "running" or type(value.get("field")) is not int or value["field"] != 2:
        return None, "campaign is not valid/running F2"
    deadline = dt.datetime.fromisoformat(value["deadline_utc"].replace("Z", "+00:00")).timestamp()
    if not math.isfinite(deadline) or deadline <= now:
        return deadline, "global deadline reached"
    queue = Path(campaign)/"queue_state.json"
    if queue.exists():
        state = strict_json(queue.read_bytes())
        if (not isinstance(state, dict) or state.get("format") != "mmsearch-queue-v1" or
                not isinstance(state.get("jobs"), dict) or "stop_reason" not in state):
            return deadline, "invalid queue state"
        if state.get("stop_reason") is not None:
            return deadline, f"queue stopped: {state['stop_reason']}"
    return deadline, None


def discover_sources(campaign, repo, identity):
    """Only live root registrations; no residual prefixes or recursive crawl."""
    sources, errors = [], []
    for registration in sorted(Path(campaign).glob("*.running.json")):
        try:
            registration_raw = registration.read_bytes()
            job = strict_json(registration_raw)
            process = identity(job.get("pid"))
            if process is None:
                continue
            started = dt.datetime.fromisoformat(job["started_utc"].replace("Z", "+00:00")).timestamp()
            if abs(process["started_unix"]-started) > 10:
                continue
            command = job["command"]
            if not isinstance(command, list) or any(not isinstance(x, str) for x in command):
                raise ValueError("active command must be a string argv")
            def resolve(text):
                path = Path(text)
                return path.resolve() if path.is_absolute() else (Path(repo)/path).resolve()
            paths = []
            for flag in ("--checkpoint", "--outdir", "--output-dir"):
                if flag not in command:
                    continue
                position = command.index(flag)
                if position+1 >= len(command):
                    raise ValueError(f"missing value for {flag}")
                path = resolve(command[position+1])
                if flag == "--checkpoint":
                    if path.is_file():
                        paths.append((path, "checkpoint"))
                else:
                    phases = sorted(p for p in path.glob("phase-*") if p.is_dir())
                    current = phases[-1] if phases else path
                    for basename in ("walk.current.txt", "walk.best.txt"):
                        shadow = current/basename
                        if shadow.is_file():
                            paths.append((shadow, "full-shadow"))
            for path, kind in paths:
                sources.append(dict(path=str(path), kind=kind, registration=str(registration.resolve()),
                    registration_raw_sha256=hashlib.sha256(registration_raw).hexdigest(), command=command,
                    registered_pid=job["pid"], process_identity=process))
        except Exception as exc:
            errors.append(dict(registration=str(registration), status="ERROR", error=f"{type(exc).__name__}: {exc}"))
    unique = {(source["path"], source["kind"]):source for source in sources}
    return [unique[key] for key in sorted(unique)], errors


class SourceError(ValueError):
    def __init__(self, message, key, raw=None):
        super().__init__(message)
        self.factor_key = key
        self.raw = raw


def read_source(source):
    raw = Path(source["path"]).read_bytes()
    raw_sha = hashlib.sha256(raw).hexdigest()
    semantic_key = raw_sha
    try:
        if source["kind"] == "checkpoint":
            value = strict_json(raw)
            semantic_key = digest(dict(n=value.get("config", {}).get("n"), field=value.get("field", 2), current=value.get("current")))
            n = value.get("config", {}).get("n")
            if type(n) is not int or n != 5 or ("field" in value and (type(value["field"]) is not int or value["field"] != 2)):
                raise ValueError("checkpoint requires exact config.n=5 and F2 when a field is declared")
            triples = value["current"]
        elif source["kind"] == "full-shadow":
            if Path(source["path"]).name not in ("walk.current.txt", "walk.best.txt"):
                raise ValueError("raw/residual prefixes are outside the full-shadow whitelist")
            triples = []
            for line in raw.decode("utf-8").splitlines():
                fields = line.split()
                if len(fields) != 3 or any(not field.isdecimal() for field in fields):
                    raise ValueError("full shadow requires exactly three decimal mask integers per line")
                triples.append(tuple(map(int, fields)))
            semantic_key = digest(triples)
        else:
            raise ValueError("source kind is outside the checkpoint/full-shadow whitelist")
        if not isinstance(triples, list) or not triples:
            raise ValueError("current triples must be a nonempty array")
        if any(not isinstance(t, (list, tuple)) or len(t) != 3 or
               any(type(mask) is not int or not 0 <= mask < 1 << 25 for mask in t) for t in triples):
            raise ValueError("every source factor must be an exact 25-bit integer mask")
        candidate = encode_candidate(triples, 5, auxiliary_source_kind=source["kind"])
        canonical, normalization = canonical_masks(candidate)
        key = digest(dict(field=2, dimension=5, full_coefficient_tuples=canonical))
        return candidate, raw, raw_sha, key, normalization
    except Exception as exc:
        raise SourceError(f"{type(exc).__name__}: {exc}", semantic_key, raw) from exc


def cpu_used():
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return time.process_time()+children.ru_utime+children.ru_stime


def cooldown(cpu_seconds, elapsed, interval, cycle_cpu_seconds):
    """Recover any quota overrun so the auxiliary average stays bounded."""
    fraction = min(0.025, cycle_cpu_seconds/interval)
    return max(0.0, max(interval, cpu_seconds/fraction)-elapsed)


def _worker(candidate, wall_seconds, cpu_seconds, sender):
    def budget(_signal, _frame):
        raise TimeoutError("auxiliary CPU quota reached")
    try:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGPROF, budget)
        signal.setitimer(signal.ITIMER_PROF, cpu_seconds)
        result = compress_candidate(candidate, seconds=wall_seconds, stop_at_record=True, max_active=109)
        signal.setitimer(signal.ITIMER_PROF, 0)
        sender.send(dict(status="VERIFIED", result=result))
    except TimeoutError as exc:
        signal.setitimer(signal.ITIMER_PROF, 0)
        sender.send(dict(status="CPU_BUDGET", reason=str(exc)))
    except Exception as exc:
        signal.setitimer(signal.ITIMER_PROF, 0)
        value = dict(status="ERROR", error=f"{type(exc).__name__}: {exc}")
        if isinstance(exc, InvalidCertificate) and exc.report is not None:
            value["input_verification"] = exc.report
        sender.send(value)
    finally:
        sender.close()


def run_case(candidate, *, wall_seconds, cpu_seconds, stop=lambda:False):
    if wall_seconds <= 0 or cpu_seconds <= 0:
        return dict(status="CPU_BUDGET", reason="no case budget remains", worker_reaped=True)
    context = mp.get_context("fork")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=_worker, args=(candidate, wall_seconds, cpu_seconds, sender))
    start, start_cpu = time.monotonic(), cpu_used()
    child.start()
    sender.close()
    result = dict(status="TIME_BUDGET", reason="per-case wall budget reached")
    try:
        while time.monotonic()-start < wall_seconds:
            if stop():
                result = dict(status="STOPPED", reason="watcher stopping")
                break
            if receiver.poll(min(0.02, max(0, wall_seconds-(time.monotonic()-start)))):
                try:
                    result = receiver.recv()
                except EOFError:
                    result = dict(status="ERROR", error="auxiliary child exited without a result")
                break
    finally:
        if child.is_alive():
            child.terminate()
        child.join(timeout=0.1)
        if child.is_alive():
            child.kill()
            child.join()
        receiver.close()
    result.update(cpu_seconds=cpu_used()-start_cpu, wall_seconds=time.monotonic()-start, worker_reaped=not child.is_alive())
    return result
