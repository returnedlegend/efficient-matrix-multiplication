import copy
import hashlib
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest import mock

from mmsearch.native_bridge44 import NativeBridge, ACTION_PROFILES, AUDITED_BINARY_SHA256
from mmsearch.rl_finetune43 import Finetune43Controller
from mmsearch.rl_finetune44 import (Finetune44Controller, migrate_payloads, raw,
                                   read_schedule, phase_usage, recovery_due, freeze_record44)
from mmsearch.rl_restart_curriculum import RecordSeeds
from mmsearch.rl_curriculum import ContextController, ContextDmEnv
from mmsearch.rl_pool_curriculum import FixedStepBridge
from mmsearch.rl_search import TinyActorCritic
from mmsearch.search import naive_terms, encode_candidate

ROOT = Path(__file__).resolve().parents[1]


def audited_binary():
    options = [ROOT/'native/flip_worker_plus_burst42',
               ROOT/'artifacts/rl_campaign42_20261103T033116Z/plus-burst42-ready-v1/native/plus-burst-worker']
    return next(p for p in options if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == AUDITED_BINARY_SHA256)


def fixture(root):
    seed = root/'seed.json'; seed.write_bytes(raw(encode_candidate(naive_terms(2), 2)))
    agent = Finetune43Controller(naive_terms(2), n=2, target_rank=1, seed=33, rollout=5)
    agent.bind_restarts(RecordSeeds([seed], n=2, known_rank=8), interval=300, record_cpu=12)
    agent.restart_if_due(12)
    for _ in range(7): agent.step(0, cost_seconds=0)
    agent.finetune_context = {'clock': {'phase_id': 'finetune43-v1', 'record_origin': 12.,
        'recovery_origin': 3., 'recovery_fraction': .05, 'episode_origin': 2, 'delayed_origin': 0},
        'curriculum_sha256': 'fixture', 'parent_checkpoint_sha256': 'older-parent'}
    agent.pool_context = {'pool_sha256': 'fixture', 'recovery_step_limit': 50000,
                          'recovery_max_actions': 4, 'record_bridge': {'archive_size': 8},
                          'recovery_bridge': {'archive_size': 1}}
    path = root/'parent.json'; agent.save(path); parent = path.read_bytes()
    schedule = {'format': 'mmsearch-finetune-schedule-v43', 'checkpoint_sha256': hashlib.sha256(parent).hexdigest(),
                'restart_context': agent.restart_context, 'finetune43': agent.finetune_context,
                'pool_context': agent.pool_context, 'record_cpu': 20., 'recovery_cpu': 4.,
                'recovery_episodes': 7, 'delayed_used': 1, 'recovery_successes': 3,
                'rng': random.Random(919).getstate(), 'recovery_fraction': .05}
    return agent, parent, raw(schedule)


def fork(root):
    old, parent, schedule = fixture(root)
    bridge = NativeBridge(root/'native', binary=audited_binary())
    qpath = root/'old-pending.json'
    child, sidecar, quarantine = migrate_payloads(parent, schedule, bridge.operator_binding, qpath, dimension=2)
    qpath.write_bytes(raw(quarantine)); path = root/'child.json'; path.write_bytes(raw(child))
    path.with_suffix('.schedule.json').write_bytes(raw(sidecar))
    return old, bridge, parent, schedule, path


class Operator44Tests(unittest.TestCase):
    def test_quarantine_preserves_all_numeric_state_without_credit_or_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); old, bridge, before, old_schedule, path = fork(root)
            value = json.loads(path.read_bytes()); side = read_schedule(path)
            original = json.loads(before); old_side = json.loads(old_schedule)
            self.assertTrue(original['pending']); self.assertEqual(value['pending'], [])
            self.assertEqual(json.loads((root/'old-pending.json').read_bytes())['samples'], original['pending'])
            for key in ('policy', 'rng', 'state', 'current', 'best', 'archive', 'seen', 'context', 'restart_curriculum', 'finetune43'):
                self.assertEqual(value[key], original[key], key)
            for key in ('record_cpu', 'recovery_cpu', 'rng', 'finetune43', 'restart_context', 'recovery_episodes', 'delayed_used'):
                self.assertEqual(side[key], old_side[key], key)
            resumed = Finetune44Controller.load(path, native_bridge=bridge)
            self.assertEqual(resumed.policy.state(), old.policy.state())
            self.assertEqual(resumed.rng.getstate(), old.rng.getstate())
            self.assertEqual(resumed.ledger.state(), old.ledger.state())
            self.assertEqual((root/'parent.json').read_bytes(), before)

    def test_allocation_clock_keeps_existing_debt_no_extra_auxiliary_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, old_schedule, path = fork(Path(tmp)); old = json.loads(old_schedule); new = read_schedule(path)
            for record, recovery in [(20, 4), (20, 3.1), (60, 4), (100, 10)]:
                self.assertEqual(phase_usage(old['finetune43']['clock'], record, recovery), phase_usage(new['finetune43']['clock'], record, recovery))
                self.assertEqual(recovery_due(old['finetune43']['clock'], record, recovery), recovery_due(new['finetune43']['clock'], record, recovery))
            self.assertFalse(recovery_due(new['finetune43']['clock'], new['record_cpu'], new['recovery_cpu']))

    def test_real_gradient_and_resume_preserve_actor_adam_rng_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, bridge, _, _, path = fork(root)
            agent = Finetune44Controller.load(path, native_bridge=bridge)
            for _ in range(3): agent.step(0, cost_seconds=0)
            saved = root/'resumed.json'; agent.save(saved)
            restored = Finetune44Controller.load(saved, native_bridge=bridge)
            before = agent.policy.state()
            for _ in range(12): self.assertEqual(agent.step(0, cost_seconds=0), restored.step(0, cost_seconds=0))
            self.assertEqual(agent.policy.state(), restored.policy.state())
            self.assertEqual(agent.rng.getstate(), restored.rng.getstate())
            self.assertGreater(agent.policy.updates, before['updates'])
            self.assertNotEqual(agent.policy.state()['params'], before['params'])
            self.assertNotEqual(agent.policy.state()['m'], before['m'])

    def test_frozen_and_random_controls_keep_weights_adam_and_counters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, bridge, _, _, path = fork(root)
            for mode in ('policy', 'random'):
                agent = Finetune44Controller.load(path, native_bridge=bridge); agent.train = False; agent.control = mode
                before = copy.deepcopy(agent.policy.state())
                for _ in range(11): agent.step(0, cost_seconds=0)
                agent._learn(); self.assertEqual(agent.policy.state(), before)

    def test_mismatched_parent_schedule_runtime_profile_and_quarantine_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, bridge, parent, schedule, path = fork(root)
            original_child = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                migrate_payloads(parent+b' ', schedule, bridge.operator_binding, root/'q', dimension=2)
            value = json.loads(path.read_bytes()); value['operator44']['binding']['profiles']['explore']['plus_burst'] = 3
            path.write_bytes(raw(value))
            with self.assertRaisesRegex(ValueError, 'binding changed'): Finetune44Controller.load(path, native_bridge=bridge)
            path.write_bytes(original_child)
            (root/'old-pending.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'quarantine checksum'): read_schedule(path)

    def test_actual_dm_env_new_profiles_exact_commands_caps_and_C3(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); bridge = NativeBridge(root/'native', binary=audited_binary(), archive_size=1)
            for index, name in enumerate(('exploit', 'explore', 'long_walk', 'cyclic'), 10):
                controller = ContextController(naive_terms(2), n=2, target_rank=1, record_rank=1,
                    native_bridge=FixedStepBridge(bridge, 2000), native_only=True, train=False, seed=100+index)
                environment = ContextDmEnv(lambda: controller); environment.reset(); step = environment.step(index)
                self.assertEqual(len(controller.features()), 20); self.assertEqual(len(controller.mask()), 14)
                result = controller.last_native; manifest = json.loads((Path(result['run_dir'])/'manifest.json').read_text()); command = manifest['command']
                profile = ACTION_PROFILES[name]
                self.assertEqual(command[command.index('--plus-burst')+1], str(profile.plus_burst))
                self.assertEqual(command[command.index('--reduction-dwell')+1], str(profile.reduction_dwell))
                self.assertEqual(manifest['max_rank'], 8+profile.rank_headroom)
                self.assertEqual(result['stats']['cyclic'], name == 'cyclic')
                self.assertEqual(step.observation.shape, (20,)); self.assertFalse(controller.train)

    def test_known_n2_eight_to_seven_and_false_n5_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); bridge = NativeBridge(root/'native', binary=audited_binary(), archive_size=1)
            result = bridge.run(encode_candidate(naive_terms(2), 2), action='explore', seed=3, target_rank=7, step_limit=200000)
            self.assertEqual(result['best_rank'], 7)
            with self.assertRaisesRegex(ValueError, 'complete tensor'):
                freeze_record44(root/'false-record', encode_candidate([(1,1,1)], 5))
            with mock.patch('mmsearch.verify.verify_candidate', return_value={'valid': True, 'exact_entries_checked': 15625}):
                with self.assertRaisesRegex(ValueError, 'second independent'):
                    freeze_record44(root/'false-record', encode_candidate([(1,1,1)], 5))
            self.assertFalse((root/'false-record/WINNER.json').exists())


if __name__ == '__main__': unittest.main()
