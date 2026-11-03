import contextlib
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from mmsearch.local_guard43 import CampaignGuard,CampaignHold
from mmsearch.local_ten43 import planted_small
from mmsearch import compact_coset43,compact_eight43
from scripts import campaign_local_ten_guard43 as worker


def tiny_bundle(root):
    b=Path(root)/'bundle';b.mkdir();source,core,_=planted_small();case=dict(id='tiny',source='source.json',core='core.json',source_products=18,source_local_products=4,target_local_products=3,free_axis=0)
    for name,value in [('source.json',source),('core.json',core),('small-plan.json',{'cases':[case]}),('plan.json',{'cases':[case]})]:(b/name).write_text(json.dumps(value))
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in b.iterdir()};(b/'launch-manifest.json').write_text(json.dumps({'files':files}))
    return b


def invoke(b,out,*extra,solver=None,patches=()):
    argv=['worker','--bundle',str(b),'--output-dir',str(out),'--seconds','5','--memory-mb','1024',*extra]
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch('sys.argv',argv));stack.enter_context(patch.object(worker.signal,'signal'))
        # CLI limits belong to its process. These in-process lifecycle controls
        # must not permanently lower the unittest process's hard memory limit.
        stack.enter_context(patch.object(worker.resource,'setrlimit'))
        if solver is not None:stack.enter_context(patch.object(compact_coset43,'solve_core',solver))
        for item in patches:stack.enter_context(item)
        captured=stack.enter_context(contextlib.redirect_stdout(io.StringIO()));code=worker.main()
    return code,json.loads(captured.getvalue())


class GuardTests(unittest.TestCase):
    def test_actual_cli_memory_limit_is_confined_to_child_process(self):
        with tempfile.TemporaryDirectory() as d:
            b=tiny_bundle(d);out=Path(d)/'out';before=resource.getrlimit(resource.RLIMIT_AS)
            result=subprocess.run([sys.executable,str(Path(worker.__file__)),
                '--bundle',str(b),'--output-dir',str(out),'--small-control',
                '--seconds','5','--memory-mb','128'],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'],'SMALL_CONTROL_PASSED')
            saved=json.loads(next(out.glob('*.result.json')).read_text())
            self.assertEqual(saved['effective_AS_limit_bytes'],128*1024**2)
            self.assertEqual(resource.getrlimit(resource.RLIMIT_AS),before)

    def test_clock_stop_and_canonical_global_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);mono=[0.];utc=[10.];deadline=datetime.fromtimestamp(20.,timezone.utc).isoformat()
            guard=CampaignGuard(5,deadline,monotonic=lambda:mono[0],utc_clock=lambda:utc[0],campaign_dir=root)
            guard.check('prelaunch');utc[0]=20
            with self.assertRaises(CampaignHold):guard.check('UTC')
            utc[0]=10;mono[0]=5
            with self.assertRaises(CampaignHold):guard.check('wall')
            mono[0]=0
            for name,value in [('guard_stopped.json',{}),('queue_state.json',{'stop_reason':'halt'}),('operations-v3/state.json',{'stop_reason':'halt'})]:
                path=root/name;path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(value))
                with self.assertRaises(CampaignHold):guard.check('globalstop')
                path.unlink()
            (root/'nested').mkdir();(root/'nested/WINNER.json').write_text('{}')
            with self.assertRaises(CampaignHold):guard.check('winner')

    def test_slow_global_read_rechecks_clock_at_barrier_exit(self):
        mono=[0.];utc=[10.];deadline=datetime.fromtimestamp(20.,timezone.utc).isoformat()
        guard=CampaignGuard(5,deadline,monotonic=lambda:mono[0],utc_clock=lambda:utc[0])
        def slow_global(force=False):mono[0]=6.;return None
        with patch.object(guard,'_campaign_reason',slow_global):
            with self.assertRaises(CampaignHold):guard.check('pre_winner_marker')
        mono[0]=0
        def utc_global(force=False):utc[0]=21.;return None
        with patch.object(guard,'_campaign_reason',utc_global):
            with self.assertRaises(CampaignHold):guard.check('pre_winner_marker')

    def test_expired_UTC_prelaunch_zero_queries_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            b=tiny_bundle(d);out=Path(d)/'out'
            for resumed in (False,True):
                _,r=invoke(b,out,'--small-control','--deadline-utc','1970-01-01T00:00:00Z',*(['--resume'] if resumed else []))
                self.assertEqual((r['status'],r['queries_this_invocation']),('UNKNOWN',0))
                self.assertEqual(json.loads((out/'cursor.json').read_text())['next_case'],0)
                self.assertFalse((out/'SMALL_CONTROL.json').exists());self.assertFalse((out/'WINNER.json').exists())

    def test_prelaunch_marker_then_resume_actual_small_positive(self):
        with tempfile.TemporaryDirectory() as d:
            b=tiny_bundle(d);out=Path(d)/'out';stop=Path(d)/'stop';stop.touch()
            _,r=invoke(b,out,'--small-control','--stop-marker',str(stop));self.assertEqual((r['status'],r['queries_this_invocation']),('UNKNOWN',0))
            stop.unlink();_,r=invoke(b,out,'--small-control','--stop-marker',str(stop),'--resume')
            self.assertEqual(r['status'],'SMALL_CONTROL_PASSED');self.assertEqual(json.loads((out/'SMALL_CONTROL.verification.json').read_text())['exact_entries_checked'],64)

    def test_midcall_stop_preserves_raw_positive_and_open_resume(self):
        with tempfile.TemporaryDirectory() as d:
            b=tiny_bundle(d);out=Path(d)/'out';stop=Path(d)/'stop';actual=compact_coset43.solve_core
            def midcall(*args,**kwargs):
                result=actual(*args,**kwargs);stop.touch();return result
            _,r=invoke(b,out,'--small-control','--stop-marker',str(stop),solver=midcall)
            self.assertEqual((r['status'],r['queries_this_invocation']),('UNKNOWN',1));state=json.loads((out/'cursor.json').read_text());self.assertEqual(state['next_case'],0)
            late=list(out.glob('*.after-cutoff.raw.json'));self.assertEqual(len(late),1);payload=json.loads(late[0].read_text())
            self.assertTrue(payload['after_cutoff']);self.assertEqual(payload['raw_decoder_result']['status'],'SAT')
            self.assertFalse((out/'SMALL_CONTROL.json').exists());self.assertFalse((out/'WINNER.json').exists())
            stop.unlink();_,r=invoke(b,out,'--small-control','--stop-marker',str(stop),'--resume');self.assertEqual(r['status'],'SMALL_CONTROL_PASSED')

    def test_delayed_negative_is_UNKNOWN_not_closed(self):
        with tempfile.TemporaryDirectory() as d:
            b=tiny_bundle(d);out=Path(d)/'out'
            def delayed_negative(*args,**kwargs):
                time.sleep(.08);return {'status':'LOCAL_UNSAT','complete':True,'case':'MOCKED_LIFECYCLE_NEGATIVE'}
            _,r=invoke(b,out,'--small-control','--seconds','.05',solver=delayed_negative)
            self.assertEqual((r['status'],r['queries_this_invocation']),('UNKNOWN',1));self.assertEqual(json.loads((out/'cursor.json').read_text())['next_case'],0)
            payload=json.loads(next(out.glob('*.after-cutoff.raw.json')).read_text());self.assertEqual(payload['raw_decoder_result']['status'],'LOCAL_UNSAT')
            _,r=invoke(b,out,'--small-control','--resume');self.assertEqual(r['status'],'SMALL_CONTROL_PASSED')

    def test_mocked_publication_marker_last_and_late_proofs_resume(self):
        # Protocol-only N5 publication harness: actual n2 source/core/lift,
        # mocked eligibility/entry-count fields. No n5 decoder or certificate.
        with tempfile.TemporaryDirectory() as d:
            b=tiny_bundle(d);out=Path(d)/'out';stop=Path(d)/'stop';actual_replace=compact_eight43.replace_and_verify;actual_atomic=worker.atomic
            def mock_full(*args,**kwargs):
                candidate,report=actual_replace(*args,**kwargs);return candidate,dict(report,exact_entries_checked=15625)
            def stop_after_proofs(path,value):
                actual_atomic(path,value)
                if path.name=='WINNER.proof.json':stop.touch()
            mocks=[patch.object(compact_eight43,'replace_and_verify',mock_full),patch('scripts.verify_record42_independent.verify_bytes',return_value={'record_eligible':True}),patch.object(worker,'atomic',stop_after_proofs)]
            _,r=invoke(b,out,'--stop-marker',str(stop),patches=mocks)
            self.assertEqual(r['status'],'UNKNOWN');self.assertFalse((out/'WINNER.json').exists());self.assertTrue((out/'WINNER.proof.json').exists())
            self.assertTrue(json.loads(next(out.glob('*.after-cutoff.raw.json')).read_text())['candidate'])
            stop.unlink();actual_write=worker.write;order=[]
            def marker_check(path,value):
                if path.name=='WINNER.json':
                    self.assertTrue((out/'WINNER.proof.json').exists());self.assertTrue((out/'WINNER.verification.json').exists());self.assertTrue((out/'WINNER.independent.verification.json').exists());self.assertTrue((out/'WINNER.core-certificate.json').exists())
                    proof=json.loads((out/'WINNER.proof.json').read_text());self.assertTrue((out/proof['proof_directory']/'candidate.json').exists())
                actual_write(path,value);order.append(path.name)
            mocks=[patch.object(compact_eight43,'replace_and_verify',mock_full),patch('scripts.verify_record42_independent.verify_bytes',return_value={'record_eligible':True}),patch.object(worker,'write',marker_check)]
            _,r=invoke(b,out,'--stop-marker',str(stop),'--resume',patches=mocks)
            self.assertEqual(r['status'],'VERIFIED_TARGET');self.assertTrue((out/'WINNER.json').exists());self.assertIn('WINNER.json',order)


if __name__=='__main__':unittest.main()
