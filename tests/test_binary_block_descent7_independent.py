"""Independent tiny exhaustive block minima and lifecycle bounds; no N5."""
import itertools
import math
import random
import unittest
from unittest.mock import patch
from mmsearch import binary_block_descent7 as subject


def literal_tensor(factors,shape):
    return [sum(((a>>i)&1)*((b>>j)&1)*((c>>k)&1) for a,b,c in factors)%2
            for i,j,k in itertools.product(*(range(d) for d in shape))]


def loss(core,shape,factors):
    return sum(x!=y for x,y in zip(core,literal_tensor(factors,shape)))


class BinaryBlockIndependentTests(unittest.TestCase):
    def test_all256_binary_cores_all_axes_literal_whole_block_oracle(self):
        shape=[2,2,2];contexts=[[(1,1,1),(2,2,2)],[(3,1,3),(1,3,2)],[(0,3,1),(3,3,1)]]
        checks=0
        for packed in range(256):
            core=[(packed>>i)&1 for i in range(8)]
            for factors,axis in itertools.product(contexts,range(3)):
                choices=[]
                for masks in itertools.product(range(4),repeat=2):
                    candidate=[list(t) for t in factors]
                    for t,mask in zip(candidate,masks):t[axis]=mask
                    choices.append(loss(core,shape,candidate))
                answer=subject.exact_block_update(core,shape,factors,axis,timeout_seconds=2)
                self.assertEqual(answer['status'],'BLOCK_MINIMUM')
                self.assertEqual(answer['loss_after'],min(choices))
                self.assertEqual(answer['loss_before'],loss(core,shape,factors))
                self.assertEqual(loss(core,shape,answer['factors']),min(choices))
                self.assertLessEqual(answer['loss_after'],answer['loss_before'])
                self.assertEqual(answer['enumerated_codewords'],4)
                checks+=1
        self.assertEqual(checks,2304);print('independent_whole_block_oracle_cases',checks)

    def test_noncubic_axes_and_rank_zero_against_literal_oracle(self):
        rng=random.Random(711035)
        for shape,slots in itertools.product(([1,2,3],[3,1,2],[2,3,1],[0,2,1]),range(3)):
            factors=[tuple(rng.randrange(1<<d) for d in shape) for _ in range(slots)]
            core=[rng.randrange(2) for _ in range(math.prod(shape))]
            for axis in range(3):
                optimum=len(core)
                for masks in itertools.product(range(1<<shape[axis]),repeat=slots):
                    candidate=[list(t) for t in factors]
                    for t,mask in zip(candidate,masks):t[axis]=mask
                    optimum=min(optimum,loss(core,shape,candidate))
                result=subject.exact_block_update(core,shape,factors,axis)
                self.assertEqual(result['loss_after'],optimum)
                self.assertEqual(subject.residual_loss(core,shape,result['factors']),optimum)

    def test_optimizer_exact_integer_loss_and_monotone_best_with_perturbations(self):
        core=[int(i in (0,13,26)) for i in range(27)];shape=[3,3,3]
        for seed in range(12):
            result=subject.optimize(core,shape,1,seed=seed,max_sweeps=6,
                                    max_restarts=2,max_perturbations=2)
            self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete'])
            self.assertEqual(result['best_loss'],loss(core,shape,result['best_factors']))
            bests=[event['best_loss'] for event in result['history']]
            self.assertTrue(all(a>=b for a,b in zip(bests,bests[1:])))
            for event in result['history']:
                if event['action']=='block':self.assertLessEqual(event['loss_after'],event['loss_before'])
            self.assertTrue(all(type(v) is int and 0<=v<8 for term in result['best_factors'] for v in term))
            self.assertFalse(result['publication_eligible'])

    def test_raw_exact_late_scalar_check_retains_nested_unaccepted_witness(self):
        cancelled=[False];scalar=subject.scalar_loss
        def late(*args):
            value=scalar(*args);cancelled[0]=True;return value
        with patch.object(subject,'scalar_loss',late):
            result=subject.optimize([1],[1,1,1],1,initial_factors=[(1,1,1)],
                                    cancelled=lambda:cancelled[0])
        self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete'])
        self.assertTrue(result['after_cutoff']);self.assertFalse(result['publication_eligible'])
        self.assertEqual(result['raw_compact']['products'],[[1,1,1]])
        self.assertFalse(result['raw_compact']['ambient_verified'])

    def test_fixed_utc_cap_memory_history_and_literal_limits(self):
        with patch.object(subject.time,'time',return_value=subject.HARD_DEADLINE+1):
            result=subject.optimize([1],[1,1,1],1,deadline_utc='2099-01-01T00:00:00Z')
        self.assertEqual((result['status'],result['case']),('UNKNOWN','deadline'))
        with patch.object(subject,'MAX_HISTORY',3):
            result=subject.optimize([1,0,0,0,0,0,0,1],[2,2,2],1,
                                    max_sweeps=8,max_restarts=3,max_perturbations=3)
        self.assertEqual(len(result['history']),3);self.assertGreater(result['history_dropped'],0)
        for kwargs in ({'rank':15},{'rank':True},{'rank':1,'max_codewords':16385},
                       {'rank':1,'timeout_seconds':float('nan')},{'rank':1,'timeout_seconds':121},
                       {'rank':1,'axis_order':[0,1,True]}):
            with self.assertRaises(ValueError):subject.optimize([1],[1,1,1],**kwargs)
        for shape in ([16,1,1],[True,1,1]):
            with self.assertRaises(ValueError):subject.optimize([1],shape,1)
        capped=subject.exact_block_update([1],[1,1,1],[(0,1,1)]*14,0,max_codewords=8192)
        self.assertEqual((capped['status'],capped['case']),('UNKNOWN','codeword_cap'))


if __name__=='__main__':unittest.main()
