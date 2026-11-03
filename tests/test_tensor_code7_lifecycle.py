"""Independent exact N2 controls for production search lifecycle.

The source has 93 distinct atoms: schoolbook8 plus disjoint zero-sum circuits.
Only production metadata and source loading are mocked to enter the runner;
all states, kernel moves, candidate reconstruction and tensor checks are real N2.
No production N5 input or search query is used.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mmsearch import tensor_code7 as math
from mmsearch.tensor import naive_candidate, strassen_candidate
from scripts import tensor_code7 as worker


def planted_exact_93():
    source=naive_candidate(2)
    used={(math.atom_from_term(t,2)[0],math.atom_from_term(t,2)[1]) for t in source['terms']}
    pairs=[(u,v) for u in range(1,16) for v in range(1,16) if (u,v) not in used]
    for i,(u,v) in enumerate(pairs[:28]):
        for w in ([1,2,4,7] if i==0 else [1,2,3]):
            source['terms'].append(math.term_from_atom((u,v,w),2))
    assert len(source['terms'])==93
    document=math.prepare([source,strassen_candidate(2)])
    return document,math.validate_prepared(document)


class TensorCodeLifecycleTests(unittest.TestCase):
    def protocol(self,trigger=None,resume=False,mutate_cursor=None,
                 publication_eligibility='eligible_within_budget'):
        document,(atoms,columns,seeds,cycles)=planted_exact_93()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prepared=root/'prepared.json';out=root/'out';out.mkdir()
            pins={'fixture':'N2 protocol only'}
            doc=dict(document,dimension=5,seed_weights=[93,93],code_sha256=pins,
                     sources=[{'provenance':{'heldout':False,'evaluation':False}}])
            prepared.write_text(json.dumps(doc))
            args=SimpleNamespace(prepared=prepared,prepared_sha256=worker.sha(prepared.read_bytes()),
                manifest=None,manifest_sha256=None,approved_root=root,seed=7,
                temporary_excess=0,samples=0,restart_after=4,max_restarts=1,resume=None)
            expired=[False];choose_calls=[]
            def guard(*_barrier):
                if expired[0]:raise worker.Stop('synthetic_cutoff')
            def choose(state,*unused,**kwargs):
                choose_calls.append(state)
                unused[1].random()  # A late proposal must also roll back its RNG draw.
                move=seeds[0]^seeds[1]
                self.assertEqual(math.xor_columns(columns,move),0)
                if trigger=='after_move':expired[0]=True
                return move,'planted_exact_cycle'
            def check(atoms,state,n,guard=None):
                answer=math.checked_candidate(atoms,state,2,guard=guard)
                if trigger=='after_verification':expired[0]=True
                return answer
            if resume:
                args.resume=root/'resume.json'
                cursor=math.Walk(seeds[1],seeds[1]).to_json()
                if mutate_cursor:mutate_cursor(cursor)
                checkpoint=dict(schema=worker.SCHEMA,prepared_sha256=worker.sha(prepared.read_bytes()),
                    code_sha256=pins,parameters=dict(seed=7,temporary_excess=0,samples=0,
                        restart_after=4,max_restarts=1,winner_weight=92),cursor=cursor,
                    basis_order=list(range(len(columns))),rng_state=random.Random(7).getstate(),
                    publication_eligibility=publication_eligibility)
                args.resume.write_text(json.dumps(checkpoint))
            with patch.object(worker,'validate_prepared',return_value=(atoms,columns,[seeds[0]],cycles)),\
                 patch.object(worker,'verify_source_binding',return_value=None,create=True),\
                 patch.object(worker,'lifecycle_config',return_value=None,create=True),\
                 patch.object(worker,'checked_candidate',check),patch.object(worker,'choose_move',choose):
                report=worker.search_main(args,out,guard,pins)
            if trigger=='after_move':
                checkpoint=json.loads((out/'checkpoint.json').read_text())
                self.assertEqual(checkpoint['cursor'],math.Walk(seeds[0],seeds[0]).to_json())
                self.assertEqual(checkpoint['rng_state'],json.loads(json.dumps(random.Random(7).getstate())))
            if trigger=='after_verification':
                checkpoint=json.loads((out/'checkpoint.json').read_text())
                if int(checkpoint['cursor']['best_hex'],16).bit_count()<=92:
                    self.assertEqual(checkpoint['publication_eligibility'],'late_raw_only')
                else:
                    self.assertEqual(checkpoint['cursor'],math.Walk(seeds[0],seeds[0]).to_json())
                    self.assertEqual(checkpoint['rng_state'],json.loads(json.dumps(random.Random(7).getstate())))
            return report,choose_calls,(out/'first-record-evidence').exists(),[
                p.read_text() for p in out.rglob('*after-cutoff*') if p.is_file()]

    def test_late_move_remains_unknown_and_retains_raw_witness(self):
        report,calls,published,late=self.protocol('after_move')
        self.assertEqual(len(calls),1);self.assertFalse(report['winner'])
        self.assertEqual(report['status'],'UNKNOWN');self.assertFalse(published)
        self.assertTrue(late)

    def test_late_full_verification_remains_unknown_and_retains_raw_witness(self):
        report,calls,published,late=self.protocol('after_verification')
        self.assertEqual(len(calls),1);self.assertFalse(report['winner'])
        self.assertEqual(report['status'],'UNKNOWN');self.assertFalse(published)
        self.assertTrue(late)

    def test_resumed_eligible_best_is_terminal_before_any_move(self):
        report,calls,published,late=self.protocol(resume=True)
        self.assertEqual(calls,[]);self.assertTrue(report['winner']);self.assertTrue(published)
        self.assertFalse(late)

    def test_resumed_late_only_best_never_promotes_or_searches(self):
        report,calls,published,late=self.protocol(resume=True,publication_eligibility='late_raw_only')
        self.assertEqual(calls,[]);self.assertFalse(report['winner']);self.assertFalse(published)
        self.assertEqual(report['status'],'UNKNOWN');self.assertFalse(report['complete'])

    def test_malformed_resume_cursor_fails_before_moves(self):
        for key,value in [('restart',-1),('step',True),('moves',-1),('no_improvement',-1),
                          ('state_hex','-0x1'),('best_hex','-0x1')]:
            with self.subTest(key=key),self.assertRaises((ValueError,TypeError)):
                self.protocol(resume=True,mutate_cursor=lambda cursor:cursor.update({key:value}))

    def test_checker_guard_between_independent_full_checks(self):
        document,(atoms,columns,seeds,cycles)=planted_exact_93();expired=[False]
        actual=math.verify_candidate
        def first(*args,**kwargs):
            answer=actual(*args,**kwargs);expired[0]=True;return answer
        def guard(*_barrier):
            if expired[0]:raise worker.Stop('synthetic_after_first_checker')
        with patch.object(math,'verify_candidate',first),patch.object(math,'second_check') as second:
            with self.assertRaises(worker.Stop):math.checked_candidate(atoms,seeds[1],2,guard=guard)
            second.assert_not_called()

    def test_checker_guard_after_second_full_check(self):
        document,(atoms,columns,seeds,cycles)=planted_exact_93();expired=[False]
        actual=math.second_check
        def second(*args,**kwargs):
            answer=actual(*args,**kwargs);expired[0]=True;return answer
        def guard(*_barrier):
            if expired[0]:raise worker.Stop('synthetic_after_second_checker')
        with patch.object(math,'second_check',second):
            with self.assertRaises(worker.Stop):math.checked_candidate(atoms,seeds[1],2,guard=guard)

    def test_operations_guard_cannot_ingest_expired_raw_92_shape(self):
        from scripts.campaign_operations_v3 import walk_files,canonical_candidate
        # Schema-valid synthetic92-term shape, not an exact multiplication claim.
        candidate=naive_candidate(5);candidate["terms"]=candidate["terms"][:92]
        atoms=[math.atom_from_term(term,5) for term in candidate["terms"]]
        self.assertEqual(len(canonical_candidate(candidate)["terms"]),92)
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            def expired(*_barrier):raise worker.Stop("synthetic_expired_before_verification")
            with self.assertRaises(worker.Stop):
                worker.save_candidate(out,"first-record-evidence",atoms,(1<<92)-1,5,{},guard=expired)
            self.assertFalse((out/"first-record-evidence").exists())
            raw_paths=list(out.glob(".raw-candidates/*/raw-candidate.json"))
            self.assertEqual(len(raw_paths),1)
            self.assertNotIn(raw_paths[0],list(walk_files(out)))
            wrapper=json.loads(raw_paths[0].read_bytes())
            with self.assertRaises((ValueError,KeyError,TypeError)):canonical_candidate(wrapper)
            self.assertEqual(wrapper["raw"]["candidate"],{key:candidate[key] for key in ("field","dimension","terms")})
            self.assertEqual(wrapper["status"],"UNKNOWN");self.assertFalse(wrapper["complete"])
            self.assertTrue(wrapper["after_cutoff"])

    def test_pending_verified_candidate_stays_hidden_before_publication(self):
        from scripts.campaign_operations_v3 import walk_files,canonical_candidate
        candidate=naive_candidate(5);candidate["terms"]=candidate["terms"][:92]
        atoms=[math.atom_from_term(term,5) for term in candidate["terms"]]
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            def expired(barrier="loop"):
                if barrier=="prepublication_views":raise worker.Stop("synthetic_expired_before_publication")
            # Checker stubbing isolates IO lifecycle; it does not assert tensor validity.
            with patch.object(worker,"checked_candidate",return_value=(candidate,{"protocol_only":True})):
                with self.assertRaises(worker.Stop):
                    worker.save_candidate(out,"first-record-evidence",atoms,(1<<92)-1,5,{},guard=expired)
            pending=list(out.glob(".raw-candidates/*/candidate.json"))
            self.assertEqual(len(pending),1)
            self.assertEqual(len(canonical_candidate(json.loads(pending[0].read_bytes()))["terms"]),92)
            self.assertNotIn(pending[0],list(walk_files(out)))
            self.assertFalse((out/"first-record-evidence").exists())

    def test_caller_cannot_extend_marathon_UTC_deadline(self):
        with patch.object(worker.signal,'signal'):
            guard=worker.Guard('2099-01-01T00:00:00Z',120)
        ceiling=datetime(2026,11,3,19,24,17,tzinfo=timezone.utc).timestamp()
        self.assertLessEqual(guard.hard.timestamp(),ceiling)

    def test_multicycle_cursor_rng_split_replay_preserves_full_equations(self):
        columns=[1,2,3,4,5,6,7];cycles,rank=math.fundamental_kernel(columns)
        self.assertEqual(len(cycles),4)
        rng=random.Random(731);walk=math.Walk(1,1);other=None;other_rng=None
        for step in range(30):
            move,kind=math.choose_move(walk.state,cycles,rng,ceiling=4,samples=24)
            if other is not None:
                self.assertEqual((move,kind),math.choose_move(other.state,cycles,other_rng,ceiling=4,samples=24))
            if move is not None:
                self.assertEqual(math.xor_columns(columns,move),0);walk.state^=move;walk.moves+=1
                self.assertLessEqual(walk.state.bit_count(),4)
                if walk.state.bit_count()<walk.best.bit_count():walk.best=walk.state
            walk.step+=1
            self.assertEqual(math.xor_columns(columns,walk.state),1)
            if other is not None:
                if move is not None:other.state^=move;other.moves+=1
                if other.state.bit_count()<other.best.bit_count():other.best=other.state
                other.step+=1;self.assertEqual(walk,other)
            if step==7:
                saved=json.loads(json.dumps({'cursor':walk.to_json(),'rng':rng.getstate()}))
                other=math.Walk.from_json(saved['cursor']);other_rng=math.rng_restore(saved['rng'])


if __name__=='__main__':unittest.main()
