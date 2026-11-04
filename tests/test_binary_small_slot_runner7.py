import contextlib
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import run_binary_small_slot_packets7 as subject
from scripts.run_c3_mixed12_pilot7 import run_case
from tests.test_binary_packet_adapter7 import tiny


class SmallSlotRunnerTests(unittest.TestCase):
    def test_selection_reproducible_distinct_bounded_stratified(self):
        chosen=subject.stratified_slots(41)
        self.assertEqual(chosen,subject.stratified_slots(41))
        self.assertEqual(chosen['population'],3003)
        self.assertEqual(len(chosen['slots']),600)
        self.assertEqual(len(set(map(tuple,chosen['slots']))),600)
        self.assertEqual(sum(chosen['quotas'].values()),600)
        self.assertEqual({min(s) for s in chosen['slots']},set(range(9)))
        self.assertNotEqual(chosen['slots'],subject.stratified_slots(42)['slots'])
        self.assertEqual(subject.stratified_slots(1,0)['slots'],[])

    def test_actual_joint_loss_one_escape_and_publication_reused(self):
        _,_,data,_=tiny();cache=SimpleNamespace(current=data,current_case='tiny')
        selection=dict(cases=[dict(id='tiny',slots=[list(range(6))])])
        result=subject.slot_bridge(cache,selection,allow_tiny=True)(data['core'],data['shape'],7)
        self.assertEqual(result['status'],'SAT',result)
        self.assertEqual(result['best_loss'],0)
        self.assertEqual(result['supported_decoder_calls'],1)
        self.assertIs(subject.guarded_run_case,run_case)

    def test_complete_child_negatives_never_become_whole_unsat_and_cache_reused(self):
        factors=[[1<<i,1<<i,1<<i] for i in range(7)]
        core=[0]*(7**3);core[0]=1
        cache=SimpleNamespace(current=dict(initial_factors=factors),current_case='tiny')
        selection=dict(cases=[dict(id='tiny',slots=[list(range(6))])]);proofs={}
        negative=dict(status='REPAIR_EXCLUDED',complete=True,case='exact_selected_residual_negative')
        with patch.object(subject.repair,'repair_slots',return_value=negative) as decode:
            solve=subject.slot_bridge(cache,selection,proofs,allow_tiny=True)
            first=solve(core,[7]*3,7);second=solve(core,[7]*3,7)
        self.assertEqual(decode.call_count,1)
        self.assertEqual(first['status'],'UNKNOWN');self.assertFalse(first['complete'])
        self.assertEqual(first['exact_decoder_exclusions'],1)
        self.assertEqual(second['negative_cache_hits'],1)
        self.assertTrue(second['negative_proofs'])

    def test_stopped_or_forged_raw_never_promotes(self):
        _,_,data,_=tiny();cache=SimpleNamespace(current=data,current_case='tiny')
        selection=dict(cases=[dict(id='tiny',slots=[list(range(6))])])
        solve=subject.slot_bridge(cache,selection,allow_tiny=True)
        stopped=solve(data['core'],data['shape'],7,cancelled=lambda:True)
        self.assertEqual(stopped['status'],'UNKNOWN');self.assertFalse(stopped['complete'])
        fake=dict(status='RAW_EXACT_COMPACT',complete=True,case='forged',factors=[[0,0,0]]*7)
        with patch.object(subject.repair,'repair_slots',return_value=fake),self.assertRaises(ValueError):
            solve(data['core'],data['shape'],7)

    def test_invalid_selection_and_disabled_cli(self):
        _,_,data,_=tiny();cache=SimpleNamespace(current=data,current_case='tiny')
        for subsets in ([[0,0,1,2,3,4]],[[0,1,2,3,4,7]],[[0,1,2,3,4,5]]*2):
            with self.assertRaises(ValueError):
                subject.slot_bridge(cache,dict(cases=[dict(id='tiny',slots=subsets)]),allow_tiny=True)(data['core'],data['shape'],7)
        with patch.object(subject,'select_plan',side_effect=AssertionError('disabled read')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(subject.main([]),0)

    def test_late_child_raw_is_retained_without_promotion(self):
        _,_,data,_=tiny();cache=SimpleNamespace(current=data,current_case='tiny')
        selection=dict(cases=[dict(id='tiny',slots=[list(range(6))])])
        actual=subject.repair.repair_slots;stopped=[False]
        def late(*args,**kwargs):
            value=actual(*args,**kwargs);stopped[0]=True;return value
        with patch.object(subject.repair,'repair_slots',late):
            result=subject.slot_bridge(cache,selection,allow_tiny=True)(data['core'],data['shape'],7,cancelled=lambda:stopped[0])
        self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete'])
        self.assertEqual(result['last_child_return']['status'],'RAW_EXACT_COMPACT')
        self.assertEqual(result['decoder_unknowns'],1)
        self.assertEqual(result['subset_results'][0]['status'],'UNKNOWN')


if __name__=='__main__':unittest.main()
