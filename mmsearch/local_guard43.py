"""Shared lifecycle barriers; a late return remains UNKNOWN and retains raw data."""
from datetime import datetime,timezone
from pathlib import Path
import json
import time
from .observed_rank3_lazy42 import FreshGuard


class CampaignHold(Exception):
    def __init__(self,reason,barrier):super().__init__(reason);self.reason=reason;self.barrier=barrier


class CampaignGuard:
    def __init__(self,seconds,deadline_utc,stop_markers=(),guard_state=None,monotonic=None,utc_clock=None,campaign_dir=None):
        self.monotonic=monotonic or time.monotonic;self.utc_clock=utc_clock or time.time;self.started=self.monotonic();self.seconds=seconds
        parsed=datetime.fromisoformat(deadline_utc.replace('Z','+00:00'))
        if parsed.tzinfo is None:raise ValueError('absolute deadline timezone required')
        self.deadline=parsed.timestamp();self.deadline_utc=parsed.astimezone(timezone.utc).isoformat();self.stop_markers=[Path(p).resolve() for p in stop_markers]
        self.resources=FreshGuard(guard_state) if guard_state else None;self.signal_stop=False
        self.campaign_dir=Path(campaign_dir).resolve() if campaign_dir else None;self._global_checked=-float('inf');self._global_reason=None
    def stop(self):self.signal_stop=True
    def _campaign_reason(self,force=False):
        if self.campaign_dir is None:return None
        now=self.monotonic()
        if not force and now-self._global_checked<.1:return self._global_reason
        self._global_checked=now;root=self.campaign_dir;reason=None
        try:
            if (root/'guard_stopped.json').exists():reason='global guard_stopped marker'
            for path in [root/'queue_state.json',root/'operations-v3/state.json']:
                if reason:break
                if path.exists():
                    state=json.loads(path.read_text())
                    if state.get('stop_reason'):reason='global stop_reason: '+str(path)
            if not reason:
                if (root/'WINNER.json').exists():reason='global WINNER marker'
                elif any(root.glob('*/WINNER.json')):reason='immediate-child WINNER marker'
        except (OSError,ValueError,TypeError):reason='global stop inputs unavailable or invalid'
        self._global_reason=reason;return reason
    def _time_reason(self):
        if self.signal_stop:return 'stop signal'
        if self.utc_clock()>=self.deadline:return 'absolute campaign deadline'
        if self.monotonic()-self.started>=self.seconds:return 'invocation wall cutoff'
        return None
    def reason(self,force=False):
        timed=self._time_reason()
        if timed:return timed
        for path in self.stop_markers:
            if path.exists():return 'stop marker: '+str(path)
        global_reason=self._campaign_reason(force)
        if global_reason:return global_reason
        if self.resources:
            resource_reason=self.resources.check()
            if resource_reason:return resource_reason
        # Global/resource reads can themselves cross a cutoff.
        return self._time_reason()
    def check(self,barrier):
        reason=self.reason(force=True)
        if reason:raise CampaignHold(reason,barrier)
    def observation(self):
        return dict(deadline_utc=self.deadline_utc,elapsed_seconds=self.monotonic()-self.started,
            checked_utc=datetime.fromtimestamp(self.utc_clock(),timezone.utc).isoformat())
