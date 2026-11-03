import unittest
from mmsearch.marathon7_cancel_poller import CancelPoller
from mmsearch.local_guard43 import CampaignHold


class FakeGuard:
    def __init__(self):
        self.now=0.;self.utc=100.;self.signal_stop=False;self.deadline=200.;self.seconds=10.;self.started=0.;self.polls=0;self.external=None;self.delay=0.
    def monotonic(self):return self.now
    def utc_clock(self):return self.utc
    def reason(self,force=False):self.polls+=1;self.now+=self.delay;return self.external
    def check(self,barrier):
        reason=self.reason(force=True)
        if reason:raise CampaignHold(reason,barrier)


class CancelPollerTests(unittest.TestCase):
    def test_global_stop_latency_at_most50ms(self):
        g=FakeGuard();poll=CancelPoller(g);self.assertFalse(poll.cancelled());self.assertEqual(g.polls,1)
        g.now=.001;g.external='global stop'
        for value in [.001,.010,.025,.049]:g.now=value;self.assertFalse(poll.cancelled())
        self.assertEqual(g.polls,1);g.now=.05;self.assertTrue(poll.cancelled());self.assertEqual(g.polls,2)

    def test_signal_case_utc_and_invocation_deadline_every_call(self):
        for kind in ['signal','case','utc','wall']:
            with self.subTest(kind=kind):
                g=FakeGuard();case=[1.];poll=CancelPoller(g,lambda:case[0]);self.assertFalse(poll.cancelled());g.now=.001
                if kind=='signal':g.signal_stop=True
                elif kind=='case':case[0]=.001
                elif kind=='utc':g.utc=g.deadline
                else:g.seconds=.001
                self.assertTrue(poll.cancelled());self.assertEqual(g.polls,1)

    def test_force_barrier_bypasses_cached_clear(self):
        g=FakeGuard();poll=CancelPoller(g);self.assertFalse(poll.cancelled());g.now=.001;g.external='new filesystem stop'
        with self.assertRaises(CampaignHold) as error:poll.force_check('post_solve')
        self.assertEqual(error.exception.barrier,'post_solve');self.assertEqual(g.polls,2)

    def test_late_filesystem_read_cannot_allow_expired_case(self):
        g=FakeGuard();g.delay=.02;poll=CancelPoller(g,lambda:.01)
        self.assertTrue(poll.cancelled());self.assertEqual(g.polls,1);self.assertEqual(poll.reason(),'per-case wall cutoff')

    def test_case_deadline_is_not_cached_across_cases(self):
        g=FakeGuard();case=[.001];poll=CancelPoller(g,lambda:case[0]);self.assertFalse(poll.cancelled());g.now=.001;self.assertTrue(poll.cancelled())
        case[0]=1.;self.assertFalse(poll.cancelled());self.assertEqual(g.polls,1)

    def test_filesystem_poll_schedule_uses_start_time(self):
        g=FakeGuard();g.delay=.02;poll=CancelPoller(g);self.assertFalse(poll.cancelled());self.assertEqual(poll.next_poll,.05)
        g.now=.049;self.assertFalse(poll.cancelled());g.now=.05;self.assertFalse(poll.cancelled());self.assertEqual(g.polls,2)

    def test_interval_validation(self):
        for interval in [0,-1,.051,float('nan'),float('inf'),True]:
            with self.assertRaises(ValueError):CancelPoller(FakeGuard(),interval=interval)


if __name__=='__main__':unittest.main()
