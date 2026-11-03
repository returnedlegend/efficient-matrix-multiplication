import copy
import contextlib
import gzip
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch
import itertools
import random
import tempfile
import unittest
from mmsearch.observed_budget642 import decode_budget6,scalar_decode,contractions
from mmsearch.observed_rank342 import rank
from mmsearch.recombine import digest
from mmsearch.observed_budget6_runtime42 import SourceRuntime as Budget6SourceRuntime
from mmsearch.observed_budget6_bounded42 import search_budget6_bounded
from mmsearch.observed_budget6_checkpoint42 import load_checkpoint,append_checkpoint,save_checkpoint
from mmsearch.observed_rank342 import prepare_space,decode_space_hit,lift_space
from mmsearch.search import naive_terms,encode_candidate
from mmsearch.free_factor_sat import build_system


def minimum(h,t,budget):
    for k in range(min(len(h),budget)+1):
        for indices in itertools.combinations(range(len(h)),k):
            chosen=[h[i] for i in indices]
            if rank(chosen+t)==rank(chosen):return k
    return 99


class Budget6Tests(unittest.TestCase):
    def test_scalar_all_small_targets_and_representative_pair_mitm(self):
        rng=random.Random(64201);cases=0
        for _ in range(100):
            h=[rng.randrange(64) for i in range(rng.randrange(1,9))]
            for target in range(8):
                best=minimum(h,[target],4)
                for b in (2,3,4):
                    r=scalar_decode(h,target,b,1);self.assertEqual(r['status']=='HIT',best<=b,(h,target,b,r,best));cases+=1
        self.assertEqual(cases,2400)
        r=scalar_decode([1,2,4,8],15,4,1);self.assertEqual((r['status'],r['weight'],r['case']),('HIT',4,'scalar_pair_mitm'))
        self.assertEqual(scalar_decode([0,1,1,2,4,8],15,3,1)['status'],'NO_WEIGHT_LE3')

    def test_fano_positive_controls_and_random_subset_oracle(self):
        controls=[([1,2,4,8,16,32],[7,25,42],6,'fano_triangle'),([1,2,4,8,16],[7,25],5,'fano_triangle'),
            ([1,2,4,8,16,32],[1,6,56],6,'fano_inside'),([1,2,4,8,16],[1,30],5,'fano_inside'),
            ([1,2,4,8,16,32],[3,12,48],6,'fano_pair'),([1,2,4,8,16],[3,28],5,'fano_pair')]
        for h,t,b,case in controls:
            self.assertEqual(minimum(h,t,b),b)
            r=decode_budget6(h,t,b,1);self.assertEqual((r['status'],r['weight'],r['case']),('HIT',b,case),(h,t,r))
        rng=random.Random(64202)
        for _ in range(250):
            m=rng.choice([2,3]);t=[7,25] if m==2 else [7,25,42];bound=5 if m==2 else 6
            h=[rng.randrange(128) for i in range(rng.randrange(1,9))];best=minimum(h,t,bound)
            r=decode_budget6(h,t,bound,1)
            self.assertEqual(r['status']=='HIT',best<=bound,(h,t,r,best))
            if best>bound:self.assertTrue(r['complete_for_requested_bound'])

    def test_nested_durable_branch_cursor_and_prefix_cap(self):
        h=[1,2,4,8,16,32,64];t=[1,14,112]
        self.assertEqual(minimum(h,t,6),99)
        q=dict(column_syndromes_hex=list(map(hex,h)),targets_hex=list(map(hex,t)),weight_bound=6,quotient_sha256='nested-control')
        with tempfile.TemporaryDirectory() as directory:
            cursor=None;nested=False
            for attempt in range(30):
                r=search_budget6_bounded(q,1,256,cursor,lambda record,state:append_checkpoint(directory,'nested-control',record,state),branch_budget=1)
                save_checkpoint(directory,'nested-control',r.get('cursor'));cursor=load_checkpoint(directory,'nested-control')
                if cursor.get('active_child') and cursor['active_child'].get('cursor'):
                    nested|=bool(cursor['active_child']['cursor'].get('completed_prefix'))
                    self.assertEqual(cursor['active_child'],r['cursor']['active_child'])
                if r['status']!='UNKNOWN':break
            self.assertEqual(r['status'],'NO_ONE_SUBSPACE_GAIN');self.assertTrue(nested);self.assertGreater(attempt,0)
        capped=decode_budget6(h,t,6,1,max_prefix=1)
        self.assertEqual(capped['status'],'UNKNOWN');self.assertIn('prefix cap',str(capped))

    def test_driver_counts_one_dispatch_for_both_storage_hold_paths(self):
        from scripts import campaign_observed_budget642 as driver
        with tempfile.TemporaryDirectory() as temporary:
            b=Path(temporary)/'prepared';b.mkdir();source=b/'sources/s/system.json';source.parent.mkdir(parents=True)
            system={'baseline_vectors':[1]};source.write_text(json.dumps(system));raw_sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
            item={'basis_values':[1,2,4],'space':[1,2,3,4,5,6,7],'k':7,'weight_bound':6}
            planfile=b/'cases.json.gz';planfile.write_bytes(gzip.compress(json.dumps([item]).encode()))
            chunk={'id':'tiny','source_id':'s','count':1,'plan':'cases.json.gz','plan_sha256':digest([item]),'compressed_sha256':raw_sha(planfile)}
            plan={'chunks':[chunk],'sources':{'s':{'system_sha256':raw_sha(source)}},'decoder':'control','scope':'test only'}
            (b/'plan.json').write_text(json.dumps(plan));code=b/'code/mmsearch/observed_budget642.py';code.parent.mkdir(parents=True);code.write_text('# control')
            bindings={str(f.relative_to(b)):raw_sha(f) for f in b.rglob('*') if f.is_file()};(b/'integrity.json').write_text(json.dumps(bindings))
            q={'k':7,'weight_bound':6,'target_rank':3,'quotient_sha256':'tiny'}
            class Runtime:
                def __init__(self,system):self.system=system
                def prepare(self,system,basis):return q
            class Guard:
                def __init__(self,path):pass
                def check(self):return None
            for inside in (False,True):
                argv=['driver','--prepared-dir',str(b),'--output-dir',str(Path(temporary)/('out'+str(inside))),
                    '--chunk-id','tiny','--guard-state',str(b/'unused'),'--seconds','5','--per-case-seconds','1','--memory-mb','256']
                response={'status':'UNKNOWN','cursor':{'completed_prefix':[]},'quotient_sha256':'tiny'}
                with patch.object(driver,'SourceRuntime',Runtime),patch.object(driver,'FreshGuard',Guard),patch.object(driver,'decode_vectors',return_value={}),\
                    patch.object(driver,'verify_candidate',return_value={'valid':True,'rank':93,'exact_entries_checked':15625}),\
                    patch.object(driver,'save_checkpoint',side_effect=driver.Hold('storage hold')),\
                    patch.object(driver,'search_bounded',side_effect=driver.Hold('storage hold') if inside else None,return_value=response),\
                    patch.object(driver.signal,'signal'),patch('sys.argv',argv),contextlib.redirect_stdout(io.StringIO()) as captured:
                    self.assertEqual(driver.main(),0)
                report=json.loads(captured.getvalue());self.assertEqual(report['status'],'UNKNOWN');self.assertEqual(report['target_queries_this_launch'],1)

    def test_full_small_MM_minimum6_and_bounded_lifecycle(self):
        terms=naive_terms(2);u,v,w=terms[0];source=terms[1:]+[(u^2,v,w),(2,v,w)]
        self.assertEqual(len({(a,b) for a,b,c in source}),9)
        system=build_system(source+[(u,v,0)],2,'uv',encode_candidate(source,2));runtime=Budget6SourceRuntime(system);q=runtime.prepare(system,[1,2,4])
        h=[int(x,16) for x in q['column_syndromes_hex']];t=[int(x,16) for x in q['targets_hex']]
        self.assertEqual((q['k'],q['target_rank'],q['weight_bound'],minimum(h,t,6)),(7,3,6,6))
        r=search_budget6_bounded(q,1,256);self.assertEqual((r['status'],r['weight']),('HIT',6));self.assertTrue(r['worker_reaped'])
        answer=runtime.decode_hit(system,q,r['entries'])
        self.assertEqual(answer['candidate']['metadata']['method'],'observed-rank3-exact-weight6-fano')
        self.assertEqual((answer['verification']['rank'],answer['verification']['exact_entries_checked']),(8,64))
        bad=copy.deepcopy(r['entries']);bad[0][1]^=1
        with self.assertRaises((AssertionError,ValueError)):lift_space(system,q,bad)
        stopped=search_budget6_bounded(q,1,256,cancelled=lambda:True)
        self.assertEqual(stopped['status'],'UNKNOWN');self.assertTrue(stopped['worker_reaped'])
        timed=search_budget6_bounded(q,1e-9,256)
        self.assertEqual(timed['status'],'UNKNOWN');self.assertTrue(timed['worker_reaped'])

    def test_physical_zero_triangle_and_cursor_timeout(self):
        branches=list(contractions([1,2,3],[4,8],lambda:None))
        self.assertNotIn(('triangle',[0,1,2]),branches)
        h=[1,2,4,8,16,32,64];t=[3,12,48]
        self.assertEqual(minimum(h,t,6),6)
        # A no-solution family gives multiple exact child negatives and can
        # resume from an identity-bound prefix rather than restarting it.
        h=[1,2,4,8,16,32,64,128];t=[3,12,240]
        self.assertEqual(minimum(h,t,6),99)
        r=decode_budget6(h,t,6,1,max_branches=1);rounds=0
        while r['status']=='UNKNOWN' and rounds<100:
            old=r['cursor'];r=decode_budget6(h,t,6,1,old,max_branches=1);rounds+=1
        self.assertEqual(r['status'],'NO_WEIGHT_LE6');self.assertGreater(rounds,0)
        bad=copy.deepcopy(r['cursor']);bad['input_sha256']='changed'
        with self.assertRaises(AssertionError):decode_budget6(h,t,6,1,bad)
        bad=copy.deepcopy(r['cursor']);bad['completed_prefix'].append(dict(branch=len(bad['completed_prefix']),kind='inside',contracted_indices=[0],child_bound=5,child_status='NO_WEIGHT_LE5',child_result_sha256='bad'))
        bad['next_branch']=len(bad['completed_prefix'])
        chain=digest([bad['input_sha256'],bad['branch_catalog_sha256']])
        for record in bad['completed_prefix']:chain=digest([chain,record])
        bad['prefix_chain_sha256']=chain
        with self.assertRaises(AssertionError):decode_budget6(h,t,6,1,bad)
        self.assertEqual(decode_budget6(h,t,6,1e-12)['status'],'UNKNOWN')
        self.assertEqual(decode_budget6(h,t,7,1)['status'],'UNKNOWN')


if __name__=='__main__':unittest.main()
