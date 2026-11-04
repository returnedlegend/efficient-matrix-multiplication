"""Tiny algebra, strict authority/schema and bounded native controls; no N5 query."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from mmsearch import native_xor3_source7 as source
from mmsearch.search import naive_terms
from mmsearch.tensor import strassen_candidate
from mmsearch.tensor_code7 import atom_from_term,atom_column
from scripts import campaign_native_xor3_7 as runner

ROOT=Path(__file__).resolve().parents[1]
BINARY=Path(os.environ.get('XOR3_7_TEST_BINARY',ROOT/'artifacts/rl_campaign42_20261103T033116Z/plus-burst42-pilot-ready-v1/native/plus-burst-worker'))
def profile():return dict(id='tiny',source_id=1,seed=7,cyclic=False,plus_burst=1,reduction_dwell=128,plus_every=2000)
def tensor(terms):
    value=0
    for term in terms:value^=atom_column(term,2)
    return value
def document():return dict(schema=source.SCHEMA,dimension=5,field=2,authority={},sources=[dict(index=0,parent_indices=[0,1,2],reduced_rank=98)],scope='test')

class SourceControls(unittest.TestCase):
    def test_strict_new_schema_and_no_original_gate_change(self):
        self.assertEqual(source.schema_check(document())['schema'],source.SCHEMA)
        for changes in [dict(dimension=5.0),dict(field=True),dict(schema='initial16'),dict(sources=[]),dict(sources=[dict(index=True,parent_indices=[0,1,2],reduced_rank=98)])]:
            with self.assertRaises(ValueError):source.schema_check({**document(),**changes})
        for parents in [[0,1],[0,0,1],[0,1,36],[0,1,2.0],[False,1,2]]:
            value=document();value['sources'][0]['parent_indices']=parents
            with self.assertRaises(ValueError):source.schema_check(value)
        for changes in [dict(dimension=5.0),dict(field=True),dict(terms=[]),dict(unreviewed=True)]:
            with self.assertRaises(ValueError):source.candidate_schema({**dict(dimension=5,field=2,terms=[{}]*98),**changes})

    def test_three_valid_tiny_parents_full_tensor_and_replay_tamper(self):
        first=naive_terms(2);second=[atom_from_term(t,2)for t in strassen_candidate(2)['terms']]
        third=list(first);i,j=next((i,j)for i in range(len(third))for j in range(i+1,len(third))if third[i][0]==third[j][0])
        u,v,w=third[i];_,x,y=third[j];third[i]=(u,v^x,w);third[j]=(u,x,w^y)
        parents=[first,second,third];self.assertEqual(len({tensor(p)for p in parents}),1)
        initial,reduced,moves=source.derive(parents);self.assertEqual(tensor(initial),tensor(first));self.assertEqual(tensor(reduced),tensor(first))
        self.assertEqual(source.encoded(source.parent_candidate(first,2)),source.encoded(source.parent_candidate(reversed(first),2)))
        self.assertEqual(source.derive(parents,json.loads(source.encoded(moves)))[1],reduced)
        with self.assertRaises(ValueError):source.derive(parents,[{'unreviewed':'move'}])
        with self.assertRaises(ValueError):source.derive(parents[:2])
        with self.assertRaisesRegex(RuntimeError,'stop'):source.derive(parents,poll=lambda:(_ for _ in()).throw(RuntimeError('stop')))

    def test_root_authority_pin_and_symlink_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp);(bundle/'a').write_bytes(b'abc');record=dict(file='a',sha256=source.sha(b'abc'))
            self.assertEqual(source.pinned_file(bundle,record),b'abc')
            with self.assertRaises(ValueError):source.pinned_file(bundle,record,'0'*64)
            (bundle/'link').symlink_to(bundle/'a')
            with self.assertRaises(ValueError):source.pinned_file(bundle,dict(file='link',sha256=record['sha256']))
            (bundle/'sources.json').write_bytes(source.encoded(document()))
            with self.assertRaises(ValueError):source.load_source(bundle,'0'*64,0,lambda _:True)

    def test_new_production_command_and_literal135_telemetry(self):
        p=profile();argv=runner.command('worker','input','walk',p)
        self.assertEqual(argv[argv.index('--seconds')+1],'180');self.assertEqual(argv[argv.index('--max-rank')+1],'135');self.assertNotIn('--cyclic',argv)
        for seconds,cyclic in [(120,False),(181,False),(180,True)]:
            with self.assertRaises(ValueError):runner.command('w','i','o',{**p,'cyclic':cyclic},seconds=seconds)
        stats=dict(dimension=5,seed=p['seed'],target_rank=92,max_rank=135,max_visited_rank=135,cyclic=False,
            reduction_dwell=128,plus_burst=1,plus_every=2000,restart_every=50000000,archive_every=1000,
            archive_size=16,exact=True,tensor_invariant_checked=True,steps=2,
            rank_residency_steps={'98':2},rank_after_move_steps={'98':2},rank_excess_residency_steps={'0':2})
        runner.validate_stats(stats,p,5,92)
        for change in [dict(max_rank=105),dict(max_rank=135.0),dict(max_visited_rank=136)]:
            with self.assertRaises(ValueError):runner.validate_stats({**stats,**change},p,5,92)

    def test_actual_tiny_early_and_late_publication_unchanged(self):
        for late in [False,True]:
            with tempfile.TemporaryDirectory()as tmp,mock.patch.object(runner.p,'command',runner.command),mock.patch.object(runner.p,'validate_stats',runner.validate_stats):
                result=runner.p.execute(BINARY,naive_terms(2),Path(tmp),lambda stage:not(late and stage=='post_target_strict_independent'),profile(),seconds=2,n=2,target=7,steps=200000)
                self.assertEqual(result['execution']['exit_code'],0);self.assertEqual(result['eligible_target_emitted'],not late)
                self.assertEqual((Path(tmp)/'records').exists(),not late);self.assertFalse((Path(tmp)/'WINNER.json').exists())

    def test_exact_output_reservation_keeps_final4kib(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);budget=runner.Budget(root,root/'bundle',root/'out',['out'])
            with mock.patch.object(runner.p.SpaceBudget,'size',return_value=0):
                with self.assertRaises(runner.p.OutputHold):budget.check(force=True,pending=30*runner.MIB-4095)

if __name__=='__main__':unittest.main()
