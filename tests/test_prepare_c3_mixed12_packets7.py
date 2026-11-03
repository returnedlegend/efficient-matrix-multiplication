import unittest
from mmsearch.search import naive_terms
from scripts.prepare_c3_mixed12_packets7 import prepare

class TriplePacketTests(unittest.TestCase):
    def test_all_tiny_triples_and_lazy_core_sampling(self):
        catalog=prepare(list(naive_terms(3)),3,pilot_cap=5)
        self.assertEqual(len(catalog['packets']),56)
        self.assertEqual([item['rank'] for item in catalog['pair_column_witnesses']],[27]*3)
        self.assertEqual(len(catalog['pilot_case_ids']),5)
        for record in catalog['packets']:
            self.assertEqual(len(record['source_indices']),12);self.assertEqual(len(set(record['source_indices'])),12)
            self.assertTrue(set(catalog['cube_source_indices'])<=set(record['source_indices']))
            data=record['branch_metadata'];self.assertEqual(data['outside_products'],15)
            if data['d']<=8:self.assertEqual(data['branch'],'RETAIN_DEFER_HIGHER_SURPLUS');self.assertEqual(data['feasibility_status'],'NOT_QUERIED_RETAINED')
            if record['id'] in catalog['pilot_case_ids']:self.assertTrue(data['actual_core_checked']);self.assertEqual(data['actual_core_mode_ranks'],data['mode_shape'])
        for d in catalog['dimension_counts']:
            self.assertGreaterEqual(catalog['core_checks_by_d'][d],min(3,int(catalog['dimension_counts'][d])))

if __name__=='__main__':unittest.main()
