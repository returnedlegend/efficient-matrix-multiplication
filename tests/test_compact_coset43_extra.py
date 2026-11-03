import unittest
from mmsearch.compact_coset43 import solve_core


class ExtraCosetControls(unittest.TestCase):
    def test_distinct_cosets_must_not_be_combined(self):
        # Two disjoint rank-two diagonal matrices: mode0 rank2, CP rank4
        # from mode1's ordinary flattening. Each separate coset only supplies
        # one of the two missing diagonal directions.
        core=[0]*32
        for a,b,c in [(0,0,0),(0,1,1),(1,2,2),(1,3,3)]:core[(a*4+b)*4+c]=1
        result=solve_core(core,[2,4,4],3,axis=0)
        self.assertEqual(result['status'],'LOCAL_UNSAT');self.assertEqual(result['case'],'no_single_coset_spans')
        self.assertEqual(result['inside_rank'],0)
        self.assertEqual(max(row[2] for row in result['bucket_span_ranks']),1)

    def test_mid_enumeration_cancel_is_unknown(self):
        calls=0
        def cancel():
            nonlocal calls
            calls+=1
            return calls>4
        result=solve_core([1,0,0,0,0,0,0,1],[2,2,2],3,cancelled=cancel)
        self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete'])


if __name__=='__main__':unittest.main()
