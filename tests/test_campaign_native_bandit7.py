"""Bounded tiny/native lifecycle controls and actual-source verification, no n5 search."""
import copy
import json
import os
from pathlib import Path
import random
import tempfile
import unittest
from unittest import mock
from scripts import campaign_native_bandit7 as b
from mmsearch.search import naive_terms

ROOT=Path(__file__).resolve().parents[1]
BINARY=Path(os.environ.get('BANDIT7_TEST_BINARY',ROOT/'artifacts/rl_campaign42_20261103T033116Z/plus-burst42-pilot-ready-v1/native/plus-burst-worker'))
FIXTURE=Path(os.environ.get('BANDIT7_TEST_SOURCE',ROOT/'tests/fixtures/native_campaign42_rank93.json'))

def state():
    return dict(schema='native-bandit7.checkpoint.v1',manifest_sha256='m',baseline_sha256='b',
        status='READY_NEXT_EPOCH',completed_epochs=0,counts=[0]*6,reward_sums=[0]*6,
        contexts={key:dict(counts=[0]*6,reward_sums=[0]*6) for key in ['cyclic_source','noncyclic_source']},
        accepted_hashes=[],observed_hashes=[],known_atoms=[],used_seeds=[],rng_state=json.loads(json.dumps(random.Random(17).getstate())))

def source():
    raw=FIXTURE.read_bytes();candidate=json.loads(raw);terms=b.p.safe.base.canonical_terms(candidate)
    record=dict(sha256=b.sha(raw),root_approved_train=True,heldout_evaluation_ancestors=False,parent_ids=[],parent_files=[],
        identity=dict(term_set_sha256=b.p.lifecycle.term_identity(candidate),rl_source_sha256=b.p.lifecycle.digest(sorted(terms))))
    return raw,record,terms

class BanditControls(unittest.TestCase):
    def test_contextual_policy_restart_exact_rng_and_exploration_fraction(self):
        s=state();sources={'0':{'cyclic_complete':True},'1':{'cyclic_complete':False}};choices=[]
        for epoch in range(8):
            b.validate_state(s,'m','b');choice=b.choose(s,sources)
            self.assertEqual(choice,b.choose(json.loads(json.dumps(s)),sources));choices.append(choice)
            arm=choice['arm'];s['completed_epochs']+=1;s['counts'][arm]+=1
            s['contexts'][choice['context']]['counts'][arm]+=1;s['rng_state']=choice['rng_state_after'];s['used_seeds'].append(choice['profile']['seed'])
        self.assertEqual(sum(x['exploration_reserved'] for x in choices),2)
        self.assertTrue(all(x['profile']['cyclic'] for x in choices if x['exploration_reserved']))
        self.assertEqual(len(set(s['used_seeds'])),8);self.assertTrue(all(x>=1<<62 for x in s['used_seeds']))
        with self.assertRaises(ValueError):b.choose(s,sources)
        s['counts'][0]+=1
        with self.assertRaises(ValueError):b.validate_state(s,'m','b')

    def test_production_command_exact180_and_no_hold_variant(self):
        p=dict(id='e',source_id=0,seed=1<<62,cyclic=False,plus_burst=4,reduction_dwell=128,plus_every=200000)
        argv=b.epoch_command('worker','input','walk',p)
        self.assertEqual(argv[argv.index('--seconds')+1],'180');self.assertNotIn('--dwell-hold-rank',argv)
        for seconds in [120,181,float('nan')]:
            with self.assertRaises(ValueError):b.epoch_command('w','i','o',p,seconds=seconds)

    def test_actual_initial_source_checks_and_ineligible_or_drifted_prechecks(self):
        raw,record,terms=source();answer=b.validate_source(raw,record,False,lambda _:True)
        self.assertEqual(answer[0],terms);self.assertEqual(answer[2]['exact_entries_checked'],15625)
        for changes in [dict(root_approved_train=False),dict(heldout_evaluation_ancestors=True),dict(parent_ids=['unknown']),dict(sha256='0'*64)]:
            with mock.patch.object(b.p.safe,'verify_candidate',side_effect=AssertionError('no verification for ineligible input')):
                with self.assertRaises(ValueError):b.validate_source(raw,{**record,**changes},False,lambda _:True)
        with self.assertRaises(b.p.OutputHold):b.validate_source(raw,record,False,lambda _:False)

    def test_reward_only_full_doubleverified_new_states_and_atoms(self):
        raw,record,terms=source();digest=b.p.safe.base.term_set_sha256(terms);text=''.join(f'{a} {v} {w}\n' for a,v,w in terms).encode()
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);b.p.safe.base.freeze(output/'.raw-native-returns'/(digest+'.txt'),text)
            summary=dict(raw_exports={digest:dict(rank=93,raw_sha256=b.sha(text))})
            reward=b.sample_rewards(summary,output,state(),{'known_hashes':[]},lambda _:True)
            self.assertEqual(reward['doubleverified_samples'],1);self.assertEqual(reward['new_atom_count'],93)
            self.assertGreater(reward['reward'],0);self.assertFalse((output/'records').exists())
            frozen=b.sample_rewards(summary,output,state(),{'known_hashes':[digest]},lambda _:True)
            self.assertEqual(frozen['reward'],0);self.assertEqual(frozen['doubleverified_samples'],0)
            observed=state();observed['observed_hashes']=[digest]
            revisited=b.sample_rewards(summary,output,observed,{'known_hashes':[]},lambda _:True)
            self.assertEqual(revisited['reward'],0);self.assertEqual(revisited['doubleverified_samples'],0)
            with self.assertRaises(ValueError):b.sample_rewards(summary,output,state(),{'known_hashes':[]},lambda _:True,cap=33)

    def test_late_reward_cannot_update_policy_or_publish_sample(self):
        raw,record,terms=source();digest=b.p.safe.base.term_set_sha256(terms);text=''.join(f'{a} {v} {w}\n' for a,v,w in terms).encode()
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);b.p.safe.base.freeze(output/'.raw-native-returns'/(digest+'.txt'),text)
            summary=dict(raw_exports={digest:dict(rank=93,raw_sha256=b.sha(text))})
            with self.assertRaises(b.p.OutputHold):b.sample_rewards(summary,output,state(),{'known_hashes':[]},lambda phase:phase!='post_reward_independent')
            self.assertFalse((output/'.reward-samples').exists());self.assertFalse((output/'checkpoint.json').exists())

    def test_timeout_unknown_error_and_incomplete_verification_stop(self):
        good=dict(execution=dict(exit_code=0,timed_out=False,interrupted=False),stats=dict(stopped_by_signal=False,seconds_budget=180,elapsed_seconds=180,target_reached=False),final_checks_complete=True,eligible_target_emitted=False)
        self.assertTrue(b.completed_native(good))
        for change in [dict(exit_code=-15),dict(timed_out=True),dict(interrupted=True)]:
            self.assertFalse(b.completed_native({**good,'execution':{**good['execution'],**change}}))
        self.assertFalse(b.completed_native({**good,'stats':None}));self.assertFalse(b.completed_native({**good,'final_checks_complete':False}))
        for change in [dict(stopped_by_signal=True),dict(elapsed_seconds=20),dict(seconds_budget=30),dict(target_reached=True)]:
            self.assertFalse(b.completed_native({**good,'stats':{**good['stats'],**change}}))

    def test_checkpoint_late_rollback_preserves_raw_and_frozen_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)
            with self.assertRaises(b.p.OutputHold):b.publish_checkpoint(output,state(),lambda phase:phase!='post_checkpoint_handoff')
            self.assertFalse((output/'checkpoint.json').exists());self.assertTrue((output/'.checkpoint.late.raw').exists())
            with self.assertRaises(ValueError):b.read_pin(output/'.checkpoint.late.raw','0'*64)

    def test_budget_reserve_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);budget=b.Budget(root,root/'bundle',root/'native-bandit7-e01')
            with mock.patch.object(b.p.SpaceBudget,'size',return_value=28*b.MIB):
                with self.assertRaises(b.p.OutputHold):budget.check()

    def test_force_scan_and_exact_pending_bytes_bypass_halfsecond_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);budget=b.Budget(root,root/'bundle',root/'native-bandit7-e01');size=[0]
            with mock.patch.object(b.p.SpaceBudget,'size',side_effect=lambda path:size[0] if path==budget.current else 0):
                budget.check();size[0]=29*b.MIB
                budget.check() # loop coalescing is allowed, non-loop barriers force.
                with self.assertRaises(b.p.OutputHold):budget.check(force=True)
                size[0]=0
                with self.assertRaises(b.p.OutputHold):budget.check(pending_bytes=31*b.MIB)
                with self.assertRaises(ValueError):budget.check(pending_bytes=-1)

    def test_exact_checkpoint_reservation_prevents_even_hidden_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            fresh=lambda _:True
            fresh.reserve=lambda barrier,size:False
            with self.assertRaises(b.p.OutputHold):b.publish_checkpoint(Path(tmp),state(),fresh)
            self.assertEqual(list(Path(tmp).iterdir()),[])

    def test_real_tiny_early_record_and_late_raw_gate(self):
        profile=dict(id='tiny',source_id=0,seed=3,cyclic=False,plus_burst=1,reduction_dwell=0,plus_every=20000)
        with tempfile.TemporaryDirectory() as tmp,mock.patch.object(b.p,'command',b.epoch_command):
            result=b.p.execute(BINARY,naive_terms(2),Path(tmp),lambda _:True,profile,seconds=2,n=2,target=7,steps=200000)
            self.assertEqual(result['execution']['exit_code'],0);self.assertTrue(result['eligible_target_emitted'])
            self.assertTrue(list((Path(tmp)/'records').glob('*.json')));self.assertFalse((Path(tmp)/'WINNER.json').exists())
        with tempfile.TemporaryDirectory() as tmp,mock.patch.object(b.p,'command',b.epoch_command):
            result=b.p.execute(BINARY,naive_terms(2),Path(tmp),lambda phase:phase!='post_target_strict_independent',profile,seconds=2,n=2,target=7,steps=200000)
            self.assertFalse(result['eligible_target_emitted']);self.assertFalse((Path(tmp)/'records').exists())
            self.assertTrue(list((Path(tmp)/'.raw-native-returns').glob('*.candidate.raw')))

if __name__=='__main__':unittest.main()
