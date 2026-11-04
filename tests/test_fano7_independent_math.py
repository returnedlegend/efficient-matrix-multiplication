"""Exact Fano-only synthetic positive: no SAT/backend/source query."""
import itertools
import unittest
from mmsearch.compact_sat import BinaryBasis
from mmsearch.compact_coset43 import mode_slices
from mmsearch.compact_rank2_edges43 import matrix_rank_at_most_two
from mmsearch.rank2_span_bound7 import classify_pair_image
from tests.fano7_independent_fixture import planted_fano_b7


class IndependentFanoMathTests(unittest.TestCase):
    def test_fano_only_shape11_rank14_with_no_repeated_pair_branch(self):
        f=planted_fano_b7();core=f['core'];shape=f['shape'];slices=f['slices']
        self.assertEqual([len(BinaryBasis(mode_slices(core,shape,a)[0]).vectors) for a in range(3)],[11]*3)
        rebuilt=[]
        for i,j,k in itertools.product(range(11),repeat=3):
            rebuilt.append(sum(((a>>i)&1)*((b>>j)&1)*((c>>k)&1) for a,b,c in f['products'])%2)
        self.assertEqual(rebuilt,core);self.assertEqual(len(f['products']),14)
        space=BinaryBasis(slices);inside=[];ranktwo_outside=0;counts={1:0,2:0,3:0}
        b0=BinaryBasis([point['matrix'] for point in f['backbone_rankone_points']])
        self.assertEqual(len(b0.vectors),7)
        for mask in range(1,2048):
            value=space.expand(mask);rank,_=matrix_rank_at_most_two(value,11,11);counts[rank]+=1
            if rank==1:inside.append(value)
            if rank==2 and b0.expand(b0.coordinates(value))!=value:ranktwo_outside+=1
        self.assertEqual(len(BinaryBasis(inside).vectors),7)
        self.assertEqual(counts,{1:29,2:98,3:1920});self.assertEqual(ranktwo_outside,0)
        negative=classify_pair_image(slices,11,11,13,max_vectors=2047)
        self.assertEqual((negative['status'],negative['required_rank2_span'],negative['rank2_span_rank']),('EXCLUDED',10,7))
        passing=classify_pair_image(slices,11,11,14,max_vectors=2047)
        self.assertEqual(passing['status'],'NOT_EXCLUDED')
        # Circuit coordinates are the identity in S/B0 by construction.
        for offset,indices in enumerate(f['circuits']):
            value=0
            for i in indices:value^=f['fano_rankone_points'][i]['matrix']
            self.assertEqual(value,slices[7+offset])


if __name__=='__main__':unittest.main()
