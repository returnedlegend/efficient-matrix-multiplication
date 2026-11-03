from functools import reduce
from collections import deque
import importlib.util
import itertools
import os
from pathlib import Path
import random
import unittest

from mmsearch.compact_rank2_edges43 import (matrix_rank_at_most_two,
    rank_two_splits,solve_pair_image,solve_core)


def load_oracle():
    path=Path(os.environ.get('EDGE_ORACLE',str(Path(__file__).resolve().parents[1]/'tests/fixtures/compact_rank2_edges43_oracle.py')))
    spec=importlib.util.spec_from_file_location('independent_edge_oracle',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def outer(x,y,a,b):
    result=0
    for i,j in itertools.product(range(a),range(b)):result^=((x>>i&1)&(y>>j&1))<<(i*b+j)
    return result


def literal_span(values):
    result={0}
    for value in values:result|={x^value for x in tuple(result)}
    return result


class RankTwoEdgeControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.oracle=load_oracle()

    def witness(self,targets,a,b,result):
        if result['status']!='SAT':return
        self.assertLessEqual(len(result['support']),result['budget'])
        for p in result['support']:
            self.assertTrue(0<p['left']<1<<a and 0<p['right']<1<<b)
            self.assertEqual(outer(p['left'],p['right'],a,b),p['column'])
        for target,mask in zip(targets,result['target_coordinates']):
            value=0
            for i,p in enumerate(result['support']):
                if mask>>i&1:value^=p['column']
            self.assertEqual(value,target)

    def test_rank_classifier_and_all_three_GL2_splits(self):
        checks=0
        for a,b in [(2,2),(2,3),(3,2),(3,3)]:
            for value in range(1<<(a*b)):
                rank=self.oracle.matrix_rank(value,a,b);self.assertEqual(matrix_rank_at_most_two(value,a,b)[0],min(rank,3))
                if rank==2:
                    splits=rank_two_splits(value,a,b);self.assertEqual({(p['p'],p['q']) for p in splits},set(self.oracle.splits(value,a,b)));checks+=1
        self.assertGreater(checks,300)

    def test_all_2892_external_oracle_subspaces_and_raw_slices(self):
        checks=0;proper_inside=0
        for a,b in [(2,2),(2,3)]:
            for encoded in self.oracle.all_subspaces(a*b):
                space=list(self.oracle.points(encoded));basis=self.oracle.independent(space);d=len(basis)
                raw=[0]+basis+([basis[0],reduce(int.__xor__,basis,0)] if basis else [0])
                oracle=self.oracle.edge_decision(space,a,b);result=solve_pair_image(raw,a,b,d+1)
                self.assertEqual(result['status']=='SAT',oracle['hit'],(a,b,basis,result));self.assertTrue(result['complete']);self.witness(raw,a,b,result)
                exact_d=solve_pair_image(raw,a,b,d);self.assertEqual(exact_d['status']=='SAT',oracle['inside_rank']==d);self.witness(raw,a,b,exact_d)
                proper_inside+=bool(result['status']=='SAT' and 0<result['inside_rank']<d);checks+=1
        self.assertEqual(checks,2892);self.assertGreater(proper_inside,0)
        print('external_subspace_differentials',checks,'proper_B0_positive',proper_inside)

    def test_random_abstract_pair_spaces_against_literal_onecoset(self):
        rng=random.Random(432991);counts={}
        for _ in range(180):
            a=rng.randrange(1,5);b=rng.randrange(1,5);raw=[rng.randrange(1<<(a*b)) for _ in range(rng.randrange(1,min(6,a*b)+1))];space=literal_span(raw);d=len(space).bit_length()-1
            points=[outer(x,y,a,b) for x in range(1,1<<a) for y in range(1,1<<b)];inside=[x for x in points if x in space];buckets={}
            for value in points:
                q=min(value^t for t in space)
                if q:buckets.setdefault(q,[]).append(value)
            expected=space<=literal_span(inside)
            if not expected:
                expected=any(space<=literal_span(inside+[x^bucket[0] for x in bucket[1:]]) for bucket in buckets.values())
            result=solve_pair_image(raw+[0,raw[0]],a,b,d+1);self.assertEqual(result['status']=='SAT',expected,(a,b,raw,result));self.witness(raw+[0,raw[0]],a,b,result);counts[result['case']]=counts.get(result['case'],0)+1
        self.assertIn('no_single_rank2_edge_coset_spans',counts)

    def test_all_256_tiny_tensors_all_axes_exact_CP_and_expansion(self):
        points=[]
        for term in itertools.product(range(1,4),repeat=3):
            value=0
            for i,j,k in itertools.product(range(2),repeat=3):value^=((term[0]>>i&1)&(term[1]>>j&1)&(term[2]>>k&1))<<((i*2+j)*2+k)
            points.append(value)
        distance={0:0};queue=deque([0])
        while queue:
            old=queue.popleft()
            for point in points:
                value=old^point
                if value not in distance:distance[value]=distance[old]+1;queue.append(value)
        for packed in range(256):
            core=[packed>>i&1 for i in range(8)]
            for axis in range(3):
                other=[j for j in range(3) if j!=axis];slices=[0,0]
                for xyz in itertools.product(range(2),repeat=3):slices[xyz[axis]]^=(packed>>((xyz[0]*2+xyz[1])*2+xyz[2])&1)<<(xyz[other[0]]*2+xyz[other[1]])
                d=len(self.oracle.independent(slices))
                for budget in [d,d+1]:
                    result=solve_core(core,[2,2,2],budget,axis=axis);self.assertEqual(result['status']=='SAT',distance[packed]<=budget)
                    if result['status']=='SAT':
                        actual=0
                        for term in result['products']:
                            for i,j,k in itertools.product(range(2),repeat=3):actual^=((term[0]>>i&1)&(term[1]>>j&1)&(term[2]>>k&1))<<((i*2+j)*2+k)
                        self.assertEqual(actual,packed)

    def test_nonzero_B0_cross_cosets_and_rank_three_negative(self):
        result=solve_pair_image([0,256,10,256^10,256],3,3,3);self.assertEqual(result['status'],'SAT');self.assertEqual(result['inside_rank'],1);self.assertEqual(len(result['support']),3);self.witness([0,256,10,256^10,256],3,3,result)
        result=solve_pair_image([33,33792],4,4,3);self.assertEqual(result['status'],'LOCAL_UNSAT');self.assertEqual(max(v[2] for v in result['bucket_span_ranks']),1)
        self.assertEqual(solve_pair_image([273],3,3,2)['status'],'LOCAL_UNSAT')

    def test_large_dimension_known_pencil_plus_diagonal(self):
        for d in [10,12]:
            basis=[1|(1<<(d+1)),(1<<1)|(1<<d)|(1<<(d+1))]+[1<<(i*d+i) for i in range(2,d)]
            raw=[0]+basis+[basis[0],reduce(int.__xor__,basis)]
            result=solve_pair_image(raw,d,d,d+1);self.assertEqual(result['status'],'SAT');self.assertEqual(result['target_rank'],d);self.assertEqual(result['inside_rank'],d-2);self.assertEqual(len(result['support']),d+1);self.assertEqual(result['enumerated_vectors'],(1<<d)-1);self.witness(raw,d,d,result)
            self.assertEqual(solve_pair_image(raw,d,d,d)['status'],'LOCAL_UNSAT')

    def test_padded_known_space_reconstructs_all_raw_free_slices(self):
        def embed(value):
            out=0
            for i,j in itertools.product(range(2),repeat=2):out^=(value>>(i*2+j)&1)<<([0,19][i]*24+[1,23][j])
            return out
        u,v=embed(9),embed(14);slices=[0,u,v,u^v,u];core=[value>>i&1 for value in slices for i in range(20*24)]
        result=solve_core(core,[5,20,24],3,axis=0);self.assertEqual(result['status'],'SAT');self.assertEqual(result['enumerated_vectors'],3);self.witness(slices,20,24,result)
        rebuilt=[0]*len(core)
        for term in result['products']:
            for i,j,k in itertools.product(range(5),range(20),range(24)):rebuilt[(i*20+j)*24+k]^=(term[0]>>i&1)&(term[1]>>j&1)&(term[2]>>k&1)
        self.assertEqual(rebuilt,core)

    def test_scope_cancellation_and_limits(self):
        self.assertEqual(solve_pair_image([9,14],2,2,4)['status'],'UNKNOWN')
        self.assertEqual(solve_pair_image([9,14],2,2,3,max_vectors=2)['status'],'UNKNOWN')
        self.assertEqual(solve_pair_image([9,14],2,2,3,cancelled=lambda:True)['status'],'UNKNOWN')
        calls=0
        def cancel():
            nonlocal calls
            calls+=1;return calls>2
        self.assertEqual(solve_pair_image([9,14],2,2,3,cancelled=cancel)['status'],'UNKNOWN')
        with self.assertRaises(ValueError):rank_two_splits(1,2,2)


if __name__=='__main__':unittest.main()
