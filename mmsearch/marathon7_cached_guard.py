"""Separate campaign-guard prototype: cache parsing, never live stop authority.

No integration with frozen runners is performed here. Every call checks live
file signatures, clocks, markers, process liveness, heartbeat age and storage.
"""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import stat
import time

from .local_guard43 import CampaignHold

DEADLINE = "2026-11-03T19:24:17Z"
HARD_DEADLINE = datetime.fromisoformat(DEADLINE.replace("Z", "+00:00")).timestamp()


def _stat_key(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


class StableJsonCache:
    """Reuse a parse only while both link and followed-file signatures match.

    Stat and reads follow the existing guard's symlink policy. A target must be
    a regular file. Changes during open/read/parse/stat are retried finitely;
    an unstable or invalid input never falls back to its previous cached value.
    """
    def __init__(self, attempts=3):
        if type(attempts) is not int or not 1 <= attempts <= 3:
            raise ValueError("stable-read attempts must be1..3")
        self.attempts = attempts
        self._entries = {}
        self._counts = dict(signature_checks=0, parses=0, hits=0, reads=0, retries=0)

    def _signature(self, path):
        self._counts["signature_checks"] += 1
        link = path.lstat()
        target = path.stat()
        if not stat.S_ISREG(target.st_mode):
            raise ValueError("guard JSON target is not a regular file")
        return _stat_key(link), _stat_key(target)

    def load(self, path):
        path = Path(os.path.abspath(path))  # Do not resolve away a symlink.
        for _ in range(self.attempts):
            before = self._signature(path)
            cached = self._entries.get(path)
            if cached is not None and cached[0] == before:
                if self._signature(path) == before:
                    self._counts["hits"] += 1
                    return cached[1]
                self._counts["retries"] += 1
                continue
            self._counts["reads"] += 1
            with path.open("rb") as stream:
                opened = _stat_key(os.fstat(stream.fileno()))
                if opened != before[1]:
                    self._counts["retries"] += 1
                    continue
                raw = stream.read()
                after_read = _stat_key(os.fstat(stream.fileno()))
            if opened != after_read or self._signature(path) != before:
                self._counts["retries"] += 1
                continue
            value = json.loads(raw)
            self._counts["parses"] += 1
            if self._signature(path) != before:
                self._counts["retries"] += 1
                continue
            self._entries[path] = before, value
            return value
        raise OSError("guard JSON changed during bounded stable read")

    def metrics(self):
        return dict(self._counts, cached_paths=len(self._entries))


def _proc_stat(pid):
    return Path("/proc", str(pid), "stat").read_text().rsplit(")", 1)[1].split()


def _immediate_child_winner(root):
    """Inspect direct marker paths without enumerating any child contents."""
    with os.scandir(root) as entries:
        for entry in entries:
            if entry.is_dir(follow_symlinks=True) and (Path(entry.path) / "WINNER.json").exists():
                return True
    return False


class CachedResourceGuard:
    def __init__(self, path, cache, utc_clock, limit=5 * 1024**3, max_age=60):
        self.path = Path(path)
        self.limit = limit
        self.max_age = max_age
        self._cache = cache
        self._utc_clock = utc_clock

    def typed(self):
        """Typed resource snapshot and a fresh live process observation."""
        state = self._cache.load(self.path)
        if type(state) is not dict:
            return None, None, "invalid resource state type"
        stamp, identity = state["updated_utc"], state["process_identity"]
        if type(stamp) is not str or type(identity) is not dict:
            return None, None, "invalid resource identity type"
        updated = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if updated.tzinfo is None:
            return None, None, "resource timestamp requires timezone"
        if any(type(v) is not int or v <= 0 for v in (state["pid"], identity["start_ticks"])):
            return None, None, "invalid resource pid/start ticks"
        storage = state["campaign_allocated_bytes"]
        if type(storage) is not int or storage < 0:
            return None, None, "invalid resource storage type/value"
        tail = _proc_stat(state["pid"])
        if tail[0] in ("Z", "X"):
            return None, None, "resource process no longer live"
        return state, (updated.timestamp(), tail), None

    def check_snapshot(self, state, observation):
        updated, _ = observation
        # Process death/reuse can occur while canonical marker I/O runs.
        tail = _proc_stat(state["pid"])
        if tail[0] in ("Z", "X"):
            return "resource process no longer live"
        age = self._utc_clock() - updated
        if age < -5 or age > self.max_age:
            return "resource guard stale"
        if state.get("stop_reason"):
            return "resource guard stop: " + str(state["stop_reason"])
        if int(tail[19]) != state["process_identity"]["start_ticks"]:
            return "resource guard process identity changed"
        if state["campaign_allocated_bytes"] >= self.limit:
            return "resource guard working storage reached 5GiB"
        return None

    def check(self):
        try:
            state, observation, reason = self.typed()
            return reason or self.check_snapshot(state, observation)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError):
            return "resource guard unavailable or invalid"


class CampaignGuard:
    """Drop-in lifecycle API; force never skips stat or any critical check.

    The cache holds parsed data only, not stop decisions. Its authority remains
    current file identity/content plus current clock/process/marker observations.
    """
    def __init__(self, seconds, deadline_utc, stop_markers=(), guard_state=None,
                 monotonic=None, utc_clock=None, campaign_dir=None):
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("finite nonnegative invocation budget required")
        self.monotonic = monotonic or time.monotonic
        self.utc_clock = utc_clock or time.time
        self.started = self.monotonic()
        self.seconds = seconds
        parsed = datetime.fromisoformat(deadline_utc.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("absolute deadline timezone required")
        self.deadline = min(parsed.timestamp(), HARD_DEADLINE)
        self.deadline_utc = datetime.fromtimestamp(self.deadline, timezone.utc).isoformat()
        self.stop_markers = [Path(p).resolve() for p in stop_markers]
        self.campaign_dir = Path(campaign_dir).resolve() if campaign_dir else None
        self.cache = StableJsonCache()
        self.resources = CachedResourceGuard(guard_state, self.cache, self.utc_clock) if guard_state else None
        self.signal_stop = False

    def stop(self):
        self.signal_stop = True

    def _time_reason(self):
        if self.signal_stop:
            return "stop signal"
        if self.utc_clock() >= self.deadline:
            return "absolute campaign deadline"
        if self.monotonic() - self.started >= self.seconds:
            return "invocation wall cutoff"
        return None

    def reason(self, force=False):
        # A known cutoff must never require parsing a large JSON file first.
        timed = self._time_reason()
        if timed:
            return timed
        try:
            canonical = []
            if self.campaign_dir:
                for path in (self.campaign_dir / "queue_state.json",
                             self.campaign_dir / "operations-v3/state.json"):
                    if path.exists():
                        state = self.cache.load(path)
                        if type(state) is not dict:
                            return "invalid canonical state type"
                        canonical.append((path, state))
            resource_state = resource_observation = None
            if self.resources:
                resource_state, resource_observation, resource_reason = self.resources.typed()
                if resource_reason:
                    return resource_reason
            # Preserve the existing guard's type/liveness checks before markers.
            timed = self._time_reason()
            if timed:
                return timed
            for path in self.stop_markers:
                if path.exists():
                    return "stop marker: " + str(path)
            if self.campaign_dir:
                root = self.campaign_dir
                if (root / "guard_stopped.json").exists():
                    return "global guard_stopped marker"
                for path, state in canonical:
                    if state.get("stop_reason"):
                        return "global stop_reason: " + str(path)
                if (root / "WINNER.json").exists():
                    return "global WINNER marker"
                if _immediate_child_winner(root):
                    return "immediate-child WINNER marker"
            if self.resources:
                # Re-stat and validate after marker I/O as well. A resource
                # replacement during that I/O must not retain earlier authority.
                reason = self.resources.check()
                if reason:
                    return reason
            # Final canonical observation: marker/resource I/O may itself have
            # replaced a queue or operation state. Read each current version
            # once (cached parses still require fresh signatures) before allow.
            # This is a bounded observation point, not a transaction spanning
            # future writes to all independent campaign files.
            if self.campaign_dir:
                for path in (self.campaign_dir / "queue_state.json",
                             self.campaign_dir / "operations-v3/state.json"):
                    if path.exists():
                        state = self.cache.load(path)
                        if type(state) is not dict:
                            return "invalid canonical state type"
                        if state.get("stop_reason"):
                            return "global stop_reason: " + str(path)
            # I/O, stat, JSON parsing and proc reads can cross a cutoff.
            return self._time_reason()
        except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError):
            return "resource/canonical state unavailable or invalid"

    def check(self, barrier):
        reason = self.reason(force=True)
        if reason:
            raise CampaignHold(reason, barrier)

    def observation(self):
        return dict(deadline_utc=self.deadline_utc,
                    elapsed_seconds=self.monotonic() - self.started,
                    checked_utc=datetime.fromtimestamp(self.utc_clock(), timezone.utc).isoformat(),
                    json_cache=self.cache.metrics())
