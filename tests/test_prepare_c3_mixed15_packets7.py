import unittest
from mmsearch.search import naive_terms
from scripts.prepare_c3_mixed15_packets7 import prepare,branch_for_dimension

class QuadruplePacketTests(unittest.TestCase):
    def test_exact70_tiny_packets_and_core_controls(self):
        c=prepare(list(naive_terms(3)),3,pilot_cap=5)
        self.assertEqual(len(c['packets']),70)
        self.assertEqual([w['rank'] for w in c['pair_column_witnesses']],[27]*3)
        self.assertEqual(len(c['pilot_case_ids']),5)
        for p in c['packets']:
            self.assertEqual(len(p['source_indices']),15);self.assertEqual(len(set(p['source_indices'])),15)
            self.assertTrue(set(c['cube_source_indices'])<=set(p['source_indices']))
            b=p['branch_metadata'];self.assertEqual(b['outside_products'],12);self.assertEqual(b['target_local_products'],14)
            self.assertEqual(b['branch'],'RETAIN_DEFER_HIGHER_SURPLUS');self.assertEqual(b['feasibility_status'],'NOT_QUERIED_RETAINED')
            if p['id'] in c['pilot_case_ids']:self.assertTrue(b['actual_core_checked']);self.assertEqual(b['actual_core_mode_ranks'],b['mode_shape'])
        for d,count in c['dimension_counts'].items():self.assertGreaterEqual(c['core_checks_by_d'][d],min(3,count))
    def test_unsupported_surplus_never_forced_into_decoder(self):
        for d in range(1,13):self.assertEqual(branch_for_dimension(d),'RETAIN_DEFER_HIGHER_SURPLUS')
        self.assertEqual(branch_for_dimension(13),'CP(d+1)');self.assertEqual(branch_for_dimension(14),'CP(d)')
        self.assertEqual(branch_for_dimension(15),'FLATTENING_EXCLUDED')

if __name__=='__main__':unittest.main()
