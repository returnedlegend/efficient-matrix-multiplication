import unittest

from scripts.select_diverse93_seeds import gf2_matrix_rank,greedy_select


class DiverseSeedTests(unittest.TestCase):
    def test_gf2_matrix_rank_handles_dependence_and_full_rank(self):
        self.assertEqual(gf2_matrix_rank(0,5),0)
        self.assertEqual(gf2_matrix_rank(sum(1<<(i*5+i) for i in range(5)),5),5)
        self.assertEqual(gf2_matrix_rank((1<<25)-1,5),1)
        # Rows 001, 010, 011 have one exact GF2 dependence.
        self.assertEqual(gf2_matrix_rank(1|(2<<3)|(3<<6),3),2)
        with self.assertRaises(ValueError):
            gf2_matrix_rank(1<<25,5)

    def test_deterministic_greedy_maximum_minimum_structural_distance(self):
        def item(name,histogram,term):
            return dict(path=name,raw_sha256=name,canonical_sha256=name,histogram=histogram,terms=frozenset([term]))
        a=item('mandatory-a',(93,0,0),(1,1,1));b=item('mandatory-b',(0,93,0),(2,2,2))
        near=item('near',(90,3,0),(3,3,3));far=item('far',(0,0,93),(4,4,4))
        balanced=item('balanced',(46,47,0),(5,5,5))
        first,decisions=greedy_select([a,b],[near,balanced,far],4)
        second,_=greedy_select([a,b],[far,near,balanced],4)
        self.assertEqual([x['path'] for x in first],['mandatory-a','mandatory-b','far','balanced'])
        self.assertEqual([x['path'] for x in second],[x['path'] for x in first])
        self.assertEqual(decisions[0]['min_histogram_l1'],186)

    def test_jaccard_breaks_equal_histogram_distance_and_duplicates_are_excluded(self):
        def item(name,terms,canonical=None):
            return dict(path=name,raw_sha256=name,canonical_sha256=canonical or name,
                        histogram=(93,),terms=frozenset(terms))
        a=item('a',[(1,1,1),(2,2,2)])
        near=item('near',[(1,1,1),(3,3,3)])
        far=item('far',[(4,4,4),(5,5,5)])
        duplicate=item('duplicate',list(a['terms']),'a')
        selected,_=greedy_select([a],[near,duplicate,far],2)
        self.assertEqual([x['path'] for x in selected],['a','far'])


if __name__=='__main__':
    unittest.main()
