import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from scripts import campaign_operations_v3 as ops
from scripts import recovery_maintenance_v3 as maintenance
from scripts.rl_campaign_queue import process_identity


def policy(directory,deadline='2099-01-01T00:00:00+00:00'):
    (directory/'campaign.json').write_text(json.dumps({'dimension':5,'field':2,'max_cpu_cores':4,
        'max_ram_gib':8,'target_rank':92,'deadline_utc':deadline}))


def schoolbook():
    terms=[]
    for i in range(5):
        for j in range(5):
            for k in range(5):
                terms.append({a:[int(q==index) for q in range(25)]
                              for a,index in [('u',i*5+j),('v',j*5+k),('w',k*5+i)]})
    return {'dimension':5,'field':2,'terms':terms}


class GuardTests(unittest.TestCase):
    def test_planted_fake_n5_rank92_never_stops_or_freezes(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); policy(directory)
            planted=directory/'records/fake.json'; planted.parent.mkdir()
            planted.write_text(json.dumps({'dimension':5,'field':2,'terms':[[1,1,1]]*91}))
            guard=ops.Operations(directory)
            for _ in range(3): guard.scan(512)
            self.assertFalse((directory/'guard_stopped.json').exists())
            self.assertFalse((directory/'operations-record').exists())
            self.assertEqual(guard.state['last_record_check']['report']['exact_entries_checked'],15625)
            self.assertFalse(guard.state['last_record_check']['report']['valid'])

    def test_residual_rank_and_wrong_schema_rejected(self):
        for value in [{'dimension':5,'field':2,'best_rank':1},
                      {'dimension':True,'field':2,'terms':[]},
                      {'dimension':5,'field':2,'terms':[[True,1,1]]},
                      {'dimension':5,'field':2,'terms':[{'u':[0]*25,'v':[0]*25,'w':[False]*25}]}]:
            with self.assertRaises((ValueError,TypeError)): ops.canonical_candidate(value)

    def test_zero_and_duplicate_parity_normalization(self):
        result=ops.canonical_candidate({'dimension':5,'field':2,'terms':[[1,2,4],[1,2,4],[0,2,4],[2,4,8]]})
        self.assertEqual(len(result['terms']),1)

    def test_freezer_persists_full_verification_and_checksums(self):
        # The known125-product identity exercises freezer integrity. Production
        # only calls this with target92 after the strict eligibility check.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'record'; candidate=schoolbook()
            hashes=ops.freeze_record(root,candidate,'planted-schoolbook',b'original',target=125)
            report=json.loads((root/'WINNER.verification.json').read_text())
            self.assertTrue(report['valid']); self.assertEqual(report['exact_entries_checked'],15625)
            independent=json.loads((root/'WINNER.independent.verification.json').read_text())
            self.assertTrue(independent['valid']); self.assertEqual(independent['exact_entries_checked'],15625)
            self.assertTrue(hashes); self.assertFalse((root/'WINNER.json').stat().st_mode&0o222)
            self.assertEqual((root/'WINNER.source.raw').read_bytes(),b'original')
            self.assertFalse(ops.eligible_report(candidate,report))

    def test_pid_reuse_never_signals(self):
        killer=mock.Mock()
        self.assertFalse(ops.signal_group({'pid':os.getpid(),'start_ticks':-1},signal.SIGKILL,
            identity=lambda pid:{'start_ticks':1},killpg=killer))
        killer.assert_not_called()

    def test_owned_session_term_then_kill_and_stale_registration(self):
        process=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print("ready",flush=True); time.sleep(60)'],
            start_new_session=True,stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'ready')
            with tempfile.TemporaryDirectory() as tmp:
                directory=Path(tmp); policy(directory)
                ident=process_identity(process.pid)
                registration={'pid':process.pid,'started_utc':ops.utc(ident['started_unix'])}
                (directory/'owned.running.json').write_text(json.dumps(registration))
                groups=ops.registered_groups(directory); self.assertEqual(len(groups),1)
                guard=ops.Operations(directory)
                guard.stop('test-owned-session'); process.poll()
                self.assertIsNone(process.returncode)
                guard.state['kill_after']=0; guard.reap_stops()
                self.assertEqual(process.wait(timeout=2),-signal.SIGKILL)
                self.assertEqual(ops.registered_groups(directory),[])
        finally:
            if process.poll() is None: os.killpg(process.pid,signal.SIGKILL); process.wait()
            process.stdout.close()

    def test_global_deadline_and_restart_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); policy(directory,'2000-01-01T00:00:00+00:00')
            guard=ops.Operations(directory)
            guard.tick()
            self.assertEqual(guard.state['stop_reason'],'global campaign deadline reached')
            self.assertTrue((directory/'guard_stopped.json').exists())
            restarted=ops.Operations(directory)
            self.assertEqual(restarted.state['stop_reason'],guard.state['stop_reason'])

    def test_policy_cache_and_unchanged_candidate_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); policy(directory)
            (directory/'fake.json').write_text(json.dumps({'dimension':5,'field':2,'terms':[[1,2,3]]}))
            clock=[100.0]; guard=ops.Operations(directory,now=lambda:clock[0])
            with mock.patch.object(ops,'load_json',wraps=ops.load_json) as reader:
                guard.config_value(); guard.config_value()
                self.assertEqual(reader.call_count,1)
                clock[0]=111; guard.config_value(); self.assertEqual(reader.call_count,2)
            with mock.patch.object(ops,'verify_candidate',wraps=ops.verify_candidate) as verifier:
                for _ in range(4): guard.scan(512)
                self.assertEqual(verifier.call_count,1)

    def test_disk_reserve_and_campaign_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); policy(directory); guard=ops.Operations(directory)
            stat=mock.Mock(f_bavail=7*ops.GIB,f_frsize=1)
            with mock.patch.object(ops.os,'statvfs',return_value=stat):
                self.assertEqual(guard.disk_step(0),'filesystem free below 8GiB')
            guard.state['campaign_allocated_bytes']=8*ops.GIB
            stat.f_bavail=20*ops.GIB
            with mock.patch.object(ops.os,'statvfs',return_value=stat):
                self.assertEqual(guard.disk_step(0),'new campaign storage reached 8GiB')


class MaintenanceTests(unittest.TestCase):
    def test_bounded_phase_rotates_and_preserves_archive_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); policy(directory)
            roots=[directory/f'learned{x}/native/known-recovery/runs' for x in range(2)]
            for root in roots: root.mkdir(parents=True)
            archiver=mock.Mock(return_value={'runs':2,'removed_runs':2})
            config={'runs_directories':[str(x) for x in roots],'max_runs':1000,'minimum_age':60}
            for _ in range(2): maintenance.phase(directory,config,archiver=archiver,free_bytes=15*ops.GIB)
            self.assertEqual([call.args[0] for call in archiver.call_args_list],roots)
            self.assertEqual(archiver.call_args.kwargs,{'minimum_age':60,'max_runs':1000,'remove_after_verify':True,'record_rank':92})
            state=json.loads((directory/'recovery-maintenance-v3/state.json').read_text())
            self.assertEqual(state['total_runs_removed'],4)

    def test_no_archive_without_disk_scratch_or_after_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); policy(directory)
            source=directory/'native/known-recovery/runs'; source.mkdir(parents=True)
            archiver=mock.Mock(); config={'runs_directories':[str(source)]}
            result=maintenance.phase(directory,config,archiver=archiver,free_bytes=8*ops.GIB)
            self.assertEqual(result['status'],'insufficient_archive_scratch'); archiver.assert_not_called()
            policy(directory,'2000-01-01T00:00:00+00:00')
            self.assertEqual(maintenance.phase(directory,config,archiver=archiver)['status'],'deadline')
            archiver.assert_not_called()


if __name__=='__main__': unittest.main()
