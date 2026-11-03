"""Coalesce inner decoder filesystem polling; never coalesce clocks or barriers."""
import math
from .local_guard43 import CampaignHold


class CancelPoller:
    """Only for decoder cancelled(); callers keep forced pre/post guard checks.

    Filesystem observations are at most50ms apart while callbacks continue.
    Signals, UTC, invocation wall time and the current case deadline are checked
    on every callback, before and after any filesystem work. A cached clear
    filesystem observation never authorizes a completed result or publication.
    """
    def __init__(self,guard,case_deadline=lambda:None,interval=.05):
        if type(interval) not in (int,float) or not math.isfinite(interval) or not 0<interval<=.05:raise ValueError('inner poll interval must be positive and<=50ms')
        self.guard=guard;self.case_deadline=case_deadline;self.interval=interval
        self.next_poll=-float('inf');self.last_global_reason=None
        self.calls=0;self.filesystem_polls=0

    def _time_reason(self):
        guard=self.guard
        if guard.signal_stop:return 'stop signal'
        if guard.utc_clock()>=guard.deadline:return 'absolute campaign deadline'
        now=guard.monotonic()
        if now-guard.started>=guard.seconds:return 'invocation wall cutoff'
        deadline=self.case_deadline()
        if deadline is not None and now>=deadline:return 'per-case wall cutoff'
        return None

    def reason(self):
        self.calls+=1;reason=self._time_reason()
        if reason:return reason
        now=self.guard.monotonic()
        if now>=self.next_poll:
            # Schedule from the start of the observation, not its completion.
            self.next_poll=now+self.interval;self.filesystem_polls+=1
            self.last_global_reason=self.guard.reason(force=False)
        return self._time_reason() or self.last_global_reason

    def cancelled(self):return self.reason() is not None

    def force_check(self,barrier):
        """Explicit fresh barrier; never consult or trust the cached observation."""
        self.guard.check(barrier)
        reason=self._time_reason()
        if reason:raise CampaignHold(reason,barrier)

    def metrics(self):return dict(inner_callbacks=self.calls,filesystem_polls=self.filesystem_polls,interval_seconds=self.interval)
