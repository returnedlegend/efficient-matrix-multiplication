import itertools
import json
import math
from pathlib import Path
import random
import subprocess
import unittest

from mmsearch.compact_eight43 import (expand_core,factor_core,packed_tensor,permute_core,
    replace_and_verify,transfer_known_products)
from mmsearch.koszul import koszul_bounds
from mmsearch.sat_neighborhoods import factor_masks
from mmsearch.tensor import naive_candidate,strassen_candidate
from mmsearch.xor_sat import build_xor_cnf,validate_model
from scripts.prepare_compact_eight43 import propagate


class CompactEight43Tests(unittest.TestCase):
    def test_complete_rank_eight_control_and_corruption(self):
        source=naive_candidate(2)
        source['terms'].append({a:[0]*4 for a in ['u','v','w']})
        problem=build_xor_cnf(source,rank=8,active_terms=list(range(8)),drop_term=8,symmetry='none')
        problem['clauses'] += [[v] for v in problem['phases']]
        model,report=propagate(problem)
        self.assertTrue(report['valid']);self.assertEqual(report['rank'],8);self.assertEqual(report['exact_entries_checked'],64)
        model[0]*=-1
        with self.assertRaises(AssertionError):validate_model(problem,model)

    def test_rank_eight_diagonal_is_excluded(self):
        terms=[(1<<i,1<<i,1<<i) for i in range(8)]
        _,core,shape=factor_core(terms,list(range(8)))
        bound=koszul_bounds(core,shape,target=7)
        self.assertEqual(bound['flattening_ranks'],[8,8,8]);self.assertEqual(bound['tensor_rank_lower_bound'],8);self.assertTrue(bound['rejected'])

    def test_real_eight_to_seven_constructive_control(self):
        naive=naive_candidate(2);terms=factor_masks(naive);bases,core,shape=factor_core(terms,list(range(8)))
        known=factor_masks(strassen_candidate(2))
        mapping=transfer_known_products(core,shape,bases,known,core,shape,bases,width=4)
        self.assertIsNotNone(mapping)
        candidate,report=replace_and_verify(naive,list(range(8)),mapping['products'])
        self.assertEqual(report['rank'],7);self.assertTrue(report['valid']);self.assertEqual(report['exact_entries_checked'],64)

    def test_explicit_axis_and_basis_isomorphism_and_corruption(self):
        old_shape=[2,3,2];old_bases=[[1,2],[1,2,4],[1,2]];products=[(1,1,1),(2,2,2)]
        old_core=[0]*(2*3*2);old_core[0]=1;old_core[(1*3+1)*2+1]=1
        new_shape,new_core=permute_core(old_core,old_shape,[1,0,2]);new_bases=[[1,2,4],[8,16],[32,64]]
        result=transfer_known_products(old_core,old_shape,old_bases,products,new_core,new_shape,new_bases)
        self.assertIsNotNone(result);actual=0
        for term in result['products']:actual^=packed_tensor(term)
        self.assertEqual(actual,expand_core(new_core,new_shape,new_bases))
        with self.assertRaises(AssertionError):
            transfer_known_products(old_core,old_shape,old_bases,[(1,1,1)],new_core,new_shape,new_bases)

    @unittest.skipUnless(Path('/tmp/compact8_koszul43').exists(),'native preprocessor must be compiled locally')
    def test_native_core_and_all_p1_ranks_match_python(self):
        rng=random.Random(843);naive=factor_masks(naive_candidate(2));diagonal=[(1<<i,1<<i,1<<i) for i in range(8)]
        random_terms=[tuple(rng.randrange(1,32) for _ in range(3)) for _ in range(8)]
        structured=[(1,1,1),(1,2,2),(2,1,2),(2,2,1),(4,4,4),(4,8,8),(8,4,8),(8,8,4)]
        sources=[naive,diagonal,random_terms,structured]
        header='4\n'+''.join(' '.join(map(str,t))+'\n' for source in sources for t in source+[(0,0,0)]*85)
        request=header+'4\n'+''.join(f'{s} {s} 255 0\n' for s in range(4))
        result=subprocess.run(['/tmp/compact8_koszul43'],input=request,text=True,capture_output=True,check=True)
        for s,line in enumerate(result.stdout.splitlines()):
            fields=line.split();shape=list(map(int,fields[4:7]));flats=list(map(int,fields[7:10]));ranks=list(map(int,fields[10:13]));lower=int(fields[13]);packed=int(fields[14],16)
            bases,core,expected_shape=factor_core(sources[s],list(range(8)))
            self.assertEqual(shape,expected_shape);self.assertEqual(core,[(packed>>i)&1 for i in range(math.prod(shape))])
            bound=koszul_bounds(core,shape,target=7)
            self.assertEqual(flats,bound['flattening_ranks']);self.assertEqual(ranks,[b['matrix_rank'] for b in bound['bounds']])
            self.assertEqual(lower,bound['tensor_rank_lower_bound'])
        bad=subprocess.run(['/tmp/compact8_koszul43'],input=header+'1\n0 0 127 0\n',text=True,capture_output=True)
        self.assertNotEqual(bad.returncode,0)


if __name__=='__main__':unittest.main()
