import ast
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mmsearch.auxiliary_pair_watcher import cooldown
from mmsearch.recombine import save
from scripts import watch_pair_compressions as v1
from scripts import watch_pair_compressions_v2 as v2


class Clock:
    def __init__(self):
        self.wall=0.0;self.cpu=0.25;self.policy_calls=0;self.beats=0;self.sleeps=[]
    def overhead(self,seconds):
        self.cpu+=seconds;self.wall+=seconds
    def read_policy(self,_campaign):
        self.policy_calls+=1;self.overhead(.03)
        return 1000.0,None
    def heartbeat(self,_remaining):
        self.beats+=1;self.overhead(.01)
    def sleep(self,seconds):
        self.sleeps.append(seconds);self.wall+=seconds


class AuxiliaryWatcherV2Tests(unittest.TestCase):
    def test_policy_feedback_old_stalls_new_ten_second_chunks_recover(self):
        old=Clock();completed=False
        for _ in range(100):
            old.read_policy(None)
            remaining=cooldown(old.cpu,old.wall,10,.25)
            if remaining<=0:
                completed=True;break
            old.sleep(min(1,remaining))
        self.assertFalse(completed)
        current=Clock()
        cache=v2.PolicyCache(None,clock=lambda:current.wall,reader=current.read_policy,cpu=lambda:current.cpu)
        reason=v2.cooldown_phase(cycle_start=0,cycle_cpu=0,interval=10,quota=.25,
            deadline=1000,stop=lambda:False,check_policy=lambda:cache.get()[1],
            heartbeat=current.heartbeat,clock=lambda:current.wall,wall=lambda:current.wall,
            cpu=lambda:current.cpu,sleeper=current.sleep)
        self.assertIsNone(reason)
        self.assertLess(current.wall,15)
        self.assertEqual(current.policy_calls,2)
        self.assertEqual(current.beats,2)
        self.assertEqual(current.sleeps[0],10)
        self.assertLessEqual(current.cpu/current.wall,.025000001)

    def test_policy_cache_rate_limit_and_deadline_clipped_sleep(self):
        c=Clock();cache=v2.PolicyCache(None,clock=lambda:c.wall,reader=c.read_policy,cpu=lambda:c.cpu)
        for _ in range(100):cache.get()
        self.assertEqual(c.policy_calls,1)
        reason=v2.cooldown_phase(cycle_start=0,cycle_cpu=0,interval=10,quota=.25,
            deadline=2,stop=lambda:False,check_policy=lambda:cache.get()[1],
            heartbeat=c.heartbeat,clock=lambda:c.wall,wall=lambda:c.wall,cpu=lambda:c.cpu,sleeper=c.sleep)
        self.assertEqual(reason,"global deadline reached")
        self.assertAlmostEqual(c.wall,2)
        self.assertLessEqual(max(c.sleeps),2)
        c=Clock();cache=v2.PolicyCache(None,clock=lambda:c.wall,reader=c.read_policy,cpu=lambda:c.cpu)
        cache.get();c.wall=8;c.cpu=.5
        v2.cooldown_phase(cycle_start=0,cycle_cpu=0,interval=10,quota=.25,
            deadline=1000,stop=lambda:False,check_policy=lambda:cache.get()[1],
            heartbeat=c.heartbeat,clock=lambda:c.wall,wall=lambda:c.wall,cpu=lambda:c.cpu,sleeper=c.sleep,
            next_policy_due=lambda:cache.checked+10)
        self.assertAlmostEqual(c.sleeps[0],2.02)

    def test_stop_interrupts_wait_and_processing_semantics_unchanged(self):
        self.assertEqual(ast.dump(ast.parse(inspect.getsource(v1.process_sources))),
                         ast.dump(ast.parse(inspect.getsource(v2.process_sources))))
        c=Clock();stopped=[False]
        def sleep(seconds):
            c.sleep(seconds);stopped[0]=True
        reason=v2.cooldown_phase(cycle_start=0,cycle_cpu=0,interval=10,quota=.25,
            deadline=1000,stop=lambda:stopped[0],check_policy=lambda:None,
            heartbeat=c.heartbeat,clock=lambda:c.wall,wall=lambda:c.wall,cpu=lambda:c.cpu,sleeper=sleep)
        self.assertEqual(reason,"self stop requested")

    def test_v2_main_exits_at_deadline_without_launch_or_resource_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            save(root/"campaign.json",dict(state="running",field=2,deadline_utc="2000-01-01T00:00:00Z"))
            with patch.object(v2.os,"sched_setaffinity"),patch.object(v2.os,"sched_getaffinity",return_value={2}),patch.object(v2.resource,"setrlimit"),patch.object(v2.signal,"signal"):
                with patch.object(v2,"discover_sources") as discover:
                    self.assertEqual(v2.main(["--campaign",str(root)]),0)
                    discover.assert_not_called()
            status=json.loads((root/"auxiliary_pair_watcher.json").read_bytes())
            self.assertEqual(status["version"],2)
            self.assertEqual(status["state"],"stopped")
            self.assertEqual(status["stop_reason"],"global deadline reached")
            self.assertEqual(status["memory_mb"],512)
            self.assertEqual(status["policy_poll_seconds"],10)


if __name__=="__main__":unittest.main()
