import ast
import copy
import inspect
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from mmsearch import auxiliary_pair_watcher as helper100
from mmsearch import auxiliary_pair_watcher_wide as helper109
from mmsearch.pair_column_compression import compress_candidate
from mmsearch.recombine import canonical_terms, encode
from mmsearch.verify import verify_candidate
from scripts import watch_pair_compressions_v2 as v2
from scripts import watch_pair_compressions_v3 as v3


def split_known93(count):
    """Exact nonnovel n5 fixture: split count U masks into unique pairs."""
    original=json.loads((Path(__file__).resolve().parents[1]/"artifacts/km93_f2.json").read_bytes())
    terms=list(canonical_terms(original));assert len(terms)==93
    occupied=set(terms)
    for u,v,w in terms[:count]:
        occupied.remove((u,v,w))
        for bit in range(25):
            d=1<<bit
            first,second=(d,v,w),(u^d,v,w)
            if u^d and first not in occupied and second not in occupied and first!=second:
                occupied.update((first,second));break
        else:raise AssertionError("could not construct a unique exact factor split")
    assert len(occupied)==93+count
    return encode(sorted(occupied),5,dict(fixture="known KM93 split-products regression only; not novel"))


def write_shadow(path,candidate):
    path.write_text("".join(" ".join(map(str,t))+"\n" for t in canonical_terms(candidate)))


class AuxiliaryWatcherV3Tests(unittest.TestCase):
    def test_cap_only_changes_and_v2_cadence_identical(self):
        for name in ("PolicyCache","cooldown_phase"):
            self.assertEqual(ast.dump(ast.parse(inspect.getsource(getattr(v2,name)))),
                             ast.dump(ast.parse(inspect.getsource(getattr(v3,name)))))
        self.assertEqual(ast.dump(ast.parse(inspect.getsource(helper100.run_case))),
                         ast.dump(ast.parse(inspect.getsource(helper109.run_case))))
        old=inspect.getsource(helper100._worker).replace("max_active=100","max_active=109")
        self.assertEqual(old,inspect.getsource(helper109._worker))
        old=inspect.getsource(v2.process_sources).replace("> 100","> 109").replace("than100","than109")
        self.assertEqual(old,inspect.getsource(v3.process_sources))

    def test_real_exact109_oldskip_newcompress93_with_measured_quota(self):
        source=split_known93(16)
        report=verify_candidate(source,random_trials=16)
        self.assertTrue(report["valid"])
        self.assertEqual(report["rank"],109)
        self.assertEqual(report["exact_entries_checked"],15625)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/"walk.current.txt";write_shadow(path,source)
            descriptor=dict(path=str(path),kind="full-shadow")
            unused=Mock()
            old=v2.process_sources([descriptor],root/"v2",{},deadline=time.time()+5,
                cycle_cpu_seconds=.25,runner=unused)
            self.assertEqual(old["events"][0]["status"],"SKIPPED")
            unused.assert_not_called()
            current=v3.process_sources([descriptor],root/"v3",{},deadline=time.time()+5,
                cycle_cpu_seconds=.25,per_case_seconds=1)
            event=current["events"][0]
            # Timeout is an honest budget outcome, never a silent cap skip.
            self.assertNotEqual(event["status"],"SKIPPED")
            if event["status"]=="VERIFIED":
                self.assertEqual(event["input_rank"],109)
                self.assertEqual(event["output_rank"],93)
                self.assertEqual(event["exact_entries_checked"],15625)
                self.assertFalse(current["winner"])
            else:
                self.assertIn(event["status"],("CPU_BUDGET","TIME_BUDGET"))
                self.assertTrue(event["worker_reaped"])
        # Unrestricted helper result establishes the mathematical reduction
        # even on a loaded host where the auxiliary hard wall may expire.
        before=time.process_time()
        result=compress_candidate(source,seconds=2,max_active=109,stop_at_record=True)
        elapsed_cpu=time.process_time()-before
        self.assertEqual(result["final_rank"],93)
        self.assertTrue(result["final_verification"]["valid"])
        self.assertEqual(result["final_verification"]["exact_entries_checked"],15625)
        self.assertLess(elapsed_cpu,1)

    def test110_cap_is_honest_skip_no_math_call_or_false_winner(self):
        source=split_known93(17)
        self.assertEqual(len(canonical_terms(source)),110)
        self.assertTrue(verify_candidate(source,random_trials=0)["valid"])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/"walk.current.txt";write_shadow(path,source)
            runner=Mock()
            result=v3.process_sources([dict(path=str(path),kind="full-shadow")],root/"out",{},
                deadline=time.time()+5,cycle_cpu_seconds=.25,runner=runner)
            runner.assert_not_called()
            self.assertEqual(result["events"][0]["status"],"SKIPPED")
            self.assertIn("109",result["events"][0]["reason"])
            self.assertFalse(result["winner"])

    def test109_worker_cpu_timeout_is_clean(self):
        def busy(*args,**kwargs):
            self.assertEqual(kwargs["max_active"],109)
            while True:pass
        with patch.object(helper109,"compress_candidate",busy):
            result=helper109.run_case(split_known93(16),wall_seconds=1,cpu_seconds=.01)
        self.assertEqual(result["status"],"CPU_BUDGET")
        self.assertTrue(result["worker_reaped"])


if __name__=="__main__":unittest.main()
