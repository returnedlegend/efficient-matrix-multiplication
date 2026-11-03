import contextlib,io,json,pathlib,tempfile,unittest
from unittest import mock
from scripts import campaign_native_plus_burst42_long as w

class PlusBurstLongHarnessTests(unittest.TestCase):
    def test_bounded_distinct_phase_schedule(self):
        self.assertEqual(w.budgets(900,300),[300,300,300])
        self.assertEqual(w.budgets(900,600),[600,300])
        self.assertEqual(w.budgets(601,600),[600,1])
        for args in [(901,300),(900,601),(0,300),(900,0),(900,float('nan')),(900,1)]:
            with self.assertRaises(ValueError):w.budgets(*args)

    def test_forwarded_native_bounds_and_no_policy_change(self):
        for k in [4,8]:
            args=w.command('bin','input','out',seconds=600,seed=991,dwell=128,plus_burst=k)
            reference=w.base.command('bin','input','out',seconds=30,seed=991,dwell=128,plus_burst=k)
            reference[reference.index('--seconds')+1]='600'
            self.assertEqual(args,reference)
        for seconds in [0,601,float('inf')]:
            with self.assertRaises(ValueError):w.command('b','i','o',seconds=seconds,seed=1,dwell=128,plus_burst=4)

    def pool(self,directory):
        directory.mkdir();(directory/'sources').mkdir()
        sources=[]
        for i in range(32):
            name=f'{i:064x}.json';(directory/'sources'/name).write_text('{}')
            sources.append(dict(file=name,sha256=w.base.sha(b'{}'),term_hash=f'{i:064x}',source_identity_sha256=f'{i+100:064x}'))
        path=directory/'pool.json';path.write_bytes(w.base.raw_json(dict(format='dwell42-bfs32-pool-v1',origin={},sources=sources)))
        return path,sources

    def fake_validate(self,path,expected,decl,dsha):
        return ((1,2,3),),dict(term_set_sha256=path.stem,source_term_hash=f'{int(path.stem,16)+100:064x}'),b'{}'

    def test_pool_hash_identity_order_and_symlinks_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,sources=self.pool(pathlib.Path(tmp)/'pool')
            with mock.patch.object(w.base,'validate_input',side_effect=self.fake_validate):
                pool,loaded,raw=w.load_pool(path,w.base.sha(path.read_bytes()),'declaration','hash')
                self.assertEqual([x['item'] for x in loaded],sources)
                with self.assertRaises(ValueError):w.load_pool(path,'0'*64,'d','h')
                source=path.parent/'sources'/sources[0]['file'];source.unlink();source.symlink_to(path)
                with self.assertRaises(ValueError):w.load_pool(path,w.base.sha(path.read_bytes()),'d','h')

    def test_pool_duplicate_identity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,_=self.pool(pathlib.Path(tmp)/'pool')
            with mock.patch.object(w.base,'validate_input',return_value=(((1,2,3),),dict(term_set_sha256='0'*64,source_term_hash='0'*64),b'{}')):
                with self.assertRaises(ValueError):w.load_pool(path,w.base.sha(path.read_bytes()),'d','h')

    def preview_args(self,campaign,pool,binary):
        code=w.runtime_hashes()
        return ['--campaign',str(campaign),'--pool',str(pool),'--binary',str(binary),'--heldout-declaration','declaration',
                '--output-dir',str(campaign/'new'), '--expected-pool-sha256',w.base.sha(pool.read_bytes()),
                '--expected-binary-sha256',w.base.sha(binary.read_bytes()),'--expected-heldout-sha256','h',
                '--expected-runtime-sha256',w.base.sha(w.base.raw_json(code)),'--seed','2026110384200','--reduction-dwell','128','--plus-burst','4','--preview']

    def test_preview_zero_mutation_fixed_schedule_and_rerun_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            campaign=pathlib.Path(tmp);(campaign/'campaign.json').write_text(json.dumps(dict(dimension=5,field=2,target_rank=92,deadline_utc='2099-11-04T21:31:16Z')))
            pool,_=self.pool(campaign/'pool');binary=campaign/'binary';binary.write_bytes(b'fake')
            args=self.preview_args(campaign,pool,binary);before={str(p):p.read_bytes() for p in campaign.rglob('*') if p.is_file()}
            with mock.patch.object(w.base,'validate_input',side_effect=self.fake_validate),mock.patch.object(w.base,'run_child',side_effect=AssertionError('native forbidden')):
                captured=io.StringIO()
                with contextlib.redirect_stdout(captured):w.main(args)
                result=json.loads(captured.getvalue());self.assertTrue(result['zero_mutations'])
                self.assertEqual([x['seed'] for x in result['phases']],[2026110384200,2026110384201,2026110384202])
                self.assertEqual([x['source']['term_hash'] for x in result['phases']],[f'{i:064x}' for i in range(3)])
                self.assertEqual(before,{str(p):p.read_bytes() for p in campaign.rglob('*') if p.is_file()})
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):w.main(args+['--cpu','1'])
                    with self.assertRaises(SystemExit):w.main(args+['--memory-mb','769'])
                (campaign/'new').mkdir()
                with self.assertRaises(ValueError):w.main(args)

    def test_stop_and_resource_barriers(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=pathlib.Path(tmp);self.assertFalse(w.barrier(c,float('inf')))
            self.assertTrue(w.barrier(c,0));self.assertTrue(w.barrier(c,float('inf'),True))
            (c/'other').mkdir();(c/'other/WINNER.json').write_text('{}')
            self.assertTrue(w.barrier(c,float('inf')))
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):w.main(['--cpu','1'])

    def test_cached_state_stops_and_fail_closed_without_repeated_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=pathlib.Path(tmp);(c/'operations-v3').mkdir();path=c/'operations-v3/state.json';path.write_text('{}')
            policy=w.StopPolicy(c,float('inf'));original=w.base.read
            with mock.patch.object(w.base,'read',wraps=original) as reader:
                for _ in range(20):self.assertFalse(policy())
                self.assertEqual(reader.call_count,1)
                path.write_text('{"stop_reason":"deadline","pending_stops":[]}');self.assertTrue(policy())
                self.assertEqual(reader.call_count,2)
            path.write_text('malformed');self.assertTrue(w.StopPolicy(c,float('inf'))())
            path.unlink();(c/'queue_state.json').write_text('{"stop_reason":"record"}');self.assertTrue(w.StopPolicy(c,float('inf'))())

    def test_record_checks_stop_after_verification_and_before_marker(self):
        from mmsearch.tensor import strassen_candidate
        from mmsearch.search import decode_candidate,encode_candidate
        candidate=encode_candidate(decode_candidate(strassen_candidate(2),2),2)
        for trigger in ['after_fullT','before_marker','never']:
            with self.subTest(trigger=trigger),tempfile.TemporaryDirectory() as tmp:
                c=pathlib.Path(tmp);calls=[];original=w.base.freeze
                def freeze(path,raw,*args,**kwargs):calls.append(pathlib.Path(path).name);return original(path,raw,*args,**kwargs)
                first=True
                def stop():
                    nonlocal first
                    if trigger=='after_fullT':
                        if first:first=False;return False
                        return True
                    return trigger=='before_marker' and 'WINNER.checksums.json' in calls
                with mock.patch.object(w.base,'freeze',side_effect=freeze):result=w.freeze_winner(c,candidate,'n2',b'control',stop,n=2,target=7)
                self.assertEqual(result,trigger=='never');self.assertEqual((c/'WINNER.json').exists(),trigger=='never')
                if trigger=='never':self.assertEqual(calls[-1],'WINNER.json')

    def test_no_late_export_promotion_and_independent_stop_check(self):
        from mmsearch.search import encode_candidate,naive_terms
        with tempfile.TemporaryDirectory() as tmp:
            c=pathlib.Path(tmp);prefix=c/'walk';pathlib.Path(str(prefix)+'.best.txt').write_text(''.join('%s %s %s\n'%x for x in naive_terms(2)))
            calls=iter([False,True]);seen={}
            self.assertFalse(w.drain(prefix,c,{},seen,lambda:next(calls,True),n=2,target=6,max_rank=10));self.assertFalse(seen);self.assertFalse((c/'verified').exists())
        candidate=encode_candidate([(1,1,1)],5);stop_flag=False
        def independent(raw):
            nonlocal stop_flag
            stop_flag=True;return {'record_eligible':True,'exact_entries_checked':15625}
        with tempfile.TemporaryDirectory() as tmp,mock.patch.object(w.base,'verify_candidate',return_value={'valid':True,'exact_entries_checked':15625}),mock.patch.object(w.base,'verify_bytes',side_effect=independent):
            self.assertFalse(w.freeze_winner(pathlib.Path(tmp),candidate,'fake',b'fake',lambda:stop_flag));self.assertFalse((pathlib.Path(tmp)/'WINNER.json').exists())

    def test_mocked_postcall_stop_is_unknown_without_export_or_next_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=pathlib.Path(tmp);(c/'campaign.json').write_text(json.dumps(dict(dimension=5,field=2,target_rank=92,deadline_utc='2099-11-04T21:31:16Z')))
            pool,_=self.pool(c/'pool');binary=c/'binary';binary.write_bytes(b'fake-not-run');args=self.preview_args(c,pool,binary);args.remove('--preview')
            held=c/'held.json';held.write_text('{}');args[args.index('--heldout-declaration')+1]=str(held)
            def child(*pos,**kw):
                (c/'guard_stopped.json').write_text('{"reason":"deadline"}')
                return dict(exit_code=0,child_cpu_seconds=.01,interrupted=False,timed_out=False)
            with mock.patch.object(w.base,'validate_input',side_effect=self.fake_validate),mock.patch.object(w.base,'run_child',side_effect=child) as runner,mock.patch.object(w,'drain',side_effect=AssertionError('late export promotion')),mock.patch.object(w.os,'sched_setaffinity'),mock.patch.object(w.resource,'setrlimit'),contextlib.redirect_stdout(io.StringIO()):w.main(args)
            self.assertEqual(runner.call_count,1);summary=json.loads((c/'new/summary.json').read_bytes())
            self.assertEqual(summary['status'],'STOPPED');self.assertEqual(summary['phases'][0]['status'],'STOPPED_POSTCALL_UNKNOWN')
            self.assertFalse((c/'new/verified').exists());self.assertFalse((c/'new/WINNER.json').exists())

if __name__=='__main__':unittest.main()
