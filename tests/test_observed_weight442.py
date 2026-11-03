import copy
import itertools
from pathlib import Path
import signal
import tempfile
import time
import unittest
from unittest.mock import patch

from mmsearch.free_factor_sat import build_system
from mmsearch.observed_plane42 import decode_plane_hit,lift_plane,plane_plan,prepare_plane
from mmsearch.observed_weight442 import decode_weight4,search_weight4_bounded,validate_prior_family,validate_prior_gap
from mmsearch.recombine import canonical_terms,digest,encode
from mmsearch.tensor import strassen_candidate
from scripts.campaign_observed_plane42 import resume_terminal
from scripts.campaign_observed_weight442 import SOURCE_FILES


def prior_fixture():
    old=[1,1,2,2,3,4,0];rows=[1<<g for g in range(len(old))]
    system=dict(coefficients=rows,right_sides=old,baseline_vectors=old,metadata=dict(width=3),pairs=[(1,1)]*len(old))
    q=prepare_plane(system,[1,2,3])
    prior=dict(status='NO_WEIGHT_LE3',complete_for_requested_gain=False,full_case=False,
        searched_bound=3,k=5,weight_bound=4,target_rank=2,worker_reaped=True,worker_exitcode=0,
        plane=q['plane'],quotient_sha256=q['quotient_sha256'])
    plan=dict(plane=q['plane'],k=5,weight_bound=4,full_case_at_weight3=False)
    binding=dict(prior_result_canonical_sha256=digest(prior),plane=q['plane'],
        quotient_sha256=q['quotient_sha256'],source_system_sha256=digest(system))
    return system,q,prior,plan,binding


class Weight442Tests(unittest.TestCase):
    def test_source_closure_and_prior_family_completion_hashes(self):
        root=Path(__file__).resolve().parents[1]
        for relative in SOURCE_FILES:
            parts=list(Path(relative).with_suffix('').parts)
            for node in ast.walk(ast.parse((root/relative).read_text())):
                if not isinstance(node,ast.ImportFrom):continue
                module=(parts[:-node.level] if node.level else [])+(node.module.split('.') if node.module else [])
                if module and module[0] in ['mmsearch','scripts']:
                    self.assertIn('/'.join(module)+'.py',SOURCE_FILES)
        system,_,_,_,_=prior_fixture();plan=plane_plan(system)
        config=dict(source_system_sha256=digest(system),plan_sha256=digest(plan))
        manifest=[dict(index=i,status='NO_WEIGHT_LE3') for i in range(len(plan))]
        counts={'NO_WEIGHT_LE3':len(plan)}
        cursor=dict(config_sha256=digest(config),plan_sha256=digest(plan),next_index=len(plan),terminal_counts=counts)
        report=dict(cursor,status='ENUMERATED_PLAN_COMPLETE')
        self.assertTrue(validate_prior_family(system,config,plan,cursor,report,manifest))
        bad=dict(cursor,config_sha256='changed')
        with self.assertRaises(AssertionError):validate_prior_family(system,config,plan,bad,report,manifest)
    def test_both_pair_types_and_zero_duplicate_columns(self):
        for columns,pair_type in [([1,4,8,14],'in_target_plus_outside'),
                ([4,5,8,10],'same_target_coset'),([4,5,8,14],'same_target_coset'),
                ([0,4,4,5,8,10],'same_target_coset')]:
            result=decode_weight4(columns,[1,2],seconds=1)
            self.assertEqual(result['status'],'HIT');self.assertEqual(result['weight'],4)
            self.assertEqual(result['pair_type'],pair_type)
            self.assertEqual(result['precondition_weight3']['status'],'NO_WEIGHT_LE3')
            for bit,target in enumerate([1,2]):
                actual=0
                for i,value in result['entries']:
                    if value>>bit&1:actual^=columns[i]
                self.assertEqual(actual,target)
        negative=decode_weight4([1,2,4,8,16],[3,28],seconds=1)
        self.assertEqual(negative['status'],'NO_WEIGHT_LE4')
        self.assertTrue(negative['complete_for_weight4'])

    def test_tiny_bruteforce_all_four_power_assignments(self):
        for n in range(5):
            for columns in itertools.combinations_with_replacement(range(8),n):
                best={}
                for y in itertools.product(range(4),repeat=n):
                    a=b=0
                    for h,v in zip(columns,y):
                        if v&1:a^=h
                        if v&2:b^=h
                    best[a,b]=min(best.get((a,b),99),sum(bool(v) for v in y))
                for a in range(1,8):
                    for b in range(a+1,8):
                        result=decode_weight4(columns,[a,b],seconds=1)
                        self.assertEqual(result['status']=='HIT',best.get((a,b),99)<=4,(columns,a,b,result))

    def test_prior_hash_scope_and_witness_corruption_rejected(self):
        system,q,prior,plan,binding=prior_fixture()
        self.assertTrue(validate_prior_gap(system,q,prior,plan,binding))
        for field,value in [('status','NO_ONE_SUBSPACE_GAIN'),('k',4),('target_rank',1),
                ('plane',[1,4,5]),('worker_reaped',False),('quotient_sha256','wrong')]:
            changed=copy.deepcopy(prior);changed[field]=value
            with self.assertRaises(AssertionError):validate_prior_gap(system,q,changed,plan,binding)
            rehashed=dict(binding,prior_result_canonical_sha256=digest(changed))
            with self.assertRaises(AssertionError):validate_prior_gap(system,q,changed,plan,rehashed)
        broken=copy.deepcopy(q);broken['target_neutral_lifts_hex'][0]='0x1'
        broken['quotient_sha256']=digest({k:v for k,v in broken.items() if k!='quotient_sha256'})
        with self.assertRaises(AssertionError):validate_prior_gap(system,broken,prior,plan,binding)

    def test_true_weight4_neutral_lift_and_full_tensor_hit_path(self):
        columns=[1,17,4,24,14,16];old=[2,3,2,2,2,4]
        rows=[sum(1<<g for g,c in enumerate(columns) if c>>r&1) for r in range(5)];rhs=[]
        for row in rows:
            value=0
            for g,w in enumerate(old):
                if row>>g&1:value^=w
            rhs.append(value)
        system=dict(coefficients=rows,right_sides=rhs,baseline_vectors=old,metadata=dict(width=3),pairs=[(1,1)]*len(old))
        q=prepare_plane(system,[1,2,3]);result=decode_weight4([int(h,16) for h in q['column_syndromes_hex']],
            [int(t,16) for t in q['targets_hex']],seconds=1)
        self.assertEqual(result['weight'],4)
        lift=lift_plane(system,q,result['entries'])
        self.assertEqual(lift['actual_gain'],1);self.assertEqual(lift['original_kernel_coordinates_verified'],2)
        # A separate real matrix-tensor control exercises the exact final
        # decoder/verifier path; the extension also accepts a <=3 precondition hit.
        terms=canonical_terms(strassen_candidate(2));actual=None
        for t,(u,delta,w) in enumerate(terms):
            for a in range(1,16):
                b=u^a
                if not b:continue
                split=list(terms[:t])+list(terms[t+1:])+[(a,delta,w),(b,delta,w)]
                if len({(z,x) for x,y,z in split})==8:
                    actual=build_system(sorted(set(split)|set(terms)),2,'wu',encode(split,2));break
            if actual is not None:break
        other=next(v for v in actual['baseline_vectors'] if v and v!=delta)
        q=prepare_plane(actual,[delta,other,delta^other]);result=decode_weight4(
            [int(h,16) for h in q['column_syndromes_hex']],[int(t,16) for t in q['targets_hex']],seconds=1)
        verified=decode_plane_hit(actual,q,result['entries'])
        self.assertLessEqual(verified['verification']['rank'],7)
        self.assertEqual(verified['verification']['exact_entries_checked'],64)

    def test_timeout_memory_and_signal_cleanup(self):
        system,q,_,_,_=prior_fixture()
        result=search_weight4_bounded(q,seconds=1,memory_mb=256)
        self.assertEqual(result['status'],'NO_ONE_SUBSPACE_GAIN')
        self.assertTrue(result['complete_for_requested_gain'])
        self.assertEqual(result['worker_stats']['address_space_limit_bytes'],256*1024**2)
        self.assertEqual(decode_weight4([1,2,4,8,16],[3,28],seconds=1e-12)['status'],'UNKNOWN')
        def stall(*args):
            self.assertEqual(signal.getsignal(signal.SIGTERM),signal.SIG_DFL);time.sleep(10)
        previous=signal.signal(signal.SIGTERM,lambda *_:None)
        try:
            with patch('mmsearch.observed_weight442._worker',stall):result=search_weight4_bounded(q,seconds=.02,memory_mb=256)
            self.assertEqual(result['status'],'UNKNOWN');self.assertTrue(result['worker_reaped'])
            self.assertLess(result['elapsed_seconds'],.5)
        finally:signal.signal(signal.SIGTERM,previous)

    def test_winner_error_resume_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.assertEqual(resume_terminal(root,dict(last_status='ERROR')),'ERROR')
            self.assertIsNone(resume_terminal(root,dict(last_status='UNKNOWN')))
            (root/'WINNER.json').write_text('{}')
            with patch('scripts.campaign_observed_plane42.verify_candidate',return_value=dict(
                    valid=True,rank=92,exact_entries_checked=15625)):
                self.assertEqual(resume_terminal(root,dict(last_status='SAT')),'SAT')


if __name__=='__main__':unittest.main()
import ast
