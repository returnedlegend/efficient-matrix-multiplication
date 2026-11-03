import contextlib
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from mmsearch.marathon7_local import CampaignGuard,CampaignHold,compact_negative,SourceCache,HARD_DEADLINE,select_plan,verify_winner_resume,raw,sha
from mmsearch.recombine import digest
from mmsearch import compact_rank2_edges43 as decoder
from mmsearch.local_ten43 import planted_small
from scripts import marathon7_local_campaign as worker


def tiny_bundle(root):
    b=Path(root)/'bundle';b.mkdir();source,core,_=planted_small();case=dict(id='tiny',source='source.json',core='core.json',source_products=18,source_local_products=4,target_local_products=3,free_axis=0)
    for name,value in [('source.json',source),('core.json',core),('small-plan.json',{'cases':[case]}),('plan.json',{'cases':[case]})]:(b/name).write_text(json.dumps(value))
    (b/'launch-manifest.json').write_text(json.dumps({'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in b.iterdir()}}));return b


def invoke(b,out,*extra,solver=None,patches=()):
    argv=['worker','--bundle',str(b),'--output-dir',str(out),'--seconds','5','--memory-mb','1024',*extra]
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch('sys.argv',argv));stack.enter_context(patch.object(worker.signal,'signal'));stack.enter_context(patch.object(worker.resource,'setrlimit'))
        if solver is not None:stack.enter_context(patch.object(decoder,'solve_core',solver))
        for item in patches:stack.enter_context(item)
        captured=stack.enter_context(contextlib.redirect_stdout(io.StringIO()));code=worker.main()
    return code,json.loads(captured.getvalue())


class Marathon7LocalTests(unittest.TestCase):
    def test_negative_edge_census_compaction(self):
        core=[(0b100010001>>i)&1 for i in range(9)];r=decoder.solve_core(core,[1,3,3],2,axis=0)
        self.assertEqual(r['status'],'LOCAL_UNSAT');c=compact_negative(r)
        self.assertNotIn('bucket_span_ranks',c)
        with self.assertRaises(ValueError):compact_negative(dict(r,enumerated_vectors=0))
        with self.assertRaises(ValueError):compact_negative(dict(r,complete=False))

    def test_hard_cutoff_cannot_extend(self):
        g=CampaignGuard(5,'2099-01-01T00:00:00Z',utc_clock=lambda:HARD_DEADLINE)
        self.assertEqual(g.deadline,HARD_DEADLINE)
        with self.assertRaises(CampaignHold):g.check('prelaunch')

    def test_typed_resource_stale_stop_and_process_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state=root/'resource.json';ticks=int(Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')',1)[1].split()[19])
            good=dict(pid=os.getpid(),process_identity=dict(start_ticks=ticks),updated_utc=datetime.now(timezone.utc).isoformat(),campaign_allocated_bytes=0,stop_reason=None)
            for value in [None,[],dict(good,pid=True),dict(good,campaign_allocated_bytes=True),dict(good,campaign_allocated_bytes=-1),dict(good,updated_utc='2026-11-03T12:24:17'),dict(good,process_identity=dict(start_ticks=ticks+1)),dict(good,stop_reason='stop')]:
                state.write_text(json.dumps(value));g=CampaignGuard(5,'2099-01-01T00:00:00Z',guard_state=state,campaign_dir=root)
                self.assertIsNotNone(g.reason(force=True),value)
            state.write_text(json.dumps(good));g=CampaignGuard(5,'2099-01-01T00:00:00Z',guard_state=state,campaign_dir=root);self.assertIsNone(g.reason(force=True))
            (root/'queue_state.json').write_text('null');self.assertIsNotNone(g.reason(force=True))

    def test_stopped_and_expired_prelaunch_no_queries(self):
        with tempfile.TemporaryDirectory() as d:
            b=tiny_bundle(d);stop=Path(d)/'stop';stop.touch()
            _,r=invoke(b,Path(d)/'out','--small-control','--stop-marker',str(stop));self.assertEqual((r['status'],r['queries_this_invocation']),('UNKNOWN',0))
            _,r=invoke(b,Path(d)/'expired','--small-control','--deadline-utc','1970-01-01T00:00:00Z');self.assertEqual((r['status'],r['queries_this_invocation']),('UNKNOWN',0))

    def test_positive_full_small_lift_resume_and_journal(self):
        with tempfile.TemporaryDirectory() as d:
            b=tiny_bundle(d);out=Path(d)/'out'
            _,r=invoke(b,out,'--small-control');self.assertEqual(r['status'],'SMALL_CONTROL_PASSED');self.assertEqual(json.loads((out/'SMALL_CONTROL.verification.json').read_text())['exact_entries_checked'],64)
            with patch.object(SourceCache,'core',side_effect=AssertionError('terminal must not rebuild')):
                _,r=invoke(b,out,'--small-control','--resume');self.assertEqual(r['status'],'SMALL_CONTROL_PASSED')
            state=json.loads((out/'cursor.json').read_text());state.update(next_case=0,results=[],terminal=False,status='UNKNOWN');(out/'cursor.json').write_text(json.dumps(state))
            with patch.object(SourceCache,'core',side_effect=AssertionError('journal must roll forward')):
                _,r=invoke(b,out,'--small-control','--resume');self.assertEqual(r['status'],'SMALL_CONTROL_PASSED')

    def test_late_negative_and_positive_remain_open_then_resume(self):
        for status in ['SAT','LOCAL_UNSAT']:
            with self.subTest(status=status),tempfile.TemporaryDirectory() as d:
                b=tiny_bundle(d);out=Path(d)/'out';actual=decoder.solve_core
                def late(*args,**kwargs):
                    result=actual(*args,**kwargs) if status=='SAT' else dict(status='LOCAL_UNSAT',complete=True)
                    time.sleep(.04);return result
                _,r=invoke(b,out,'--small-control','--per-case-seconds','.02',solver=late)
                self.assertEqual((r['status'],r['queries_this_invocation']),('UNKNOWN',1));self.assertEqual(json.loads((out/'cursor.json').read_text())['next_case'],0)
                self.assertTrue((out/'current/core.json').exists());self.assertFalse((out/'WINNER.json').exists());self.assertFalse((out/'SMALL_CONTROL.json').exists())
                payload=json.loads(next(out.glob('*.after-cutoff.raw.json')).read_text());self.assertEqual(payload['raw_decoder_result']['status'],status)
                _,r=invoke(b,out,'--small-control','--per-case-seconds','1','--resume');self.assertEqual(r['status'],'SMALL_CONTROL_PASSED');self.assertFalse((out/'current').exists())

    def test_new_source_requires_production_guard(self):
        # Protocol mock only: real n2 source/core; no N5 decoder query.
        with tempfile.TemporaryDirectory() as d:
            b=tiny_bundle(d);actual=SourceCache.core
            def n5_metadata(self,case):
                source,*rest=actual(self,case);return (dict(source,dimension=5),*rest)
            with patch.object(SourceCache,'core',n5_metadata),patch.object(decoder,'solve_core',side_effect=AssertionError('guard must block dispatch')):
                _,r=invoke(b,Path(d)/'out');self.assertEqual((r['status'],r['queries_this_invocation']),('UNKNOWN',0))

    def test_manifest_and_resume_config_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            b=tiny_bundle(d);out=Path(d)/'out';_,r=invoke(b,out,'--controls-only');self.assertEqual(r['status'],'CONTROLS_PASSED')
            with self.assertRaises(ValueError):invoke(b,out,'--controls-only','--resume','--deadline-utc','1970-01-01T00:00:00Z')
            (b/'source.json').write_text('{}')
            with self.assertRaises(ValueError):invoke(b,Path(d)/'out2','--controls-only')

    def test_winner_resume_binds_marker_views_immutable_core_and_config(self):
        # Provenance protocol only: verifier mocked eligible, no N5 candidate/query.
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);proofdir=out/'proofs'/'case';proofdir.mkdir(parents=True)
            data=dict(shape=[1,1,1],core=[1]);candidate=dict(terms=['protocol fixture'])
            certificate=dict(config_sha256='config',case='case',core_input_sha256=sha(raw(data)),core_math_sha256=digest(data))
            files={}
            for name,value in [('candidate.json',candidate),('input-core.json',data),('verification.json',{'valid':True}),('independent.json',{'record_eligible':True}),('core-certificate.json',certificate)]:
                (proofdir/name).write_bytes(raw(value))
            (out/'WINNER.json').write_bytes(raw(candidate))
            for view,original in [('WINNER.verification.json','verification.json'),('WINNER.independent.verification.json','independent.json'),('WINNER.core-certificate.json','core-certificate.json')]:
                (out/view).write_bytes((proofdir/original).read_bytes());files[view]=sha((out/view).read_bytes())
            proof=dict(candidate_sha256=sha(raw(candidate)),proof_directory='proofs/case',files=files)
            (out/'WINNER.proof.json').write_bytes(raw(proof));eligible=lambda _:dict(record_eligible=True)
            self.assertTrue(verify_winner_resume(out,'config',[dict(id='case')],eligible)['record_eligible'])
            with self.assertRaises(ValueError):verify_winner_resume(out,'changed',[dict(id='case')],eligible)
            for target in [out/'WINNER.json',proofdir/'candidate.json',out/'WINNER.verification.json',proofdir/'verification.json',proofdir/'input-core.json']:
                content=target.read_bytes();target.write_bytes(b'{}')
                with self.assertRaises(ValueError):verify_winner_resume(out,'config',[dict(id='case')],eligible)
                target.write_bytes(content)
            with self.assertRaises(ValueError):verify_winner_resume(out,'config',[dict(id='other')],eligible)
            (out/'WINNER.proof.json').write_bytes(raw(dict(proof,proof_directory='../outside')))
            with self.assertRaises(ValueError):verify_winner_resume(out,'config',[dict(id='case')],eligible)


if __name__=='__main__':unittest.main()
