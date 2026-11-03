"""Queue-only native continuation: nine durable/admission/exactness controls."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.native_portfolio_controller42 import Portfolio,PROFILES,GIB,checked_certificate,digest
from scripts.phase_coordinator42_v2 import atomic,job_digest,utc,validate_job

ROOT=Path(__file__).resolve().parents[1]
NOW=dt.datetime(2026,11,3,tzinfo=dt.timezone.utc).timestamp()


class Fixture:
    def __init__(self,path):
        self.c=Path(path);self.c.mkdir(exist_ok=True);self.now=NOW;self.seed=self.c/'seed.json'
        self.seed.write_bytes((ROOT/'artifacts/km93_f2.json').read_bytes())
        self.wrapper=self.c/'wrapper.py';self.wrapper.write_text('reviewed\n');self.worker=self.c/'worker';self.worker.write_bytes(b'reviewed-worker')
        self.pred='initial-h12';self.command=['python3','approved.py','--seed','4242'];self.result=self.c/(self.pred+'-job.result.json')
        atomic(self.c/'campaign.json',{'dimension':5,'field':2,'max_cpu_cores':4,'max_ram_gib':8,'deadline_utc':utc(NOW+7200)})
        (self.c/'operations-v3').mkdir();self.guard={'pid':777,'process_identity':{'start_ticks':10},'updated_utc':utc(NOW),'rss_bytes':1,'filesystem_free_bytes':20*GIB,'campaign_allocated_bytes':0,'stop_reason':None};self.save_guard()
        self.job={'id':self.pred,'cpu':2,'memory_mb':768,'seconds':1815,'command':self.command,'enabled':True};atomic(self.c/'queue.json',{'jobs':[self.job]});atomic(self.c/'queue_state.json',{'jobs':{self.pred:{'status':'completed'}},'stop_reason':None})
        folder=self.c/self.pred;(folder/'verified').mkdir(parents=True);(folder/'verification').mkdir();(folder/'verified/known.json').write_bytes(self.seed.read_bytes())
        report=checked_certificate(self.seed)['verification'];atomic(folder/'verification/known.verification.json',report)
        phase={'phase':0,'command':['native','--plus-every','20000','--restart-every','50000000'],'source_essential_rank':93,'max_rank':105,'final_stats':{'exact':True,'tensor_invariant_checked':True,'target_rank':92}}
        atomic(folder/'summary.json',{'winner':False,'phases':[phase]});atomic(folder/'manifest.json',{'headroom':12,'target_rank':92,'cyclic':False,'binary_sha256':digest(self.worker.read_bytes())})
        atomic(self.result,{'exit_code':0,'timed_out':False,'interrupted':False,'command':self.command,'cpu_seconds':100})
        self.plan={'format':'native-portfolio-plan-v1','campaign':str(self.c),'deadline_utc':utc(NOW+7200),'profiles':PROFILES,'cpu':2,'memory_mb':768,'phase_seconds':1800,'pool_cap':32,'seed_block':1000000,'seed_base':202611030000000,'wrapper':str(self.wrapper),'worker':str(self.worker),'worker_sha256':digest(self.worker.read_bytes()),'bindings':{str(self.wrapper):digest(self.wrapper.read_bytes()),str(self.worker):digest(self.worker.read_bytes())},'initial_pool':[{'path':str(self.seed),'sha256':digest(self.seed.read_bytes())}],'predecessors':[{'id':self.pred,'profile':'h12','command':self.command}]}
        self.plan_path=self.c/'plan.json';atomic(self.plan_path,self.plan);self.gate=self.c/'gate.json';self.arm(True)
    def save_guard(self):atomic(self.c/'operations-v3/state.json',self.guard)
    def controller(self):return Portfolio(self.plan_path,self.gate,now=lambda:self.now,pid_identity=lambda pid:10 if pid==777 else None,disk_free=lambda path:20*GIB)
    def arm(self,value):
        controller=self.controller();atomic(self.gate,{'format':'native-portfolio-arm-v1','owner':'root','armed':value,'plan_sha256':controller.plan_sha,'controller_sha256':controller.code_sha})
    def queue(self):return json.loads((self.c/'queue.json').read_text())


class NativePortfolioTests(unittest.TestCase):
    def test_preview_and_unarmed_have_no_writes_or_launches(self):
        with tempfile.TemporaryDirectory() as temporary:
            f=Fixture(temporary);before=(f.c/'queue.json').read_bytes();f.arm(False)
            self.assertEqual(f.controller().tick(preview=True)['status'],'UNARMED')
            self.assertFalse((f.c/'native-portfolio42').exists());f.arm(True)
            result=f.controller().tick(preview=True);self.assertEqual(result['status'],'PROPOSED');self.assertIn(result['action']['profile'],PROFILES)
            self.assertEqual((f.c/'queue.json').read_bytes(),before);self.assertFalse((f.c/'native-portfolio42').exists())

    def test_crash_after_queue_append_recovers_intent_once_and_pool_has_only_certificates(self):
        with tempfile.TemporaryDirectory() as temporary:
            f=Fixture(temporary);controller=f.controller();action,_=controller.proposal();controller.state['pending']=action;controller.save()
            queue=f.queue();queue['jobs'].append(action['job']);atomic(f.c/'queue.json',queue)
            restored=f.controller();self.assertEqual(restored.tick()['status'],'QUEUED');self.assertIsNone(restored.state['pending']);self.assertEqual(len(restored.state['ledger']),1)
            self.assertEqual(len(f.queue()['jobs']),2);self.assertEqual(len(list(Path(action['pool_dir']).glob('*.json'))),1)
            self.assertEqual(restored.tick()['status'],'WAITING_PREDECESSOR');self.assertEqual(len(f.queue()['jobs']),2)

    def test_error_is_sticky_and_preserves_queue(self):
        with tempfile.TemporaryDirectory() as temporary:
            f=Fixture(temporary);value=json.loads(f.result.read_text());value['exit_code']=1;atomic(f.result,value);before=(f.c/'queue.json').read_bytes()
            controller=f.controller();self.assertEqual(controller.tick()['status'],'ERROR');value['exit_code']=0;atomic(f.result,value)
            self.assertTrue(f.controller().tick()['status'].startswith('ERROR'));self.assertEqual((f.c/'queue.json').read_bytes(),before)

    def test_pid_none_guard_clock_resource_and_winner_barriers(self):
        with tempfile.TemporaryDirectory() as temporary:
            f=Fixture(temporary);original=copy.deepcopy(f.guard)
            for changes,expected in (({'pid':None},'GUARD_IDENTITY'),({'updated_utc':utc(NOW-61)},'GUARD_CLOCK'),({'rss_bytes':7*GIB+1},'RAM_HOLD'),({'filesystem_free_bytes':8*GIB-1},'GLOBAL_DISK_HOLD'),({'campaign_allocated_bytes':5*GIB},'WORKING_DATA_HOLD_5GIB')):
                with self.subTest(expected=expected):
                    f.guard={**original,**changes};f.save_guard();self.assertEqual(f.controller().tick(preview=True)['status'],expected)
            f.guard=original;f.save_guard();(f.c/'WINNER.json').write_text('{}');self.assertEqual(f.controller().tick(preview=True)['status'],'WINNER')

    def test_duplicate_job_collision_and_exact_queue_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            f=Fixture(temporary);controller=f.controller();action,_=controller.proposal();bad=copy.deepcopy(action['job']);bad['note']='not allowed'
            with self.assertRaises(ValueError):validate_job(bad)
            collision=copy.deepcopy(action['job']);collision['memory_mb']=512;queue=f.queue();queue['jobs'].append(collision);atomic(f.c/'queue.json',queue)
            with self.assertRaisesRegex(ValueError,'collision'):controller.append(action)
            controller.state['ledger']=[{'fingerprint':action['fingerprint'],'seed':action['seed'],'job':action['job'],'profile':'h6'}]
            self.assertEqual(len(f.queue()['jobs']),2)

    def test_invalid_fake92_is_rejected_and_valid93_is_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            f=Fixture(temporary);valid=checked_certificate(f.seed);self.assertEqual(valid['rank'],93);self.assertFalse(valid['record']);self.assertEqual(valid['verification']['exact_entries_checked'],15625)
            value=json.loads(f.seed.read_text());value['terms'].pop();bad=f.c/'fake92.json';bad.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'tensor'):checked_certificate(bad)
            value=json.loads(f.seed.read_text());value['terms'][0]['u'][0]=0.0;bad.write_text(json.dumps(value))
            with self.assertRaises(ValueError):checked_certificate(bad)

    def test_certificate_cache_uses_bytes_and_completed_output_mutation_pauses(self):
        with tempfile.TemporaryDirectory() as temporary:
            f=Fixture(temporary);controller=f.controller();first=controller.certificate(f.seed);value=json.loads(f.seed.read_text());value.setdefault('metadata',{})['extra']='changed';f.seed.write_text(json.dumps(value));second=controller.certificate(f.seed)
            self.assertNotEqual(first['sha256'],second['sha256']);self.assertEqual(len(controller.state['certificates']),2)
            # Restore initial binding, ingest once, then mutate immutable outcome.
            f.seed.write_bytes((ROOT/'artifacts/km93_f2.json').read_bytes());controller=f.controller();controller.proposal();path=f.c/f.pred/'summary.json';value=json.loads(path.read_text());value['extra']='mutation';atomic(path,value)
            with self.assertRaisesRegex(ValueError,'outcome changed'):controller.consume(f.pred,'h12',f.command)

    def test_deadline_trim_and_busy_cpu_never_append(self):
        with tempfile.TemporaryDirectory() as temporary:
            f=Fixture(temporary);f.now=NOW+7200-115;f.guard['updated_utc']=utc(f.now);f.save_guard();action,status=f.controller().proposal();self.assertEqual(status,'PROPOSED');self.assertEqual(action['job']['seconds'],115)
            f.now=NOW+7200;f.guard['updated_utc']=utc(f.now);f.save_guard();self.assertEqual(f.controller().tick(preview=True)['status'],'DEADLINE')
            f.now=NOW;f.guard['updated_utc']=utc(NOW);f.save_guard();queue=f.queue();queue['jobs'].append({'id':'other','cpu':2,'memory_mb':768,'seconds':90,'command':['none'],'enabled':True});atomic(f.c/'queue.json',queue)
            self.assertEqual(f.controller().tick(preview=True)['status'],'CPU2_OR_MEMORY_BUSY')

    def test_adaptation_keeps_coverage_and_does_not_turn93_into_record_reward(self):
        with tempfile.TemporaryDirectory() as temporary:
            f=Fixture(temporary);controller=f.controller();controller.state['outcomes']={'A':{'profile':'h12','new_histogram_buckets':5,'cpu_seconds':100},'B':{'profile':'h6','new_histogram_buckets':0,'cpu_seconds':100}}
            self.assertEqual(controller.choose_profile(1)[0],'h12');self.assertEqual(controller.choose_profile(2)[0],'h6');self.assertEqual(controller.choose_profile(3)[0],'h12');self.assertEqual(controller.choose_profile(4)[0],'h12')
            controller.state['outcomes']['A']['new_histogram_buckets']=0;self.assertEqual(controller.choose_profile(7)[0],'h12')


if __name__=='__main__':unittest.main()
