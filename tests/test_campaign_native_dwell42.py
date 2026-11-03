"""No n5 native queries: forwarding, proof publication and owned-child controls."""
import contextlib
import io
import json
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest import mock

from mmsearch.search import decode_candidate,encode_candidate,naive_terms
from mmsearch.tensor import strassen_candidate
from scripts import campaign_native_dwell42 as pilot

ROOT=Path(__file__).resolve().parents[1]


class HarnessTests(unittest.TestCase):
    def source(self,root):
        path=ROOT/'tests/fixtures/native_campaign42_rank93.json'
        target=root/'input.json';target.write_bytes(path.read_bytes())
        held=root/'heldout.json';held.write_text(json.dumps({'heldout_source_term_hashes':[str(i)*64 for i in range(1,5)]}))
        return target,held

    def test_native_command_forwards_exact_matched_arm_parameters(self):
        for dwell in (0,64,32768):
            command=pilot.command('worker','input','walk',seconds=30,seed=42110301,dwell=dwell)
            for key,value in {'--target':'92','--n':'5','--max-rank':'105','--seconds':'30','--seed':'42110301',
                              '--reduction-dwell':str(dwell),'--plus-every':'20000','--restart-every':'50000000'}.items():
                self.assertEqual(command[command.index(key)+1],value)
        with self.assertRaises(ValueError):pilot.command('x','y','z',seconds=31,seed=0,dwell=64)

    def test_source_hash_full_tensor_and_heldout_exclusion_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,held=self.source(root)
            terms,report,raw=pilot.validate_input(source,pilot.sha(source.read_bytes()),held,pilot.sha(held.read_bytes()))
            self.assertEqual(len(terms),93);self.assertEqual(report['canonical_verification']['exact_entries_checked'],15625)
            self.assertTrue(report['heldout_excluded'])
            with self.assertRaisesRegex(ValueError,'raw hash'):pilot.validate_input(source,'wrong',held,pilot.sha(held.read_bytes()))
            held.write_text(json.dumps({'heldout_source_term_hashes':[pilot.source_identity(terms),'1'*64,'2'*64,'3'*64]}))
            with self.assertRaisesRegex(ValueError,'heldout source'):pilot.validate_input(source,pilot.sha(raw),held,pilot.sha(held.read_bytes()))

    def test_preview_is_zero_query_and_zero_output_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,held=self.source(root);binary=root/'fake-not-executed';binary.write_bytes(b'preview only')
            (root/'campaign.json').write_text(json.dumps({'dimension':5,'field':2,'target_rank':92,'deadline_utc':'2099-01-01T00:00:00Z'}))
            args=['--campaign',str(root),'--input',str(source),'--binary',str(binary),'--heldout-declaration',str(held),
                  '--output-dir',str(root/'NEW'),'--expected-input-sha256',pilot.sha(source.read_bytes()),
                  '--expected-binary-sha256',pilot.sha(binary.read_bytes()),'--expected-heldout-sha256',pilot.sha(held.read_bytes()),
                  '--expected-runtime-sha256',pilot.sha(pilot.raw_json(pilot.runtime_hashes())),
                  '--seed','42110301','--reduction-dwell','32768','--preview']
            before={str(p):pilot.sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
            with mock.patch.object(pilot.subprocess,'Popen') as process,contextlib.redirect_stdout(io.StringIO()) as output:pilot.main(args)
            process.assert_not_called();self.assertFalse((root/'NEW').exists())
            self.assertTrue(json.loads(output.getvalue())['zero_mutations'])
            self.assertEqual(before,{str(p):pilot.sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()})

    def test_positive_n2_winner_is_fully_verified_and_marker_published_last(self):
        candidate=encode_candidate(decode_candidate(strassen_candidate(2),2),2)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);calls=[];original=pilot.freeze
            def recording(path,raw,*args,**kwargs):calls.append(Path(path).name);return original(path,raw,*args,**kwargs)
            with mock.patch.object(pilot,'freeze',side_effect=recording):pilot.freeze_winner(root,candidate,'control',b'knownStrassen7',n=2,target=7)
            self.assertEqual(calls[-1],'WINNER.json')
            report=json.loads((root/'WINNER.verification.json').read_text());self.assertTrue(report['valid']);self.assertEqual(report['exact_entries_checked'],64)
            checks=json.loads((root/'WINNER.checksums.json').read_text())
            self.assertEqual(checks['WINNER.json'],pilot.sha((root/'WINNER.json').read_bytes()))
            self.assertFalse((root/'WINNER.json').stat().st_mode&0o222)

    def test_planted_false_n5_rank92_cannot_publish_stop_marker(self):
        candidate=encode_candidate([(1,1,1)],5)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaisesRegex(ValueError,'full tensor'):pilot.freeze_winner(root,candidate,'fake',b'fake')
            self.assertFalse((root/'WINNER.json').exists())

    def test_all_exports_are_checked_and_distinct_certificates_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);prefix=root/'walk';seen={}
            first=decode_candidate(strassen_candidate(2),2);second=naive_terms(2)
            for name,terms in [('best',first),('current',second)]:Path(str(prefix)+'.'+name+'.txt').write_text(''.join(f'{a} {b} {c}\n' for a,b,c in terms))
            self.assertFalse(pilot.drain(prefix,root,{},seen,n=2,target=6,max_rank=10));self.assertEqual(len(seen),2)
            self.assertEqual({item['rank'] for item in seen.values()},{7,8})
            Path(str(prefix)+'.current.txt').write_text('1 1 1\n')
            with self.assertRaisesRegex(ValueError,'full tensor'):pilot.drain(prefix,root,{},seen,n=2,target=6,max_rank=10)
            self.assertFalse((root/'WINNER.json').exists())

    def test_wait4_records_owned_child_cpu_without_group_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (Path(tmp)/'log').open('w') as log,mock.patch.object(pilot.os,'killpg') as group:
                result=pilot.run_child([sys.executable,'-c','print(sum(i*i for i in range(100000)))'],log,lambda:False,lambda:False,wall_seconds=1,interval=.005)
                group.assert_not_called()
            self.assertEqual(result['exit_code'],0);self.assertGreater(result['child_cpu_seconds'],0)
            self.assertAlmostEqual(result['child_cpu_seconds'],result['child_user_seconds']+result['child_system_seconds'])

    def test_owned_ignoring_child_is_reaped_after_bounded_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'log'
            with path.open('w') as log,mock.patch.object(pilot.os,'killpg') as group:
                result=pilot.run_child([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("READY",flush=True);time.sleep(60)'],
                    log,lambda:'READY' in path.read_text(),lambda:False,wall_seconds=5,interval=.005)
                group.assert_not_called()
            self.assertEqual(result['exit_code'],-signal.SIGKILL);self.assertTrue(result['interrupted']);self.assertLess(result['elapsed_seconds'],4)

    def test_instrumentation_counts_and_maximum_must_match_complete_histograms(self):
        stats={'dimension':5,'target_rank':92,'max_rank':105,'seed':1,'reduction_dwell':64,'plus_every':20000,
               'restart_every':50000000,'exact':True,'tensor_invariant_checked':True,'cyclic':False,'steps':4,
               'rank_residency_steps':{'93':4},'rank_after_move_steps':{'93':4},'rank_excess_residency_steps':{'0':4},
               'best_rank':93,'current_rank':93,'max_visited_rank':93,'max_rank_excess':0,
               'accepted_by_kind':{'flip':4,'plus':0,'reduction':0},'accepted_moves':4,'rejected_moves':0,
               'flip_attempts':4,'plus_attempts':0,'reduction_attempts':0,
               'rank_changes_by_kind':{k:{'up':0,'equal':4 if k=='flip' else 0,'down':0,'delta_sum':0} for k in ['flip','plus','reduction']}}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'stats.json';path.write_text(json.dumps(stats));pilot.validate_stats(path,seed=1,dwell=64)
            stats['rank_excess_residency_steps']['0']=3;path.write_text(json.dumps(stats))
            with self.assertRaisesRegex(ValueError,'histogram'):pilot.validate_stats(path,seed=1,dwell=64)
            stats['rank_excess_residency_steps']['0']=4;stats['max_visited_rank']=94;path.write_text(json.dumps(stats))
            with self.assertRaisesRegex(ValueError,'complete histograms'):pilot.validate_stats(path,seed=1,dwell=64)


if __name__=='__main__':unittest.main()
