import copy
import fcntl
import json
import os
from pathlib import Path
import signal
import unittest
from unittest import mock

from scripts import phase_coordinator42_v2 as v2
from scripts import phase_coordinator42_v3 as v3
from scripts import migrate_phase_coordinator42_v3 as migration
from tests import test_phase_coordinator42_v2 as fixtures


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True)+'\n');return migration.sha(path.read_bytes())


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.CoordinatorTests('test_preview_zero_writes_and_unarmed_default');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups);self.root=self.fixture.root
        self.new_plan=self.root/'plan-v3.json';self.new_gate=self.root/'ARMED-v3.json'
        self.launch=self.root/'v2-launch.json';self.new_code=Path(v3.__file__).resolve()

    def prepare(self):
        f=self.fixture;old=v2.Coordinator(f.plan_path,f.gate_path,now=lambda:f.now)
        old.root.mkdir(exist_ok=True)
        if not (old.root/'state.json').exists():v2.atomic(old.root/'state.json',old.state)
        if not (old.root/'supervisor.lock').exists():(old.root/'supervisor.lock').touch()
        plan=copy.deepcopy(f.plan);plan['format']='mmsearch-phase-plan-v3';write(self.new_plan,plan)
        write(self.launch,{'pid':2147483647,'start_ticks':123,'source_sha256':migration.sha(Path(v2.__file__).read_bytes()),
            'plan_sha256':migration.sha(f.plan_path.read_bytes()),'command':['python3',str(Path(v2.__file__).resolve()),'run',
                '--plan',str(f.plan_path),'--gate',str(f.gate_path)]})
        return migration.inspect(self.root,f.plan_path,f.gate_path,self.launch,self.new_plan,self.new_code,self.new_gate,
            expected_new_plan_sha=migration.sha(self.new_plan.read_bytes()),expected_new_code_sha=migration.sha(self.new_code.read_bytes()))

    def migrate(self):
        context=self.prepare();receipt=migration.apply(context)
        gate,_=migration.read(self.new_gate);gate['armed']=True;v2.atomic(self.new_gate,gate)
        return v3.Coordinator(self.new_plan,self.new_gate,now=lambda:self.fixture.now),receipt

    def fingerprints(self,directory):
        return {str(p.relative_to(directory)):(p.stat().st_mtime_ns,migration.sha(p.read_bytes()))
                for p in directory.rglob('*') if p.is_file()}

    def test_empty_roots_disappear_and_reappear_without_preview_writes(self):
        coordinator,_=self.migrate();before=self.fingerprints(self.root)
        self.assertEqual(coordinator.preview()['branches'][0]['status'],'NO_ELIGIBLE_NATIVE_ROOTS')
        self.assertEqual(before,self.fingerprints(self.root))
        runs=self.root/'learned/native/record/runs';(runs/'legitimate-active-run').mkdir()
        report=coordinator.preview();snapshot=report['actions'][0]['config_snapshot']
        self.assertEqual(snapshot['exact_runs_directories'],[str(runs)])
        self.assertFalse(snapshot['value']['discover_all_native'])
        (runs/'legitimate-active-run').rmdir()
        self.assertEqual(coordinator.preview()['branches'][0]['status'],'NO_ELIGIBLE_NATIVE_ROOTS')

    def test_hidden_files_and_symlink_runs_do_not_count_but_real_dirs_remain(self):
        coordinator,_=self.migrate();runs=self.root/'learned/native/record/runs'
        (runs/'.archived-hidden').mkdir();(runs/'worker.log').write_text('retained')
        (runs/'linked').symlink_to(runs/'.archived-hidden')
        self.assertFalse(v3.contains_real_runs(runs));self.assertEqual(coordinator.preview()['actions'],[])
        (runs/'normal-run').mkdir();self.assertTrue(v3.contains_real_runs(runs))
        self.assertEqual(coordinator.preview()['actions'][0]['config_snapshot']['exact_runs_directories'],[str(runs)])

    def test_root_ancestor_symlink_still_fails_closed(self):
        prior,old=self.fixture.prior();(self.root/'linked-root').symlink_to(old.parents[2])
        coordinator,_=self.migrate();report=coordinator.preview()
        self.assertEqual(report['actions'],[]);self.assertEqual(report['branches'][0]['status'],'PAUSED')
        self.assertIn('symlink',report['branches'][0]['reason'])

    def test_preview_migration_is_read_only_and_pending_intents_are_rejected(self):
        context=self.prepare();before=self.fingerprints(self.root)
        again=self.prepare();self.assertEqual(context['ledger_sha256'],again['ledger_sha256'])
        # prepare() only rewrites fixture review files; inspect itself is pure.
        before=self.fingerprints(self.root)
        migration.inspect(self.root,self.fixture.plan_path,self.fixture.gate_path,self.launch,self.new_plan,self.new_code,self.new_gate,
            expected_new_plan_sha=context['new_plan_sha256'],expected_new_code_sha=context['new_code_sha256'])
        self.assertEqual(before,self.fingerprints(self.root))
        state_path=self.root/'phase-coordinator42-v2/state.json';state,_=migration.read(state_path)
        for key,value in [('pending_action',{'job':{'id':'unresolved'}}),('held_actions',{'rl':{'job':{'id':'held'}}})]:
            modified=copy.deepcopy(state);modified[key]=value;v2.atomic(state_path,modified)
            with self.assertRaisesRegex(ValueError,'unresolved'):
                migration.inspect(self.root,self.fixture.plan_path,self.fixture.gate_path,self.launch,self.new_plan,self.new_code,self.new_gate,
                    expected_new_plan_sha=context['new_plan_sha256'],expected_new_code_sha=context['new_code_sha256'])
            with mock.patch.object(migration,'stop_v2') as stopper:
                with self.assertRaisesRegex(ValueError,'unresolved'):migration.apply(context,stopper=stopper)
                stopper.assert_not_called()
        self.assertFalse((self.root/'phase-coordinator42-v3').exists())

    def complete_stream(self,action,*,total,start,catalog):
        output=Path(action['outdir']);output.mkdir(exist_ok=True)
        write(output/'manifest.json',{'input_sha256':'input','catalog_sha256':catalog,'binary_sha256':'binary','start_row':start,'triples_total':total})
        write(output/'native_final_stats.json',{'input_sha256':'input','catalog_sha256':catalog,'next_row':total,
            'prefix_rows_skipped':start,'triples_considered':total-start,'triples_total':total})
        write(output/'summary.json',{'status':'NO_TARGET','coverage':{'prefix_completed':total,'next_row':total,'triples_total':total,
            'triples_completed_this_run':total-start,'contiguous_from_initial':True,'supplied_catalog_completed':True}})
        self.fixture.result(action['job']['id'])

    def test_full_history_migration_preserves_next_rl_parent_and_completed_stream(self):
        f=self.fixture;rl=f.setup_rl();rl_gate,_=v2.read(f.gate_path);stream=f.setup_stream()
        f.plan['branches']=[rl,stream];f.arm(['rl','stream'],rl_clearance=rl_gate['rl_clearance'])
        old=v2.Coordinator(f.plan_path,f.gate_path,now=lambda:f.now)
        rl_first=old.tick()['actions'][0];stream_first=old.tick()['actions'][0]
        self.complete_stream(stream_first,total=20,start=10,catalog='catalog1')
        stream_second=old.tick()['actions'][0];self.complete_stream(stream_second,total=30,start=0,catalog='catalog2')
        f.pair(Path(rl_first['outdir'])/'checkpoint.json',f.context);f.result(rl_first['job']['id'])
        (old.root/'supervisor.lock').touch()
        old_state,_=v2.read(old.root/'state.json');old_files=self.fingerprints(old.root)
        coordinator,receipt=self.migrate()
        self.assertEqual(old_files,self.fingerprints(old.root))
        self.assertEqual(coordinator.state['ledger'],old_state['ledger'])
        self.assertEqual(receipt['old_ledger_sha256'],receipt['new_ledger_sha256'])
        self.assertEqual(receipt['sequence_counts'],{'rl:learned':1,'stream:triples':2})
        self.assertEqual(migration.sha((coordinator.root/'migration-inputs/v2-state.json').read_bytes()),receipt['old_state_sha256'])
        report=coordinator.preview();action=report['actions'][0]
        self.assertEqual(action['job']['id'],'auto-learned-002')
        self.assertEqual(action['parents']['checkpoint'],str(Path(rl_first['outdir'])/'checkpoint.json'))
        self.assertEqual(next(b['status'] for b in report['branches'] if b['name']=='triples'),'SUPPLIED_TIERS_NO_TARGET_COMPLETE')
        coordinator.tick();queue,_=v2.queue_value(self.root/'queue.json')
        self.assertEqual([job['id'] for job in queue['jobs']],['auto-learned-001','auto-triple-001','auto-triple-002','auto-learned-002'])
        for before,after in zip(old_state['ledger'],coordinator.state['ledger']):
            self.assertEqual(before['job_sha256'],after['job_sha256']);self.assertEqual(before.get('expected_start_row'),after.get('expected_start_row'))
        restarted=v3.Coordinator(self.new_plan,self.new_gate,now=lambda:f.now)
        self.assertEqual(restarted.preview()['actions'],[])
        value,_=v2.read(coordinator.root/'state.json');value['ledger']=value['ledger'][1:];v2.atomic(coordinator.root/'state.json',value)
        with self.assertRaisesRegex(ValueError,'preserved V2'):
            v3.Coordinator(self.new_plan,self.new_gate,now=lambda:f.now)

    def test_plan_changes_and_unledgered_reserved_jobs_cannot_migrate(self):
        context=self.prepare();plan,_=migration.read(self.new_plan);plan['branches'][0]['phase_seconds']=999;write(self.new_plan,plan)
        with self.assertRaisesRegex(ValueError,'changes more than'):
            migration.inspect(self.root,self.fixture.plan_path,self.fixture.gate_path,self.launch,self.new_plan,self.new_code,self.new_gate,
                expected_new_plan_sha=migration.sha(self.new_plan.read_bytes()),expected_new_code_sha=context['new_code_sha256'])
        context=self.prepare();queue,_=v2.queue_value(self.root/'queue.json');queue['jobs'].append({'id':'auto-archive-001','cpu':3,'memory_mb':512,'seconds':300,'enabled':True,'command':['reviewed']});write(self.root/'queue.json',queue)
        with self.assertRaisesRegex(ValueError,'outside full ledger'):
            migration.inspect(self.root,self.fixture.plan_path,self.fixture.gate_path,self.launch,self.new_plan,self.new_code,self.new_gate,
                expected_new_plan_sha=context['new_plan_sha256'],expected_new_code_sha=context['new_code_sha256'])

    def test_pid_reuse_never_signals_and_pidfd_targets_only_v2(self):
        context=self.prepare();info={'pid':context['old_pid'],'start_ticks':context['old_start_ticks'],'argv':['python3',context['old_code_path'],'run',
            '--plan',context['old_plan_path'],'--gate',context['old_gate_path']]}
        with (mock.patch.object(migration,'process_info',return_value={**info,'start_ticks':999}),mock.patch.object(migration.os,'pidfd_open') as opener,
              mock.patch.object(migration.signal,'pidfd_send_signal') as sender):
            with self.assertRaisesRegex(ValueError,'PID reused'):migration.stop_v2(context)
            opener.assert_not_called();sender.assert_not_called()
        with (mock.patch.object(migration,'process_info',side_effect=[info,info,None]),mock.patch.object(migration.os,'pidfd_open',return_value=1234) as opener,
              mock.patch.object(migration.signal,'pidfd_send_signal') as sender,mock.patch.object(migration.os,'close') as closer,
              mock.patch.object(migration.os,'kill') as kill,mock.patch.object(migration.os,'killpg') as killpg):
            result=migration.stop_v2(context)
            opener.assert_called_once_with(context['old_pid'],0);sender.assert_called_once_with(1234,signal.SIGTERM,None,0)
            self.assertEqual(result['only_pid'],context['old_pid']);closer.assert_called_once_with(1234)
            kill.assert_not_called();killpg.assert_not_called()

    def test_v3_cannot_start_with_fresh_state_or_while_v2_lock_is_owned(self):
        context=self.prepare()
        with self.assertRaisesRegex(ValueError,'migrated V2 state'):
            v3.Coordinator(self.new_plan,self.new_gate,now=lambda:self.fixture.now)
        coordinator,_=self.migrate();legacy=self.root/'phase-coordinator42-v2/supervisor.lock'
        before=self.fingerprints(self.root)
        with legacy.open('r') as lock,mock.patch.object(v3.os,'sched_setaffinity'),mock.patch.object(v3.os,'nice'),mock.patch.object(v3.resource,'setrlimit'):
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):v3.main(['run','--plan',str(self.new_plan),'--gate',str(self.new_gate),'--once'])
        self.assertEqual(before,self.fingerprints(self.root))

    def test_virtual_migration_preview_preserves_history_without_writes(self):
        context=self.prepare();before=self.fingerprints(self.root)
        coordinator=v3.Coordinator(self.new_plan,self.new_gate,now=lambda:self.fixture.now,
            preview_state=self.root/'phase-coordinator42-v2/state.json',preview_gate=self.fixture.gate_path)
        report=coordinator.preview(['maintenance'])
        self.assertTrue(report['zero_mutations']);self.assertIn('virtual_migration_from_v2',report)
        self.assertEqual(before,self.fingerprints(self.root))
        with self.assertRaisesRegex(ValueError,'cannot write'):coordinator.tick()


if __name__=='__main__':unittest.main()
