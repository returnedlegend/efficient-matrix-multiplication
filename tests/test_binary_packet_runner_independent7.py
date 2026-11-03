"""Final bridge controls; original pre-freeze leak remains archived in repro-v1."""
import contextlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import run_binary_block_packets7 as runner
from scripts.run_c3_mixed12_pilot7 import run_case
from mmsearch.marathon7_cached_guard import CampaignHold
from mmsearch.verify import verify_candidate
from tests.test_binary_packet_adapter7 import tiny
from tests.test_run_c3_mixed9_pilot7 import Guard


class BinaryPacketRunnerIndependentTests(unittest.TestCase):
    def test_actual_runtime_reuses_reviewed_guarded_publication(self):
        self.assertIs(runner.guarded_run_case,run_case)
        source,_,data,observation=tiny()
        class Cache:
            def core(self,_):
                return source,data,verify_candidate(source,random_trials=0),'sourcepin','corepin','rawcorepin'
        case=dict(id='bridge-tiny',source_indices=list(range(8)),target_local_products=7,free_axis=0)
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            result=runner.guarded_run_case(Cache(),case,out,Guard(),
                solver=lambda *_a,**_kw:dict(status='SAT',complete=True,products=observation['raw_compact']['products']),control_expected_rank=7)
            self.assertEqual(result['status'],'SMALL_CONTROL_PASSED',result)
            self.assertEqual(result['primary']['exact_entries_checked'],64)
            self.assertEqual(result['independent']['exact_entries_checked'],64)
            self.assertEqual(len(list((out/'records').glob('*.json'))),1)
            self.assertFalse((out/'WINNER.json').exists())

    def test_actual_lifecycle_late_solve_checks_and_publication_hide_all_records(self):
        source,_,data,observation=tiny()
        class Cache:
            def core(self,_):return source,data,verify_candidate(source,random_trials=0),'sourcepin','corepin','rawcorepin'
        case=dict(id='bridge-late',source_indices=list(range(8)),target_local_products=7,free_axis=0)
        for barrier in ('post_solve','post_lift_full','post_persisted_primary_full','post_strict_independent_full',
                        'pre_canonical_rename','post_eligible_publication','post_result_publication'):
            with self.subTest(barrier=barrier),tempfile.TemporaryDirectory() as directory:
                class Late(Guard):
                    def check(self,name):
                        if name==barrier:raise CampaignHold('independent cutoff',name)
                out=Path(directory)
                result=runner.guarded_run_case(Cache(),case,out,Late(),
                    solver=lambda *_a,**_kw:dict(status='SAT',complete=True,products=observation['raw_compact']['products']),control_expected_rank=7)
                self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete'])
                self.assertFalse(list((out/'records').glob('*.json')))
                self.assertFalse((out/(case['id']+'.result.json')).exists())
                self.assertTrue(list((out/'.raw-returns').glob('*.raw')))
                self.assertFalse((out/'WINNER.json').exists())

    def test_bridge_promotes_only_checked_exact_compact_and_uses_fixed_policy(self):
        products=[[1,1,1],[2,2,2]]+[[0,0,0] for _ in range(12)]
        core=[int(i in (0,133)) for i in range(1331)]
        cache=SimpleNamespace(current=dict(initial_factors=products))
        guard=SimpleNamespace(seconds=120,started=0,monotonic=lambda:1)
        solve=runner.controller_bridge(cache,guard,7)
        exact=dict(status='RAW_EXACT_COMPACT',raw_compact=dict(products=products),best_loss=0)
        with patch.object(runner,'run_controller',return_value=exact) as controller:
            result=solve(core,[11]*3,14,cancelled=lambda:False)
        self.assertEqual(result['status'],'SAT');self.assertEqual(result['products'],products)
        kwargs=controller.call_args.kwargs
        self.assertEqual(kwargs['mode'],'fixed');self.assertFalse(kwargs['training'])
        self.assertEqual(kwargs['source_product_count'],15);self.assertLessEqual(kwargs['timeout_seconds'],12)
        with patch.object(runner,'run_controller',return_value=dict(status='UNKNOWN',best_loss=0)):
            self.assertEqual(solve(core,[11]*3,14)['status'],'UNKNOWN')
        forged=dict(status='RAW_EXACT_COMPACT',raw_compact=dict(products=[[0,0,0]]*14),best_loss=0)
        with patch.object(runner,'run_controller',return_value=forged),self.assertRaises(ValueError):
            solve(core,[11]*3,14)

    def test_scope_gate_and_disabled_cli_do_not_dispatch(self):
        cache=SimpleNamespace(current=dict(initial_factors=[]))
        guard=SimpleNamespace(seconds=120,started=0,monotonic=lambda:1)
        solve=runner.controller_bridge(cache,guard)
        for shape,target in (([12]*3,14),([11]*3,13),([11,11,10],14)):
            with self.assertRaises(ValueError):solve([],shape,target)
        with patch.object(runner,'select_plan',side_effect=AssertionError('disabled read')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main([]),0)


if __name__=='__main__':unittest.main()
