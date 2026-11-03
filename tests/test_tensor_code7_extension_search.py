"""Tiny extension search-protocol controls; no production optimization."""
from datetime import datetime,timezone
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mmsearch import tensor_code7 as math
from scripts import tensor_code7 as legacy
from scripts import tensor_code7_extension_search as worker
from tests.test_tensor_code7_lifecycle import planted_exact_93

REPO=Path(__file__).resolve().parents[1]


class ExtensionSearchTests(unittest.TestCase):
    def protocol(self,trigger=None,resume=False):
        doc,(atoms,columns,seeds,cycles)=planted_exact_93()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out=root/'out';out.mkdir()
            prepared=root/'prepared.json';base=root/'base.json'
            prepared.write_text(json.dumps(dict(doc,schema=worker.PREPARED_SCHEMA,dimension=5,field=2)))
            config=dict(campaign_sha256='fixture',campaign_dir=str(root),guard_state=str(root/'guard'),deadline_utc='fixture')
            base.write_text(json.dumps(dict(lifecycle_config=config)))
            args=SimpleNamespace(prepared=prepared,prepared_sha256=worker.sha(prepared.read_bytes()),base_prepared=base,
                base_sha256='fixture',witnesses=root/'witnesses.json',witnesses_sha256='fixture',source_manifest=root/'manifest.json',
                source_manifest_sha256='fixture',approved_root=root,campaign_dir=root,guard_state=root/'guard',
                campaign_sha256='fixture',seed=71,temporary_excess=0,samples=0,restart_after=4,max_restarts=1,resume=None)
            args.witnesses.write_text('{}');args.source_manifest.write_text('{}')
            fullconfig=dict(config,prepared_sha256=args.prepared_sha256,base_prepared_sha256='fixture',witness_manifest_sha256='fixture',source_manifest_sha256='fixture')
            expired=[False];calls=[];hashes={'protocol':'tiny only'}
            def guard(*_barrier):
                if expired[0]:raise worker.Stop('synthetic_late')
            def check(atoms,state,n,guard=None):
                result=math.checked_candidate(atoms,state,2,guard=guard)
                if trigger=='after_verification':expired[0]=True
                return result
            def choose(state,*unused,**kwargs):
                calls.append(state);unused[1].random()
                if trigger=='after_move':expired[0]=True
                return seeds[0]^seeds[1],'known_tiny_cycle'
            if resume:
                args.resume=root/'resume.json'
                args.resume.write_text(json.dumps(dict(schema=worker.SCHEMA,prepared_sha256=args.prepared_sha256,
                    code_sha256=hashes,parameters=dict(seed=71,temporary_excess=0,samples=0,restart_after=4,max_restarts=1,winner_weight=92,certified_five_term_moves=True),
                    lifecycle_config=fullconfig,cursor=math.Walk(seeds[1],seeds[1]).to_json(),basis_order=list(range(len(columns))),
                    rng_state=random.Random(71).getstate(),publication_eligibility='eligible_within_budget')))
            with patch.object(worker,'load_root_pinned_extension',return_value=(atoms,columns,[seeds[0]],cycles,{'protocol_only':True})),\
                 patch.object(worker,'lifecycle_config',return_value=fullconfig),patch.object(worker,'checked_candidate',check),\
                 patch.object(legacy,'checked_candidate',check),patch.object(worker,'choose_move',choose):
                report=worker.search_main(args,out,guard,hashes)
            checkpoint=json.loads((out/'checkpoint.json').read_bytes())
            if trigger:
                self.assertEqual(checkpoint['cursor'],math.Walk(seeds[0],seeds[0]).to_json())
                self.assertEqual(checkpoint['rng_state'],json.loads(json.dumps(random.Random(71).getstate())))
                from scripts.campaign_operations_v3 import walk_files
                self.assertFalse(any('.raw-candidates' in path.parts for path in walk_files(out)))
            return report,calls,(out/'first-record-evidence').exists()

    def test_known_tiny_reduction_double_checks_and_stops(self):
        report,calls,published=self.protocol()
        self.assertTrue(report['winner']);self.assertEqual(report['best_weight'],7)
        self.assertEqual(len(calls),1);self.assertTrue(published)

    def test_late_proposal_rolls_back_and_remains_unknown(self):
        report,calls,published=self.protocol('after_move')
        self.assertEqual(report['status'],'UNKNOWN');self.assertFalse(report['winner']);self.assertFalse(published)

    def test_late_checker_keeps_hidden_raw_without_publication(self):
        report,calls,published=self.protocol('after_verification')
        self.assertEqual(report['status'],'UNKNOWN');self.assertFalse(report['winner']);self.assertFalse(published)

    def test_eligible_resume_does_not_search_again(self):
        report,calls,published=self.protocol(resume=True)
        self.assertTrue(report['winner']);self.assertEqual(calls,[]);self.assertTrue(published)

    def test_authenticated_small_cycles_are_direct_moves_even_if_dependent(self):
        columns=[1,2,3,4,4]
        basis,rank=math.fundamental_kernel(columns)
        # This five-term relation is the XOR of both fundamental cycles.
        doc=dict(odd_relation_certificates=[dict(cycle_hex=hex(31))])
        moves=worker.move_generators(columns,basis,doc)
        self.assertIn(31,moves)
        self.assertEqual(len(moves),len(basis)+1)
        self.assertTrue(all(math.xor_columns(columns,z)==0 for z in moves))
        with self.assertRaises(ValueError):worker.move_generators(columns,basis,dict(odd_relation_certificates=[dict(cycle_hex='0x1')]))

    def test_v1_schema_rejected_before_trusted_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'old.json';path.write_text(json.dumps(dict(schema='tensor_code7.v1',dimension=5,field=2)))
            args=SimpleNamespace(prepared=path,prepared_sha256=worker.sha(path.read_bytes()))
            with patch.object(worker,'load_root_pinned_extension') as loader,self.assertRaisesRegex(ValueError,'extension schema'):
                worker.search_main(args,root,lambda *_:None,{})
            loader.assert_not_called()

    def test_inner_poll_clocks_signals_and_fresh_stage_barriers(self):
        class Fake:
            started=0;seconds=120;hard=datetime(2099,1,1,tzinfo=timezone.utc)
            canonical=SimpleNamespace(signal_stop=False)
            def __init__(self):self.calls=[]
            def __call__(self,barrier):self.calls.append(barrier)
        direct=Fake();poll=worker.InnerPoll(direct)
        with patch.object(worker.time,'monotonic',return_value=1):poll()
        with patch.object(worker.time,'monotonic',return_value=1.05):poll()
        self.assertEqual(direct.calls,['loop'])
        with patch.object(worker.time,'monotonic',return_value=1.06):poll('premarker')
        self.assertEqual(direct.calls,['loop','premarker'])
        direct.canonical.signal_stop=True
        with self.assertRaises(worker.Stop):poll()
        direct.canonical.signal_stop=False
        with patch.object(worker.time,'monotonic',return_value=121),self.assertRaises(worker.Stop):poll()

    def test_disabled_query_does_not_read_inputs(self):
        completed=subprocess.run([sys.executable,'-B',str(REPO/'scripts/tensor_code7_extension_search.py'),
            '--prepared','/DO_NOT_READ'],capture_output=True,text=True,check=True)
        report=json.loads(completed.stdout)
        self.assertFalse(report['production_inputs_read']);self.assertFalse(report['search_called'])


if __name__=='__main__':unittest.main()
