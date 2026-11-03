import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from mmsearch.auxiliary_pair_watcher import (SourceError, cooldown, discover_sources,
    policy, read_source, run_case)
from mmsearch.pair_column_compression import compress_candidate
from mmsearch.recombine import canonical_terms, save
from mmsearch.tensor import naive_candidate, strassen_candidate
from scripts.watch_pair_compressions import process_sources


def checkpoint(candidate):
    return dict(config=dict(n=5), current=[list(t) for t in canonical_terms(candidate)], state=dict(step=1))


class AuxiliaryPairWatcherTests(unittest.TestCase):
    def test_discover_only_live_checkpoint_and_latest_full_global_shadows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            native = root/"native"
            for phase in ("phase-000", "phase-001"):
                for name in ("walk.current.txt", "walk.best.txt", "residual_walk.current.txt", "kernel_walk.w"):
                    path = native/phase/name;path.parent.mkdir(parents=True, exist_ok=True);path.write_text("1 1 1\n")
            save(root/"checkpoint.json", checkpoint(naive_candidate(5)))
            now = time.time()
            stamp = dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat()
            save(root/"active.running.json", dict(pid=123, started_utc=stamp,
                command=["python", "worker.py", "--checkpoint",str(root/"checkpoint.json"),"--output-dir",str(native)]))
            save(root/"dead.running.json", dict(pid=456,started_utc=stamp,command=["x","--checkpoint",str(root/"checkpoint.json")]))
            save(root/"verification.json", naive_candidate(5))
            identity = lambda pid:dict(started_unix=now,start_ticks=1) if pid == 123 else None
            sources, errors = discover_sources(root, root, identity)
            self.assertFalse(errors)
            self.assertEqual(len(sources), 3)
            self.assertTrue(any(s["kind"] == "checkpoint" for s in sources))
            self.assertTrue(all("phase-001" in s["path"] for s in sources if s["kind"] == "full-shadow"))
            self.assertFalse(any("residual" in s["path"] or "kernel_walk" in s["path"] or "verification" in s["path"] for s in sources))

    def test_full_term_cache_ignores_checkpoint_metadata_and_enforces_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/"checkpoint.json";value=checkpoint(naive_candidate(5));save(path,value)
            source=dict(path=str(path),kind="checkpoint")
            first=read_source(source)
            cache={};runner=Mock()
            result=process_sources([source],root/"out",cache,deadline=time.time()+5,runner=runner)
            self.assertEqual(result["processed"],1)
            self.assertEqual(result["events"][0]["status"],"SKIPPED")
            runner.assert_not_called()
            value["state"]["step"]=999;value["policy"]={"new":1};save(path,value)
            second=read_source(source)
            self.assertNotEqual(first[2],second[2])
            self.assertEqual(first[3],second[3])
            self.assertEqual(process_sources([source],root/"out",cache,deadline=time.time()+5,runner=runner)["processed"],0)

    def test_deadline_queue_stop_invalid_policy_and_cpu_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            future=dt.datetime.fromtimestamp(time.time()+100,dt.timezone.utc).isoformat()
            save(root/"campaign.json",dict(state="running",field=2,deadline_utc=future))
            self.assertIsNone(policy(root)[1])
            save(root/"queue_state.json",dict(format="mmsearch-queue-v1",jobs={},stop_reason="record found"))
            self.assertIn("queue stopped",policy(root)[1])
            save(root/"queue_state.json",{})
            self.assertEqual(policy(root)[1],"invalid queue state")
            runner=Mock()
            self.assertEqual(process_sources([{}],root,{},deadline=time.time()-1,runner=runner)["processed"],0)
            runner.assert_not_called()
        self.assertEqual(cooldown(0.5,1,10,0.25),19)
        self.assertEqual(cooldown(0.1,1,10,0.25),9)
        self.assertEqual(cooldown(0,11,10,0.25),0)

    def test_real_n2_generic_control_and_cpu_timer_cleanup(self):
        # Generic exact n2 control, never a dimension5 research record.
        result=run_case(naive_candidate(2),wall_seconds=1,cpu_seconds=0.2)
        self.assertEqual(result["status"],"VERIFIED")
        self.assertTrue(result["result"]["final_verification"]["valid"])
        self.assertEqual(result["result"]["final_verification"]["exact_entries_checked"],64)
        self.assertTrue(result["worker_reaped"])
        def busy(*_args,**_kwargs):
            while True:
                pass
        with patch("mmsearch.auxiliary_pair_watcher.compress_candidate",busy):
            limited=run_case(naive_candidate(2),wall_seconds=1,cpu_seconds=0.02)
        self.assertEqual(limited["status"],"CPU_BUDGET")
        self.assertTrue(limited["worker_reaped"])
        self.assertLess(limited["cpu_seconds"],0.15)

    def test_invalid_source_error_cached_until_factor_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/"checkpoint.json"
            value=dict(config=dict(n=5),current=[[1,1,1]],state=dict(step=1));save(path,value)
            source=dict(path=str(path),kind="checkpoint");cache={}
            result=process_sources([source],root/"out",cache,deadline=time.time()+5,cycle_cpu_seconds=0.2)
            self.assertEqual(result["events"][0]["status"],"ERROR")
            self.assertFalse(result["events"][0]["input_verification"]["valid"])
            value["state"]["step"]=2;save(path,value)
            self.assertEqual(process_sources([source],root/"out",cache,deadline=time.time()+5)["processed"],0)
            value["current"]=[[2,1,1]];save(path,value)
            self.assertEqual(process_sources([source],root/"out",cache,deadline=time.time()+5,cycle_cpu_seconds=0.2)["processed"],1)
            shadow=root/"walk.current.txt";shadow.write_text("4 4 4\n")
            shadow_result=process_sources([dict(path=str(shadow),kind="full-shadow")],root/"out",cache,
                deadline=time.time()+5,cycle_cpu_seconds=0.2)
            self.assertEqual(shadow_result["events"][0]["status"],"ERROR")
            self.assertFalse(shadow_result["events"][0]["input_verification"]["valid"])
            value["config"]["n"]=5.0;save(path,value)
            with self.assertRaises(SourceError):read_source(source)
            raw=root/"residual_walk.current.txt";raw.write_text("1 1 1\n")
            with self.assertRaises(SourceError):read_source(dict(path=str(raw),kind="full-shadow"))

    def test_first_winner_stops_before_second_hypothetical_n2_case(self):
        # Only eligibility is mocked. Both exact n2 examples are really
        # compressed and verified, and the existing freezer re-verifies them.
        first=naive_candidate(2);second=strassen_candidate(2)
        parsed=[(first,b"first",hashlib.sha256(b"first").hexdigest(),"first",dict(canonical_terms=8)),
                (second,b"second",hashlib.sha256(b"second").hexdigest(),"second",dict(canonical_terms=7))]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cache={}
            actual=Mock(wraps=run_case)
            with patch("scripts.watch_pair_compressions.read_source",side_effect=parsed):
                with patch("scripts.watch_pair_compressions._winner_eligible",return_value=True):
                    result=process_sources([dict(path="hypothetical1"),dict(path="hypothetical2")],root,cache,
                        deadline=time.time()+5,cycle_cpu_seconds=0.2,runner=actual)
            self.assertTrue(result["winner"])
            self.assertEqual(actual.call_count,1)
            self.assertEqual(result["processed"],1)
            self.assertEqual(len(cache),1)
            self.assertEqual(len(json.loads((root/"WINNER.json").read_bytes())["terms"]),8)
            self.assertTrue((root/"WINNER.sha256").exists())


if __name__ == "__main__":
    unittest.main()
