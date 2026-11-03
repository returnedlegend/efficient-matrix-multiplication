import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.collect_operator44_pilots import budget_status, policy_checks, event_summary, encoded, native_summary


class CollectorTests(unittest.TestCase):
    def test_clean_exit_below_cpu_target_is_unknown_and_failure_never_complete(self):
        clean = {'exit_code':0,'timed_out':False,'interrupted':False}
        self.assertEqual(budget_status(clean, 449.9), 'UNKNOWN_WALL_CENSORED_CPU_TARGET_NOT_MET')
        self.assertEqual(budget_status(clean, 451.5), 'CPU_TARGET_COMPLETED')
        self.assertEqual(budget_status({**clean,'timed_out':True}, 451.5), 'INTERRUPTED_OR_FAILED')
        self.assertEqual(budget_status(None, 20), 'PENDING_OR_RUNNING')

    def test_Adam_only_control_mutation_is_detected_even_with_same_weights_counter(self):
        policy = {'params':{'W':[1.]},'m':{'W':[.1]},'s':{'W':[.01]},'updates':4,'hidden':32,'entropy':.015,'learning_rate':.001}
        changed = copy.deepcopy(policy); changed['m']['W'][0] = .2
        self.assertFalse(policy_checks(policy, changed, 'frozen')['full_policy_Adam_scalars_counters_unchanged'])
        changed = copy.deepcopy(policy); changed['updates'] += 1
        self.assertFalse(policy_checks(policy, changed, False)['weights_changed'])

    def test_new_recovery_episode_without_inherited_debt_is_detected(self):
        initial = {'operator44':{},'finetune43':{'clock':{'record_origin':0,'recovery_origin':0,'recovery_fraction':.05}},
                   'context':{'ledger':{'cap':25}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'events.jsonl'
            path.write_text(json.dumps({'event':'recovery_start','training_split':'train','record_cpu':100,'recovery_cpu':20})+'\n')
            report = event_summary(path, initial, {'record_cpu':100,'recovery_cpu':20}, None)
            self.assertTrue(any('without inherited CPU debt' in x for x in report['errors']))

    def test_accepted_six_cap_and_internal_eight_cap_are_distinct(self):
        profile = {'cyclic':False,'rank_headroom':8,'plus_burst':4,'reduction_dwell':128,'plus_every':100,'restart_every':200000}
        record = {'action':'native_explore','task_kind':'RECORD_SEARCH','attempted_moves':50}
        manifest = {'action_parameters':profile,'binary_sha256':'binary','source_sha256':'source','max_rank':107,
                    'code_sha256':{'native_bridge44.py':'bridge'},'target_rank':92}
        stats = {'max_rank':107,'max_visited_rank':106,'steps':50,'cyclic':False,'plus_burst':4,
                 'reduction_dwell':128,'plus_every':100,'restart_every':200000,'target_rank':92}
        binding = {'profiles':{'explore':profile},'binary_sha256':'binary','source_sha256':'source','bridge_sha256':'bridge'}
        self.assertTrue(all(native_summary(record,manifest,stats,binding,99)['checks'].values()))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'events.jsonl';path.write_text(json.dumps({'event':'transition','action':'native_explore','rank':100,'best_rank':93})+'\n')
            initial={'finetune43':{'clock':{'record_origin':0,'recovery_origin':0}},'context':{'ledger':{'cap':25}}}
            self.assertTrue(any('best+6 cap' in e for e in event_summary(path, initial, {'record_cpu':0,'recovery_cpu':0}, None)['errors']))


if __name__=='__main__': unittest.main()
