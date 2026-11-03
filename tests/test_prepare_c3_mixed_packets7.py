import unittest
from math import comb
from mmsearch.search import naive_terms
from scripts.prepare_c3_mixed_packets7 import packet_family,source_pair_witnesses,literal_terms

class PacketPreparationTests(unittest.TestCase):
    def test_exact_tiny_family_and_retained_actual_cores(self):
        source=list(naive_terms(3));catalog=packet_family(source,3)
        self.assertEqual(catalog['packet_count'],comb(8,2));self.assertEqual(len(catalog['cube_source_indices']),3)
        self.assertEqual([item['rank'] for item in catalog['pair_column_witnesses']],[27]*3)
        masks=set();retained=0
        for record in catalog['packets']:
            ids=record['source_indices'];self.assertEqual(len(ids),9);self.assertEqual(len(set(ids)),9)
            self.assertTrue(set(catalog['cube_source_indices'])<=set(ids));masks.add((record['term_mask_lo'],record['term_mask_hi']))
            data=record['branch_metadata'];self.assertEqual(data['outside_products'],18)
            if data['d']<=8:
                retained+=1;self.assertEqual(data['actual_core_mode_ranks'],[data['d']]*3);self.assertEqual(data['ambient_entries_checked'],729)
            else:self.assertEqual(data['branch'],'FLATTENING_EXCLUDED');self.assertEqual(data['factor_rank_witness']['rank'],9)
        self.assertEqual(len(masks),28);self.assertEqual(catalog['retained_actual_core_checks'],retained)

    def test_pair_independence_and_full_orbit_holds_fail_closed(self):
        with self.assertRaises(ValueError):source_pair_witnesses([(1,1,1),(2,1,1)],4)
        broken=list(naive_terms(3));broken.pop(1)
        with self.assertRaises(ValueError):packet_family(broken,3)

    def test_source_order_and_literal_type_are_explicit(self):
        candidate={'dimension':1,'field':2,'terms':[{'u':[True],'v':[1],'w':[1]}]}
        with self.assertRaises(ValueError):literal_terms(candidate)

if __name__=='__main__':unittest.main()
