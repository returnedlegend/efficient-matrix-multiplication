import contextlib,io,json,pathlib,tempfile,unittest
from unittest import mock
from scripts import campaign_native_dwell42_v2 as w

class LongHarnessTests(unittest.TestCase):
    def test_bounded_distinct_phase_schedule(self):
        self.assertEqual(w.budgets(900,300),[300,300,300])
        self.assertEqual(w.budgets(900,600),[600,300])
        self.assertEqual(w.budgets(601,600),[600,1])
        for args in [(901,300),(900,601),(0,300),(900,0),(900,float('nan')),(900,1)]:
            with self.assertRaises(ValueError):w.budgets(*args)

    def test_forwarded_native_bounds_and_no_policy_change(self):
        for dwell in [0,64,32768]:
            args=w.command('bin','input','out',seconds=600,seed=991,dwell=dwell)
            reference=w.base.command('bin','input','out',seconds=30,seed=991,dwell=dwell)
            reference[reference.index('--seconds')+1]='600'
            self.assertEqual(args,reference)
        for seconds in [0,601,float('inf')]:
            with self.assertRaises(ValueError):w.command('b','i','o',seconds=seconds,seed=1,dwell=0)

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
                '--expected-runtime-sha256',w.base.sha(w.base.raw_json(code)),'--seed','2026110384200','--reduction-dwell','0','--preview']

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

if __name__=='__main__':unittest.main()
