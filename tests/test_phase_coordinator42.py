import json
import fcntl
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from scripts import phase_coordinator42 as phase


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True)+'\n');return phase.sha(path.read_bytes())


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.now=time.time();self.deadline='2099-01-01T00:00:00+00:00'
        write(self.root/'campaign.json',{'dimension':5,'field':2,'max_cpu_cores':4,'max_ram_gib':8,'deadline_utc':self.deadline})
        write(self.root/'queue.json',{'jobs':[]});write(self.root/'queue_state.json',{'jobs':{},'stop_reason':None})
        write(self.root/'operations-v3/state.json',{'updated_utc':phase.utc(self.now),'pid':os.getpid(),
            'process_identity':{'start_ticks':phase.identity(os.getpid())},'rss_bytes':1000,
            'filesystem_free_bytes':15*phase.GIB,'campaign_allocated_bytes':phase.GIB})
        config=self.root/'maintenance.json';digest=write(config,{'max_runs':500,'max_raw_bytes':512*1024**2})
        self.maintenance={'kind':'maintenance','name':'archive','enabled':True,'prefix':'auto-archive','cpu':3,'memory_mb':512,
            'phase_seconds':300,'grace_seconds':15,'minimum_interval_seconds':120,'config':str(config),
            'command_template':['python3','reviewed-maintenance.py','--config',str(config)]}
        self.plan={'format':'mmsearch-phase-plan-v1','campaign':str(self.root),'deadline_utc':self.deadline,
            'max_total_jobs':100,'bindings':{str(config):digest},'branches':[self.maintenance]}
        self.plan_path=self.root/'plan.json';self.gate_path=self.root/'ARMED.json';self.arm(['maintenance'])

    def arm(self,kinds,**fields):
        plan_sha=write(self.plan_path,self.plan)
        gate={'format':'mmsearch-phase-arm-v1','owner':'root','armed':True,'plan_sha256':plan_sha,
              'coordinator_sha256':phase.sha(Path(phase.__file__).read_bytes()),'armed_kinds':kinds,**fields}
        write(self.gate_path,gate)

    def coordinator(self): return phase.Coordinator(self.plan_path,self.gate_path,now=lambda:self.now)

    def result(self,name,**values):
        return write(self.root/(name+'-job.result.json'),{'exit_code':0,'timed_out':False,'interrupted':False,**values})

    def fingerprints(self):
        return {str(p.relative_to(self.root)):(p.stat().st_mtime_ns,phase.sha(p.read_bytes()))
                for p in self.root.rglob('*') if p.is_file()}

    def test_preview_zero_writes_and_unarmed_default(self):
        before=self.fingerprints();report=self.coordinator().preview()
        self.assertEqual(report['status'],'READY');self.assertEqual(len(report['actions']),1)
        self.assertEqual(before,self.fingerprints())
        self.gate_path.unlink();before=self.fingerprints()
        self.assertEqual(self.coordinator().preview()['status'],'UNARMED');self.assertEqual(before,self.fingerprints())

    def test_hypothetical_preview_cannot_authorize_run(self):
        self.gate_path.unlink();before=self.fingerprints()
        report=self.coordinator().preview(['maintenance'])
        self.assertTrue(report['hypothetical_unarmed_preview']);self.assertEqual(len(report['actions']),1)
        self.assertEqual(before,self.fingerprints())
        with mock.patch('sys.stderr'):
            with self.assertRaises(SystemExit) as stopped:
                phase.main(['run','--plan',str(self.plan_path),'--gate',str(self.gate_path),'--assume-kinds','maintenance'])
        self.assertEqual(stopped.exception.code,2);self.assertEqual(before,self.fingerprints())

    def test_maintenance_append_is_one_job_with_audit_snapshot(self):
        coordinator=self.coordinator();coordinator.tick()
        queue,_=phase.queue_value(self.root/'queue.json');self.assertEqual(len(queue['jobs']),1)
        self.assertEqual(queue['jobs'][0]['cpu'],3)
        self.assertTrue((self.root/'phase-coordinator42/phases/auto-archive-001.json').exists())
        self.assertTrue((self.root/'phase-coordinator42/HANDOFF.md').exists())
        coordinator.tick();self.assertEqual(len(phase.queue_value(self.root/'queue.json')[0]['jobs']),1)

    def test_plan_source_and_artifact_hashes_fail_closed(self):
        value,_=phase.read(self.gate_path);value['plan_sha256']='wrong';write(self.gate_path,value)
        with self.assertRaisesRegex(ValueError,'binding mismatch'):self.coordinator().preview()
        self.arm(['maintenance']);write(self.root/'maintenance.json',{'max_runs':999})
        with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):self.coordinator().preview()

    def test_pending_priority_cpu3_prevents_maintenance_v3_v4_overlap(self):
        job={'id':'root-v3-archive','cpu':3,'memory_mb':512,'seconds':600,'enabled':True,'command':['python3','scripts/recovery_maintenance_v3.py']}
        write(self.root/'queue.json',{'jobs':[job]})
        report=self.coordinator().preview();self.assertEqual(report['actions'],[])
        self.assertEqual(report['branches'][0]['status'],'WAITING_PRIORITY_CPU3')

    def test_legacy_archive_lock_blocks_without_mutating_lock(self):
        path=self.root/'recovery-maintenance-v3.lock';path.write_text('preserved')
        with path.open('r') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            before=self.fingerprints();report=self.coordinator().preview()
            self.assertEqual(report['branches'][0]['status'],'WAITING_V3_V4_ARCHIVE_LOCK')
            self.assertEqual(before,self.fingerprints())

    def test_guard_deadline_winner_and_resource_barriers(self):
        coordinator=self.coordinator()
        write(self.root/'guard_stopped.json',{'reason':'test'});self.assertEqual(coordinator.preview()['status'],'BLOCKED')
        (self.root/'guard_stopped.json').unlink();write(self.root/'winner/WINNER.json',{})
        self.assertEqual(coordinator.preview()['reason'],'existing WINNER/approved stop file')
        (self.root/'winner/WINNER.json').unlink()
        value,_=phase.read(self.root/'operations-v3/state.json');value['updated_utc']=phase.utc(self.now-61);write(self.root/'operations-v3/state.json',value)
        self.assertEqual(coordinator.preview()['reason'],'resource guard heartbeat stale')
        self.now=phase.stamp(self.deadline)+1;self.assertEqual(coordinator.preview()['reason'],'global deadline')

    def test_maintenance_outcomes_and_error_pause_are_preserved(self):
        coordinator=self.coordinator();coordinator.tick();self.result('auto-archive-001')
        (self.root/'auto-archive-001-job.log').write_text(json.dumps({'status':'ok','removed_runs':30,'raw_bytes':4000000,'archive_bytes':400000})+'\n')
        self.now+=130
        value,_=phase.read(self.root/'operations-v3/state.json');value['updated_utc']=phase.utc(self.now);write(self.root/'operations-v3/state.json',value)
        report=coordinator.tick();self.assertEqual(report['actions'][0]['job']['id'],'auto-archive-002')
        self.assertEqual(coordinator.state['ledger'][0]['outcome']['maintenance']['removed_runs'],30)
        self.result('auto-archive-002',exit_code=2)
        report=coordinator.tick();self.assertEqual(report['branches'][0]['status'],'PAUSED')
        self.assertIn('archive',coordinator.state['paused_branches'])

    def setup_rl(self):
        manifest_sha=write(self.root/'pool/frozen/manifest.json',{'frozen':'fixture'})
        ready_sha=write(self.root/'pool/READY.json',{'manifest_sha256':manifest_sha})
        context={'clock':{'phase_id':'finetune43-v1','recovery_fraction':.05,'record_origin':0,'recovery_origin':0},
                 'curriculum_sha256':manifest_sha,'parent_checkpoint_sha256':'fixed-lifetime-parent'}
        self.context=context;self.pool_sha=manifest_sha
        self.pair(self.root/'pilot/checkpoint.json',context)
        prerequisite=['pilot','frozen-control','random-control','validation']
        digests={name:self.result(name) for name in prerequisite}
        report_sha=write(self.root/'validation/summary.json',{'format':'source-heldout-policy-evaluation-v43','complete_pairs':2,'heldout_subset':'validation'})
        clear={'format':'rl-phase-clearance-v1','approved':True,'pool_ready':True,'pilot_completed':True,
            'control_pair_validated':True,'completed_jobs':prerequisite,'result_sha256':digests,'pool_ready_sha256':ready_sha,
            'pilot_checkpoint_sha256':phase.sha((self.root/'pilot/checkpoint.json').read_bytes()),
            'pilot_schedule_sha256':phase.sha((self.root/'pilot/checkpoint.schedule.json').read_bytes()),
            'validated_artifacts':[{'path':str(self.root/'validation/summary.json'),'sha256':report_sha}]}
        clear_path=self.root/'RL_CLEARANCE.json';clear_sha=write(clear_path,clear)
        branch={'kind':'rl','name':'learned','enabled':True,'prefix':'auto-learned','cpu':0,'memory_mb':1024,
            'phase_seconds':3600,'grace_seconds':15,'cutoff_utc':self.deadline,'phase_id':'finetune43-v1',
            'checkpoint_format':'mmsearch-finetune-a2c-v43','schedule_format':'mmsearch-finetune-schedule-v43','context_key':'finetune43',
            'pool_ready':str(self.root/'pool/READY.json'),'pool_manifest':str(self.root/'pool/frozen/manifest.json'),
            'prerequisite_jobs':prerequisite,'initial_predecessor_job':'pilot','initial_checkpoint':str(self.root/'pilot/checkpoint.json'),
            'command_template':['python3','reviewed-v43.py','--resume','{previous_checkpoint}','--seconds','{seconds}',
                                '--phase-id','finetune43-v1','--checkpoint','{outdir}/checkpoint.json']}
        self.plan['branches']=[branch];self.arm(['rl'],rl_clearance={'path':str(clear_path),'sha256':clear_sha})
        return branch

    def pair(self,path,context):
        digest=write(path,{'format':'mmsearch-finetune-a2c-v43','restart_curriculum':{'fixed':'restart'},'finetune43':context,
            'config':{'n':5,'target_rank':92,'native_only':True,'control':'policy','train':True},'state':{'terminal':False},'best':[[1,1,1]]*93})
        write(Path(path).with_suffix('.schedule.json'),{'format':'mmsearch-finetune-schedule-v43','checkpoint_sha256':digest,
            'restart_context':{'fixed':'restart'},'finetune43':context,'pool_context':{'pool_sha256':self.pool_sha}})

    def test_rl_never_autoarms_without_root_clearance(self):
        self.setup_rl();self.arm(['maintenance'])
        self.assertEqual(self.coordinator().preview()['branches'][0]['status'],'UNARMED')
        self.arm(['rl']);report=self.coordinator().preview()
        self.assertEqual(report['actions'],[]);self.assertEqual(report['branches'][0]['status'],'WAITING_ROOT_PILOT_CLEARANCE')

    def test_rl_coherent_hourly_chain_uses_previous_pair_without_reset(self):
        self.setup_rl();coordinator=self.coordinator();first=coordinator.tick()['actions'][0]
        self.assertEqual(first['parents']['checkpoint'],str(self.root/'pilot/checkpoint.json'))
        self.pair(Path(first['outdir'])/'checkpoint.json',self.context);self.result(first['job']['id'])
        second=coordinator.preview()['actions'][0]
        self.assertEqual(second['job']['id'],'auto-learned-002')
        self.assertEqual(second['parents']['checkpoint'],str(Path(first['outdir'])/'checkpoint.json'))
        self.assertEqual(first['parents']['phase_context_sha256'],second['parents']['phase_context_sha256'])

    def test_rl_corrupt_pair_and_lifetime_clock_reset_pause(self):
        self.setup_rl();path=self.root/'pilot/checkpoint.schedule.json';value,_=phase.read(path);value['checkpoint_sha256']='wrong';write(path,value)
        report=self.coordinator().preview();self.assertEqual(report['actions'],[]);self.assertIn('incoherent',report['branches'][0]['reason'])
        self.setup_rl();coordinator=self.coordinator();first=coordinator.tick()['actions'][0]
        changed=json.loads(json.dumps(self.context));changed['clock']['record_origin']=999
        self.pair(Path(first['outdir'])/'checkpoint.json',changed);self.result(first['job']['id'])
        report=coordinator.preview();self.assertEqual(report['actions'],[]);self.assertIn('reset',report['branches'][0]['reason'])

    def setup_stream(self,status='UNKNOWN',prefix=10,total=20,start=0):
        initial=self.root/'initial-stream';initial.mkdir(exist_ok=True)
        hashes={'input_sha256':'input','catalog_sha256':'catalog1','binary_sha256':'binary'}
        write(initial/'manifest.json',{**hashes,'start_row':start,'triples_total':total})
        write(initial/'native_final_stats.json',{'input_sha256':'input','catalog_sha256':'catalog1','next_row':prefix,
            'prefix_rows_skipped':start,'triples_considered':prefix-start,'triples_total':total})
        write(initial/'summary.json',{'status':status,'coverage':{'prefix_completed':prefix,'next_row':prefix,
            'triples_total':total,'triples_completed_this_run':prefix-start,'contiguous_from_initial':True,
            'supplied_catalog_completed':status=='NO_TARGET' and prefix==total}})
        self.result('stream-initial')
        template=['python3','reviewed-stream.py','--triple-catalog','CATALOG','--outdir','{outdir}','--seconds','{seconds}']
        branch={'kind':'stream','name':'triples','enabled':True,'prefix':'auto-triple','cpu':2,'memory_mb':1024,
            'phase_seconds':300,'grace_seconds':15,'initial_predecessor_job':'stream-initial','initial_outdir':str(initial),
            'partition_ready':str(self.root/'stream-READY.json'),
            'initial_tier':0,'tiers':[{'label':'new5','total_rows':20,'instance_hashes':hashes,'command_template':template},
            {'label':'old-long','total_rows':30,'instance_hashes':{**hashes,'catalog_sha256':'catalog2'},'command_template':template}]}
        write(self.root/'stream-READY.json',{'families_pairwise_disjoint':True,'exclusions_exactly_partition_completed_catalog':True,
            'input_sha256':'input','binary_sha256':'binary','cases':[{'label':'new5','sha256':'catalog1','selected':20},
            {'label':'old-long','sha256':'catalog2','selected':30}]})
        self.plan['branches']=[branch];self.arm(['stream']);return branch

    def test_unknown_stream_resumes_exact_fresh_cursor(self):
        self.setup_stream();action=self.coordinator().preview()['actions'][0]
        self.assertEqual(action['expected_start_row'],10);self.assertEqual(action['tier'],0)
        self.assertEqual(action['job']['command'][-2:],['--resume-from',str(self.root/'initial-stream')])
        self.assertFalse(Path(action['outdir']).exists())

    def test_completed_no_target_moves_only_to_fixed_next_tier(self):
        self.setup_stream(status='NO_TARGET',prefix=20)
        action=self.coordinator().preview()['actions'][0]
        self.assertEqual(action['tier'],1);self.assertEqual(action['expected_start_row'],0)
        self.assertNotIn('--resume-from',action['job']['command'])
        self.setup_stream(status='NO_TARGET',prefix=10)
        report=self.coordinator().preview();self.assertEqual(report['actions'],[])
        self.assertIn('lacks completed',report['branches'][0]['reason'])

    def test_stream_hash_mismatch_no_progress_and_error_pause(self):
        self.setup_stream(status='ERROR');self.assertEqual(self.coordinator().preview()['branches'][0]['status'],'PAUSED')
        self.setup_stream(prefix=0);self.assertIn('no progress',self.coordinator().preview()['branches'][0]['reason'])
        self.setup_stream();value,_=phase.read(self.root/'initial-stream/manifest.json');value['catalog_sha256']='other';write(self.root/'initial-stream/manifest.json',value)
        self.assertIn('hash differs',self.coordinator().preview()['branches'][0]['reason'])

    def test_stream_never_repeats_covered_rows(self):
        self.setup_stream();coordinator=self.coordinator();action=coordinator.tick()['actions'][0]
        output=Path(action['outdir']);output.mkdir()
        write(output/'manifest.json',{'input_sha256':'input','catalog_sha256':'catalog1','binary_sha256':'binary','start_row':0,'triples_total':20})
        write(output/'native_final_stats.json',{'input_sha256':'input','catalog_sha256':'catalog1','next_row':15,
            'prefix_rows_skipped':0,'triples_considered':15,'triples_total':20})
        write(output/'summary.json',{'status':'UNKNOWN','coverage':{'prefix_completed':15,'next_row':15,'triples_total':20,
            'triples_completed_this_run':15,'contiguous_from_initial':True,'supplied_catalog_completed':False}})
        self.result(action['job']['id']);report=coordinator.preview()
        self.assertEqual(report['actions'],[]);self.assertIn('reran covered',report['branches'][0]['reason'])

    def test_manual_external_continuation_requires_rebase_before_repeating_rows(self):
        self.setup_stream()
        other={'id':'root-manual-next','cpu':2,'memory_mb':1024,'seconds':300,'enabled':True,
            'command':['python3','reviewed-stream.py','--triple-catalog','CATALOG','--outdir',str(self.root/'external')]}
        write(self.root/'queue.json',{'jobs':[other]})
        self.assertEqual(self.coordinator().preview()['branches'][0]['status'],'WAITING_EXTERNAL_STREAM_CONTINUATION')
        self.result(other['id']);write(self.root/'external/summary.json',{'status':'UNKNOWN','coverage':{'prefix_completed':15}})
        report=self.coordinator().preview();self.assertEqual(report['actions'],[])
        self.assertIn('root rebase',report['branches'][0]['reason'])

    def test_crash_after_queue_append_recovers_durable_intent_without_duplicate(self):
        coordinator=self.coordinator();original=coordinator.append
        def crash(action): original(action);raise RuntimeError('simulated process death after append')
        with mock.patch.object(coordinator,'append',side_effect=crash):
            with self.assertRaises(RuntimeError):coordinator.tick()
        (self.root/'auto-archive-001').mkdir()
        restarted=self.coordinator();report=restarted.tick()
        self.assertEqual(report['actions'][0]['append_status'],'already_present')
        self.assertEqual(len(phase.queue_value(self.root/'queue.json')[0]['jobs']),1)
        self.assertNotIn('pending_action',restarted.state)

    def test_paused_error_does_not_silently_skip_or_retry(self):
        self.setup_stream(status='ERROR');coordinator=self.coordinator();coordinator.tick()
        self.setup_stream(status='UNKNOWN')
        restarted=self.coordinator();report=restarted.preview()
        self.assertEqual(report['actions'],[]);self.assertEqual(report['branches'][0]['status'],'PAUSED')


if __name__=='__main__':unittest.main()
