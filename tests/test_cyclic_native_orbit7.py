import unittest
from mmsearch.search import naive_terms
from mmsearch.cyclic_native_orbit7 import build_metadata
from mmsearch import cyclic_tensor_code7 as c
class NewCyclicOrbitMetadataControls(unittest.TestCase):
    def test_n5_default_rejects(self):
        with self.assertRaises(ValueError):build_metadata([],[],[],[],5)
        with self.assertRaises(ValueError):c.TinyOrbitCode.build([(1,1,1)],5)
    def test_tiny_seed_states_projection_and_new_independent_F_direction(self):
        seed=list(naive_terms(3));old=c.orbit_representatives(seed,3)
        forms=[2,4,8];cubes=[]
        for mask in range(1,8):
            value=0
            for i,v in enumerate(forms):
                if mask>>i&1:value^=v
            cubes.append((value,value,value))
        alternate=seed+cubes+list(c.orbit((2,4,8),3))+list(c.orbit((2,8,4),3))
        d,r,p=build_metadata([dict(id='naive',atoms=seed),dict(id='polar3',atoms=alternate)],seed,old,[1,16,256],3)
        self.assertEqual(r['seed_product_cost'],27);self.assertEqual(r['dictionary_independent_entries_checked'],len(d['representatives'])*729);self.assertEqual(r['F_rank'],3)
        self.assertEqual(r['F_rank_added'],1);self.assertEqual(r['new_nonzero_F_orbits'],2);self.assertTrue(r['kernel_parity']['can_change_cost_parity'])
        self.assertTrue(r['all_fulltensor_kernel_relations_respected_by_F']);self.assertEqual([x['product_cost'] for x in r['registered_source_states']],[27,40])
        self.assertGreater(sum(x['quotient_factor_rank']==3 for x in p),0)
    def test_non_target_complete_schema_rejected(self):
        seed=list(naive_terms(2))
        with self.assertRaises(ValueError):build_metadata([dict(id='wrong',atoms=[(1,1,1)])],seed,c.orbit_representatives(seed,2),[1,8],2)
if __name__=='__main__':unittest.main()
